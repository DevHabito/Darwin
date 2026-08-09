from __future__ import annotations

from copy import deepcopy
import json
import unittest
from typing import Any, Mapping

from darwin_v50.conversation import (
    ConversationAvailability,
    ConversationBackendKind,
    ConversationRuntime,
    ConversationSettings,
    OpenAIResponsesBackend,
)
from darwin_v50.language import (
    DarwinLanguageGateway,
    ExpressionPlan,
    GroundedFact,
    LanguageBackendError,
    LanguageModelRequest,
    LanguageOperation,
    UnderstandingRequest,
)


def completed_output(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(payload, ensure_ascii=False),
                    }
                ],
            }
        ],
    }


def understanding_payload() -> dict[str, Any]:
    return {
        "intent": "ask_question",
        "entities": [{"kind": "topic", "value": "estrelas"}],
        "reported_signals": [],
        "temporal_reference": None,
        "explicit_preference": None,
        "confidence": 0.75,
    }


class CapturingTransport:
    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def request_json(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: Mapping[str, object] | None,
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "body": deepcopy(body),
                "timeout_seconds": timeout_seconds,
            }
        )
        if not self.responses:
            raise AssertionError("unexpected transport call")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        if not isinstance(response, Mapping):
            raise AssertionError("scripted response must be a mapping")
        return response


def expression_plan() -> ExpressionPlan:
    return ExpressionPlan(
        speech_act="answer",
        facts=(GroundedFact("fact-1", "No persistent state changed."),),
        fallback_text="Backend unavailable.",
    )


class OpenAIResponsesBackendTests(unittest.TestCase):
    def test_probe_uses_exact_configured_model(self) -> None:
        transport = CapturingTransport(
            {"object": "model", "id": "account/model:revision"}
        )
        backend = OpenAIResponsesBackend(
            model="account/model:revision",
            api_key="test-secret",
            transport=transport,
        )

        backend.probe_model()

        call = transport.calls[0]
        self.assertEqual(call["method"], "GET")
        self.assertTrue(call["url"].endswith("/models/account%2Fmodel%3Arevision"))
        self.assertIsNone(call["body"])

    def test_understand_and_express_use_responses_store_false(self) -> None:
        transport = CapturingTransport(
            completed_output(understanding_payload()),
            completed_output(
                {
                    "text": "As estrelas nascem em nuvens moleculares.",
                    "acknowledged_fact_ids": ["fact-1"],
                }
            ),
        )
        backend = OpenAIResponsesBackend(
            model="configured-model",
            api_key="test-secret",
            transport=transport,
        )
        gateway = DarwinLanguageGateway(backend)

        gateway.understand(
            UnderstandingRequest(
                "Como nascem as estrelas?",
                locale="pt-BR",
                recent_turns=("user:\nFalávamos sobre o céu.",),
            )
        )
        expression = gateway.express(expression_plan())

        self.assertEqual(expression.text, "As estrelas nascem em nuvens moleculares.")
        self.assertEqual(len(transport.calls), 2)
        for call in transport.calls:
            body = call["body"]
            self.assertEqual(call["method"], "POST")
            self.assertTrue(call["url"].endswith("/responses"))
            self.assertEqual(body["model"], "configured-model")
            self.assertIs(body["store"], False)
            self.assertNotIn("previous_response_id", body)
            self.assertNotIn("tools", body)
            self.assertNotIn("tool_choice", body)
            self.assertEqual(body["text"]["format"]["type"], "json_schema")
            self.assertIs(body["text"]["format"]["strict"], True)

        understand_input = json.loads(
            transport.calls[0]["body"]["input"][0]["content"][0]["text"]
        )
        express_input = json.loads(
            transport.calls[1]["body"]["input"][0]["content"][0]["text"]
        )
        self.assertEqual(understand_input["operation"], "understand")
        self.assertEqual(express_input["operation"], "express")
        self.assertEqual(
            express_input["payload"]["conversation_request"]["text"],
            "Como nascem as estrelas?",
        )

    def test_express_requires_immediately_prior_understanding(self) -> None:
        backend = OpenAIResponsesBackend(
            model="configured-model",
            api_key="test-secret",
            transport=CapturingTransport(),
        )
        gateway = DarwinLanguageGateway(backend)

        with self.assertRaisesRegex(
            LanguageBackendError,
            "express_requires_prior_understand",
        ):
            gateway.express(expression_plan())

    def test_pending_context_is_one_use_only(self) -> None:
        transport = CapturingTransport(
            completed_output(understanding_payload()),
            completed_output(
                {"text": "Resposta.", "acknowledged_fact_ids": ["fact-1"]}
            ),
        )
        gateway = DarwinLanguageGateway(
            OpenAIResponsesBackend(
                model="configured-model",
                api_key="test-secret",
                transport=transport,
            )
        )
        gateway.understand(UnderstandingRequest("Pergunta"))
        gateway.express(expression_plan())

        with self.assertRaisesRegex(
            LanguageBackendError,
            "express_requires_prior_understand",
        ):
            gateway.express(expression_plan())

    def test_refusal_incomplete_and_malformed_outputs_fail_closed(self) -> None:
        cases = (
            {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "refusal", "refusal": "no"}],
                    }
                ],
            },
            {"status": "incomplete", "output": []},
            {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "not json"}],
                    }
                ],
            },
        )
        for response in cases:
            with self.subTest(response=response):
                backend = OpenAIResponsesBackend(
                    model="configured-model",
                    api_key="test-secret",
                    transport=CapturingTransport(response),
                )
                with self.assertRaises(LanguageBackendError):
                    backend.invoke(
                        LanguageModelRequest(
                            contract_version="darwin-language-v1",
                            operation=LanguageOperation.UNDERSTAND,
                            payload={"text": "Olá", "locale": "pt-BR", "recent_turns": []},
                        )
                    )

    def test_openai_probe_failure_does_not_select_supplied_local_backend(self) -> None:
        class LocalTrap:
            name = "must-not-be-used"
            model = "configured-model"

            def __init__(self) -> None:
                self.calls = 0

            def invoke(self, request: LanguageModelRequest) -> Mapping[str, Any]:
                self.calls += 1
                raise AssertionError("silent local fallback occurred")

            def clear_ephemeral_context(self) -> None:
                pass

        local = LocalTrap()
        runtime = ConversationRuntime.create(
            ConversationSettings(
                backend=ConversationBackendKind.OPENAI,
                model="configured-model",
                api_key="test-secret",
            ),
            openai_transport=CapturingTransport(
                LanguageBackendError("model_unavailable")
            ),
            local_backend=local,
        )

        self.assertEqual(runtime.snapshot().availability, ConversationAvailability.UNAVAILABLE)
        self.assertEqual(runtime.snapshot().unavailable_reason, "openai_model_probe_failed")
        self.assertEqual(local.calls, 0)


if __name__ == "__main__":
    unittest.main()
