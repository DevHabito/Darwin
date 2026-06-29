from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"
EXECUTIONS = "goal_executions_v49_42"
STEPS = "goal_execution_steps_v49_42"
EVIDENCE = "goal_execution_evidence_v49_42"


def exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def diagnose(details: bool = False) -> dict[str, Any]:
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        tables_ok = all(exists(conn, table) for table in (EXECUTIONS, STEPS, EVIDENCE))
        rows = {}
        if tables_ok:
            for scenario in ("self_test_aligned", "self_test_mismatch", "self_test_internal"):
                row = conn.execute(
                    f"SELECT * FROM {EXECUTIONS} WHERE scenario_kind=? ORDER BY id DESC LIMIT 1",
                    (scenario,),
                ).fetchone()
                rows[scenario] = dict(row) if row else {}
        ids = [row["execution_id"] for row in rows.values() if row]
        steps = [
            dict(row) for row in conn.execute(
                f"SELECT * FROM {STEPS} WHERE execution_id IN ({','.join('?' for _ in ids)})",
                ids,
            ).fetchall()
        ] if ids else []
        evidence = [
            dict(row) for row in conn.execute(
                f"SELECT * FROM {EVIDENCE} WHERE execution_id IN ({','.join('?' for _ in ids)})",
                ids,
            ).fetchall()
        ] if ids else []
    aligned = rows.get("self_test_aligned", {})
    mismatch = rows.get("self_test_mismatch", {})
    internal = rows.get("self_test_internal", {})
    checks = {
        "tables_exist": tables_ok,
        "three_execution_scenarios": all(rows.values()) and len(rows) == 3,
        "aligned_goal_waited_for_outcome": (
            aligned.get("status") == "completed"
            and aligned.get("selected_activity") == aligned.get("target_activity")
            and float(aligned.get("outcome_value", 0)) > 0
        ),
        "mismatch_forced_replanning": (
            mismatch.get("status") == "replanning"
            and mismatch.get("selected_activity") != mismatch.get("target_activity")
        ),
        "internal_goal_completed_without_fake_external_outcome": (
            internal.get("status") == "completed"
            and internal.get("target_activity") == "rest"
            and internal.get("activity_decision_id") == ""
        ),
        "causal_steps_persisted": len(steps) == 9,
        "real_evidence_required": any(
            row["evidence_kind"] == "activity_outcome" and int(row["accepted"]) == 1
            for row in evidence
        ),
        "mismatch_evidence_rejected": any(
            row["evidence_kind"] == "activity_choice" and int(row["accepted"]) == 0
            for row in evidence
        ),
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "executions": rows,
        "steps": steps if details else [],
        "evidence": evidence if details else [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Checker Darwin v49.42 Goal Execution Loop")
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args()
    report = diagnose(args.details)
    print("DARWIN v49.42 - CHECK EXECUCAO DE OBJETIVOS")
    print("=" * 68)
    for name, passed in report["checks"].items():
        print(f"- {name}: {'OK' if passed else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'REVISAR'}")
    if args.details:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
