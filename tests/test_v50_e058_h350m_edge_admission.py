from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys
import unittest

import scripts.run_e057_granite_edge_admission as harness


class H350MAdmissionProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        harness._activate_profile(harness.E058_PROFILE)

    def tearDown(self) -> None:
        harness._activate_profile(harness.E057_PROFILE)

    def test_profile_freezes_exact_artifact_and_stricter_thresholds(self) -> None:
        profile = harness.E058_PROFILE

        self.assertEqual(profile.port, 18058)
        self.assertEqual(profile.model_bytes, 222_662_560)
        self.assertEqual(
            profile.model_sha256,
            "0a8d6a7373602fadfba274a640ba784b86cc6847f1c67f1b0a90fa2ec266b7fb",
        )
        self.assertEqual(profile.max_peak_working_set, 1_000_000_000)
        self.assertEqual(profile.minimum_prompt_tokens_per_second, 50.0)
        self.assertEqual(profile.minimum_generation_tokens_per_second, 20.0)

    def test_profile_decision_rejects_values_just_below_thresholds(self) -> None:
        measurements = {
            "prompt_processing_tokens_per_second_mean": 49.999999,
            "generation_tokens_per_second_mean": 19.999999,
        }

        failures = harness.performance_admission_failures(
            exit_code=0,
            peak_working_set_bytes=500_000_000,
            measurements=measurements,
            parse_failures=[],
        )

        self.assertEqual(
            failures,
            [
                "prompt_throughput_below_threshold",
                "generation_throughput_below_threshold",
            ],
        )

    def test_launcher_selects_only_the_e058_profile(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "scripts/run_e058_h350m_edge_admission.py").read_text(
            encoding="utf-8"
        )

        self.assertIn('["--experiment", "E058", *sys.argv[1:]]', source)
        self.assertNotIn("ConversationRuntime", source)
        self.assertNotIn("generate_structured", source)

    def test_direct_script_launcher_resolves_sibling_with_src_pythonpath(self) -> None:
        root = Path(__file__).resolve().parents[1]
        environment = dict(os.environ)
        environment["PYTHONPATH"] = "src"

        completed = subprocess.run(
            [
                sys.executable,
                "scripts/run_e058_h350m_edge_admission.py",
                "--help",
            ],
            cwd=root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--repository", completed.stdout)
        self.assertIn("--experiment", completed.stdout)


if __name__ == "__main__":
    unittest.main()
