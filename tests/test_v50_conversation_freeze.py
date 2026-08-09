from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FROZEN_BASE_COMMIT = "2602c57f21dc930b6fbe4426610469b39357119f"


def _git_blob(revision: str, repository_path: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", f"{revision}:{repository_path}"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def _normalized_line_ending_digest(path: Path) -> str:
    normalized = path.read_bytes().replace(b"\r\n", b"\n")
    if b"\r" in normalized:
        raise AssertionError("frozen file contains a non-CRLF carriage return")
    return hashlib.sha256(normalized).hexdigest()


class ConversationDevelopmentFreezeTests(unittest.TestCase):
    def assert_frozen_file(
        self,
        *,
        repository_path: str,
        expected_blob: str,
        expected_normalized_digest: str,
    ) -> None:
        base_blob = _git_blob(FROZEN_BASE_COMMIT, repository_path)
        head_blob = _git_blob("HEAD", repository_path)

        self.assertEqual(base_blob, expected_blob)
        self.assertEqual(head_blob, expected_blob)
        self.assertEqual(head_blob, base_blob)
        self.assertEqual(
            _normalized_line_ending_digest(REPOSITORY_ROOT / repository_path),
            expected_normalized_digest,
        )

    def test_e043_runtime_remains_identical_to_frozen_base(self) -> None:
        self.assert_frozen_file(
            repository_path="src/darwin_v50/desktop_runtime.py",
            expected_blob="01687c8e57aa1a867b18a66df9442b8745c08566",
            expected_normalized_digest=(
                "fd0d8aaf2bd1011addea581eaef172ce"
                "940157164dc013681d5326476d49f7e8"
            ),
        )

    def test_e043_protocol_remains_identical_to_frozen_base(self) -> None:
        self.assert_frozen_file(
            repository_path=(
                "docs/v50/EXPERIMENT_043_PERSISTENT_DESKTOP_RUNTIME.md"
            ),
            expected_blob="5becbc0177c7fc1fc1cfe0e2903e7a8323a7bd7d",
            expected_normalized_digest=(
                "beea70ce6bcfd177a18d36feca016f5f9"
                "3ed0bed7743fc73c31152cc19eaefad"
            ),
        )

    def test_freeze_digest_normalizes_only_crlf_and_lf(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            lf_path = root / "lf.txt"
            crlf_path = root / "crlf.txt"
            lone_cr_path = root / "lone-cr.txt"
            lf_path.write_bytes(b"alpha\nbeta\n")
            crlf_path.write_bytes(b"alpha\r\nbeta\r\n")
            lone_cr_path.write_bytes(b"alpha\rbeta\r")

            self.assertEqual(
                _normalized_line_ending_digest(lf_path),
                _normalized_line_ending_digest(crlf_path),
            )
            with self.assertRaisesRegex(AssertionError, "non-CRLF"):
                _normalized_line_ending_digest(lone_cr_path)


if __name__ == "__main__":
    unittest.main()
