from __future__ import annotations

import hashlib
from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class ConversationDevelopmentFreezeTests(unittest.TestCase):
    def test_e043_runtime_remains_byte_identical(self) -> None:
        path = REPOSITORY_ROOT / "src" / "darwin_v50" / "desktop_runtime.py"

        self.assertEqual(
            hashlib.sha256(path.read_bytes()).hexdigest(),
            "fd0d8aaf2bd1011addea581eaef172ce940157164dc013681d5326476d49f7e8",
        )

    def test_e043_protocol_remains_byte_identical(self) -> None:
        path = (
            REPOSITORY_ROOT
            / "docs"
            / "v50"
            / "EXPERIMENT_043_PERSISTENT_DESKTOP_RUNTIME.md"
        )

        self.assertEqual(
            hashlib.sha256(path.read_bytes()).hexdigest(),
            "beea70ce6bcfd177a18d36feca016f5f93ed0bed7743fc73c31152cc19eaefad",
        )


if __name__ == "__main__":
    unittest.main()
