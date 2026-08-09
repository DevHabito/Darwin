"""Command-line entry point for the Darwin language development corpus."""

from __future__ import annotations

from collections.abc import Iterable

from .language.conformance import main as conformance_main


def main(argv: Iterable[str] | None = None) -> int:
    return conformance_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
