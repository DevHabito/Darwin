"""Command-line tools for blind language annotation and agreement reports."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from .language import (
    build_blind_annotation_packet,
    load_annotation_candidates,
    load_language_annotations,
    measure_annotation_agreement,
    require_balanced_calibration_candidates,
    validate_annotation_panel,
)
from .models import canonical_json


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare blind Darwin language packets or measure agreement."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    packet = commands.add_parser(
        "packet",
        help="emit a shuffled, label-free annotation packet as JSONL",
    )
    packet.add_argument("candidates", help="path to the frozen candidate JSONL")
    packet.add_argument("--packet-id", required=True)
    packet.add_argument("--seed", required=True, type=int)

    agreement = commands.add_parser(
        "agreement",
        help="validate complete independent panels and emit per-field metrics",
    )
    agreement.add_argument("candidates", help="path to the frozen candidate JSONL")
    agreement.add_argument(
        "annotations",
        nargs="+",
        help="one or more annotation JSONL files",
    )
    agreement.add_argument("--minimum-annotators", type=int, default=2)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    candidates = load_annotation_candidates(arguments.candidates)
    require_balanced_calibration_candidates(candidates)

    if arguments.command == "packet":
        packet = build_blind_annotation_packet(
            candidates,
            packet_id=arguments.packet_id,
            seed=arguments.seed,
        )
        print(packet.jsonl(), end="")
        return 0

    records = tuple(
        record
        for path in arguments.annotations
        for record in load_language_annotations(path)
    )
    panel = validate_annotation_panel(
        candidates,
        records,
        minimum_annotators=arguments.minimum_annotators,
    )
    print(canonical_json(measure_annotation_agreement(panel).to_dict()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
