"""Explicit terminal entry point for the provider-free local language seed."""

from __future__ import annotations

import os
import sys
from typing import TextIO

from ..language import LanguageBoundaryError
from ..models import ValidationError
from .config import ConversationBackendKind, ConversationSettings
from .local_seed import (
    LlamaCppServerTransport,
    LocalSeedTransportError,
    PortableLocalLanguageBackend,
)
from .runtime import ConversationAvailability, ConversationRuntime


def _write(stream: TextIO, message: str) -> None:
    stream.write(message + "\n")
    stream.flush()


def main() -> int:
    try:
        settings = ConversationSettings.from_environment()
    except ValidationError as exc:
        _write(sys.stderr, f"Darwin local configuration error: {exc}")
        return 2
    if settings.backend is not ConversationBackendKind.LOCAL:
        _write(sys.stderr, "Darwin local mode requires DARWIN_LLM_BACKEND=local.")
        return 2
    if settings.model is None:
        _write(sys.stderr, "Darwin local mode requires DARWIN_LLM_MODEL.")
        return 2
    endpoint = os.environ.get("DARWIN_LOCAL_ENDPOINT", "").strip()
    if not endpoint:
        _write(sys.stderr, "Darwin local mode requires DARWIN_LOCAL_ENDPOINT.")
        return 2

    try:
        transport = LlamaCppServerTransport(
            endpoint=endpoint,
            timeout_seconds=settings.request_timeout_seconds,
        )
        backend = PortableLocalLanguageBackend(
            model=settings.model,
            transport=transport,
        )
        backend.probe_model()
    except (ValidationError, LocalSeedTransportError, LanguageBoundaryError) as exc:
        _write(sys.stderr, f"Darwin local backend is unavailable: {exc}")
        return 2

    runtime = ConversationRuntime.create(settings, local_backend=backend)
    snapshot = runtime.snapshot()
    if snapshot.availability is not ConversationAvailability.AVAILABLE:
        _write(
            sys.stderr,
            f"Darwin local backend is unavailable: {snapshot.unavailable_reason}.",
        )
        runtime.close()
        return 2

    _write(sys.stdout, f"Darwin local conversation is active via {snapshot.language_source}.")
    _write(sys.stdout, "This session is temporary and uses no paid provider.")
    _write(sys.stdout, "Type /exit to erase the transcript and leave.")
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
                _write(sys.stderr, f"Darwin local turn failed closed: {exc}")
                continue
            _write(sys.stdout, f"Darwin: {result.expression.text}")
    except KeyboardInterrupt:
        _write(sys.stdout, "")
    finally:
        runtime.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
