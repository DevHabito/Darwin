"""Explicitly launched terminal surface for conversational development."""

from __future__ import annotations

import sys
from typing import TextIO

from ..language import LanguageBoundaryError
from ..models import ValidationError
from .config import ConversationSettings
from .runtime import ConversationAvailability, ConversationRuntime


def _write(stream: TextIO, message: str) -> None:
    stream.write(message + "\n")
    stream.flush()


def main() -> int:
    try:
        settings = ConversationSettings.from_environment()
    except ValidationError as exc:
        _write(sys.stderr, f"Darwin configuration error: {exc}")
        return 2

    runtime = ConversationRuntime.create(settings)
    snapshot = runtime.snapshot()
    if snapshot.availability is not ConversationAvailability.AVAILABLE:
        _write(
            sys.stderr,
            "Darwin conversational backend is unavailable: "
            f"{snapshot.unavailable_reason}.",
        )
        _write(
            sys.stderr,
            "Select a backend explicitly. For OpenAI, set "
            "DARWIN_LLM_BACKEND=openai, DARWIN_LLM_MODEL, and OPENAI_API_KEY.",
        )
        runtime.close()
        return 2

    _write(
        sys.stdout,
        f"Darwin conversational dev is active via {snapshot.language_source}.",
    )
    _write(
        sys.stdout,
        "This session is temporary. Type /exit to erase it and leave.",
    )
    try:
        while True:
            try:
                text = input("You: ").strip()
            except EOFError:
                break
            if text.lower() in {"/exit", "/quit"}:
                break
            if not text:
                continue
            try:
                result = runtime.turn(text)
            except LanguageBoundaryError as exc:
                _write(sys.stderr, f"Darwin turn failed closed: {exc}")
                continue
            _write(sys.stdout, f"Darwin: {result.expression.text}")
    except KeyboardInterrupt:
        _write(sys.stdout, "")
    finally:
        runtime.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
