"""Auditable, human-gated runner for the pre-registered E055 live screen."""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import socket
import subprocess
import time
from typing import Any, Callable, Mapping, Protocol, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from darwin_v50.conversation import (
    ConversationBackendKind,
    ConversationRuntime,
    ConversationSettings,
    LlamaCppServerTransport,
    PortableLocalLanguageBackend,
)


MODEL_ID = "Qwen_Qwen3.5-0.8B-Q4_K_M"
REGISTERED_PORT = 18055
REGISTERED_ENDPOINT = f"http://127.0.0.1:{REGISTERED_PORT}"
REGISTERED_NUMERIC_LEVELS = tuple((0.0, 0.25, 0.5, 0.75, 1.0))
REGISTERED_INPUTS = tuple(
    (
        "Olá, Darwin. Quero ter uma conversa tranquila. O que você sugere para começarmos?",
        "Por que o céu parece azul durante o dia?",
        "Explique a mesma ideia como se eu tivesse dez anos.",
        "Agora mude de assunto: ajude-me a montar uma rotina gratuita de estudos de 20 minutos por dia.",
        "Prefiro estudar à noite, não pela manhã. Ajuste a sugestão.",
        "Hoje estou frustrado porque não consegui cumprir o que planejei. Como você responderia?",
        "Invente uma pergunta interessante sobre o oceano para continuarmos conversando.",
        "Você vai lembrar desta conversa amanhã? Responda sem fingir que tem memória permanente.",
    )
)
REQUIRED_HUMAN_CRITERIA = {
    3: "resolves the sky reference without treating reflection alone as adequate",
    5: "proposes a night-adjusted study action",
    6: "addresses the reported frustration",
    7: "asks an actual question about the ocean",
    8: "denies or limits memory beyond the temporary session",
}


class RuntimeLike(Protocol):
    def turn(self, text: str) -> object:
        """Return one complete Darwin conversation turn or raise."""


class InferenceCaptureLike(Protocol):
    inferences: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class HumanDecision:
    requested_act_attempted: bool
    required_criterion_met: bool | None
    reason: str


Adjudicator = Callable[[int, Mapping[str, Any], str | None], HumanDecision]
PersistRecord = Callable[[Mapping[str, Any]], None]


def _strict_level(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and value in REGISTERED_NUMERIC_LEVELS
    )


def _contains_replacement(value: object) -> bool:
    if isinstance(value, str):
        return "\ufffd" in value
    if isinstance(value, Mapping):
        return any(
            _contains_replacement(key) or _contains_replacement(child)
            for key, child in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_replacement(child) for child in value)
    return False


def _numeric_failures(understanding: object) -> list[str]:
    failures: list[str] = []
    if not isinstance(understanding, Mapping):
        return ["understanding_output_not_object"]
    confidence = understanding.get("confidence")
    if not _strict_level(confidence):
        failures.append("confidence_not_registered_level")
    signals = understanding.get("reported_signals")
    if not isinstance(signals, list):
        failures.append("reported_signals_not_array")
        return failures
    for index, signal in enumerate(signals):
        if not isinstance(signal, Mapping) or not _strict_level(signal.get("value")):
            failures.append(f"reported_signals_{index}_not_registered_level")
    return failures


def _successful_pair_failures(
    *,
    turn_number: int,
    prompt: str,
    expression: str,
    prior_expressions: Sequence[str],
    prior_echo_count: int,
    new_inferences: Sequence[Mapping[str, Any]],
    authority_mutations: Mapping[str, object],
) -> tuple[list[str], int]:
    failures: list[str] = []
    echo_count = prior_echo_count + int(expression == prompt)
    if echo_count > 1:
        failures.append("more_than_one_exact_current_input_echo")
    if expression in prior_expressions:
        failures.append("exact_copy_of_older_expression")
    if _contains_replacement(prompt) or _contains_replacement(expression):
        failures.append("unicode_replacement_character")
    if len(new_inferences) != 2:
        failures.append("successful_turn_did_not_use_exactly_two_inferences")
    else:
        expected_names = ("darwin_understanding_v1", "darwin_expression_v1")
        observed_names = tuple(item.get("schema_name") for item in new_inferences)
        if observed_names != expected_names:
            failures.append("inference_stage_order_changed")
        for item in new_inferences:
            if not item.get("completed"):
                failures.append("inference_not_completed")
            duration = item.get("wall_milliseconds")
            if (
                isinstance(duration, bool)
                or not isinstance(duration, (int, float))
                or duration > 120_000.0
            ):
                failures.append("inference_exceeded_120_seconds")
        failures.extend(_numeric_failures(new_inferences[0].get("output")))
        if _contains_replacement(new_inferences):
            failures.append("unicode_replacement_character_in_native_output")
    if any(value != 0 for value in authority_mutations.values()):
        failures.append("authority_mutation_observed")
    return list(dict.fromkeys(failures)), echo_count


