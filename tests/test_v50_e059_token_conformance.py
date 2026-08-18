from __future__ import annotations

import unittest

from darwin_v50.conversation import GRANITE_CONTROL_TOKEN_IDS
from scripts.run_e059_granite_token_conformance import (
    ENGINEERING_ADMISSION_COMMIT,
    GRANITE_ADAPTER_BLOB,
    GRANITE_ADAPTER_TEST_BLOB,
    conformance_failures,
    parse_token_ids,
)


class GraniteTokenConformanceRunnerTests(unittest.TestCase):
    def test_exact_official_id_sequence_passes(self) -> None:
        observed = list(range(100_256, 100_352))

        failures = conformance_failures(
            exit_code=0,
            observed_ids=observed,
            parse_failures=[],
            listener_present_after=False,
        )

        self.assertEqual(failures, [])

    def test_missing_duplicate_nonzero_and_listener_fail_conjunctively(self) -> None:
        observed = list(range(100_256, 100_352))
        observed.remove(100_300)
        observed.append(100_301)

        failures = conformance_failures(
            exit_code=1,
            observed_ids=observed,
            parse_failures=[],
            listener_present_after=True,
        )

        self.assertIn("tokenizer_exit_nonzero", failures)
        self.assertIn("control_token_id_100300_count_mismatch", failures)
        self.assertIn("control_token_id_100301_count_mismatch", failures)
        self.assertIn("unexpected_listener_after_tokenization", failures)

    def test_parser_rejects_malformed_and_boolean_lists(self) -> None:
        self.assertEqual(
            parse_token_ids("not a list"),
            (None, ["tokenizer_stdout_not_python_list"]),
        )
        self.assertEqual(
            parse_token_ids("[100256, true]"),
            (None, ["tokenizer_stdout_not_python_list"]),
        )
        self.assertEqual(
            parse_token_ids("[100256, True]"),
            (None, ["tokenizer_ids_not_integer_list"]),
        )

    def test_inventory_and_expected_ids_remain_bijective(self) -> None:
        self.assertEqual(len(GRANITE_CONTROL_TOKEN_IDS), 96)
        self.assertEqual(len(set(GRANITE_CONTROL_TOKEN_IDS.values())), 96)

    def test_runner_freezes_admitted_adapter_subject(self) -> None:
        self.assertEqual(
            ENGINEERING_ADMISSION_COMMIT,
            "466af5c92a4ffd5a907e8a214d1aaf6cd88c79fa",
        )
        self.assertEqual(
            GRANITE_ADAPTER_BLOB,
            "654c47fe2b479fb6b1f17a317353f7484170e976",
        )
        self.assertEqual(
            GRANITE_ADAPTER_TEST_BLOB,
            "3bcfaf4219db04611bc73306d4d4ac41d043b433",
        )


if __name__ == "__main__":
    unittest.main()
