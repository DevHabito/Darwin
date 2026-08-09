from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from typing import Any, Mapping

from darwin_v50.conversation import (
    ConversationAvailability,
    ConversationBackendKind,
    ConversationRuntime,
    ConversationRuntimeError,
    ConversationSettings,
    ConversationUnavailableError,
)
from darwin_v50.language import (
    LanguageAuthorityError,
    LanguageBackendError,
    LanguageMode,
    LanguageModelRequest,
    LanguageOperation,
)
from darwin_v50.models import ValidationError


def understanding_response() -> dict[str, Any]:
    return {
        "intent": "open_conversation",
        "entities": [],
        "reported_signals": [],
        "temporal_reference": None,
        "explicit_preference": None,
        "confidence": 0.6,
    }


class ScriptedLocalBackend:
    name = "explicit-local-test-backend"

    def __init__(
        self,
        *,
        model: str = "local-test-model",
        fail_expression: bool = False,
        authority_violation: bool = False,
    ) -> None:
        self.model = model
        self.fail_expression = fail_expression
        self.authority_violation = authority_violation
        self.requests: list[LanguageModelRequest] = []
        self.clear_calls = 0

    def invoke(self, request: LanguageModelRequest) -> Mapping[str, Any]:
        self.requests.append(request)
        if request.operation is LanguageOperation.UNDERSTAND:
            result = understanding_response()
            if self.authority_violation:
                result["memory"] = {"write": "forbidden"}
            return result
        if request.operation is LanguageOperation.EXPRESS:
            if self.fail_expression:
                raise LanguageBackendError("scripted_expression_failure")
            facts = request.payload["facts"]
            return {
                "text": "Uma resposta nova, produzida para este turno.",
                "acknowledged_fact_ids": [fact["fact_id"] for fact in facts],
            }
        raise AssertionError("consult must not be called")

    def clear_ephemeral_context(self) -> None:
        self.clear_calls += 1


def local_settings(**overrides: object) -> ConversationSettings:
    values: dict[str, object] = {
        "backend": ConversationBackendKind.LOCAL,
        "model": "local-test-model",
        "locale": "pt-BR",
    }
    values.update(overrides)
    return ConversationSettings(**values)  # type: ignore[arg-type]


class ConversationConfigurationTests(unittest.TestCase):
    def test_environment_defaults_to_no_backend_and_no_model(self) -> None:
        settings = ConversationSettings.from_environment({})

        self.assertEqual(settings.backend, ConversationBackendKind.NONE)
        self.assertIsNone(settings.model)
        self.assertIsNone(settings.api_key)

    def test_environment_never_infers_backend_from_available_api_key(self) -> None:
        settings = ConversationSettings.from_environment(
            {
                "OPENAI_API_KEY": "secret-key",
                "DARWIN_LLM_MODEL": "account-model",
            }
        )

        self.assertEqual(settings.backend, ConversationBackendKind.NONE)

    def test_invalid_or_blank_backend_is_rejected(self) -> None:
        for backend in ("ollama", "auto", ""):
            with self.subTest(backend=backend):
                with self.assertRaises(ValidationError):
                    ConversationSettings.from_environment(
                        {"DARWIN_LLM_BACKEND": backend}
                    )

    def test_api_key_is_excluded_from_settings_repr(self) -> None:
        settings = ConversationSettings(
            backend=ConversationBackendKind.OPENAI,
            model="account-model",
            api_key="never-print-this-secret",
        )

        self.assertNotIn("never-print-this-secret", repr(settings))

    def test_missing_openai_configuration_is_unavailable_not_local(self) -> None:
        runtime = ConversationRuntime.create(
            ConversationSettings(
                backend=ConversationBackendKind.OPENAI,
                model="account-model",
            ),
            local_backend=ScriptedLocalBackend(model="account-model"),
        )

        snapshot = runtime.snapshot()
        self.assertEqual(snapshot.availability, ConversationAvailability.UNAVAILABLE)
        self.assertEqual(snapshot.language_mode, LanguageMode.PURE)
        self.assertEqual(snapshot.unavailable_reason, "openai_api_key_not_configured")
        with self.assertRaises(ConversationUnavailableError):
            runtime.turn("Olá")

    def test_local_backend_requires_explicit_instance_and_matching_model(self) -> None:
        absent = ConversationRuntime.create(local_settings())
        mismatch = ConversationRuntime.create(
            local_settings(),
            local_backend=ScriptedLocalBackend(model="different-model"),
        )

        self.assertEqual(absent.snapshot().availability, ConversationAvailability.UNAVAILABLE)
        self.assertEqual(
            absent.snapshot().unavailable_reason,
            "explicit_local_backend_not_supplied",
        )
        self.assertEqual(mismatch.snapshot().availability, ConversationAvailability.UNAVAILABLE)
        self.assertEqual(mismatch.snapshot().unavailable_reason, "local_model_mismatch")

    def test_local_backend_must_expose_ephemeral_clear(self) -> None:
        class MissingClearBackend:
            name = "missing-clear"
            model = "local-test-model"

            def invoke(self, request: LanguageModelRequest) -> Mapping[str, Any]:
                raise AssertionError("unavailable backend must not be invoked")

        runtime = ConversationRuntime.create(
            local_settings(),
            local_backend=MissingClearBackend(),  # type: ignore[arg-type]
        )

        self.assertEqual(runtime.snapshot().availability, ConversationAvailability.UNAVAILABLE)
        self.assertEqual(
            runtime.snapshot().unavailable_reason,
            "local_backend_missing_ephemeral_clear",
        )

    def test_snapshot_never_contains_api_key(self) -> None:
        class ProbeTransport:
            def request_json(self, **_: object) -> Mapping[str, Any]:
                return {"object": "model", "id": "account-model"}

        runtime = ConversationRuntime.create(
            ConversationSettings(
                backend=ConversationBackendKind.OPENAI,
                model="account-model",
                api_key="never-print-this-secret",
            ),
            openai_transport=ProbeTransport(),  # type: ignore[arg-type]
        )

        self.assertNotIn("never-print-this-secret", repr(runtime.snapshot()))
        self.assertNotIn("never-print-this-secret", repr(asdict(runtime.snapshot())))