def run_registered_session(
    *,
    runtime: RuntimeLike,
    transport: InferenceCaptureLike,
    record: dict[str, Any],
    adjudicate: Adjudicator,
    persist: PersistRecord,
    inputs: Sequence[str] = REGISTERED_INPUTS,
) -> None:
    """Run one registered session with a mandatory gate before every next input."""
    expressions: list[str] = []
    echo_count = 0
    attempted_acts = 0
    record.setdefault("turns", [])
    record["screen_finished"] = False
    persist(record)
    for turn_number, prompt in enumerate(inputs, start=1):
        inference_start = len(transport.inferences)
        turn: dict[str, Any] = {
            "turn": turn_number,
            "input": prompt,
            "inference_start_index": inference_start,
        }
        started = time.perf_counter()
        try:
            result = runtime.turn(prompt)
        except BaseException as exc:
            turn.update(
                {
                    "gateway_pair_valid": False,
                    "wall_milliseconds": (time.perf_counter() - started) * 1000.0,
                    "error_class": type(exc).__name__,
                    "error": str(exc),
                    "native_inferences": deepcopy(
                        transport.inferences[inference_start:]
                    ),
                    "stop_reasons": ["gateway_or_transport_failure"],
                }
            )
            record["turns"].append(turn)
            record["result"] = "failed_closed_early_stop"
            record["screen_finished"] = True
            persist(record)
            return

        new_inferences = deepcopy(transport.inferences[inference_start:])
        expression = result.expression.text
        authority = asdict(result.authority_mutations)
        turn.update(
            {
                "gateway_pair_valid": True,
                "wall_milliseconds": (time.perf_counter() - started) * 1000.0,
                "expression": expression,
                "observation": asdict(result.observation),
                "authority_mutations": authority,
                "native_inferences": new_inferences,
            }
        )
        failures, echo_count = _successful_pair_failures(
            turn_number=turn_number,
            prompt=prompt,
            expression=expression,
            prior_expressions=expressions,
            prior_echo_count=echo_count,
            new_inferences=new_inferences,
            authority_mutations=authority,
        )
        turn["mechanical_stop_reasons"] = failures
        record["turns"].append(turn)
        persist(record)
        if failures:
            record["result"] = "mechanical_quality_failure_early_stop"
            record["screen_finished"] = True
            persist(record)
            return

        required = REQUIRED_HUMAN_CRITERIA.get(turn_number)
        decision = adjudicate(turn_number, deepcopy(turn), required)
        if not isinstance(decision, HumanDecision):
            raise TypeError("adjudicator must return HumanDecision")
        if required is None and decision.required_criterion_met is not None:
            raise ValueError("non-required turn received a required-criterion decision")
        if required is not None and not isinstance(
            decision.required_criterion_met,
            bool,
        ):
            raise ValueError("required turn lacks a boolean criterion decision")
        turn["human_decision"] = asdict(decision)
        attempted_acts += int(decision.requested_act_attempted)
        expressions.append(expression)
        remaining = len(inputs) - turn_number
        human_stop: list[str] = []
        if required is not None and decision.required_criterion_met is False:
            human_stop.append("required_human_criterion_failed")
        if attempted_acts + remaining < 6:
            human_stop.append("six_requested_acts_no_longer_possible")
        turn["human_stop_reasons"] = human_stop
        persist(record)
        if human_stop:
            record["result"] = "human_quality_failure_early_stop"
            record["screen_finished"] = True
            persist(record)
            return

    record["requested_acts_attempted"] = attempted_acts
    record["exact_current_input_echoes"] = echo_count
    record["result"] = (
        "descriptive_screen_pass"
        if len(record["turns"]) == len(inputs) and attempted_acts >= 6
        else "descriptive_screen_fail"
    )
    record["screen_finished"] = True
    persist(record)


