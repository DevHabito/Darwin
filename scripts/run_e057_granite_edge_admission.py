"""Load and raw-performance runner for pre-registered Experiment 057."""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import secrets
import socket
import statistics
import subprocess
import time
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from darwin_v50.conversation import LlamaCppServerTransport


PRE_REGISTRATION_COMMIT = "b52636131fbd445e4d2976a67aec8f3559dd134c"
VOICE_HOST_COMMIT = "b383fc4e8b19f7638ee61773c8a026e0e4b6846c"
E052_BLOB = "ead5427a064da10e4afd0ac574d5e6c8825f6e83"
E053_PERFORMANCE_BLOB = "f97f62a91c7dc7c8f94fc7cbd49cfda3f00bfb38"
E055_RESULT_BLOB = "1ed64692286b5d46f061629ff3b6a422ab47c642"
MODEL_ID = "ibm-granite-4.0-1b-Q3_K_S"
MODEL_BYTES = 785_585_920
MODEL_SHA256 = "1dc4514416725646ecdd4668759937981a34407f422533cf330fba6709320182"
SERVER_SHA256 = "aa6b7907d3901f2e24892838e6f15243a47b22ad792eaccbdc0e2a4bccfd5283"
BENCH_SHA256 = "23947ddff87fe418e2db0e49d6fb1b79f2f66c142cf7d5c614d0f4c870e05c4b"
PORT = 18057
ENDPOINT = f"http://127.0.0.1:{PORT}"
MAX_READY_MILLISECONDS = 60_000.0
MAX_PEAK_WORKING_SET = 1_800_000_000
MIN_PROMPT_TOKENS_PER_SECOND = 25.0
MIN_GENERATION_TOKENS_PER_SECOND = 8.0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_blob(root: Path, path: Path) -> str:
    completed = subprocess.run(
        ["git", "hash-object", str(path)],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def artifact_identity_failures(*, observed_bytes: int, observed_sha256: str) -> list[str]:
    failures: list[str] = []
    if observed_bytes != MODEL_BYTES:
        failures.append("artifact_byte_count_mismatch")
    if observed_sha256.lower() != MODEL_SHA256:
        failures.append("artifact_sha256_mismatch")
    return failures


def load_admission_failures(
    *,
    ready_milliseconds: float | None,
    peak_working_set_bytes: int | None,
    probe_passed: bool,
    server_exit_code: int | None,
    listener_present_after_stop: bool,
    api_key_present_in_logs: bool = False,
) -> list[str]:
    failures: list[str] = []
    if (
        ready_milliseconds is None
        or not math.isfinite(ready_milliseconds)
        or ready_milliseconds > MAX_READY_MILLISECONDS
    ):
        failures.append("server_readiness_failed")
    if (
        peak_working_set_bytes is None
        or peak_working_set_bytes > MAX_PEAK_WORKING_SET
    ):
        failures.append("load_peak_working_set_exceeded")
    if not probe_passed:
        failures.append("exact_runtime_probe_failed")
    if server_exit_code is None:
        failures.append("server_exit_unobserved")
    if listener_present_after_stop:
        failures.append("listener_remained_after_stop")
    if api_key_present_in_logs:
        failures.append("ephemeral_key_present_in_logs")
    return failures


def parse_benchmark_records(
    records: object,
) -> tuple[dict[str, Any] | None, list[str]]:
    failures: list[str] = []
    if not isinstance(records, list):
        return None, ["benchmark_output_not_array"]
    prompt = [item for item in records if isinstance(item, Mapping) and item.get("n_prompt") == 256 and item.get("n_gen") == 0]
    generation = [item for item in records if isinstance(item, Mapping) and item.get("n_prompt") == 0 and item.get("n_gen") == 32]
    if len(prompt) != 1:
        failures.append("prompt_record_count_mismatch")
    if len(generation) != 1:
        failures.append("generation_record_count_mismatch")
    if failures:
        return None, failures

    prompt_record = prompt[0]
    generation_record = generation[0]
    prompt_samples = prompt_record.get("samples_ts")
    generation_samples = generation_record.get("samples_ts")
    if not isinstance(prompt_samples, list) or len(prompt_samples) != 2:
        failures.append("prompt_sample_count_mismatch")
    if not isinstance(generation_samples, list) or len(generation_samples) != 2:
        failures.append("generation_sample_count_mismatch")
    if failures:
        return None, failures

    all_samples = prompt_samples + generation_samples
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) <= 0.0
        for value in all_samples
    ):
        return None, ["benchmark_sample_not_finite_positive"]

    prompt_values = [float(value) for value in prompt_samples]
    generation_values = [float(value) for value in generation_samples]
    measured = {
        "prompt_processing_tokens_per_second_mean": statistics.fmean(prompt_values),
        "prompt_processing_standard_deviation": statistics.pstdev(prompt_values),
        "prompt_processing_samples": prompt_values,
        "generation_tokens_per_second_mean": statistics.fmean(generation_values),
        "generation_standard_deviation": statistics.pstdev(generation_values),
        "generation_samples": generation_values,
        "model_type": prompt_record.get("model_type"),
        "benchmark_reported_weight_bytes": prompt_record.get("model_size"),
        "benchmark_reported_parameters": prompt_record.get("model_n_params"),
        "build_commit": prompt_record.get("build_commit"),
        "build_number": prompt_record.get("build_number"),
        "cpu_info": prompt_record.get("cpu_info"),
        "backends": prompt_record.get("backends"),
    }
    return measured, []


