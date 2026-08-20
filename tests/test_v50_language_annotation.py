from __future__ import annotations

from dataclasses import replace
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from darwin_v50.language import (
    LANGUAGE_CALIBRATION_CANDIDATES_V1,
    LANGUAGE_SIGNAL_NAMES_V1,
    AnnotatedSignal,
    AnnotationCandidate,
    AnnotationCandidateSet,
    AnnotationStatus,
    LanguageAnnotation,
    LanguageCorpusFamily,
    ObservedEntity,
    SignalIntensity,
    build_blind_annotation_packet,
    load_annotation_candidates,
    load_language_annotations,
    measure_annotation_agreement,
    require_balanced_calibration_candidates,
    require_disjoint_from_development,
    validate_annotation_panel,
)
from darwin_v50.language.annotation import annotation_candidate_digest
from darwin_v50.language.corpus import load_language_corpus
from darwin_v50.models import ValidationError
from darwin_v50.language_annotation_evaluation import main


ROOT = Path(__file__).resolve().parents[1]
CANDIDATES_PATH = (
    ROOT
    / "docs"
    / "v50"
    / "corpora"
    / "LANGUAGE_CALIBRATION_CANDIDATES_V1.jsonl"
)
DEVELOPMENT_PATH = (
    ROOT
    / "docs"
    / "v50"
    / "corpora"
    / "LANGUAGE_CORPUS_V1_DEVELOPMENT.jsonl"
)
CANDIDATE_DIGEST = (
    "e12cb042164203cbb2eee33b4dce9b5298bd39257d5cd2f6d3c0c8e651b3cf27"
)


def _signal_vector(
    **overrides: SignalIntensity,
) -> tuple[AnnotatedSignal, ...]:
    return tuple(
        AnnotatedSignal(
            name,
            overrides.get(name, SignalIntensity.NONE),
        )
        for name in sorted(LANGUAGE_SIGNAL_NAMES_V1)
    )


def _small_candidate_set() -> AnnotationCandidateSet:
    cases = (
        AnnotationCandidate(
            case_id="case-1",
            version=LANGUAGE_CALIBRATION_CANDIDATES_V1,
            family=LanguageCorpusFamily.SIMPLE_INTENT,
            locale="pt-BR",
            text="Olá.",
            recent_turns=(),
        ),
        AnnotationCandidate(
            case_id="case-2",
            version=LANGUAGE_CALIBRATION_CANDIDATES_V1,
            family=LanguageCorpusFamily.AMBIGUITY,
            locale="pt-BR",
            text="Pode ser.",
            recent_turns=("Quer que eu continue?",),
        ),
    )
    return AnnotationCandidateSet(
        version=LANGUAGE_CALIBRATION_CANDIDATES_V1,
        cases=cases,
        digest=annotation_candidate_digest(cases),
    )


def _annotation(
    candidates: AnnotationCandidateSet,
    annotator_id: str,
    case_id: str,
) -> LanguageAnnotation:
    if case_id == "case-1":
        return LanguageAnnotation(
            candidate_digest=candidates.digest,
            case_id=case_id,
            annotator_id=annotator_id,
            intent_labels=("greet",),
            entities=(),
            signals=_signal_vector(energy=SignalIntensity.LOW),
            temporal_reference=None,
            explicit_preference=None,
            should_abstain=False,
            annotation_status=AnnotationStatus.CLEAR,
        )
    return LanguageAnnotation(
        candidate_digest=candidates.digest,
        case_id=case_id,
        annotator_id=annotator_id,
        intent_labels=("ambiguous_acceptance", "continue_activity"),
        entities=(ObservedEntity("activity", "prior activity"),),
        signals=_signal_vector(current_willingness=SignalIntensity.MODERATE),
        temporal_reference=None,
        explicit_preference=None,
        should_abstain=True,
        annotation_status=AnnotationStatus.AMBIGUOUS,
    )


class CalibrationCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.candidates = load_annotation_candidates(CANDIDATES_PATH)

    def test_reference_candidates_are_balanced_fresh_and_digest_frozen(self) -> None:
        require_balanced_calibration_candidates(self.candidates)
        require_disjoint_from_development(
            self.candidates,
            load_language_corpus(DEVELOPMENT_PATH),
        )

        self.assertEqual(len(self.candidates.cases), 150)
        self.assertEqual(
            self.candidates.family_counts,
            {family.value: 30 for family in LanguageCorpusFamily},
        )
        self.assertEqual(self.candidates.digest, CANDIDATE_DIGEST)

    def test_source_contains_no_labels_or_annotation_status(self) -> None:
        rows = [
            json.loads(line)
            for line in CANDIDATES_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        forbidden = {
            "intents",
            "entities",
            "signals",
            "temporal",
            "preference",
            "abstain",
            "status",
            "annotator_id",
        }

        self.assertTrue(all(not (set(row) & forbidden) for row in rows))

    def test_candidate_surface_spans_are_unique_and_absent_from_development(self) -> None:
        candidate_spans = [
            span
            for case in self.candidates.cases
            for span in (case.text, *case.recent_turns)
        ]
        development = load_language_corpus(DEVELOPMENT_PATH)
        development_spans = {
            span
            for case in development.cases
            for span in (case.text, *case.recent_turns)
        }

        self.assertEqual(len(candidate_spans), len(set(candidate_spans)))
        self.assertFalse(set(candidate_spans) & development_spans)

    def test_blind_packet_hides_family_version_and_all_labels(self) -> None:
        packet = build_blind_annotation_packet(
            self.candidates,
            packet_id="reviewer-a",
            seed=4101,
        )
        rows = [json.loads(line) for line in packet.jsonl().splitlines()]

        self.assertEqual(len(rows), 150)
        self.assertEqual({row["candidate_digest"] for row in rows}, {CANDIDATE_DIGEST})
        for row in rows:
            self.assertEqual(
                set(row),
                {
                    "schema",
                    "packet_id",
                    "candidate_digest",
                    "id",
                    "locale",
                    "text",
                    "context",
                },
            )

    def test_blind_packet_order_is_seeded_and_reproducible(self) -> None:
        first = build_blind_annotation_packet(
            self.candidates, packet_id="a", seed=1
        )
        repeat = build_blind_annotation_packet(
            self.candidates, packet_id="a", seed=1
        )
        other = build_blind_annotation_packet(
            self.candidates, packet_id="b", seed=2
        )

        self.assertEqual(first.jsonl(), repeat.jsonl())
        self.assertNotEqual(
            [case.case_id for case in first.cases],
            [case.case_id for case in other.cases],
        )

    def test_candidate_loader_rejects_unknown_and_duplicate_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            unknown = Path(directory) / "unknown.jsonl"
            unknown.write_text(
                '{"id":"x","version":"darwin-language-calibration-candidates-v1",'
                '"family":"simple_intent","locale":"pt-BR","text":"oi",'
                '"context":[],"label":"greet"}\n',
                encoding="utf-8",
            )
            duplicate = Path(directory) / "duplicate.jsonl"
            duplicate.write_text(
                '{"id":"x","id":"y"}\n',
                encoding="utf-8",
            )

            with self.assertRaises(ValidationError):
                load_annotation_candidates(unknown)
            with self.assertRaises(ValidationError):
                load_annotation_candidates(duplicate)


class AnnotationContractTests(unittest.TestCase):
    def test_signal_scale_is_categorical_with_declared_anchors(self) -> None:
        self.assertEqual(
            [level.normalized_value for level in SignalIntensity],
            [0.0, 0.25, 0.5, 0.75, 1.0],
        )
        self.assertEqual(
            SignalIntensity.from_label("very_high"),
            SignalIntensity.VERY_HIGH,
        )
        with self.assertRaises(ValidationError):
            SignalIntensity.from_label("0.83")

    def test_annotation_round_trip_preserves_multiple_intents_and_status(self) -> None:
        candidates = _small_candidate_set()
        annotation = _annotation(candidates, "reviewer-a", "case-2")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "annotations.jsonl"
            path.write_text(
                json.dumps(annotation.to_dict(), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            loaded = load_language_annotations(path)

        self.assertEqual(loaded, (annotation,))
        self.assertEqual(len(loaded[0].intent_labels), 2)
        self.assertEqual(loaded[0].annotation_status, AnnotationStatus.AMBIGUOUS)

    def test_annotation_loader_rejects_continuous_signal_values(self) -> None:
        annotation = _annotation(_small_candidate_set(), "a", "case-1").to_dict()
        annotation["signals"] = [["energy", 0.83]]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "annotations.jsonl"
            path.write_text(json.dumps(annotation), encoding="utf-8")

            with self.assertRaises(ValidationError):
                load_language_annotations(path)

    def test_annotation_contract_rejects_open_vocabulary_and_missing_signals(self) -> None:
        annotation = _annotation(_small_candidate_set(), "a", "case-1")

        with self.assertRaises(ValidationError):
            replace(annotation, intent_labels=("invented_intent",))
        with self.assertRaises(ValidationError):
            replace(annotation, entities=(ObservedEntity("invented_kind", "x"),))
        with self.assertRaises(ValidationError):
            replace(annotation, signals=annotation.signals[:-1])


class AnnotationPanelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.candidates = _small_candidate_set()
        self.records = tuple(
            _annotation(self.candidates, annotator, case_id)
            for annotator in ("reviewer-a", "reviewer-b")
            for case_id in ("case-1", "case-2")
        )

    def test_panel_requires_two_complete_independent_annotator_ids(self) -> None:
        with self.assertRaises(ValidationError):
            validate_annotation_panel(self.candidates, self.records[:2])
        with self.assertRaises(ValidationError):
            validate_annotation_panel(self.candidates, self.records[:-1])
        with self.assertRaises(ValidationError):
            validate_annotation_panel(
                self.candidates,
                self.records + (self.records[0],),
            )

    def test_panel_rejects_wrong_candidate_digest_and_unknown_case(self) -> None:
        wrong_digest = replace(self.records[0], candidate_digest="0" * 64)
        unknown_case = replace(self.records[0], case_id="unknown")
        with self.assertRaises(ValidationError):
            validate_annotation_panel(
                self.candidates,
                (wrong_digest,) + self.records[1:],
            )
        with self.assertRaises(ValidationError):
            validate_annotation_panel(
                self.candidates,
                (unknown_case,) + self.records[1:],
            )

    def test_perfect_pairwise_report_has_no_promotion_claim(self) -> None:
        panel = validate_annotation_panel(self.candidates, self.records)
        report = measure_annotation_agreement(panel)

        self.assertEqual(report.cases, 2)
        self.assertEqual(report.disagreement_case_ids, ())
        self.assertTrue(
            all(
                value == 1.0
                for value in report.aggregate_pairwise_means.values()
                if value is not None
            )
        )
        self.assertFalse(report.declares_pass)
        self.assertFalse(report.calibration_corpus_promoted)

    def test_disagreements_remain_visible_per_field_and_case(self) -> None:
        changed = replace(
            self.records[-1],
            intent_labels=("decline_activity",),
            signals=_signal_vector(),
            annotation_status=AnnotationStatus.UNDERSPECIFIED,
        )
        panel = validate_annotation_panel(
            self.candidates,
            self.records[:-1] + (changed,),
        )
        report = measure_annotation_agreement(panel)

        self.assertEqual(report.disagreement_case_ids, ("case-2",))
        self.assertLess(
            report.aggregate_pairwise_means["intent_mean_jaccard"] or 1.0,
            1.0,
        )
        self.assertLess(
            report.aggregate_pairwise_means["status_exact_agreement"] or 1.0,
            1.0,
        )
        self.assertIn(
            "signal_intensity_quadratic_weighted_kappa",
            report.aggregate_pairwise_means,
        )

    def test_three_annotators_produce_all_pairwise_comparisons(self) -> None:
        third = tuple(
            _annotation(self.candidates, "reviewer-c", case_id)
            for case_id in ("case-1", "case-2")
        )
        panel = validate_annotation_panel(
            self.candidates,
            self.records + third,
        )
        report = measure_annotation_agreement(panel)

        self.assertEqual(len(report.pairwise), 3)
        self.assertEqual(report.annotators, ("reviewer-a", "reviewer-b", "reviewer-c"))


class AnnotationCommandTests(unittest.TestCase):
    def test_packet_command_emits_only_blind_rows(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            result = main(
                [
                    "packet",
                    str(CANDIDATES_PATH),
                    "--packet-id",
                    "reviewer-a",
                    "--seed",
                    "4101",
                ]
            )

        rows = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual(result, 0)
        self.assertEqual(len(rows), 150)
        self.assertTrue(all("family" not in row for row in rows))

    def test_agreement_command_emits_non_promoting_report(self) -> None:
        candidates = load_annotation_candidates(CANDIDATES_PATH)
        records = tuple(
            LanguageAnnotation(
                candidate_digest=candidates.digest,
                case_id=case.case_id,
                annotator_id=annotator,
                intent_labels=("request_information",),
                entities=(),
                signals=_signal_vector(),
                temporal_reference=None,
                explicit_preference=None,
                should_abstain=False,
                annotation_status=AnnotationStatus.CLEAR,
            )
            for annotator in ("reviewer-a", "reviewer-b")
            for case in candidates.cases
        )
        with tempfile.TemporaryDirectory() as directory:
            annotation_path = Path(directory) / "annotations.jsonl"
            annotation_path.write_text(
                "\n".join(
                    json.dumps(record.to_dict(), ensure_ascii=False)
                    for record in records
                )
                + "\n",
                encoding="utf-8",
            )
            stdout = StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "agreement",
                        str(CANDIDATES_PATH),
                        str(annotation_path),
                    ]
                )

        report = json.loads(stdout.getvalue())
        self.assertEqual(result, 0)
        self.assertFalse(report["declares_pass"])
        self.assertFalse(report["calibration_corpus_promoted"])


if __name__ == "__main__":
    unittest.main()