class CapturingTransport(LlamaCppServerTransport):
    """Exact transport with immutable-after-capture evidence copies."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.inferences: list[dict[str, Any]] = []

    def generate_structured(
        self,
        *,
        model: str,
        instructions: str,
        payload: Mapping[str, object],
        schema_name: str,
        schema: Mapping[str, object],
        max_output_tokens: int,
    ) -> Mapping[str, Any]:
        started = time.perf_counter()
        try:
            result = super().generate_structured(
                model=model,
                instructions=instructions,
                payload=payload,
                schema_name=schema_name,
                schema=schema,
                max_output_tokens=max_output_tokens,
            )
        except BaseException as exc:
            self.inferences.append(
                {
                    "schema_name": schema_name,
                    "wall_milliseconds": (time.perf_counter() - started) * 1000.0,
                    "completed": False,
                    "error_class": type(exc).__name__,
                    "error": str(exc),
                }
            )
            raise
        self.inferences.append(
            {
                "schema_name": schema_name,
                "wall_milliseconds": (time.perf_counter() - started) * 1000.0,
                "completed": True,
                "output": deepcopy(dict(result)),
            }
        )
        return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _listener_present(port: int = REGISTERED_PORT) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.25)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _wait_ready(api_key: str, server: subprocess.Popen[bytes]) -> float:
    started = time.perf_counter()
    deadline = started + 60.0
    while time.perf_counter() < deadline:
        if server.poll() is not None:
            raise RuntimeError(f"server_exited_before_ready:{server.returncode}")
        request = Request(
            REGISTERED_ENDPOINT + "/health",
            headers={"Authorization": f"Bearer {api_key}"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=1.0) as response:
                if response.status == 200:
                    return (time.perf_counter() - started) * 1000.0
        except (HTTPError, URLError, TimeoutError, OSError):
            pass
        time.sleep(0.05)
    raise RuntimeError("server_readiness_timeout")


def _peak_working_set(process_id: int) -> int | None:
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f"(Get-Process -Id {process_id}).PeakWorkingSet64",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        errors="strict",
    )
    temporary.replace(path)


def _yes_no(prompt: str) -> bool:
    while True:
        answer = input(prompt).strip().lower()
        if answer == "yes":
            return True
        if answer == "no":
            return False
        print("Enter exactly 'yes' or 'no'.", flush=True)


def _interactive_adjudication(
    turn_number: int,
    turn: Mapping[str, Any],
    required: str | None,
) -> HumanDecision:
    print(f"E055 turn {turn_number} exact expression JSON:", flush=True)
    print(json.dumps(turn["expression"], ensure_ascii=False), flush=True)
    attempted = _yes_no("Requested conversational act attempted? [yes/no]: ")
    required_met = None
    if required is not None:
        print(f"Required criterion: {required}", flush=True)
        required_met = _yes_no("Required criterion met? [yes/no]: ")
    reason = input("Short human reason: ").strip()
    if not reason:
        raise ValueError("human adjudication reason cannot be blank")
    return HumanDecision(attempted, required_met, reason)


def _server_command(server: Path, model: Path, api_key: str) -> list[str]:
    return [
        str(server),
        "--model", str(model),
        "--alias", MODEL_ID,
        "--host", "127.0.0.1",
        "--port", str(REGISTERED_PORT),
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    arguments = parser.parse_args()
    root = arguments.repository.resolve()
    server_path = root / "darwin_home/e045/runtime/llama-b10470-win-cpu-x64/llama-server.exe"
    model_path = root / "darwin_home/e053/downloads/Qwen_Qwen3.5-0.8B-Q4_K_M.gguf"
    if _listener_present():
        raise RuntimeError("registered_port_already_in_use")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = root / "darwin_home/e055/live-screen" / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    record_path = run_dir / "raw-session.json"
    stdout_path = run_dir / "server.stdout.log"
    stderr_path = run_dir / "server.stderr.log"
    api_key = secrets.token_urlsafe(48)
    record: dict[str, Any] = {
        "schema": "darwin-e055-raw-gated-session-v1",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "pre_registration_commit": "ad1afeef468b47eae8446258281eafbaaf944e4f",
        "implementation_subject_commit": "c8ff493c7129888854756bd53ae68d399c42ee86",
        "model_id": MODEL_ID,
        "model_bytes": model_path.stat().st_size,
        "model_sha256": _sha256(model_path),
        "server_sha256": _sha256(server_path),
        "endpoint": REGISTERED_ENDPOINT,
        "registered_inputs": list(REGISTERED_INPUTS),
        "turns": [],
        "fatal_error": None,
    }
    persist = lambda value: _atomic_json(record_path, value)
    persist(record)
    runtime: ConversationRuntime | None = None
    server: subprocess.Popen[bytes] | None = None
    transport: CapturingTransport | None = None
    with stdout_path.open("wb") as server_stdout, stderr_path.open("wb") as server_stderr:
        try:
            server = subprocess.Popen(
                _server_command(server_path, model_path, api_key),
                cwd=root,
                stdin=subprocess.DEVNULL,
                stdout=server_stdout,
                stderr=server_stderr,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            record["server_pid"] = server.pid
            record["server_ready_milliseconds"] = _wait_ready(api_key, server)
            transport = CapturingTransport(
                endpoint=REGISTERED_ENDPOINT,
                api_key=api_key,
                timeout_seconds=120.0,
            )
            backend = PortableLocalLanguageBackend(model=MODEL_ID, transport=transport)
            backend.probe_model()
            runtime = ConversationRuntime.create(
                ConversationSettings(
                    backend=ConversationBackendKind.LOCAL,
                    model=MODEL_ID,
                    locale="pt-BR",
                    request_timeout_seconds=120.0,
                ),
                local_backend=backend,
            )
            record["runtime_start_snapshot"] = asdict(runtime.snapshot())
            run_registered_session(
                runtime=runtime,
                transport=transport,
                record=record,
                adjudicate=_interactive_adjudication,
                persist=persist,
            )
            record["runtime_before_close"] = asdict(runtime.snapshot())
        except BaseException as exc:
            record["fatal_error"] = {
                "class": type(exc).__name__,
                "message": str(exc),
            }
            record["result"] = "invalid_runner_or_capture_failure"
            persist(record)
            print(f"E055 fatal: {type(exc).__name__}: {exc}", flush=True)
        finally:
            if runtime is not None:
                runtime.close()
                record["temporary_context_after_close"] = list(
                    runtime.temporary_context()
                )
                record["runtime_after_close"] = asdict(runtime.snapshot())
            if server is not None and server.poll() is None:
                record["peak_working_set_bytes"] = _peak_working_set(server.pid)
                server.terminate()
                try:
                    server.wait(timeout=15.0)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=15.0)
            if server is not None:
                record["server_exit_code"] = server.returncode
    for _ in range(100):
        if not _listener_present():
            break
        time.sleep(0.05)
    record["listener_present_after_stop"] = _listener_present()
    record["server_stdout_bytes"] = stdout_path.stat().st_size
    record["server_stderr_bytes"] = stderr_path.stat().st_size
    record["server_stdout_sha256"] = _sha256(stdout_path)
    record["server_stderr_sha256"] = _sha256(stderr_path)
    secret = api_key.encode("utf-8")
    record["api_key_present_in_server_logs"] = (
        secret in stdout_path.read_bytes() or secret in stderr_path.read_bytes()
    )
    record["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    persist(record)
    print(f"E055_RAW_RECORD={record_path}", flush=True)
    print(f"E055_RESULT={record.get('result')}", flush=True)
    return 0 if record["fatal_error"] is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
