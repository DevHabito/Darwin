from __future__ import annotations

import unittest
from typing import Any, Mapping

from darwin_v50.language import (
    DarwinLanguageGateway,
    ExpressionPlan,
    GroundedFact,
    KnowledgeQuery,
    KnowledgeStatus,
    LanguageAuthorityError,
    LanguageBackendError,
    LanguageMode,
    LanguageModelRequest,
    LanguageOperation,
    UnderstandingRequest,
)
from darwin_v50.models import ValidationError, canonical_json


class ScriptedBackend:
    def __init__(
        self,
        responses: Mapping[LanguageOperation, Mapping[str, Any]],
        *,
        name: str = "scripted-model",
    ) -> None:
        self.name = name
        self.responses = dict(responses)
        self.requests: list[LanguageModelRequest] = []

    def invoke(self, request: LanguageModelRequest) -> Mapping[str, Any]:
        self.requests.append(request)
        return self.responses[request.operation]


def understanding_response() -> dict[str, Any]:
    return {
        "intent": "share_experience",
        "entities": [{"kind": "activity", "value": "memory_cards"}],
        "reported_signals": [
            {"name": "fatigue", "value": 0.82},
            {"name": "enjoyment", "value": 0.35},
        ],
        "temporal_reference": "yesterday",
        "explicit_preference": None,
        "confidence": 0.87,
    }


def expression_plan() -> ExpressionPlan:
    return ExpressionPlan(
        speech_act="propose_alternative",
        facts=(
            GroundedFact(
                fact_id="decision",
                statement="Do not propose the memory game today.",
            ),
            GroundedFact(
                fact_id="reason",
                statement="The most recent reported outcome was tiring.",
            ),
            GroundedFact(
                fact_id="alternative",
                statement="Offer conversation instead.",
                required=False,
            ),
        ),
        fallback_text=(
            "I would rather talk today because the last memory game was tiring."
        ),
        style_hints=("warm", "concise"),
    )


class DarwinPureLanguageTests(unittest.TestCase):
    def test_pure_understanding_is_explicitly_unclassified(self) -> None:
        gateway = DarwinLanguageGateway()

        observation = gateway.understand(
            UnderstandingRequest(
                text="The game tired me yesterday.",
                locale="en-US",
            )
        )

        self.assertEqual(gateway.mode, LanguageMode.PURE)
        self.assertEqual(observation.raw_text, "The game tired me yesterday.")
        self.assertEqual(observation.intent, "unclassified")
        self.assertEqual(observation.confidence, 0.0)
        self.assertEqual(observation.entities, ())
        self.assertEqual(observation.reported_signals, ())
        self.assertEqual(observation.source_name, "darwin-pure")

    def test_pure_expression_uses_only_core_fallback(self) -> None:
        plan = expression_plan()

        expression = DarwinLanguageGateway().express(plan)

        self.assertEqual(expression.text, plan.fallback_text)
        self.assertEqual(
            expression.acknowledged_fact_ids,
            ("decision", "reason", "alternative"),
        )
        self.assertFalse(expression.semantic_fidelity_verified)

    def test_pure_consultation_reports_explicit_unavailability(self) -> None:
        candidate = DarwinLanguageGateway().consult(
            KnowledgeQuery("What is photosynthesis?")
        )

        self.assertFalse(candidate.available)
        self.assertIsNone(candidate.content)
        self.assertEqual(candidate.status, KnowledgeStatus.UNAVAILABLE)
        self.assertEqual(candidate.reported_confidence, 0.0)