def performance_admission_failures(
    *,
    exit_code: int | None,
    peak_working_set_bytes: int | None,
    measurements: Mapping[str, Any] | None,
    parse_failures: Sequence[str],
) -> list[str]:
    failures = list(parse_failures)
    if exit_code != 0:
        failures.append("benchmark_exit_nonzero")
    if (
        peak_working_set_bytes is None
        or peak_working_set_bytes > MAX_PEAK_WORKING_SET
    ):
        failures.append("benchmark_peak_working_set_exceeded")
    if measurements is None:
        return list(dict.fromkeys(failures))
    prompt_mean = measurements.get("prompt_processing_tokens_per_second_mean")
    generation_mean = measurements.get("generation_tokens_per_second_mean")
    if not isinstance(prompt_mean, (int, float)) or prompt_mean < MIN_PROMPT_TOKENS_PER_SECOND:
        failures.append("prompt_throughput_below_threshold")
    if not isinstance(generation_mean, (int, float)) or generation_mean < MIN_GENERATION_TOKENS_PER_SECOND:
        failures.append("generation_throughput_below_threshold")
    return list(dict.fromkeys(failures))


class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def _peak_working_set(process_id: int) -> int | None:
    if not hasattr(ctypes, "windll"):
        return None
    process_query_information = 0x0400
    process_vm_read = 0x0010
    kernel32 = ctypes.windll.kernel32
    psapi = ctypes.windll.psapi
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_ProcessMemoryCounters),
        wintypes.DWORD,
    ]
    handle = kernel32.OpenProcess(
        process_query_information | process_vm_read,
        False,
        process_id,
    )
    if not handle:
        return None
    try:
        counters = _ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(
            handle,
            ctypes.byref(counters),
            counters.cb,
        ):
            return None
        return int(counters.PeakWorkingSetSize)
    finally:
        kernel32.CloseHandle(handle)


def _listener_present() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.25)
        return probe.connect_ex(("127.0.0.1", PORT)) == 0


