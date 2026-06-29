from __future__ import annotations

import argparse
import json
import math
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"
SNAPSHOTS = "intrinsic_drive_snapshots_v49_43"
DECISIONS = "intrinsic_motivation_decisions_v49_43"
VALUE_EVIDENCE = "intrinsic_value_evidence_v49_43"
VALUES = "intrinsic_values_v49_43"
SCENARIOS = (
    "self_test_baseline",
    "self_test_low_energy",
    "self_test_curiosity",
    "self_test_competence",
)
VALID_RZS = {"continue", "narrow_focus", "replay_memory", "consolidate", "pause_for_stability"}


def exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def diagnose(details: bool = False) -> dict[str, Any]:
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        tables_ok = all(exists(conn, table) for table in (SNAPSHOTS, DECISIONS, VALUE_EVIDENCE, VALUES))
        decisions = {}
        if tables_ok:
            for scenario in SCENARIOS:
                row = conn.execute(
                    f"SELECT * FROM {DECISIONS} WHERE scenario_kind=? ORDER BY id DESC LIMIT 1",
                    (scenario,),
                ).fetchone()
                decisions[scenario] = dict(row) if row else {}
        ids = [row["decision_id"] for row in decisions.values() if row]
        snapshots = [
            dict(row) for row in conn.execute(
                f"SELECT * FROM {SNAPSHOTS} WHERE decision_id IN ({','.join('?' for _ in ids)})",
                ids,
            ).fetchall()
        ] if ids else []
        values = [dict(row) for row in conn.execute(f"SELECT * FROM {VALUES}").fetchall()] if tables_ok else []
        evidence = [dict(row) for row in conn.execute(f"SELECT * FROM {VALUE_EVIDENCE}").fetchall()] if tables_ok else []
    emerging = [row for row in values if row["status"] == "emerging"]
    checks = {
        "tables_exist": tables_ok,
        "six_drives_competed": len(snapshots) == 24,
        "low_energy_causes_stability": decisions.get("self_test_low_energy", {}).get("drive_key") == "stability",
        "curiosity_intervention_is_causal": decisions.get("self_test_curiosity", {}).get("drive_key") == "curiosity",
        "competence_intervention_is_causal": decisions.get("self_test_competence", {}).get("drive_key") == "competence",
        "rzs_regulates_motivation": all(
            row.get("rzs_decision") in VALID_RZS
            and finite(row.get("sigma_before"))
            and finite(row.get("sigma_after"))
            for row in decisions.values()
        ),
        "values_have_observed_evidence": len(evidence) >= 6,
        "no_single_event_value_promotion": all(
            int(row["evidence_count"]) >= 3 and int(row["domain_count"]) >= 2
            for row in emerging
        ),
        "multicontext_value_emerged": len(emerging) >= 1,
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "decisions": decisions,
        "values": values,
        "evidence_count": len(evidence),
        "snapshots": snapshots if details else [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Checker Darwin v49.43 Intrinsic Motivation")
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args()
    report = diagnose(args.details)
    print("DARWIN v49.43 - CHECK MOTIVACOES E VALORES")
    print("=" * 68)
    for name, passed in report["checks"].items():
        print(f"- {name}: {'OK' if passed else 'FALHOU'}")
    print(f"- valores: {[row['value_key'] + ':' + row['status'] for row in report['values']]}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'REVISAR'}")
    if args.details:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
