"""Capability-constrained workspace adapter for one real E2 integration.

This is application-level confinement, not an operating-system sandbox.  It
does not execute commands, access the network, delete files, overwrite files,
or create directories.
"""

from __future__ import annotations

import hashlib
from pathlib import Path, PureWindowsPath
from typing import Mapping

from .evidence import ActionRequest, HMACObservationSigner, ObservationEnvelope
from .models import JSONValue, ValidationError


CREATE_TEXT_FILE = "workspace.create_text_file"
INSPECT_FILE = "workspace.inspect_file"
ALLOWED_OPERATIONS = frozenset({CREATE_TEXT_FILE, INSPECT_FILE})


class WorkspacePolicyError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class CapabilityWorkspaceExecutor:
    """Execute two declarative file capabilities inside one existing root."""

    def __init__(
        self,
        *,
        root: str | Path,
        signer: HMACObservationSigner,
        max_write_bytes: int = 64 * 1024,
        max_inspect_bytes: int = 4 * 1024 * 1024,
    ) -> None:
        root_path = Path(root)
        if not root_path.exists() or not root_path.is_dir():
            raise ValidationError("workspace root must be an existing directory")
        self.root = root_path.resolve(strict=True)
        self.signer = signer
        if max_write_bytes <= 0:
            raise ValidationError("max_write_bytes must be positive")
        if max_inspect_bytes <= 0:
            raise ValidationError("max_inspect_bytes must be positive")
        if max_inspect_bytes < max_write_bytes:
            raise ValidationError(
                "max_inspect_bytes cannot be smaller than max_write_bytes"
            )
        self.max_write_bytes = max_write_bytes
        self.max_inspect_bytes = max_inspect_bytes

    def execute(self, request: ActionRequest) -> ObservationEnvelope:
        return self.signer.attest(request, self.perform(request))

    def perform(self, request: ActionRequest) -> dict[str, JSONValue]:
        """Perform one request and return observed metrics without signing."""

        try:
            if request.action_name == CREATE_TEXT_FILE:
                metrics = self._create_text_file(request.parameters)
            elif request.action_name == INSPECT_FILE:
                metrics = self._inspect_file(request.parameters)
            else:
                raise WorkspacePolicyError("operation_not_allowed")
        except WorkspacePolicyError as exc:
            metrics = self._failure_metrics(request.action_name, exc.code)
        except OSError:
            metrics = self._failure_metrics(request.action_name, "io_error")
        return metrics

    def _create_text_file(
        self,
        parameters: Mapping[str, JSONValue],
    ) -> dict[str, JSONValue]:
        if set(parameters) != {"path", "content"}:
            raise WorkspacePolicyError("invalid_parameters")
        raw_path = parameters["path"]
        content = parameters["content"]
        if not isinstance(content, str):
            raise WorkspacePolicyError("content_must_be_text")
        encoded = content.encode("utf-8")
        if len(encoded) > self.max_write_bytes:
            raise WorkspacePolicyError("content_too_large")

        target, relative = self._resolve_target(raw_path)
        if target.exists() or target.is_symlink():
            raise WorkspacePolicyError("overwrite_forbidden")

        with target.open("x", encoding="utf-8", newline="") as stream:
            stream.write(content)

        observed_size, observed_hash = self._bounded_file_hash(target)
        return {
            "operation": CREATE_TEXT_FILE,
            "operation_succeeded": True,
            "created": True,
            "file_exists": target.is_file(),
            "relative_path": relative,
            "size_bytes": observed_size,
            "sha256": observed_hash,
            "policy_version": "workspace-capabilities-v1",
        }

    def _inspect_file(
        self,
        parameters: Mapping[str, JSONValue],
    ) -> dict[str, JSONValue]:
        if set(parameters) != {"path"}:
            raise WorkspacePolicyError("invalid_parameters")
        target, relative = self._resolve_target(parameters["path"])
        if not target.exists():
            return {
                "operation": INSPECT_FILE,
                "operation_succeeded": True,
                "file_exists": False,
                "relative_path": relative,
                "size_bytes": 0,
                "sha256": None,
                "policy_version": "workspace-capabilities-v1",
            }
        if not target.is_file() or target.is_symlink():
            raise WorkspacePolicyError("regular_file_required")
        observed_size, observed_hash = self._bounded_file_hash(target)
        return {
            "operation": INSPECT_FILE,
            "operation_succeeded": True,
            "file_exists": True,
            "relative_path": relative,
            "size_bytes": observed_size,
            "sha256": observed_hash,
            "policy_version": "workspace-capabilities-v1",
        }

    def _resolve_target(self, raw_path: JSONValue) -> tuple[Path, str]:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise WorkspacePolicyError("relative_path_required")
        if "\x00" in raw_path:
            raise WorkspacePolicyError("invalid_path")
        relative_path = Path(raw_path)
        if (
            relative_path.is_absolute()
            or relative_path.drive
            or relative_path.anchor
        ):
            raise WorkspacePolicyError("absolute_path_forbidden")

        current = self.root
        parts = relative_path.parts
        if not parts:
            raise WorkspacePolicyError("relative_path_required")
        for part in parts:
            if part == "..":
                raise WorkspacePolicyError("path_outside_root")
            if part in {"", "."}:
                continue
            if (
                ":" in part
                or part.rstrip(" .") != part
                or PureWindowsPath(part).is_reserved()
            ):
                raise WorkspacePolicyError("invalid_path")
        for part in parts[:-1]:
            if part in {"", "."}:
                continue
            current = current / part
            if current.is_symlink():
                raise WorkspacePolicyError("symlink_forbidden")
            if not current.exists() or not current.is_dir():
                raise WorkspacePolicyError("parent_directory_missing")

        unresolved = self.root / relative_path
        if unresolved.is_symlink():
            raise WorkspacePolicyError("symlink_forbidden")
        resolved = unresolved.resolve(strict=False)
        if resolved == self.root or not resolved.is_relative_to(self.root):
            raise WorkspacePolicyError("path_outside_root")
        relative = resolved.relative_to(self.root).as_posix()
        return resolved, relative

    def _bounded_file_hash(self, target: Path) -> tuple[int, str]:
        size = target.stat().st_size
        if size > self.max_inspect_bytes:
            raise WorkspacePolicyError("file_too_large")
        digest = hashlib.sha256()
        observed_size = 0
        with target.open("rb") as stream:
            while block := stream.read(64 * 1024):
                observed_size += len(block)
                if observed_size > self.max_inspect_bytes:
                    raise WorkspacePolicyError("file_too_large")
                digest.update(block)
        return observed_size, digest.hexdigest()

    @staticmethod
    def _failure_metrics(
        operation: str,
        error_code: str,
    ) -> dict[str, JSONValue]:
        return {
            "operation": operation,
            "operation_succeeded": False,
            "error_code": error_code,
            "policy_version": "workspace-capabilities-v1",
        }
