from __future__ import annotations

from dataclasses import replace
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from typing import Any, Mapping

from darwin_v50.language import (
    DarwinLanguageGateway,
    LanguageCorpus,
    LanguageCorpusFamily,
    LanguageModelRequest,
    compare_language_reports,
    evaluate_language_gateway,
    load_language_corpus,
    require_balanced_v1_development_corpus,
)
from darwin_v50.language.conformance import main
from darwin_v50.language.corpus import language_corpus_digest
from darwin_v50.models import ValidationError, canonical_json


REFERENCE_CORPUS = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "v50"
    / "corpora"
    / "LANGUAGE_CORPUS_V1_DEVELOPMENT.jsonl"
)
REFERENCE_DIGEST = (
    "12435ce8746f540e55f9a43d8636c5be6910c214c4c573d611a90c5ed2ad2fdb"
)
PURE_BASELINE_RESULT = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "v50"
    / "results"
    / "LANGUAGE_CONFORMANCE_V1_PURE_BASELINE.json"
)


class LabelOracleBackend:
    """Evaluator-only sensitivity ceiling; it is not a usable model backend."""

    name = "label-oracle-test-double"

    def __init__(self, corpus: LanguageCorpus) -> None:
        self._cases = {
            (case.text, case.recent_turns): case for case in corpus.cases
        }

    def invoke(self, request: LanguageModelRequest) -> Mapping[str, Any]:
        text = str(request.payload["text"])
        recent_turns = tuple(str(turn) for turn in request.payload["recent_turns"])
        case = self._cases[(text, recent_turns)]
        return {
            "intent": case.expected.accepted_intents[0],
            "entities": [
                {"kind": entity.kind, "value": entity.value}
                for entity in case.expected.entities
            ],
            "reported_signals": [
                {"name": signal.name, "value": signal.value}
                for signal in case.expected.signals
            ],
            "temporal_reference": case.expected.temporal_reference,
            "explicit_preference": case.expected.explicit_preference,
            "confidence": 0.35 if case.expected.should_abstain else 0.95,
        }


class AuthorityViolatingBackend(LabelOracleBackend):
    name = "authority-violating-test-double"

    def invoke(self, request: LanguageModelRequest) -> Mapping[str, Any]:
        response = dict(super().invoke(request))
        text = str(request.payload["text"])
        recent_turns = tuple(str(turn) for turn in request.payload["recent_turns"])
        if self._cases[(text, recent_turns)].family is LanguageCorpusFamily.BOUNDARY_ATTACK:
            response["sigma"] = 10
        return response


class WrongIntentBackend:
    name = "wrong-intent-test-double"

    def invoke(self, request: LanguageModelRequest) -> Mapping[str, Any]:
        return {
            "intent": "request_conversation",
            "entities": [],
            "reported_signals": [],
            "temporal_reference": None,
            "explicit_preference": None,
            "confidence": 0.99,
        }


class BrokenBackend:
    name = "broken-test-double"

    def invoke(self, request: LanguageModelRequest) -> Mapping[str, Any]:
        raise RuntimeError("deliberate test failure")


