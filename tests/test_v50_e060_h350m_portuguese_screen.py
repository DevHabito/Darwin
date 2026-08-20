from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
import unittest

from darwin_v50.conversation import (
    AuthorityMutationCounts,
    ConversationBackendKind,
    ConversationRuntime,
    ConversationSettings,
    GraniteControlBoundaryError,
    GraniteSafeTransport,
)
from darwin_v50.language import (
    LANGUAGE_CONTRACT_VERSION,
    LanguageAuthorityError,
    LanguageExpression,
    LanguageMode,
    LanguageModelRequest,
    LanguageObservation,
    LanguageOperation,
)
from scripts.run_e060_h350m_portuguese_screen import (
    build_candidate_backend,
    run_registered_session,
)


SIX_INPUTS = tuple(f"input-{number}" for number in range(1, 7))


def understanding_output(confidence: float = 0.75) -> dict[str, object]:
    return {
        "intent": "open_conversation",
        "entities": [],
        "reported_signals": [],
        "temporal_reference": None,
        "explicit_preference": None,
        "confidence": confidence,
    }


def inference_pair(confidence: float = 0.75) -> list[dict[str, object]]:
    return [
        {
            "schema_name": "darwin_understanding_v1",
            "wall_milliseconds": 10.0,
            "completed": True,
            "output": understanding_output(confidence),
        },
        {
            "schema_name": "darwin_expression_v1",
            "wall_milliseconds": 10.0,
            "completed": True,
            "output": {
                "text": "captured",
                "acknowledged_fact_ids": ["candidate-status", "authority-status"],
            },
        },
    ]


def turn_result(text: str, expression: str) -> object:
    return SimpleNamespace(
        observation=LanguageObservation(
            raw_text=text,
            intent="open_conversation",
            entities=(),
            reported_signals=(),
            temporal_reference=None,
            explicit_preference=None,
            confidence=0.75,
            source_name="fake-local",
            mode=LanguageMode.MODEL,
        ),
        expression=LanguageExpression(
            text=expression,
            acknowledged_fact_ids=("candidate-status", "authority-status"),
            source_name="fake-local",
            mode=LanguageMode.MODEL,
        ),
        authority_mutations=AuthorityMutationCounts(),
    )


class FakeCapture:
    def __init__(self) -> None:
        self.inferences: list[dict[str, object]] = []


class FakeRuntime:
    def __init__(
        self,
        capture: FakeCapture,
        expressions: list[str | BaseException],
        confidences: list[float] | None = None,
    ) -> None:
        self.capture = capture
        self.expressions = list(expressions)
        self.confidences = list(confidences or [0.75] * len(expressions))
        self.calls: list[str] = []

    def turn(self, text: str) -> object:
        self.calls.append(text)
        value = self.expressions.pop(0)
        confidence = self.confidences.pop(0)
        if isinstance(value, BaseException):
            raise value
        self.capture.inferences.extend(inference_pair(confidence))
        return turn_result(text, value)


class InnerTransport:
    def __init__(self) -> None:
        self.generate_calls = 0

    def probe(self, *, model: str, context_tokens: int) -> None:
        return None

    def generate_structured(self, **kwargs: object) -> dict[str, object]:
        self.generate_calls += 1
        return {}


class RuntimeBackend:
    model = "runtime-fake"
    name = "runtime-fake-backend"

    def __init__(self, *, forbidden: bool = False) -> None:
        self.forbidden = forbidden
        self.clear_calls = 0
        self.operations: list[LanguageOperation] = []

    def probe_model(self) -> None:
        return None

    def clear_ephemeral_context(self) -> None:
        self.clear_calls += 1

    def invoke(self, request: LanguageModelRequest) -> dict[str, object]:
        self.operations.append(request.operation)
        if request.operation is LanguageOperation.UNDERSTAND:
            result = understanding_output()
            if self.forbidden:
                result["memory_write"] = "forbidden"
            return result
        return {
            "text": "Uma resposta nova e curta.",
            "acknowledged_fact_ids": ["candidate-status", "authority-status"],
        }


