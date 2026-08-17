from __future__ import annotations

import ast
from copy import deepcopy
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
from threading import Thread
import unittest
from unittest.mock import patch
from typing import Any, Mapping

from darwin_v50.conversation import (
    ConversationAvailability,
    ConversationBackendKind,
    ConversationRuntime,
    ConversationSettings,
    LlamaCppServerTransport,
    LocalSeedTransportError,
    LoopbackJSONTransport,
    PortableLocalLanguageBackend,
    REGISTERED_CONTEXT_TOKENS,
)
from darwin_v50.language import (
    DarwinLanguageGateway,
    ExpressionPlan,
    GroundedFact,
    LanguageAuthorityError,
    LanguageBackendError,
    LanguageModelRequest,
    LanguageOperation,
    UnderstandingRequest,
)
from darwin_v50.models import ValidationError


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "Qwen_Qwen3-0.6B-Q4_K_M"
FROZEN_BLOBS = {
    "src/darwin_v50/desktop_runtime.py": (
        "01687c8e57aa1a867b18a66df9442b8745c08566"
    ),
    "docs/v50/EXPERIMENT_043_PERSISTENT_DESKTOP_RUNTIME.md": (
        "5becbc0177c7fc1fc1cfe0e2903e7a8323a7bd7d"
    ),
    "src/darwin_v50/conversation/config.py": (
        "1be6d0baf1a2b126f8762b697ba349efbbd92562"
    ),
    "src/darwin_v50/conversation/runtime.py": (
        "5139f9896fe8666c2114e63a97b9e6124f62ad13"
    ),
    "src/darwin_v50/conversation/openai_responses.py": (
        "511888e6ceed389988348570b63a6a1818498aea"
    ),
    "src/darwin_v50/conversation/cli.py": (
        "aebaa6015bb615166c0192c06005cefe6e03cc60"
    ),
    "docs/v50/EXPERIMENT_044_CONVERSATIONAL_DEVELOPMENT_RUNTIME.md": (
        "1ddcc7682cf4f4f65e0ee06d7d9a44bc221499dd"
    ),
    "docs/v50/EXPERIMENT_045_PORTABLE_LOCAL_LANGUAGE_SEED.md": (
        "e29124e0aa96a54f54d0a9c72815559492d2e708"
    ),
}


def understanding_payload() -> dict[str, Any]:
    return {
        "intent": "open_conversation",
        "entities": [{"kind": "topic", "value": "astronomia"}],
        "reported_signals": [],
        "temporal_reference": None,
        "explicit_preference": None,
        "confidence": 0.7,
    }


def completion(payload: object, **choice_overrides: object) -> dict[str, Any]:
    choice: dict[str, Any] = {
        "finish_reason": "stop",
        "message": {
            "role": "assistant",
            "content": json.dumps(payload, ensure_ascii=False),
        },
    }
    choice.update(choice_overrides)
    return {"choices": [choice]}


def model_probe() -> dict[str, Any]:
    return {"data": [{"id": MODEL_ID, "object": "model"}]}


def runtime_probe(**overrides: object) -> dict[str, Any]:
    result: dict[str, Any] = {
        "default_generation_settings": {"n_ctx": REGISTERED_CONTEXT_TOKENS},
        "total_slots": 1,
        "modalities": {"vision": False, "audio": False},
        "build_info": "llama.cpp-test-build",
    }
    result.update(overrides)
    return result


class CapturingJSONTransport:
    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def request_json(
        self,
        *,
        method: str,
        url: str,
        body: Mapping[str, object] | None,
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "body": deepcopy(body),
                "timeout_seconds": timeout_seconds,
            }
        )
        if not self.responses:
            raise AssertionError("unexpected local transport call")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        if not isinstance(response, Mapping):
            raise AssertionError("scripted response must be an object")
        return response


class ScriptedStructuredTransport:
    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.probes: list[tuple[str, int]] = []
        self.calls: list[dict[str, Any]] = []

    def probe(self, *, model: str, context_tokens: int) -> None:
        self.probes.append((model, context_tokens))

    def generate_structured(self, **request: object) -> Mapping[str, Any]:
        def detach(value: object) -> object:
            if isinstance(value, Mapping):
                return {str(key): detach(child) for key, child in value.items()}
            if isinstance(value, (list, tuple)):
                return [detach(child) for child in value]
            return value

        detached = detach(request)
        if not isinstance(detached, dict):
            raise AssertionError("detached structured request must be an object")
        self.calls.append(detached)
        if not self.responses:
            raise AssertionError("unexpected structured generation")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        if not isinstance(response, Mapping):
            raise AssertionError("scripted response must be an object")
        return response