class ConversationRuntimeTests(unittest.TestCase):
    def test_successful_turn_is_understand_then_express(self) -> None:
        backend = ScriptedLocalBackend()
        runtime = ConversationRuntime.create(
            local_settings(),
            local_backend=backend,
        )

        result = runtime.turn("Vamos falar sobre astronomia?")

        self.assertEqual(
            [request.operation for request in backend.requests],
            [LanguageOperation.UNDERSTAND, LanguageOperation.EXPRESS],
        )
        self.assertEqual(result.observation.intent, "open_conversation")
        self.assertEqual(
            result.expression.text,
            "Uma resposta nova, produzida para este turno.",
        )
        self.assertEqual(
            result.expression.acknowledged_fact_ids,
            ("candidate-status", "authority-status"),
        )
        self.assertEqual(result.authority_mutations.memory_writes, 0)
        self.assertEqual(result.authority_mutations.goal_changes, 0)
        self.assertEqual(result.authority_mutations.rzs_changes, 0)
        self.assertEqual(result.authority_mutations.sigma_changes, 0)
        self.assertEqual(result.authority_mutations.actions_executed, 0)

    def test_later_turn_receives_bounded_temporary_transcript(self) -> None:
        backend = ScriptedLocalBackend()
        runtime = ConversationRuntime.create(local_settings(), local_backend=backend)
        runtime.turn("Primeiro assunto")
        runtime.turn("Agora outro assunto")

        second_understand = backend.requests[2]
        self.assertEqual(
            tuple(second_understand.payload["recent_turns"]),
            (
                "user:\nPrimeiro assunto",
                "darwin:\nUma resposta nova, produzida para este turno.",
            ),
        )

    def test_failed_expression_does_not_commit_partial_turn(self) -> None:
        backend = ScriptedLocalBackend(fail_expression=True)
        runtime = ConversationRuntime.create(local_settings(), local_backend=backend)

        with self.assertRaisesRegex(
            LanguageBackendError,
            "scripted_expression_failure",
        ):
            runtime.turn("Este turno deve falhar")

        self.assertEqual(runtime.temporary_context(), ())
        self.assertEqual(runtime.snapshot().completed_turns, 0)
        self.assertEqual(backend.clear_calls, 1)

    def test_authority_bearing_understanding_is_rejected_without_context_write(self) -> None:
        backend = ScriptedLocalBackend(authority_violation=True)
        runtime = ConversationRuntime.create(local_settings(), local_backend=backend)

        with self.assertRaises(LanguageAuthorityError):
            runtime.turn("Grave isso diretamente na memória")

        self.assertEqual(runtime.temporary_context(), ())
        self.assertEqual(runtime.snapshot().authority_mutations.memory_writes, 0)

    def test_context_is_bounded_to_sixty_messages(self) -> None:
        backend = ScriptedLocalBackend()
        runtime = ConversationRuntime.create(local_settings(), local_backend=backend)

        for index in range(31):
            runtime.turn(f"turno {index}")

        context = runtime.temporary_context()
        self.assertEqual(len(context), 60)
        self.assertNotIn("user:\nturno 0", context)
        self.assertIn("user:\nturno 30", context)

    def test_long_messages_are_marked_when_clipped_from_future_context(self) -> None:
        backend = ScriptedLocalBackend()
        runtime = ConversationRuntime.create(local_settings(), local_backend=backend)
        runtime.turn("x" * 3_000)

        first_message = runtime.temporary_context()[0]
        self.assertEqual(len(first_message), 2_000)
        self.assertTrue(first_message.endswith("[truncated from temporary context]"))

    def test_close_erases_transcript_and_pending_state(self) -> None:
        backend = ScriptedLocalBackend()
        runtime = ConversationRuntime.create(local_settings(), local_backend=backend)
        runtime.turn("Conversa temporária")

        runtime.close()

        snapshot = runtime.snapshot()
        self.assertEqual(snapshot.availability, ConversationAvailability.CLOSED)
        self.assertEqual(snapshot.temporary_messages, 0)
        self.assertEqual(runtime.temporary_context(), ())
        self.assertEqual(backend.clear_calls, 1)
        with self.assertRaisesRegex(ConversationRuntimeError, "closed"):
            runtime.turn("não deve funcionar")

    def test_conversation_runtime_creates_no_files(self) -> None:
        backend = ScriptedLocalBackend()
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = tuple(root.rglob("*"))
            runtime = ConversationRuntime.create(local_settings(), local_backend=backend)
            runtime.turn("Nada deve ser persistido")
            runtime.close()
            after = tuple(root.rglob("*"))

        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