class DarwinModelLanguageTests(unittest.TestCase):
    def test_model_understanding_returns_candidate_observation(self) -> None:
        backend = ScriptedBackend(
            {LanguageOperation.UNDERSTAND: understanding_response()}
        )
        gateway = DarwinLanguageGateway(backend)

        observation = gateway.understand(
            UnderstandingRequest(
                text="That game tired me yesterday.",
                locale="en-US",
                recent_turns=("We played memory cards.",),
            )
        )

        self.assertEqual(gateway.mode, LanguageMode.MODEL)
        self.assertEqual(observation.intent, "share_experience")
        self.assertEqual(observation.entities[0].kind, "activity")
        self.assertEqual(observation.reported_signals[0].name, "fatigue")
        self.assertEqual(observation.reported_signals[0].value, 0.82)
        self.assertEqual(observation.source_name, "scripted-model")
        self.assertEqual(len(backend.requests), 1)
        self.assertEqual(
            backend.requests[0].operation,
            LanguageOperation.UNDERSTAND,
        )

    def test_backend_request_is_detached_and_deeply_immutable(self) -> None:
        class MutationBackend:
            name = "mutation-probe"

            def __init__(self) -> None:
                self.top_level_blocked = False
                self.nested_blocked = False

            def invoke(self, request: LanguageModelRequest) -> Mapping[str, Any]:
                try:
                    request.payload["text"] = "rewritten"  # type: ignore[index]
                except TypeError:
                    self.top_level_blocked = True
                turns = request.payload["recent_turns"]
                try:
                    turns[0] = "rewritten"  # type: ignore[index]
                except TypeError:
                    self.nested_blocked = True
                return understanding_response()

        backend = MutationBackend()
        request = UnderstandingRequest(
            text="Original text",
            recent_turns=("Original turn",),
        )

        observation = DarwinLanguageGateway(backend).understand(request)

        self.assertTrue(backend.top_level_blocked)
        self.assertTrue(backend.nested_blocked)
        self.assertEqual(request.text, "Original text")
        self.assertEqual(request.recent_turns, ("Original turn",))
        self.assertEqual(observation.raw_text, "Original text")

    def test_model_expression_can_change_words_but_not_core_plan(self) -> None:
        plan = expression_plan()
        core_state = {
            "decision": "avoid_memory_game_today",
            "reason": "negative_recent_outcome",
            "alternative": "conversation",
            "preference": 0.31,
            "sigma": 0.44,
        }
        before = canonical_json(core_state)
        backend = ScriptedBackend(
            {
                LanguageOperation.EXPRESS: {
                    "text": (
                        "Let's talk today. The last memory game seemed tiring."
                    ),
                    "acknowledged_fact_ids": ["decision", "reason"],
                }
            }
        )

        pure_expression = DarwinLanguageGateway().express(plan)
        model_expression = DarwinLanguageGateway(backend).express(plan)

        self.assertNotEqual(pure_expression.text, model_expression.text)
        self.assertEqual(before, canonical_json(core_state))
        self.assertEqual(plan, expression_plan())
        self.assertFalse(model_expression.semantic_fidelity_verified)

    def test_model_expression_must_acknowledge_required_core_facts(self) -> None:
        backend = ScriptedBackend(
            {
                LanguageOperation.EXPRESS: {
                    "text": "Let's talk.",
                    "acknowledged_fact_ids": ["decision"],
                }
            }
        )

        with self.assertRaises(LanguageBackendError):
            DarwinLanguageGateway(backend).express(expression_plan())

    def test_model_expression_cannot_acknowledge_invented_core_facts(self) -> None:
        backend = ScriptedBackend(
            {
                LanguageOperation.EXPRESS: {
                    "text": "I formed a new goal.",
                    "acknowledged_fact_ids": ["decision", "reason", "new_goal"],
                }
            }
        )

        with self.assertRaises(LanguageBackendError):
            DarwinLanguageGateway(backend).express(expression_plan())

    def test_consultation_provenance_is_assigned_by_gateway(self) -> None:
        backend = ScriptedBackend(
            {
                LanguageOperation.CONSULT: {
                    "content": "Plants convert light energy into chemical energy.",
                    "reported_confidence": 0.72,
                    "references": ["model-supplied reference; not verified"],
                }
            },
            name="knowledge-model",
        )

        candidate = DarwinLanguageGateway(backend).consult(
            KnowledgeQuery("What is photosynthesis?")
        )

        self.assertTrue(candidate.available)
        self.assertEqual(candidate.source_name, "knowledge-model")
        self.assertEqual(candidate.status, KnowledgeStatus.EXTERNAL_UNVERIFIED)
        self.assertEqual(candidate.reported_confidence, 0.72)

    def test_backend_name_is_frozen_before_invocation(self) -> None:
        class RenamingBackend:
            name = "registered-model"

            def invoke(self, request: LanguageModelRequest) -> Mapping[str, Any]:
                self.name = "Felipe"
                return understanding_response()

        backend = RenamingBackend()
        gateway = DarwinLanguageGateway(backend)

        observation = gateway.understand(UnderstandingRequest("Hello"))

        self.assertEqual(backend.name, "Felipe")
        self.assertEqual(gateway.source_name, "registered-model")
        self.assertEqual(observation.source_name, "registered-model")


