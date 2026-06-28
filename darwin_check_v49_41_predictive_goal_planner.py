from __future__ import annotations

import argparse
import json
import math
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"
CANDIDATES = "goal_candidates_v49_41"
DECISIONS = "goal_decisions_v49_41"
PLANS = "goal_plans_v49_41"
SCENARIOS = (
    "self_test_baseline",
    "self_test_low_energy",
    "self_test_uncertainty",
    "self_test_negative_surprise",
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
        tables_ok = all(exists(conn, table) for table in (CANDIDATES, DECISIONS, PLANS))
        decisions = {}
        if tables_ok:
            for scenario in SCENARIOS:
                row = conn.execute(
                    f"SELECT * FROM {DECISIONS} WHERE scenario_kind=? ORDER BY id DESC LIMIT 1",
                    (scenario,),
                ).fetchone()
                decisions[scenario] = dict(row) if row else {}
        ids = [row["decision_id"] for row in decisions.values() if row]
        candidate_rows = [
            dict(row) for row in conn.execute(
                f"SELECT * FROM {CANDIDATES} WHERE decision_id IN ({','.join('?' for _ in ids)})",
                ids,
            ).fetchall()
        ] if ids else []
        plan_rows = [
            dict(row) for row in conn.execute(
                f"SELECT * FROM {PLANS} WHERE decision_id IN ({','.join('?' for _ in ids)})",
                ids,
            ).fetchall()
        ] if ids else []
    checks = {
        "tables_exist": tables_ok,
        "four_intervention_scenarios": all(decisions.values()) and len(decisions) == 4,
        "multiple_goals_competed": len(candidate_rows) == 20,
        "low_energy_selects_stability": decisions.get("self_test_low_energy", {}).get("goal_key") == "restore_stability",
        "uncertainty_selects_information_goal": (
            decisions.get("self_test_uncertainty", {}).get("goal_key") == "reduce_world_uncertainty"
            and decisions.get("self_test_uncertainty", {}).get("target_activity") == "formula_sketch"
        ),
        "negative_surprise_selects_repair": (
            decisions.get("self_test_negative_surprise", {}).get("goal_key") == "repair_prediction_error"
            and decisions.get("self_test_negative_surprise", {}).get("target_activity") == "memory_cards"
        ),
        "plans_have_causal_steps_and_stop": all(
            len([row for row in plan_rows if row["decision_id"] == decision["decision_id"]]) == 3
            and all(row["stop_condition"] for row in plan_rows if row["decision_id"] == decision["decision_id"])
            for decision in decisions.values()
        ),
        "rzs_governs_goals": all(
            row.get("rzs_decision") in VALID_RZS
            and finite(row.get("sigma_before"))
            and finite(row.get("sigma_after"))
            for row in decisions.values()
        ),
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "decisions": decisions,
        "candidates": candidate_rows if details else [],
        "plans": plan_rows if details else [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Checker Darwin v49.41 Predictive Goal Planner")
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args()
    report = diagnose(args.details)
    print("DARWIN v49.41 - CHECK OBJETIVOS E PLANEJAMENTO")
    print("=" * 68)
    for name, passed in report["checks"].items():
        print(f"- {name}: {'OK' if passed else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'REVISAR'}")
    if args.details:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
