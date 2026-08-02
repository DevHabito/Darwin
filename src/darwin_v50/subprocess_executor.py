"""Launch the fixed Darwin workspace worker in a separate process."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import sys

from .capabilities import CapabilityGrant
from .evidence import ActionRequest, ObservationEnvelope
from .ipc import OBSERVATION_SECRET_ENV
from .isolation import IsolationAssessment, same_user_subprocess_assessment
from .models import ValidationError, canonical_json, require_text


MAX_WORKER_OUTPUT_BYTES = 512 * 1024
SAFE_PARENT_ENVIRONMENT = frozenset(
    {
        "SYSTEMROOT",
        "WINDIR",
        "SYSTEMDRIVE",
        "TEMP",
        "TMP",
    }
)


class SubprocessExecutionError(RuntimeError):
    def __init__(self, code: str, *, returncode: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.returncode = returncode


class SubprocessWorkspaceExecutor:
    """Execute only ``darwin_v50.worker`` with ``shell=False``.

    The child has another PID but the same Windows account and permissions.
    This is fault separation, not a security boundary against hostile code.
    """

    def __init__(
        self,
        *,
        database: str | Path,
        workspace_root: str | Path,
        adapter_source: str,
        observation_secret: bytes,
        python_executable: str | Path | None = None,
        timeout_seconds: float = 10.0,
        require_appcontainer: bool = False,
    ) -> None:
        self.database = Path(database).resolve(strict=True)
        self.workspace_root = Path(workspace_root).resolve(strict=True)
        if not self.workspace_root.is_dir():
            raise ValidationError("workspace_root must be a directory")
        self.adapter_source = require_text(adapter_source, "adapter_source")
        if (
            not isinstance(observation_secret, bytes)
            or len(observation_secret) < 32
        ):
            raise ValidationError(
                "worker observation secret must contain at least 32 bytes"
            )
        self._observation_secret = observation_secret
        executable = Path(python_executable or sys.executable)
        self.python_executable = executable.resolve(strict=True)
        if timeout_seconds <= 0:
            raise ValidationError("timeout_seconds must be positive")
        self.timeout_seconds = timeout_seconds
        if not isinstance(require_appcontainer, bool):
            raise ValidationError("require_appcontainer must be boolean")
        self.require_appcontainer = require_appcontainer
        self.package_root = Path(__file__).resolve().parents[1]

    @property
    def isolation(self) -> IsolationAssessment:
        return same_user_subprocess_assessment()

    def execute(
        self,
        request: ActionRequest,
        grant: CapabilityGrant,
    ) -> ObservationEnvelope:
        payload = canonical_json(
            {
                "request": request.to_dict(),
                "grant": grant.to_dict(),
            }
        )
        environment = {
            name: value
            for name, value in os.environ.items()
            if name.upper() in SAFE_PARENT_ENVIRONMENT
        }
        environment["PYTHONNOUSERSITE"] = "1"
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONUTF8"] = "1"
        environment[OBSERVATION_SECRET_ENV] = base64.b64encode(
            self._observation_secret
        ).decode("ascii")
        command = [
            str(self.python_executable),
            "-B",
            "-s",
            "-m",
            "darwin_v50.worker",
            "--database",
            str(self.database),
            "--workspace-root",
            str(self.workspace_root),
            "--adapter-source",
            self.adapter_source,
        ]
        if self.require_appcontainer:
            command.append("--require-appcontainer")
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            completed = subprocess.run(
                command,
                input=payload,
                text=True,
                capture_output=True,
                cwd=self.package_root,
                env=environment,
                shell=False,
                timeout=self.timeout_seconds,
                creationflags=creation_flags,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise SubprocessExecutionError("worker_timeout") from exc
        finally:
            environment.pop(OBSERVATION_SECRET_ENV, None)

        encoded_output = completed.stdout.encode("utf-8", errors="replace")
        if len(encoded_output) > MAX_WORKER_OUTPUT_BYTES:
            raise SubprocessExecutionError(
                "worker_output_too_large",
                returncode=completed.returncode,
            )
        if completed.stderr.strip():
            raise SubprocessExecutionError(
                "worker_stderr_not_empty",
                returncode=completed.returncode,
            )
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise SubprocessExecutionError(
                "worker_output_invalid",
                returncode=completed.returncode,
            ) from exc
        if not isinstance(result, dict):
            raise SubprocessExecutionError(
                "worker_output_invalid",
                returncode=completed.returncode,
            )
        if completed.returncode != 0 or result.get("ok") is not True:
            code = result.get("error_code")
            raise SubprocessExecutionError(
                str(code) if isinstance(code, str) else "worker_failed",
                returncode=completed.returncode,
            )
        envelope_payload = result.get("envelope")
        if not isinstance(envelope_payload, dict):
            raise SubprocessExecutionError(
                "worker_envelope_missing",
                returncode=completed.returncode,
            )
        envelope = ObservationEnvelope.from_dict(envelope_payload)
        if (
            envelope.source != self.adapter_source
            or envelope.session_id != request.session_id
            or envelope.goal_id != request.goal_id
            or envelope.action_id != request.action_id
            or envelope.action_digest != request.action_digest
        ):
            raise SubprocessExecutionError(
                "worker_envelope_correlation_mismatch",
                returncode=completed.returncode,
            )
        return envelope
