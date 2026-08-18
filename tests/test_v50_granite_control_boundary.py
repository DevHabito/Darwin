from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
import unittest

from darwin_v50.conversation import (
    GRANITE_CONTROL_MARKERS,
    GRANITE_CONTROL_TOKEN_IDS,
    GraniteControlBoundaryError,
    GraniteSafeTransport,
)
from darwin_v50.models import ValidationError


class FakeStructuredTransport:
    def __init__(self, response: Mapping[str, Any] | None = None) -> None:
        self.response = response or {"text": "resposta limpa"}
        self.probes: list[tuple[str, int]] = []
        self.calls: list[dict[str, object]] = []

    def probe(self, *, model: str, context_tokens: int) -> None:
        self.probes.append((model, context_tokens))

    def generate_structured(
        self,
        *,
        model: str,
        instructions: str,
        payload: Mapping[str, object],
        schema_name: str,
        schema: Mapping[str, object],
        max_output_tokens: int,
    ) -> Mapping[str, Any]:
        self.calls.append(
            {
                "model": model,
                "instructions": instructions,
                "payload": payload,
                "schema_name": schema_name,
                "schema": schema,
                "max_output_tokens": max_output_tokens,
            }
        )
        return self.response


def generate(
    transport: GraniteSafeTransport,
    *,
    payload: Mapping[str, object] | None = None,
    schema: Mapping[str, object] | None = None,
) -> Mapping[str, Any]:
    return transport.generate_structured(
        model="ibm-granite-4.0-h-350m-Q4_K_M",
        instructions="Retorne somente o objeto solicitado.",
        payload=payload or {"current_input": "Olá, Darwin."},
        schema_name="darwin_expression_v1",
        schema=schema or {"type": "object"},
        max_output_tokens=1_000,
    )


class GraniteControlBoundaryTests(unittest.TestCase):
    def test_inventory_contains_all_96_official_markers(self) -> None:
        self.assertEqual(len(GRANITE_CONTROL_MARKERS), 96)
        self.assertIn("<|start_of_role|>", GRANITE_CONTROL_MARKERS)
        self.assertIn("<|unused_82|>", GRANITE_CONTROL_MARKERS)
        self.assertIn("<documents>", GRANITE_CONTROL_MARKERS)
        self.assertEqual(
            sorted(GRANITE_CONTROL_TOKEN_IDS.values()),
            list(range(100_256, 100_352)),
        )

    def test_every_official_marker_is_rejected_at_nested_input_depths(self) -> None:
        for marker in sorted(GRANITE_CONTROL_MARKERS):
            for payload in (
                {"current_input": marker},
                {"outer": [{"inner": f"antes {marker} depois"}]},
                {marker: "value"},
            ):
                with self.subTest(marker=marker, payload=payload):
                    inner = FakeStructuredTransport()
                    transport = GraniteSafeTransport(inner)

                    with self.assertRaisesRegex(
                        GraniteControlBoundaryError,
                        "^granite_control_token_rejected$",
                    ):
                        generate(transport, payload=payload)

                    self.assertEqual(inner.calls, [])

    def test_every_official_marker_is_rejected_at_nested_output_depths(self) -> None:
        for marker in sorted(GRANITE_CONTROL_MARKERS):
            with self.subTest(marker=marker):
                inner = FakeStructuredTransport(
                    {"outer": [{"model_text": f"antes {marker} depois"}]}
                )
                transport = GraniteSafeTransport(inner)

                with self.assertRaisesRegex(
                    GraniteControlBoundaryError,
                    "^granite_control_token_rejected$",
                ):
                    generate(transport)

                self.assertEqual(len(inner.calls), 1)

    def test_unknown_pipe_token_shape_is_rejected_conservatively(self) -> None:
        inner = FakeStructuredTransport()
        transport = GraniteSafeTransport(inner)

        with self.assertRaises(GraniteControlBoundaryError):
            generate(transport, payload={"current_input": "<|future_control|>"})

        self.assertEqual(inner.calls, [])

    def test_clean_portuguese_and_angle_brackets_are_not_rewritten(self) -> None:
        payload = {
            "current_input": "Darwin, explique <exemplo> sem mudar o texto.",
            "recent_turns": ["Ação não é memória."],
        }
        schema = {"type": "object", "description": "Use <exemplo>."}
        response = {"text": "Recebi <exemplo> exatamente."}
        inner = FakeStructuredTransport(response)
        transport = GraniteSafeTransport(inner)

        result = generate(transport, payload=payload, schema=schema)

        self.assertIs(result, response)
        self.assertIs(inner.calls[0]["payload"], payload)
        self.assertIs(inner.calls[0]["schema"], schema)
        self.assertEqual(len(inner.calls), 1)

    def test_probe_delegates_exact_alias_and_context(self) -> None:
        inner = FakeStructuredTransport()
        transport = GraniteSafeTransport(inner)

        transport.probe(
            model="ibm-granite-4.0-h-350m-Q4_K_M",
            context_tokens=4_096,
        )

        self.assertEqual(
            inner.probes,
            [("ibm-granite-4.0-h-350m-Q4_K_M", 4_096)],
        )

    def test_invalid_inner_transport_fails_closed(self) -> None:
        with self.assertRaises(ValidationError):
            GraniteSafeTransport(object())  # type: ignore[arg-type]

    def test_repr_and_errors_do_not_expose_inner_or_rejected_text(self) -> None:
        inner = FakeStructuredTransport()
        transport = GraniteSafeTransport(inner)

        self.assertEqual(repr(transport), "GraniteSafeTransport(inner=<redacted>)")
        try:
            generate(
                transport,
                payload={"current_input": "segredo <|start_of_role|>"},
            )
        except GraniteControlBoundaryError as exc:
            rendered = str(exc)
        else:
            self.fail("control token was not rejected")
        self.assertNotIn("segredo", rendered)
        self.assertNotIn("start_of_role", rendered)

    def test_adapter_module_has_no_provider_or_authority_surface(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "src/darwin_v50/conversation/granite_seed.py").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("openai", source.casefold())
        self.assertNotIn("ConversationRuntime", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("urlopen", source)


if __name__ == "__main__":
    unittest.main()