def expression_plan() -> ExpressionPlan:
    return ExpressionPlan(
        speech_act="answer",
        facts=(
            GroundedFact("fact-1", "The interpretation is an unverified candidate."),
            GroundedFact("fact-2", "No persistent state changed."),
        ),
        fallback_text="The local language backend is unavailable.",
    )


class PortableLocalSeedFreezeTests(unittest.TestCase):
    def test_frozen_experiment_blobs_are_still_exact(self) -> None:
        for path, expected_blob in FROZEN_BLOBS.items():
            with self.subTest(path=path):
                result = subprocess.run(
                    ["git", "rev-parse", f"HEAD:{path}"],
                    cwd=REPOSITORY_ROOT,
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )
                self.assertEqual(result.stdout.strip(), expected_blob)

    def test_maintained_seed_modules_have_no_module_level_response_table(self) -> None:
        for relative_path in (
            "src/darwin_v50/conversation/local_seed.py",
            "src/darwin_v50/conversation/local_cli.py",
        ):
            with self.subTest(path=relative_path):
                tree = ast.parse((REPOSITORY_ROOT / relative_path).read_text("utf-8"))
                collection_assignments = []
                for node in tree.body:
                    value = None
                    if isinstance(node, ast.Assign):
                        value = node.value
                    elif isinstance(node, ast.AnnAssign):
                        value = node.value
                    if isinstance(value, (ast.Dict, ast.List, ast.Set, ast.Tuple)):
                        collection_assignments.append(node)
                self.assertEqual(collection_assignments, [])


class LoopbackTransportTests(unittest.TestCase):
    def test_only_exact_registered_loopback_origin_is_accepted(self) -> None:
        invalid = (
            "https://127.0.0.1:8080",
            "http://localhost:8080",
            "http://0.0.0.0:8080",
            "http://192.168.0.2:8080",
            "http://8.8.8.8:8080",
            "http://user@127.0.0.1:8080",
            "http://127.0.0.1",
            "http://127.0.0.1:80",
            "http://127.0.0.1:8080/v1",
            "http://127.0.0.1:8080?mode=local",
            "http://127.0.0.1:8080#fragment",
        )
        for endpoint in invalid:
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(ValidationError):
                    LlamaCppServerTransport(endpoint=endpoint)

        transport = LlamaCppServerTransport(endpoint="http://127.0.0.1:8080/")
        self.assertEqual(transport.endpoint, "http://127.0.0.1:8080")

    def test_redirect_is_rejected_without_following_it(self) -> None:
        class RedirectHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self.send_response(302)
                self.send_header("Location", "http://example.com/escaped")
                self.end_headers()

            def log_message(self, *_: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertRaisesRegex(
                LocalSeedTransportError,
                "redirect_rejected",
            ):
                LoopbackJSONTransport().request_json(
                    method="GET",
                    url=f"http://127.0.0.1:{server.server_port}/probe",
                    body=None,
                    timeout_seconds=2.0,
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2.0)

    def test_oversized_response_is_rejected(self) -> None:
        class OversizedHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                body = b'{' + b'"x":"' + (b"a" * 2_000_001) + b'"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), OversizedHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertRaisesRegex(
                LocalSeedTransportError,
                "response_too_large",
            ):
                LoopbackJSONTransport().request_json(
                    method="GET",
                    url=f"http://127.0.0.1:{server.server_port}/probe",
                    body=None,
                    timeout_seconds=2.0,
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2.0)