class H350MPortugueseScreenTests(unittest.TestCase):
    def run_fake(
        self,
        expressions: list[str | BaseException],
        *,
        confidences: list[float] | None = None,
    ) -> tuple[dict[str, object], FakeRuntime, list[dict[str, object]]]:
        capture = FakeCapture()
        runtime = FakeRuntime(capture, expressions, confidences)
        record: dict[str, object] = {"turns": []}
        persisted: list[dict[str, object]] = []
        run_registered_session(
            runtime=runtime,
            capture=capture,
            record=record,
            persist=lambda value: persisted.append(deepcopy(dict(value))),
            inputs=SIX_INPUTS,
        )
        return record, runtime, persisted

    def test_candidate_backend_wraps_inner_in_granite_boundary(self) -> None:
        inner = InnerTransport()
        backend = build_candidate_backend(inner)
        self.assertIsInstance(backend._transport, GraniteSafeTransport)
        with self.assertRaises(GraniteControlBoundaryError):
            backend.invoke(
                LanguageModelRequest(
                    contract_version=LANGUAGE_CONTRACT_VERSION,
                    operation=LanguageOperation.UNDERSTAND,
                    payload={
                        "text": "texto <|pad|>",
                        "locale": "pt-BR",
                        "recent_turns": [],
                    },
                )
            )
        self.assertEqual(inner.generate_calls, 0)

    def test_runtime_rejects_forbidden_authority_field(self) -> None:
        backend = RuntimeBackend(forbidden=True)
        runtime = ConversationRuntime.create(
            ConversationSettings(
                backend=ConversationBackendKind.LOCAL,
                model=backend.model,
                locale="pt-BR",
            ),
            local_backend=backend,
        )
        with self.assertRaises(LanguageAuthorityError):
            runtime.turn("teste")
        self.assertEqual(backend.operations, [LanguageOperation.UNDERSTAND])
        self.assertEqual(backend.clear_calls, 1)

    def test_runtime_close_erases_temporary_context(self) -> None:
        backend = RuntimeBackend()
        runtime = ConversationRuntime.create(
            ConversationSettings(
                backend=ConversationBackendKind.LOCAL,
                model=backend.model,
                locale="pt-BR",
            ),
            local_backend=backend,
        )
        result = runtime.turn("teste")
        self.assertEqual(result.authority_mutations, AuthorityMutationCounts())
        self.assertEqual(len(runtime.temporary_context()), 2)
        runtime.close()
        self.assertEqual(runtime.temporary_context(), ())
        self.assertEqual(backend.clear_calls, 1)

    def test_gateway_failure_stops_before_next_input(self) -> None:
        record, runtime, persisted = self.run_fake([RuntimeError("failed")])
        self.assertEqual(runtime.calls, ["input-1"])
        self.assertEqual(record["result"], "model_or_boundary_failure_early_stop")
        self.assertGreaterEqual(len(persisted), 2)

    def test_exact_current_input_echo_stops_immediately(self) -> None:
        record, runtime, _ = self.run_fake(["input-1", "unused"])
        self.assertEqual(runtime.calls, ["input-1"])
        self.assertIn(
            "exact_current_input_echo",
            record["turns"][0]["mechanical_stop_reasons"],
        )

    def test_exact_older_expression_stops_before_third_input(self) -> None:
        record, runtime, _ = self.run_fake(["answer", "answer", "unused"])
        self.assertEqual(runtime.calls, ["input-1", "input-2"])
        self.assertIn(
            "exact_copy_of_older_expression",
            record["turns"][1]["mechanical_stop_reasons"],
        )

    def test_legacy_phrase_stops_without_rewrite_or_retry(self) -> None:
        expression = "Ainda não conheço essa expressão; o que significa?"
        record, runtime, _ = self.run_fake([expression, "unused"])
        self.assertEqual(runtime.calls, ["input-1"])
        self.assertEqual(record["turns"][0]["expression"], expression)
        self.assertIn(
            "legacy_failure_phrase_in_expression",
            record["turns"][0]["mechanical_stop_reasons"],
        )

    def test_unregistered_numeric_level_is_preserved_and_rejected(self) -> None:
        record, runtime, _ = self.run_fake(
            ["answer", "unused"],
            confidences=[0.7, 0.75],
        )
        self.assertEqual(runtime.calls, ["input-1"])
        native = record["turns"][0]["native_inferences"][0]["output"]
        self.assertEqual(native["confidence"], 0.7)
        self.assertIn(
            "confidence_not_registered_level",
            record["turns"][0]["mechanical_stop_reasons"],
        )

    def test_six_clean_pairs_finish_pending_owner_adjudication(self) -> None:
        expressions = [f"answer-{number}" for number in range(1, 7)]
        record, runtime, persisted = self.run_fake(expressions)
        self.assertEqual(runtime.calls, list(SIX_INPUTS))
        self.assertEqual(len(record["turns"]), 6)
        self.assertEqual(
            record["result"],
            "mechanically_complete_owner_adjudication_pending",
        )
        self.assertIsNone(record["owner_adjudication"])
        self.assertGreaterEqual(len(persisted), 8)
        self.assertTrue(
            all(len(turn["native_inferences"]) == 2 for turn in record["turns"])
        )


if __name__ == "__main__":
    unittest.main()
