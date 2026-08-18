from __future__ import annotations

from pathlib import Path
import unittest

from darwin_v50.conversation.windows_voice_io import WindowsSpeechListener


class WindowsSpeechListenerProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ready: list[tuple[str, str]] = []
        self.results: list[object] = []
        self.low_confidence: list[object] = []
        self.errors: list[str] = []
        self.listener = WindowsSpeechListener(
            lambda culture, name: self.ready.append((culture, name)),
            self.results.append,
            self.low_confidence.append,
            self.errors.append,
        )

    def test_ready_and_result_protocol_are_parsed_without_storage(self) -> None:
        self.listener._handle_line("READY|pt-BR|Windows Media SpeechRecognizer")
        self.listener._handle_line("RESULT|0.920|Darwin, explique o céu")

        self.assertEqual(
            self.ready,
            [("pt-BR", "Windows Media SpeechRecognizer")],
        )
        self.assertEqual(len(self.results), 1)
        speech = self.results[0]
        self.assertEqual(getattr(speech, "text"), "Darwin, explique o céu")
        self.assertEqual(getattr(speech, "confidence"), 0.92)
        self.assertEqual(self.errors, [])

    def test_pause_discards_recognizer_output_instead_of_buffering_it(self) -> None:
        self.listener.set_paused(True)

        self.listener._handle_line("RESULT|0.920|feedback from the speaker")

        self.assertEqual(self.results, [])

    def test_low_confidence_is_separate_from_accepted_speech(self) -> None:
        self.listener._handle_line("LOWCONF|0.100|uncertain audio")

        self.assertEqual(self.results, [])
        self.assertEqual(len(self.low_confidence), 1)


class MaintainedVoiceSurfaceTests(unittest.TestCase):
    def test_v50_voice_modules_do_not_import_legacy_dialogue(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sources = "\n".join(
            (root / relative).read_text(encoding="utf-8")
            for relative in (
                "src/darwin_v50/conversation/voice_runtime.py",
                "src/darwin_v50/conversation/windows_voice_io.py",
                "src/darwin_v50/conversation/voice_cli.py",
            )
        )

        self.assertNotIn("darwin_companion_shell", sources)
        self.assertNotIn("darwin_basic_language_core", sources)
        self.assertNotIn("darwin_contextual_language_learning", sources)
        self.assertNotIn("Ainda nao conheco", sources)
        self.assertNotIn("sinais computacionais de valencia", sources)


if __name__ == "__main__":
    unittest.main()