class LlamaCppServerTransportTests(unittest.TestCase):
    def test_probe_checks_exact_model_context_slot_modality_and_build(self) -> None:
        json_transport = CapturingJSONTransport(model_probe(), runtime_probe())
        transport = LlamaCppServerTransport(
            endpoint="http://127.0.0.1:8080",
            json_transport=json_transport,  # type: ignore[arg-type]
        )

        transport.probe(model=MODEL_ID, context_tokens=REGISTERED_CONTEXT_TOKENS)

        self.assertEqual(
            [(call["method"], call["url"]) for call in json_transport.calls],
            [
                ("GET", "http://127.0.0.1:8080/v1/models"),
                ("GET", "http://127.0.0.1:8080/props"),
            ],
        )

    def test_probe_mismatches_fail_closed(self) -> None:
        cases = (
            ({"data": [{"id": "different-model"}]}, runtime_probe()),
            (model_probe(), runtime_probe(default_generation_settings={"n_ctx": 8192})),
            (model_probe(), runtime_probe(total_slots=2)),
            (model_probe(), runtime_probe(modalities={"vision": True})),
            (model_probe(), runtime_probe(build_info="")),
        )
        for responses in cases:
            with self.subTest(responses=responses):
                transport = LlamaCppServerTransport(
                    endpoint="http://127.0.0.1:8080",
                    json_transport=CapturingJSONTransport(*responses),  # type: ignore[arg-type]
                )
                with self.assertRaises(LocalSeedTransportError):
                    transport.probe(
                        model=MODEL_ID,
                        context_tokens=REGISTERED_CONTEXT_TOKENS,
                    )

    def test_generation_is_schema_constrained_bounded_and_toolless(self) -> None:
        json_transport = CapturingJSONTransport(completion(understanding_payload()))
        transport = LlamaCppServerTransport(
            endpoint="http://127.0.0.1:8080",
            json_transport=json_transport,  # type: ignore[arg-type]
        )

        result = transport.generate_structured(
            model=MODEL_ID,
            instructions="Return the requested object.",
            payload={"operation": "understand", "payload": {"text": "Olá"}},
            schema_name="darwin_understanding_v1",
            schema={"type": "object", "additionalProperties": False},
            max_output_tokens=1_000,
        )

        self.assertEqual(result, understanding_payload())
        call = json_transport.calls[0]
        self.assertEqual(call["url"], "http://127.0.0.1:8080/v1/chat/completions")
        body = call["body"]
        self.assertEqual(body["model"], MODEL_ID)
        self.assertIs(body["stream"], False)
        self.assertEqual(body["temperature"], 0.0)
        self.assertEqual(body["max_tokens"], 1_000)
        self.assertEqual(body["chat_template_kwargs"], {"enable_thinking": False})
        self.assertNotIn("tools", body)
        self.assertNotIn("tool_choice", body)
        self.assertEqual(body["response_format"]["type"], "json_schema")
        self.assertIs(body["response_format"]["json_schema"]["strict"], True)

    def test_malformed_multiple_truncated_and_tool_outputs_fail_closed(self) -> None:
        cases = (
            {"choices": []},
            {"choices": [{}, {}]},
            completion(understanding_payload(), finish_reason="length"),
            completion(
                understanding_payload(),
                message={"content": "{}", "tool_calls": [{"id": "forbidden"}]},
            ),
            completion(understanding_payload(), message={"content": "not-json"}),
        )
        for response in cases:
            with self.subTest(response=response):
                transport = LlamaCppServerTransport(
                    endpoint="http://127.0.0.1:8080",
                    json_transport=CapturingJSONTransport(response),  # type: ignore[arg-type]
                )
                with self.assertRaises(LocalSeedTransportError):
                    transport.generate_structured(
                        model=MODEL_ID,
                        instructions="Return the requested object.",
                        payload={"operation": "understand"},
                        schema_name="darwin_understanding_v1",
                        schema={"type": "object"},
                        max_output_tokens=1_000,
                    )

    def test_registered_context_output_and_prompt_limits_cannot_expand(self) -> None:
        transport = LlamaCppServerTransport(
            endpoint="http://127.0.0.1:8080",
            json_transport=CapturingJSONTransport(),  # type: ignore[arg-type]
        )
        with self.assertRaisesRegex(ValidationError, "registered 4096"):
            transport.probe(model=MODEL_ID, context_tokens=8_192)
        with self.assertRaisesRegex(ValidationError, "registered limit"):
            transport.generate_structured(
                model=MODEL_ID,
                instructions="Return an object.",
                payload={"text": "bounded"},
                schema_name="bounded",
                schema={"type": "object"},
                max_output_tokens=2_000,
            )
        with self.assertRaisesRegex(LanguageBackendError, "prompt_exceeds"):
            transport.generate_structured(
                model=MODEL_ID,
                instructions="Return an object.",
                payload={"text": "x" * 14_000},
                schema_name="bounded",
                schema={"type": "object"},
                max_output_tokens=1_000,
            )


