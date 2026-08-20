"""Offline artifact-token conformance runner for Experiment 059."""

from __future__ import annotations

import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import subprocess
from typing import Any, Mapping, Sequence

from darwin_v50.conversation import GRANITE_CONTROL_TOKEN_IDS


PRE_REGISTRATION_COMMIT = "7678b9b9cc2cd4acee7c9a9295080d7a783bb37d"
ENGINEERING_ADMISSION_COMMIT = "466af5c92a4ffd5a907e8a214d1aaf6cd88c79fa"
E058_RESULT_BLOB = "8fccbb571a567c0d2ff216f67834255763e45689"
LOCAL_TRANSPORT_BLOB = "c8871d2bfb925007e3856319cd096cff72dc912a"
GRANITE_ADAPTER_BLOB = "654c47fe2b479fb6b1f17a317353f7484170e976"
GRANITE_ADAPTER_TEST_BLOB = "3bcfaf4219db04611bc73306d4d4ac41d043b433"
MODEL_BYTES = 222_662_560
MODEL_SHA256 = "0a8d6a7373602fadfba274a640ba784b86cc6847f1c67f1b0a90fa2ec266b7fb"
TOKENIZER_SHA256 = "f7a3a6f6d750e96dc818ec822eba2a3d7b3108e6333f9c657ba6fb8e5db2d3d2"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_token_ids(stdout: str) -> tuple[list[int] | None, list[str]]:
    try:
        value = ast.literal_eval(stdout.strip())
    except (SyntaxError, ValueError):
        return None, ["tokenizer_stdout_not_python_list"]
    if not isinstance(value, list) or any(
        isinstance(item, bool) or not isinstance(item, int) for item in value
    ):
        return None, ["tokenizer_ids_not_integer_list"]
    return value, []


def conformance_failures(
    *,
    exit_code: int,
    observed_ids: Sequence[int] | None,
    parse_failures: Sequence[str],
    listener_present_after: bool,
) -> list[str]:
    failures = list(parse_failures)
    if exit_code != 0:
        failures.append("tokenizer_exit_nonzero")
    if observed_ids is not None:
        counts = Counter(observed_ids)
        for expected in GRANITE_CONTROL_TOKEN_IDS.values():
            if counts[expected] != 1:
                failures.append(f"control_token_id_{expected}_count_mismatch")
    if listener_present_after:
        failures.append("unexpected_listener_after_tokenization")
    return list(dict.fromkeys(failures))


def _git_blob(root: Path, relative: str) -> str:
    completed = subprocess.run(
        ["git", "hash-object", relative],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def _listener_present(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.25)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        errors="strict",
    )
    temporary.replace(path)


