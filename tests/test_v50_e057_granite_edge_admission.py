from __future__ import annotations

from pathlib import Path
import unittest

from scripts.run_e057_granite_edge_admission import (
    MAX_PEAK_WORKING_SET,
    artifact_identity_failures,
    load_admission_failures,
    parse_benchmark_records,
    performance_admission_failures,
)


def benchmark_records(
    *,
    prompt_samples: list[float] | None = None,
    generation_samples: list[float] | None = None,
) -> list[dict[str, object]]:
    common = {
        "model_type": "granite test",
        "model_size": 700_000_000,
        "model_n_params": 1_000_000_000,
        "build_commit": "34af94cd9",
        "build_number": 10470,
        "cpu_info": "test cpu",
        "backends": "CPU",
    }
    return [
        {
            **common,
            "n_prompt": 256,
            "n_gen": 0,
            "samples_ts": prompt_samples or [30.0, 32.0],
        },
        {
            **common,
            "n_prompt": 0,
            "n_gen": 32,
            "samples_ts": generation_samples or [9.0, 10.0],
        },
    ]


class GraniteAdmissionDecisionTests(unittest.TestCase):
    def test_artifact_identity_is_strictly_conjunctive(self) -> None:
        self.assertEqual(
            artifact_identity_failures(
                observed_bytes=785_585_920,
                observed_sha256="1dc4514416725646ecdd4668759937981a34407f422533cf330fba6709320182",
            ),
            [],
        )
        self.assertEqual(
            artifact_identity_failures(observed_bytes=1, observed_sha256="wrong"),
            ["artifact_byte_count_mismatch", "artifact_sha256_mismatch"],
        )

    def test_load_gate_rejects_timeout_memory_probe_and_listener(self) -> None:
        failures = load_admission_failures(
            ready_milliseconds=60_001.0,
            peak_working_set_bytes=MAX_PEAK_WORKING_SET + 1,
            probe_passed=False,
            server_exit_code=None,
            listener_present_after_stop=True,
            api_key_present_in_logs=True,
        )

        self.assertEqual(len(failures), 6)

    def test_benchmark_parser_requires_exact_registered_samples(self) -> None:
        measured, failures = parse_benchmark_records(benchmark_records())

        self.assertEqual(failures, [])
        assert measured is not None
        self.assertEqual(
            measured["prompt_processing_tokens_per_second_mean"],
            31.0,
        )
        self.assertEqual(
            measured["generation_tokens_per_second_mean"],
            9.5,
        )

        _, invalid = parse_benchmark_records(
            benchmark_records(generation_samples=[9.0])
        )
        self.assertEqual(invalid, ["generation_sample_count_mismatch"])

    def test_performance_gate_does_not_round_into_a_pass(self) -> None:
        measured, parse_failures = parse_benchmark_records(
            benchmark_records(
                prompt_samples=[24.999, 24.999],
                generation_samples=[7.999, 7.999],
            )
        )

        failures = performance_admission_failures(
            exit_code=0,
            peak_working_set_bytes=1_000_000_000,
            measurements=measured,
            parse_failures=parse_failures,
        )

        self.assertEqual(
            failures,
            [
                "prompt_throughput_below_threshold",
                "generation_throughput_below_threshold",
            ],
        )

    def test_runner_has_no_conversation_or_generation_surface(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "scripts/run_e057_granite_edge_admission.py").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("ConversationRuntime", source)
        self.assertNotIn("PortableLocalLanguageBackend", source)
        self.assertNotIn("generate_structured", source)
        self.assertNotIn('"/completion"', source)


if __name__ == "__main__":
    unittest.main()