class PortableLocalLanguageBackendTests(unittest.TestCase):
    def test_turn_is_understand_then_express_with_zero_authority(self) -> None:
        transport = ScriptedStructuredTransport(
            understanding_payload(),
            {
                "text": "Podemos conversar sobre como as estrelas se formam.",
                "acknowledged_fact_ids": ["candidate-status", "authority-status"],
            },
        )
        backend = PortableLocalLanguageBackend(model=MODEL_ID, transport=transport)
        backend.probe_model()
        settings = ConversationSettings(
            backend=ConversationBackendKind.LOCAL,
            model=MODEL_ID,
            locale="pt-BR",
        )
        runtime = ConversationRuntime.create(settings, local_backend=backend)

        result = runtime.turn("Como as estrelas se formam?")

        self.assertEqual(runtime.snapshot().availability, ConversationAvailability.AVAILABLE)
        self.assertEqual(transport.probes, [(MODEL_ID, REGISTERED_CONTEXT_TOKENS)])
        self.assertEqual(
            [call["payload"]["operation"] for call in transport.calls],
            ["understand", "express"],
        )
        express_payload = transport.calls[1]["payload"]["payload"]
        self.assertEqual(
            express_payload["conversation_request"]["text"],
            "Como as estrelas se formam?",
        )
        self.assertEqual(result.authority_mutations.memory_writes, 0)
        self.assertEqual(result.authority_mutations.goal_changes, 0)
        self.assertEqual(result.authority_mutations.identity_changes, 0)
        self.assertEqual(result.authority_mutations.world_model_changes, 0)
        self.assertEqual(result.authority_mutations.actions_dispatched, 0)
        self.assertEqual(result.authority_mutations.actions_executed, 0)

    def test_explicit_local_mode_never_constructs_openai_backend(self) -> None:
        transport = ScriptedStructuredTransport(
            understanding_payload(),
            {
                "text": "Resposta local nova.",
                "acknowledged_fact_ids": ["candidate-status", "authority-status"],
            },
        )
        backend = PortableLocalLanguageBackend(model=MODEL_ID, transport=transport)
        settings = ConversationSettings(
            backend=ConversationBackendKind.LOCAL,
            model=MODEL_ID,
            locale="pt-BR",
        )

        with patch(
            "darwin_v50.conversation.runtime.OpenAIResponsesBackend",
            side_effect=AssertionError("paid provider fallback attempted"),
        ):
            runtime = ConversationRuntime.create(settings, local_backend=backend)
            result = runtime.turn("Esta chamada deve permanecer local.")

        self.assertEqual(result.expression.text, "Resposta local nova.")

    def test_failed_turn_writes_no_transcript_and_clears_pending_context(self) -> None:
        transport = ScriptedStructuredTransport(
            {**understanding_payload(), "unknown": "rejected"},
        )
        backend = PortableLocalLanguageBackend(model=MODEL_ID, transport=transport)
        runtime = ConversationRuntime.create(
            ConversationSettings(
                backend=ConversationBackendKind.LOCAL,
                model=MODEL_ID,
                locale="pt-BR",
            ),
            local_backend=backend,
        )

        with self.assertRaises(LanguageBackendError):
            runtime.turn("Do not commit this failed turn.")

        self.assertEqual(runtime.temporary_context(), ())
        self.assertEqual(runtime.snapshot().completed_turns, 0)
        with self.assertRaisesRegex(
            LanguageBackendError,
            "express_requires_prior_understand",
        ):
            DarwinLanguageGateway(backend).express(expression_plan())

    def test_express_context_is_one_use_and_clearable(self) -> None:
        transport = ScriptedStructuredTransport(
            understanding_payload(),
            {
                "text": "Resposta.",
                "acknowledged_fact_ids": ["fact-1", "fact-2"],
            },
        )
        backend = PortableLocalLanguageBackend(model=MODEL_ID, transport=transport)
        gateway = DarwinLanguageGateway(backend)
        gateway.understand(UnderstandingRequest("Pergunta"))
        gateway.express(expression_plan())

        with self.assertRaisesRegex(
            LanguageBackendError,
            "express_requires_prior_understand",
        ):
            gateway.express(expression_plan())

        transport = ScriptedStructuredTransport(understanding_payload())
        backend = PortableLocalLanguageBackend(model=MODEL_ID, transport=transport)
        gateway = DarwinLanguageGateway(backend)
        gateway.understand(UnderstandingRequest("Outra pergunta"))
        backend.clear_ephemeral_context()
        with self.assertRaisesRegex(
            LanguageBackendError,
            "express_requires_prior_understand",
        ):
            gateway.express(expression_plan())

    def test_gateway_rejects_authority_and_unknown_fields(self) -> None:
        responses = (
            {**understanding_payload(), "memory": {"write": "forbidden"}},
            {**understanding_payload(), "invented_field": "forbidden"},
        )
        for response in responses:
            with self.subTest(response=response):
                backend = PortableLocalLanguageBackend(
                    model=MODEL_ID,
                    transport=ScriptedStructuredTransport(response),
                )
                gateway = DarwinLanguageGateway(backend)
                expected_error = (
                    LanguageAuthorityError if "memory" in response else LanguageBackendError
                )
                with self.assertRaises(expected_error):
                    gateway.understand(UnderstandingRequest("Teste"))

    def test_consult_is_not_enabled(self) -> None:
        backend = PortableLocalLanguageBackend(
            model=MODEL_ID,
            transport=ScriptedStructuredTransport(),
        )
        with self.assertRaisesRegex(LanguageBackendError, "consult_not_enabled"):
            backend.invoke(
                LanguageModelRequest(
                    contract_version="darwin-language-v1",
                    operation=LanguageOperation.CONSULT,
                    payload={"query": "outside the boundary"},
                )
            )


if __name__ == "__main__":
    unittest.main()
