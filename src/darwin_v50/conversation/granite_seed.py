"""Candidate-specific control-token boundary for Granite local models."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from ..language import LanguageBackendError
from ..models import ValidationError
from .local_seed import StructuredLocalTransport


_TOKEN_STRINGS_100256_TO_100283 = (
    "<|pad|>",
    "<|end_of_text|>",
    "<|fim_prefix|>",
    "<|fim_middle|>",
    "<|fim_suffix|>",
    "<|fim_pad|>",
    "<|filename|>",
    "<|reponame|>",
    "<|start_of_role|>",
    "<|end_of_role|>",
    "<|unused_1|>",
    "<|start_of_plugin|>",
    "<|end_of_plugin|>",
    "<|unk|>",
    "<tool_call>",
    "</tool_call>",
    "<tool_response>",
    "</tool_response>",
    "<think>",
    "</think>",
    "<think_on>",
    "<think_off>",
    "<schema>",
    "</schema>",
    "<tools>",
    "</tools>",
    "<documents>",
    "</documents>",
)
GRANITE_CONTROL_TOKEN_IDS = {
    **{
        marker: token_id
        for token_id, marker in enumerate(
            _TOKEN_STRINGS_100256_TO_100283,
            start=100_256,
        )
    },
    **{
        f"<|unused_{unused_number}|>": token_id
        for unused_number, token_id in zip(
            range(15, 83),
            range(100_284, 100_352),
            strict=True,
        )
    },
}
GRANITE_CONTROL_MARKERS = frozenset(GRANITE_CONTROL_TOKEN_IDS)
GRANITE_PIPE_CONTROL_MARKERS = frozenset(
    marker for marker in GRANITE_CONTROL_MARKERS if marker.startswith("<|")
)
GRANITE_XML_CONTROL_MARKERS = frozenset(
    GRANITE_CONTROL_MARKERS - GRANITE_PIPE_CONTROL_MARKERS
)
_PIPE_TOKEN_SHAPE = re.compile(r"<\|[^<>\r\n]{1,64}\|>")


class GraniteControlBoundaryError(LanguageBackendError):
    """Sanitized rejection at the candidate-specific Granite boundary."""


def _reject_granite_control_tokens(value: object) -> None:
    if isinstance(value, str):
        if _PIPE_TOKEN_SHAPE.search(value) or any(
            marker in value for marker in GRANITE_XML_CONTROL_MARKERS
        ):
            raise GraniteControlBoundaryError("granite_control_token_rejected")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            _reject_granite_control_tokens(key)
            _reject_granite_control_tokens(child)
        return
    if isinstance(value, (list, tuple)):
        for child in value:
            _reject_granite_control_tokens(child)


class GraniteSafeTransport:
    """Rejects Granite control tokens around one unchanged inner call."""

    def __init__(self, inner: StructuredLocalTransport) -> None:
        if not callable(getattr(inner, "probe", None)) or not callable(
            getattr(inner, "generate_structured", None)
        ):
            raise ValidationError("Granite transport requires a structured inner transport")
        self._inner = inner

    def __repr__(self) -> str:
        return "GraniteSafeTransport(inner=<redacted>)"

    def probe(self, *, model: str, context_tokens: int) -> None:
        self._inner.probe(model=model, context_tokens=context_tokens)

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
        _reject_granite_control_tokens(model)
        _reject_granite_control_tokens(instructions)
        _reject_granite_control_tokens(payload)
        _reject_granite_control_tokens(schema_name)
        _reject_granite_control_tokens(schema)
        result = self._inner.generate_structured(
            model=model,
            instructions=instructions,
            payload=payload,
            schema_name=schema_name,
            schema=schema,
            max_output_tokens=max_output_tokens,
        )
        _reject_granite_control_tokens(result)
        return result