class DarwinLanguageBoundaryAdversarialTests(unittest.TestCase):
    def test_forbidden_core_authority_field_fails_closed(self) -> None:
        for forbidden in (
            "memory_update",
            "goal",
            "motivation",
            "sigma",
            "rzs",
        ):
            with self.subTest(forbidden=forbidden):
                response = understanding_response()
                response[forbidden] = {"value": "model-selected"}
                backend = ScriptedBackend(
                    {LanguageOperation.UNDERSTAND: response}
                )
                with self.assertRaises(LanguageAuthorityError):
                    DarwinLanguageGateway(backend).understand(
                        UnderstandingRequest("Hello")
                    )

    def test_nested_forbidden_authority_field_fails_closed(self) -> None:
        response = understanding_response()
        response["entities"] = [
            {"kind": "activity", "value": {"memory_write": "yes"}}
        ]
        backend = ScriptedBackend({LanguageOperation.UNDERSTAND: response})

        with self.assertRaises(LanguageAuthorityError):
            DarwinLanguageGateway(backend).understand(
                UnderstandingRequest("Hello")
            )

    def test_unknown_response_field_fails_closed(self) -> None:
        response = understanding_response()
        response["persuasive_note"] = "Trust this parse."
        backend = ScriptedBackend({LanguageOperation.UNDERSTAND: response})

        with self.assertRaises(LanguageBackendError):
            DarwinLanguageGateway(backend).understand(
                UnderstandingRequest("Hello")
            )

    def test_backend_exception_does_not_silently_fall_back(self) -> None:
        class BrokenBackend:
            name = "broken"

            def invoke(self, request: LanguageModelRequest) -> Mapping[str, Any]:
                raise RuntimeError("network failure")

        with self.assertRaises(LanguageBackendError) as captured:
            DarwinLanguageGateway(BrokenBackend()).understand(
                UnderstandingRequest("Hello")
            )

        self.assertIn("backend invocation failed", str(captured.exception))

    def test_model_cannot_choose_its_own_knowledge_source(self) -> None:
        backend = ScriptedBackend(
            {
                LanguageOperation.CONSULT: {
                    "content": "An answer",
                    "reported_confidence": 0.9,
                    "references": [],
                    "source_name": "Felipe",
                }
            }
        )

        with self.assertRaises(LanguageBackendError):
            DarwinLanguageGateway(backend).consult(KnowledgeQuery("Question"))

    def test_mutable_sequences_are_rejected_by_schema(self) -> None:
        with self.assertRaises(ValidationError):
            UnderstandingRequest(
                text="Hello",
                recent_turns=["mutable"]  # type: ignore[arg-type]
            )

    def test_non_text_backend_name_is_rejected(self) -> None:
        class InvalidBackend:
            name = 42

            def invoke(self, request: LanguageModelRequest) -> Mapping[str, Any]:
                return understanding_response()

        with self.assertRaises(ValidationError):
            DarwinLanguageGateway(InvalidBackend())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
