from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
import unittest

from darwin_v50.conversation import AuthorityMutationCounts
from darwin_v50.language import (
    LanguageExpression,
    LanguageMode,
    LanguageObservation,
)
from scripts.run_e055_gated_local_screen import (
    HumanDecision,
    run_registered_session,
)


EIGHT_INPUTS = tuple(f"input-{number}" for number in range(1, 9))


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
                "text": "captured separately",
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


class FakeTransport:
    def __init__(self) -> None:
        self.inferences: list[dict[str, object]] = []


class FakeRuntime:
    def __init__(
        self,
        transport: FakeTransport,
        expressions: list[str | BaseException],
        confidences: list[float] | None = None,
    ) -> None:
        self.transport = transport
        self.expressions = list(expressions)
        self.confidences = list(confidences or [0.75] * len(expressions))
        self.calls: list[str] = []

    def turn(self, text: str) -> object:
        self.calls.append(text)
        value = self.expressions.pop(0)
        confidence = self.confidences.pop(0)
        if isinstance(value, BaseException):
            raise value
        self.transport.inferences.extend(inference_pair(confidence))
        return turn_result(text, value)


class GatedLocalScreenTests(unittest.TestCase):
    def run_fake(
        self,
        *,
        inputs: tuple[str, ...],
        expressions: list[str | BaseException],
        confidences: list[float] | None = None,
        decisions: list[HumanDecision] | None = None,
    ) -> tuple[dict[str, object], FakeRuntime, list[dict[str, object]]]:
        transport = FakeTransport()
        runtime = FakeRuntime(transport, expressions, confidences)
        record: dict[str, object] = {"turns": []}
        persisted: list[dict[str, object]] = []
        decision_queue = list(
            decisions
            or [HumanDecision(True, None, "attempted") for _ in inputs]
        )

        def adjudicate(number: int, turn: object, required: str | None) -> HumanDecision:
            self.assertTrue(persisted)
            latest_turns = persisted[-1]["turns"]
            self.assertEqual(len(latest_turns), number)
            self.assertNotIn("human_decision", latest_turns[-1])
            decision = decision_queue.pop(0)
            if required is not None and decision.required_criterion_met is None:
                return HumanDecision(
                    decision.requested_act_attempted,
                    True,
                    decision.reason,
                )
            return decision

        run_registered_session(
            runtime=runtime,
            transport=transport,
            record=record,
            adjudicate=adjudicate,
            persist=lambda value: persisted.append(deepcopy(dict(value))),
            inputs=inputs,
        )
        return record, runtime, persisted

    def test_gateway_failure_stops_before_next_input(self) -> None:
        record, runtime, _ = self.run_fake(
            inputs=EIGHT_INPUTS,
            expressions=[RuntimeError("failed")],
        )
        self.assertEqual(runtime.calls, ["input-1"])
        self.assertEqual(record["result"], "failed_closed_early_stop")

    def test_exact_older_expression_copy_stops_before_third_input(self) -> None:
        record, runtime, _ = self.run_fake(
            inputs=EIGHT_INPUTS,
            expressions=["new answer", "new answer", "unused"],
        )
        self.assertEqual(runtime.calls, ["input-1", "input-2"])
        second = record["turns"][1]
        self.assertIn(
            "exact_copy_of_older_expression",
            second["mechanical_stop_reasons"],
        )

    def test_second_exact_current_input_echo_stops_without_retry(self) -> None:
        record, runtime, _ = self.run_fake(
            inputs=EIGHT_INPUTS,
            expressions=["input-1", "input-2", "unused"],
        )
        self.assertEqual(runtime.calls, ["input-1", "input-2"])
        self.assertEqual(len(record["turns"]), 2)
        self.assertIn(
            "more_than_one_exact_current_input_echo",
            record["turns"][1]["mechanical_stop_reasons"],
        )

    def test_unregistered_native_level_is_preserved_and_rejected(self) -> None:
        record, runtime, persisted = self.run_fake(
            inputs=EIGHT_INPUTS,
            expressions=["answer", "unused"],
            confidences=[0.7, 0.75],
        )
        self.assertEqual(runtime.calls, ["input-1"])
        first = record["turns"][0]
        self.assertEqual(
            first["native_inferences"][0]["output"]["confidence"],
            0.7,
        )
        self.assertIn(
            "confidence_not_registered_level",
            first["mechanical_stop_reasons"],
        )
        self.assertGreaterEqual(len(persisted), 3)

    def test_required_human_failure_stops_before_next_input(self) -> None:
        record, runtime, _ = self.run_fake(
            inputs=EIGHT_INPUTS,
            expressions=["a", "b", "c", "unused"],
            decisions=[
                HumanDecision(True, None, "turn one"),
                HumanDecision(True, None, "turn two"),
                HumanDecision(True, False, "criterion failed"),
            ],
        )
        self.assertEqual(runtime.calls, ["input-1", "input-2", "input-3"])
        self.assertEqual(record["result"], "human_quality_failure_early_stop")
        self.assertIn(
            "required_human_criterion_failed",
            record["turns"][2]["human_stop_reasons"],
        )


if __name__ == "__main__":
    unittest.main()