def _verify_inputs(root: Path, model: Path, tokenizer: Path) -> None:
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", PRE_REGISTRATION_COMMIT, "HEAD"],
        cwd=root,
        check=False,
    )
    if ancestry.returncode != 0:
        raise RuntimeError("pre_registration_not_ancestor")
    engineering_ancestry = subprocess.run(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            ENGINEERING_ADMISSION_COMMIT,
            "HEAD",
        ],
        cwd=root,
        check=False,
    )
    if engineering_ancestry.returncode != 0:
        raise RuntimeError("engineering_admission_not_ancestor")
    if (
        _git_blob(
            root,
            "docs/v50/results/EXPERIMENT_058_H350M_EDGE_ADMISSION.json",
        )
        != E058_RESULT_BLOB
    ):
        raise RuntimeError("e058_result_blob_mismatch")
    if (
        _git_blob(root, "src/darwin_v50/conversation/local_seed.py")
        != LOCAL_TRANSPORT_BLOB
    ):
        raise RuntimeError("shared_local_transport_blob_mismatch")
    if (
        _git_blob(root, "src/darwin_v50/conversation/granite_seed.py")
        != GRANITE_ADAPTER_BLOB
    ):
        raise RuntimeError("granite_adapter_blob_mismatch")
    if (
        _git_blob(root, "tests/test_v50_granite_control_boundary.py")
        != GRANITE_ADAPTER_TEST_BLOB
    ):
        raise RuntimeError("granite_adapter_test_blob_mismatch")
    if model.stat().st_size != MODEL_BYTES or _sha256(model) != MODEL_SHA256:
        raise RuntimeError("e058_model_identity_mismatch")
    if _sha256(tokenizer) != TOKENIZER_SHA256:
        raise RuntimeError("tokenizer_executable_identity_mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    arguments = parser.parse_args()
    root = arguments.repository.resolve()
    model = root / "darwin_home/e058/downloads/granite-4.0-h-350m-Q4_K_M.gguf"
    tokenizer = root / "darwin_home/e045/runtime/llama-b10470-win-cpu-x64/llama-tokenize.exe"
    output_dir = root / "darwin_home/e059/token-conformance"
    output_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = output_dir / "llama-tokenize.stdout.log"
    stderr_path = output_dir / "llama-tokenize.stderr.log"
    result_path = output_dir / "raw-result.json"
    record: dict[str, Any] = {
        "schema": "darwin-e059-raw-token-conformance-v1",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "pre_registration_commit": PRE_REGISTRATION_COMMIT,
        "engineering_admission_commit": ENGINEERING_ADMISSION_COMMIT,
        "granite_adapter_blob": GRANITE_ADAPTER_BLOB,
        "granite_adapter_test_blob": GRANITE_ADAPTER_TEST_BLOB,
        "model_bytes": None,
        "model_sha256": None,
        "tokenizer_sha256": None,
        "markers_submitted": len(GRANITE_CONTROL_TOKEN_IDS),
        "fatal_error": None,
    }
    _atomic_json(result_path, record)
    try:
        _verify_inputs(root, model, tokenizer)
        record["model_bytes"] = model.stat().st_size
        record["model_sha256"] = _sha256(model)
        record["tokenizer_sha256"] = _sha256(tokenizer)
        ordered_markers = [
            marker
            for marker, _ in sorted(
                GRANITE_CONTROL_TOKEN_IDS.items(),
                key=lambda item: item[1],
            )
        ]
        prompt = "\n".join(ordered_markers)
        completed = subprocess.run(
            [
                str(tokenizer),
                "--model", str(model),
                "--offline",
                "--ids",
                "--no-bos",
                "--prompt", prompt,
            ],
            cwd=root,
            check=False,
            capture_output=True,
        )
        stdout_path.write_bytes(completed.stdout)
        stderr_path.write_bytes(completed.stderr)
        try:
            stdout_text = completed.stdout.decode("utf-8", errors="strict")
            stderr_text = completed.stderr.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            observed_ids = None
            parse_failures = ["tokenizer_output_not_strict_utf8"]
            strict_utf8 = False
            stderr_text = ""
        else:
            observed_ids, parse_failures = parse_token_ids(stdout_text)
            strict_utf8 = True
        listeners = sum(
            int(_listener_present(port)) for port in (18057, 18058, 18059)
        )
        failures = conformance_failures(
            exit_code=completed.returncode,
            observed_ids=observed_ids,
            parse_failures=parse_failures,
            listener_present_after=bool(listeners),
        )
        record.update(
            {
                "exit_code": completed.returncode,
                "strict_utf8": strict_utf8,
                "observed_token_ids": observed_ids,
                "expected_control_token_ids": sorted(
                    GRANITE_CONTROL_TOKEN_IDS.values()
                ),
                "stdout_bytes": len(completed.stdout),
                "stdout_sha256": _sha256(stdout_path),
                "stderr_bytes": len(completed.stderr),
                "stderr_sha256": _sha256(stderr_path),
                "stderr_contains_generation_marker": "eval time" in stderr_text,
                "listener_count_after": listeners,
                "failures": failures,
                "passed": not failures,
                "result": (
                    "pass_offline_token_conformance"
                    if not failures
                    else "fail_offline_token_conformance"
                ),
            }
        )
        return_code = 0 if not failures else 1
    except BaseException as exc:
        record["fatal_error"] = {
            "class": type(exc).__name__,
            "message": str(exc),
        }
        record["result"] = "invalid_runner_or_capture_failure"
        return_code = 2
    finally:
        record["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        _atomic_json(result_path, record)
    print(f"E059_RAW_RESULT={result_path}")
    print(f"E059_RESULT={record.get('result')}")
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
