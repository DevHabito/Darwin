from __future__ import annotations

from pathlib import Path
import unittest

from scripts.check_maintained_surface import ROOT, check_english_and_encoding


FIXTURE_PATH = ROOT / "docs" / "fixture.md"


class MaintainedSurfaceLanguageTests(unittest.TestCase):
    def test_portuguese_inside_inline_code_is_preserved_as_fixture(self) -> None:
        errors = check_english_and_encoding(
            FIXTURE_PATH,
            "Send the exact turn: `Você não tem memória permanente.`",
        )

        self.assertEqual(errors, [])

    def test_portuguese_in_prose_remains_rejected(self) -> None:
        errors = check_english_and_encoding(
            FIXTURE_PATH,
            "The protocolo must remain in English.",
        )

        self.assertEqual(
            errors,
            [
                f"{Path('docs/fixture.md')}:1: "
                "Portuguese marker on maintained English surface"
            ],
        )

    def test_inline_code_does_not_hide_portuguese_prose(self) -> None:
        errors = check_english_and_encoding(
            FIXTURE_PATH,
            "Keep `memória` verbatim, but the protocolo prose is invalid.",
        )

        self.assertEqual(len(errors), 1)
        self.assertIn("Portuguese marker", errors[0])


if __name__ == "__main__":
    unittest.main()
