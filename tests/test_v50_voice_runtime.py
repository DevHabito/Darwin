from __future__ import annotations

from types import SimpleNamespace
import unittest

from darwin_v50.conversation import (
    AuthorityMutationCounts,
    DarwinVoiceController,
    VoiceActionKind,
    VoiceHostState,
    command_after_wake_word,
    contains_wake_word,
    is_sleep_command,
)
from darwin_v50.models import ValidationError


class FakeConversationRuntime:
    def __init__(
        self,
        *,
        expression: str = "Resposta produzida pelo backend para este turno.",
        mutations: AuthorityMutationCounts | None = None,
        failure: Exception | None = None,
    ) -> None:
        self.expression = expression
        self.mutations = mutations or AuthorityMutationCounts()
        self.failure = failure
        self.turns: list[str] = []
        self.closed = False

    def turn(self, text: str) -> object:
        self.turns.append(text)
        if self.failure is not None:
            raise self.failure
        return SimpleNamespace(
            expression=SimpleNamespace(text=self.expression),
            authority_mutations=self.mutations,
        )

    def close(self) -> None:
        self.closed = True


class VoiceCommandTests(unittest.TestCase):
    def test_wake_word_is_token_based_and_accent_insensitive(self) -> None:
        self.assertTrue(contains_wake_word("Ei, DARWIN!"))
        self.assertTrue(contains_wake_word("Darvim, acorde"))
        self.assertFalse(contains_wake_word("darwinismo"))

    def test_only_text_after_wake_word_becomes_model_input(self) -> None:
        self.assertEqual(
            command_after_wake_word("Ei, Darwin, explique o céu"),
            "explique o céu",
        )

    def test_sleep_command_does_not_match_general_sleep_discussion(self) -> None:
        self.assertTrue(is_sleep_command("pode dormir agora"))
        self.assertTrue(is_sleep_command("tá na hora de mimir"))
        self.assertFalse(is_sleep_command("tenho dificuldade para dormir cedo"))


class DarwinVoiceControllerTests(unittest.TestCase):
    def test_sleeping_noise_never_reaches_conversation_runtime(self) -> None:
        runtime = FakeConversationRuntime()
        controller = DarwinVoiceController(runtime)  # type: ignore[arg-type]

        action = controller.handle("conversa da chamada", confidence=0.92)

        self.assertEqual(action.kind, VoiceActionKind.IGNORED)
        self.assertEqual(controller.state, VoiceHostState.SLEEPING)
        self.assertEqual(runtime.turns, [])

    def test_wake_word_alone_opens_without_a_scripted_spoken_reply(self) -> None:
        runtime = FakeConversationRuntime()
        controller = DarwinVoiceController(runtime)  # type: ignore[arg-type]

        action = controller.handle("Darwin", confidence=0.92)

        self.assertEqual(action.kind, VoiceActionKind.AWAKENED)
        self.assertIsNone(action.expression_text)
        self.assertEqual(runtime.turns, [])
        self.assertFalse(controller.snapshot().scripted_reply_enabled)

    def test_wake_command_routes_only_command_and_returns_exact_model_text(self) -> None:
        runtime = FakeConversationRuntime(expression="Texto novo e não cadastrado.")
        controller = DarwinVoiceController(runtime)  # type: ignore[arg-type]

        action = controller.handle(
            "Ei, Darwin, por que o céu parece azul?",
            confidence=0.92,
        )

        self.assertEqual(runtime.turns, ["por que o céu parece azul?"])
        self.assertEqual(action.kind, VoiceActionKind.MODEL_REPLY)
        self.assertEqual(action.expression_text, "Texto novo e não cadastrado.")
        self.assertEqual(controller.snapshot().accepted_model_turns, 1)

    def test_awake_turn_uses_runtime_and_sleep_command_does_not(self) -> None:
        runtime = FakeConversationRuntime()
        controller = DarwinVoiceController(runtime)  # type: ignore[arg-type]
        controller.handle("Darwin", confidence=0.92)

        reply = controller.handle("mude de assunto", confidence=0.72)
        slept = controller.handle("pode dormir agora", confidence=0.92)

        self.assertEqual(reply.kind, VoiceActionKind.MODEL_REPLY)
        self.assertEqual(runtime.turns, ["mude de assunto"])
        self.assertEqual(slept.kind, VoiceActionKind.SLEPT)
        self.assertEqual(controller.state, VoiceHostState.SLEEPING)

    def test_backend_failure_never_manufactures_spoken_text(self) -> None:
        runtime = FakeConversationRuntime(failure=RuntimeError("backend down"))
        controller = DarwinVoiceController(runtime)  # type: ignore[arg-type]

        action = controller.handle("Darwin responda", confidence=0.92)

        self.assertEqual(action.kind, VoiceActionKind.FAILED_CLOSED)
        self.assertIsNone(action.expression_text)
        self.assertEqual(
            action.error_code,
            "voice_model_turn_failed:RuntimeError",
        )
        self.assertNotIn("backend down", action.error_code or "")
        self.assertEqual(controller.snapshot().failed_model_turns, 1)

    def test_authority_mutation_never_becomes_speech(self) -> None:
        runtime = FakeConversationRuntime(
            mutations=AuthorityMutationCounts(memory_writes=1),
        )
        controller = DarwinVoiceController(runtime)  # type: ignore[arg-type]

        action = controller.handle("Darwin grave isso", confidence=0.92)

        self.assertEqual(action.kind, VoiceActionKind.FAILED_CLOSED)
        self.assertIsNone(action.expression_text)
        self.assertEqual(
            action.error_code,
            "voice_model_turn_failed:VoiceHostError",
        )

    def test_close_erases_runtime_context_through_runtime_contract(self) -> None:
        runtime = FakeConversationRuntime()
        controller = DarwinVoiceController(runtime)  # type: ignore[arg-type]

        controller.close()

        self.assertTrue(runtime.closed)
        self.assertEqual(controller.state, VoiceHostState.CLOSED)
        with self.assertRaisesRegex(Exception, "voice_host_closed"):
            controller.handle("Darwin", confidence=0.92)

    def test_explicit_sleep_hides_without_calling_model(self) -> None:
        runtime = FakeConversationRuntime()
        controller = DarwinVoiceController(runtime)  # type: ignore[arg-type]
        controller.handle("Darwin", confidence=0.92)

        action = controller.sleep()

        self.assertEqual(action.kind, VoiceActionKind.SLEPT)
        self.assertEqual(controller.state, VoiceHostState.SLEEPING)
        self.assertEqual(runtime.turns, [])

    def test_invalid_confidence_fails_before_runtime_call(self) -> None:
        runtime = FakeConversationRuntime()
        controller = DarwinVoiceController(runtime)  # type: ignore[arg-type]

        with self.assertRaises(ValidationError):
            controller.handle("Darwin", confidence=1.5)

        self.assertEqual(runtime.turns, [])


if __name__ == "__main__":
    unittest.main()