def _wait_ready(api_key: str, process: subprocess.Popen[bytes]) -> tuple[float, int | None]:
    started = time.perf_counter()
    peak: int | None = None
    while (time.perf_counter() - started) * 1000.0 <= MAX_READY_MILLISECONDS:
        observed = _peak_working_set(process.pid)
        if observed is not None:
            peak = observed if peak is None else max(peak, observed)
        if process.poll() is not None:
            raise RuntimeError(f"server_exited_before_ready:{process.returncode}")
        request = Request(
            ENDPOINT + "/health",
            headers={"Authorization": f"Bearer {api_key}"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=1.0) as response:
                if response.status == 200:
                    return (time.perf_counter() - started) * 1000.0, peak
        except (HTTPError, URLError, TimeoutError, OSError):
            pass
        time.sleep(0.05)
    raise RuntimeError("server_readiness_timeout")


def _run_monitored(
    command: Sequence[str],
    *,
    root: Path,
    stdout_path: Path,
    stderr_path: Path,
    timeout_seconds: float,
) -> tuple[int, int | None, float]:
    started = time.perf_counter()
    peak: int | None = None
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(
            list(command),
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        deadline = started + timeout_seconds
        while process.poll() is None:
            observed = _peak_working_set(process.pid)
            if observed is not None:
                peak = observed if peak is None else max(peak, observed)
            if time.perf_counter() >= deadline:
                process.terminate()
                try:
                    process.wait(timeout=10.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10.0)
                raise RuntimeError("benchmark_timeout")
            time.sleep(0.05)
    return process.returncode, peak, (time.perf_counter() - started) * 1000.0


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        errors="strict",
    )
    temporary.replace(path)


def _server_command(server: Path, model: Path, api_key: str) -> list[str]:
    return [
        str(server),
        "--model", str(model),
        "--alias", MODEL_ID,
        "--host", "127.0.0.1",
        "--port", str(PORT),
        "--ctx-size", "4096",
        "--parallel", "1",
        "--threads", "4",
        "--n-gpu-layers", "0",
        "--no-webui",
        "--cache-ram", "0",
        "--no-warmup",
        "--no-cache-prompt",
        "--reasoning", "off",
        "--reasoning-format", "none",
        "--api-key", api_key,
    ]


def _verify_frozen_inputs(root: Path, model: Path, server: Path, bench: Path) -> None:
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", PRE_REGISTRATION_COMMIT, "HEAD"],
        cwd=root,
        check=False,
    )
    if ancestry.returncode != 0:
        raise RuntimeError("pre_registration_not_ancestor")
    expected_blobs = {
        root / "docs/v50/results/EXPERIMENT_052_LOCAL_INFERENCE_BOTTLENECK_DIAGNOSTIC.json": E052_BLOB,
        root / "docs/v50/results/EXPERIMENT_053_RAW_PERFORMANCE_ADMISSION.json": E053_PERFORMANCE_BLOB,
        root / "docs/v50/results/EXPERIMENT_055_GATED_LOCAL_SCREEN.json": E055_RESULT_BLOB,
    }
    for path, expected in expected_blobs.items():
        if _git_blob(root, path) != expected:
            raise RuntimeError(f"frozen_blob_mismatch:{path.name}")
    if _sha256(server) != SERVER_SHA256:
        raise RuntimeError("server_sha256_mismatch")
    if _sha256(bench) != BENCH_SHA256:
        raise RuntimeError("bench_sha256_mismatch")
    failures = artifact_identity_failures(
        observed_bytes=model.stat().st_size,
        observed_sha256=_sha256(model),
    )
    if failures:
        raise RuntimeError(",".join(failures))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    arguments = parser.parse_args()
    root = arguments.repository.resolve()
    runtime_dir = root / "darwin_home/e045/runtime/llama-b10470-win-cpu-x64"
    server_path = runtime_dir / "llama-server.exe"
    bench_path = runtime_dir / "llama-bench.exe"
    model_path = root / "darwin_home/e057/downloads/granite-4.0-1b-Q3_K_S.gguf"
    run_dir = root / "darwin_home/e057/admission"
    run_dir.mkdir(parents=True, exist_ok=True)
    result_path = run_dir / "raw-result.json"
    server_stdout = run_dir / "server.stdout.log"
    server_stderr = run_dir / "server.stderr.log"
    bench_stdout = run_dir / "llama-bench.json"
    bench_stderr = run_dir / "llama-bench.stderr.log"
    record: dict[str, Any] = {
        "schema": "darwin-e057-raw-edge-admission-v1",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "pre_registration_commit": PRE_REGISTRATION_COMMIT,
        "voice_host_commit": VOICE_HOST_COMMIT,
        "model_id": MODEL_ID,
        "model_bytes": None,
        "model_sha256": None,
        "load": {"performed": False, "passed": False, "failures": []},
        "performance": {"performed": False, "passed": False, "failures": []},
        "fatal_error": None,
    }
    _atomic_json(result_path, record)
    server: subprocess.Popen[bytes] | None = None
    api_key = secrets.token_urlsafe(48)
    try:
        if _listener_present():
            raise RuntimeError("registered_port_already_in_use")
        _verify_frozen_inputs(root, model_path, server_path, bench_path)
        record["model_bytes"] = model_path.stat().st_size
        record["model_sha256"] = _sha256(model_path)
        ready_ms: float | None = None
        load_peak: int | None = None
        probe_passed = False
        load_error: str | None = None
        try:
            with server_stdout.open("wb") as stdout, server_stderr.open("wb") as stderr:
                server = subprocess.Popen(
                    _server_command(server_path, model_path, api_key),
                    cwd=root,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                ready_ms, load_peak = _wait_ready(api_key, server)
                transport = LlamaCppServerTransport(
                    endpoint=ENDPOINT,
                    api_key=api_key,
                    timeout_seconds=120.0,
                )
                transport.probe(model=MODEL_ID, context_tokens=4096)
                probe_passed = True
                observed = _peak_working_set(server.pid)
                if observed is not None:
                    load_peak = (
                        observed if load_peak is None else max(load_peak, observed)
                    )
        except (OSError, RuntimeError, ValueError) as exc:
            load_error = f"{type(exc).__name__}:{exc}"
        finally:
            if server is not None and server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=15.0)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=15.0)
        for _ in range(100):
            if not _listener_present():
                break
            time.sleep(0.05)
        listener_after_stop = _listener_present()
        api_key_present = (
            server_stdout.exists()
            and server_stderr.exists()
            and (
                api_key.encode("utf-8") in server_stdout.read_bytes()
                or api_key.encode("utf-8") in server_stderr.read_bytes()
            )
        )
        load_failures = load_admission_failures(
            ready_milliseconds=ready_ms,
            peak_working_set_bytes=load_peak,
            probe_passed=probe_passed,
            server_exit_code=None if server is None else server.returncode,
            listener_present_after_stop=listener_after_stop,
            api_key_present_in_logs=api_key_present,
        )
        if load_error is not None:
            load_failures.append("load_execution_failed")
        record["load"] = {
            "performed": True,
            "ready_milliseconds": ready_ms,
            "peak_working_set_bytes": load_peak,
            "probe_passed": probe_passed,
            "server_exit_code": None if server is None else server.returncode,
            "listener_present_after_stop": listener_after_stop,
            "server_stdout_sha256": _sha256(server_stdout),
            "server_stderr_sha256": _sha256(server_stderr),
            "api_key_present_in_logs": api_key_present,
            "error": load_error,
            "failures": load_failures,
            "passed": not load_failures,
        }
        _atomic_json(result_path, record)
        if load_failures:
            record["result"] = "failed_load_admission"
            return_code = 1
        else:
            command = [
                str(bench_path),
                "--model", str(model_path),
                "--offline",
                "--n-gpu-layers", "0",
                "--n-prompt", "256",
                "--n-gen", "32",
                "--threads", "4",
                "--repetitions", "2",
                "--delay", "1",
                "--output", "json",
            ]
            bench_error: str | None = None
            exit_code: int | None = None
            bench_peak: int | None = None
            elapsed_ms: float | None = None
            try:
                exit_code, bench_peak, elapsed_ms = _run_monitored(
                    command,
                    root=root,
                    stdout_path=bench_stdout,
                    stderr_path=bench_stderr,
                    timeout_seconds=300.0,
                )
            except (OSError, RuntimeError, ValueError) as exc:
                bench_error = f"{type(exc).__name__}:{exc}"
            if bench_error is not None:
                measurements = None
                parse_failures = ["benchmark_execution_failed"]
            else:
                try:
                    raw_records = json.loads(
                        bench_stdout.read_text(encoding="utf-8")
                    )
                except (UnicodeDecodeError, json.JSONDecodeError):
                    measurements = None
                    parse_failures = ["benchmark_json_invalid"]
                else:
                    measurements, parse_failures = parse_benchmark_records(
                        raw_records
                    )
            performance_failures = performance_admission_failures(
                exit_code=exit_code,
                peak_working_set_bytes=bench_peak,
                measurements=measurements,
                parse_failures=parse_failures,
            )
            record["performance"] = {
                "performed": True,
                "exit_code": exit_code,
                "elapsed_milliseconds": elapsed_ms,
                "peak_working_set_bytes": bench_peak,
                "error": bench_error,
                "measurements": measurements,
                "stdout_bytes": bench_stdout.stat().st_size,
                "stdout_sha256": _sha256(bench_stdout),
                "stderr_bytes": bench_stderr.stat().st_size,
                "stderr_sha256": _sha256(bench_stderr),
                "failures": performance_failures,
                "passed": not performance_failures,
            }
            record["result"] = (
                "pass_edge_admission_only"
                if not performance_failures
                else "failed_raw_performance_admission"
            )
            return_code = 0 if not performance_failures else 1
    except BaseException as exc:
        record["fatal_error"] = {
            "class": type(exc).__name__,
            "message": str(exc),
        }
        record["result"] = "invalid_runner_or_capture_failure"
        return_code = 2
    finally:
        if server is not None and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=15.0)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=15.0)
        record["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        record["listener_present_at_finalization"] = _listener_present()
        _atomic_json(result_path, record)
    print(f"E057_RAW_RESULT={result_path}")
    print(f"E057_RESULT={record.get('result')}")
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
