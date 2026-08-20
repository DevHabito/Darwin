from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from darwin_v50.conversation import ConversationAvailability
from darwin_v50.conversation.voice_cli import (
    VoiceHostStartupError,
    create_local_runtime,
)


class VoiceHostConfigurationTests(unittest.TestCase):
    def test_unconfigured_backend_fails_before_transport_creation(self) -> None:
        with patch(
            "darwin_v50.conversation.voice_cli.LlamaCppServerTransport"
        ) as transport:
            with self.assertRaisesRegex(
                VoiceHostStartupError,
                "requires_explicit_local_backend",
            ):
                create_local_runtime({})

        transport.assert_not_called()

    def test_openai_backend_is_rejected_without_fallback(self) -> None:
        environment = {
            "DARWIN_LLM_BACKEND": "openai",
            "DARWIN_LLM_MODEL": "any-provider-model",
            "OPENAI_API_KEY": "not-used",
        }

        with patch(
            "darwin_v50.conversation.voice_cli.LlamaCppServerTransport"
        ) as transport:
            with self.assertRaisesRegex(
                VoiceHostStartupError,
                "requires_explicit_local_backend",
            ):
                create_local_runtime(environment)

        transport.assert_not_called()

    def test_local_backend_requires_endpoint_and_ephemeral_local_key(self) -> None:
        base = {
            "DARWIN_LLM_BACKEND": "local",
            "DARWIN_LLM_MODEL": "locked-local-model",
        }

        with self.assertRaisesRegex(
            VoiceHostStartupError,
            "local_endpoint_not_configured",
        ):
            create_local_runtime(base)

        with self.assertRaisesRegex(
            VoiceHostStartupError,
            "local_key_not_configured",
        ):
            create_local_runtime(
                {**base, "DARWIN_LOCAL_ENDPOINT": "http://127.0.0.1:18057"}
            )

    @patch("darwin_v50.conversation.voice_cli.ConversationRuntime.create")
    @patch("darwin_v50.conversation.voice_cli.PortableLocalLanguageBackend")
    @patch("darwin_v50.conversation.voice_cli.LlamaCppServerTransport")
    def test_exact_explicit_local_configuration_is_probed(
        self,
        transport_type: Mock,
        backend_type: Mock,
        runtime_create: Mock,
    ) -> None:
        environment = {
            "DARWIN_LLM_BACKEND": "local",
            "DARWIN_LLM_MODEL": "locked-local-model",
            "DARWIN_LOCAL_ENDPOINT": "http://127.0.0.1:18057",
            "DARWIN_LOCAL_API_KEY": "ephemeral-loopback-key",
            "DARWIN_LLM_TIMEOUT_SECONDS": "120",
        }
        transport = transport_type.return_value
        backend = backend_type.return_value
        runtime = runtime_create.return_value
        runtime.snapshot.return_value = SimpleNamespace(
            availability=ConversationAvailability.AVAILABLE,
            unavailable_reason=None,
        )

        result = create_local_runtime(environment)

        self.assertIs(result, runtime)
        transport_type.assert_called_once_with(
            endpoint="http://127.0.0.1:18057",
            api_key="ephemeral-loopback-key",
            timeout_seconds=120.0,
        )
        backend_type.assert_called_once_with(
            model="locked-local-model",
            transport=transport,
        )
        backend.probe_model.assert_called_once_with()
        runtime_create.assert_called_once()
        settings = runtime_create.call_args.args[0]
        self.assertEqual(settings.backend.value, "local")
        self.assertEqual(settings.model, "locked-local-model")


if __name__ == "__main__":
    unittest.main()