class LanguageCorpusV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.corpus = load_language_corpus(REFERENCE_CORPUS)

    def test_reference_corpus_is_balanced_unique_and_digest_frozen(self) -> None:
        require_balanced_v1_development_corpus(self.corpus)

        self.assertEqual(len(self.corpus.cases), 100)
        self.assertEqual(
            self.corpus.family_counts,
            {family.value: 20 for family in LanguageCorpusFamily},
        )
        self.assertEqual(self.corpus.digest, REFERENCE_DIGEST)

    def test_corpus_keeps_context_and_current_report_separate(self) -> None:
        contradiction = next(
            case for case in self.corpus.cases if case.case_id == "LCV1-CT-001"
        )

        self.assertEqual(contradiction.recent_turns, ("Eu adoro música clássica.",))
        self.assertEqual(
            contradiction.expected.explicit_preference,
            "dislikes classical music",
        )
        self.assertNotIn("resolve", contradiction.expected.accepted_intents[0])

    def test_boundary_cases_label_requests_without_core_update_fields(self) -> None:
        boundary_cases = [
            case
            for case in self.corpus.cases
            if case.family is LanguageCorpusFamily.BOUNDARY_ATTACK
        ]

        self.assertEqual(len(boundary_cases), 20)
        self.assertTrue(
            all(
                "request_" in case.expected.accepted_intents[0]
                or "assert_" in case.expected.accepted_intents[0]
                for case in boundary_cases
            )
        )

    def test_loader_rejects_duplicate_json_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.jsonl"
            path.write_text(
                '{"id":"one","id":"two"}\n',
                encoding="utf-8",
            )

            with self.assertRaises(ValidationError):
                load_language_corpus(path)

    def test_loader_rejects_unknown_fields(self) -> None:
        first = self.corpus.cases[0].to_dict()
        first["unexpected"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unknown.jsonl"
            import json

            path.write_text(json.dumps(first, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(ValidationError):
                load_language_corpus(path)

    def test_reference_balance_check_rejects_a_small_subset(self) -> None:
        cases = (self.corpus.cases[0],)
        subset = LanguageCorpus(
            version=self.corpus.version,
            cases=cases,
            digest=language_corpus_digest(cases),
        )

        with self.assertRaises(ValidationError):
            require_balanced_v1_development_corpus(subset)


class LanguageConformanceEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.corpus = load_language_corpus(REFERENCE_CORPUS)

    def test_pure_baseline_is_safe_but_has_no_language_skill(self) -> None:
        report = evaluate_language_gateway(DarwinLanguageGateway(), self.corpus)

        self.assertEqual(report.cases, 100)
        self.assertEqual(report.accepted_cases, 100)
        self.assertEqual(report.authority_violations, 0)
        self.assertEqual(report.authority_violation_rate, 0.0)
        self.assertEqual(report.backend_errors, 0)
        self.assertEqual(report.backend_error_rate, 0.0)
        self.assertEqual(report.contract_success_rate, 1.0)
        self.assertEqual(report.boundary_contract_success_rate, 1.0)
        self.assertEqual(report.boundary_authority_violation_rate, 0.0)
        self.assertEqual(report.intent_accuracy, 0.0)
        self.assertEqual(report.entity_f1, 0.0)
        self.assertEqual(report.signal_f1, 0.0)
        self.assertEqual(report.exact_structure_accuracy, 0.0)
        self.assertEqual(report.temporal_recall, 0.0)
        self.assertEqual(report.preference_recall, 0.0)
        self.assertEqual(report.abstention_accuracy, 0.2)
        self.assertEqual(report.confidence_brier, 0.0)
        self.assertEqual(report.confidence_ece, 0.0)
        self.assertFalse(report.semantic_fidelity_tested)
        self.assertFalse(report.core_state_equivalence_tested)
        self.assertEqual(report.evidence_level, "development-only")

    def test_checked_in_pure_baseline_matches_the_evaluator_exactly(self) -> None:
        report = evaluate_language_gateway(DarwinLanguageGateway(), self.corpus)

        self.assertEqual(
            PURE_BASELINE_RESULT.read_text(encoding="utf-8").strip(),
            canonical_json(report.to_dict()),
        )

    def test_label_oracle_establishes_metric_sensitivity_only(self) -> None:
        report = evaluate_language_gateway(
            DarwinLanguageGateway(LabelOracleBackend(self.corpus)),
            self.corpus,
        )

        self.assertEqual(report.contract_success_rate, 1.0)
        self.assertEqual(report.intent_accuracy, 1.0)
        self.assertEqual(report.entity_f1, 1.0)
        self.assertEqual(report.signal_f1, 1.0)
        self.assertEqual(report.signal_intensity_mae, 0.0)
        self.assertEqual(report.temporal_accuracy, 1.0)
        self.assertEqual(report.temporal_recall, 1.0)
        self.assertEqual(report.temporal_false_positive_rate, 0.0)
        self.assertEqual(report.preference_accuracy, 1.0)
        self.assertEqual(report.preference_recall, 1.0)
        self.assertEqual(report.preference_false_positive_rate, 0.0)
        self.assertEqual(report.abstention_accuracy, 1.0)
        self.assertEqual(report.exact_structure_accuracy, 1.0)
        self.assertAlmostEqual(report.confidence_brier or 0.0, 0.0865)
        self.assertAlmostEqual(report.confidence_ece or 0.0, 0.17)

    def test_wrong_backend_is_detected_without_contract_failure(self) -> None:
        report = evaluate_language_gateway(
            DarwinLanguageGateway(WrongIntentBackend()),
            self.corpus,
        )

        self.assertEqual(report.contract_success_rate, 1.0)
        self.assertLess(report.intent_accuracy, 0.1)
        self.assertEqual(report.entity_recall, 0.0)
        self.assertEqual(report.signal_recall, 0.0)
        self.assertLess(report.exact_structure_accuracy, 0.1)
        self.assertGreater(report.confidence_brier or 0.0, 0.9)

    def test_authority_violations_are_separate_from_language_accuracy(self) -> None:
        report = evaluate_language_gateway(
            DarwinLanguageGateway(AuthorityViolatingBackend(self.corpus)),
            self.corpus,
        )

        self.assertEqual(report.authority_violations, 20)
        self.assertEqual(report.authority_violation_rate, 0.2)
        self.assertEqual(report.backend_errors, 0)
        self.assertEqual(report.contract_success_rate, 0.8)
        self.assertEqual(report.boundary_contract_success_rate, 0.0)
        self.assertEqual(report.boundary_authority_violation_rate, 1.0)
        self.assertEqual(report.intent_accuracy, 0.8)

    def test_backend_failures_are_not_counted_as_authority_violations(self) -> None:
        report = evaluate_language_gateway(
            DarwinLanguageGateway(BrokenBackend()),
            self.corpus,
        )

        self.assertEqual(report.accepted_cases, 0)
        self.assertEqual(report.backend_errors, 100)
        self.assertEqual(report.backend_error_rate, 1.0)
        self.assertEqual(report.authority_violations, 0)
        self.assertIsNone(report.confidence_brier)
        self.assertIsNone(report.confidence_ece)

    def test_comparison_has_deltas_but_never_declares_a_winner(self) -> None:
        pure = evaluate_language_gateway(DarwinLanguageGateway(), self.corpus)
        oracle = evaluate_language_gateway(
            DarwinLanguageGateway(LabelOracleBackend(self.corpus)),
            self.corpus,
        )

        comparison = compare_language_reports(pure, oracle)
        by_name = {metric.metric: metric for metric in comparison.metrics}

        self.assertEqual(by_name["intent_accuracy"].delta, 1.0)
        self.assertEqual(by_name["boundary_authority_violation_rate"].delta, 0.0)
        self.assertFalse(comparison.safety_regressed)
        self.assertFalse(comparison.declares_winner)

    def test_comparison_detects_security_regression(self) -> None:
        pure = evaluate_language_gateway(DarwinLanguageGateway(), self.corpus)
        violating = evaluate_language_gateway(
            DarwinLanguageGateway(AuthorityViolatingBackend(self.corpus)),
            self.corpus,
        )

        comparison = compare_language_reports(pure, violating)

        self.assertTrue(comparison.safety_regressed)
        self.assertFalse(comparison.declares_winner)

    def test_comparison_rejects_a_different_corpus_digest(self) -> None:
        report = evaluate_language_gateway(DarwinLanguageGateway(), self.corpus)

        with self.assertRaises(ValidationError):
            compare_language_reports(
                report,
                replace(report, corpus_digest="0" * 64),
            )

    def test_invalid_metric_configuration_fails_closed(self) -> None:
        with self.assertRaises(ValidationError):
            evaluate_language_gateway(
                DarwinLanguageGateway(),
                self.corpus,
                calibration_bins=1,
            )
        with self.assertRaises(ValidationError):
            evaluate_language_gateway(
                DarwinLanguageGateway(),
                self.corpus,
                abstention_threshold=1.0,
            )

    def test_cli_emits_strict_json_for_the_pure_baseline(self) -> None:
        output = StringIO()

        with redirect_stdout(output):
            exit_code = main([str(REFERENCE_CORPUS)])

        self.assertEqual(exit_code, 0)
        self.assertIn('"source_name":"darwin-pure"', output.getvalue())
        self.assertIn('"cases":100', output.getvalue())


if __name__ == "__main__":
    unittest.main()
