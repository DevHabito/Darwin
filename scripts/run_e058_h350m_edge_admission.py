"""Launch the frozen E058 profile through the admitted edge harness."""

from __future__ import annotations

import sys

from scripts.run_e057_granite_edge_admission import main


if __name__ == "__main__":
    raise SystemExit(main(["--experiment", "E058", *sys.argv[1:]]))
