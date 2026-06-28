from __future__ import annotations

import argparse
import json
import math
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"
MODULE = Path("darwin_autonomous_activity_choice_v49_38.py")
SESSIONS = "activity_choice_sessions_v49_38"
CANDIDATES = "activity_choice_candidates_v49_38"
DECISIONS = "activity_choice_decisions_v49_38"
DISPATCHES = "activity_choice_dispatches_v49_38"
EXPECTED = {"memory_cards", "classical_music", "child_story", "formula_sketch", "conversation", "rest"}
VALID_RZS = {"continue", "narrow_focus", "replay_memory", "consolidate", "pause_for_stability"}


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def loads(value: Any, fallback: Any) -> Any:
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def diagnose(details: bool = False) -> dict[str, Any]:
    required = (SESSIONS, CANDIDATES, DECISIONS, DISPATCHES)
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        tables_ok = all(table_exists(conn, table) for table in required)
        latest = {}
        if tables_ok:
            for scenario in ("self_test_baseline", "self_test_low_energy", "self_test_preference_intervention"):
                row = conn.execute(
                    f"SELECT * FROM {DECISIONS} WHERE scenario_kind=? ORDER BY id DESC LIMIT 1", (scenario,)
                ).fetchone()
                latest[scenario] = dict(row) if row else {}
        decision_ids = [str(row.get("decision_id", "")) for row in latest.values() if row]
        candidate_rows = [
            dict(row)
            for row in conn.execute(
                f"SELECT * FROM {CANDIDATES} WHERE decision_id IN ({','.join('?' for _ in decision_ids)}) ORDER BY id",
                decision_ids,
            ).fetchall()
        ] if decision_ids else []
        dispatch_rows = [
            dict(row)
            for row in conn.execute(
                f"SELECT * FROM {DISPATCHES} WHERE decision_id IN ({','.join('?' for _ in decision_ids)}) ORDER BY id",
                decision_ids,
            ).fetchall()
        ] if decision_ids else []

    by_decision: dict[str, list[dict[str, Any]]] = {}
    for row in candidate_rows:
        by_decision.setdefault(str(row["decision_id"]), []).append(row)
    baseline = latest.get("self_test_baseline", {})
    low = latest.get("self_test_low_energy", {})
    preference = latest.get("self_test_preference_intervention", {})
    baseline_rows = by_decision.get(str(baseline.get("decision_id", "")), [])
    low_rows = by_decision.get(str(low.get("decision_id", "")), [])
    pref_rows = by_decision.get(str(preference.get("decision_id", "")), [])

    def row_for(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
        return next((row for row in rows if row["activity_key"] == key), {})

    source_tables = {
        source
        for row in baseline_rows
        for source in loads(row.get("source_tables_json"), [])
        if isinstance(source, str)
    }
    source_code = MODULE.read_text(encoding="utf-8") if MODULE.exists() else ""
    selected_keys = {str(row.get("selected_key", "")) for row in latest.values() if row}
    checks = {
        "tables_exist": tables_ok,
        "three_counterfactual_scenarios": len(latest) == 3 and all(latest.values()),
        "all_six_candidates_competed": all({row["activity_key"] for row in rows} == EXPECTED for rows in by_decision.values()),
        "utilities_are_not_fixed_equal": len({round(float(row["utility"]), 6) for row in baseline_rows}) >= 4,
        "winner_is_regulated_argmax": all(
            rows
            and str(decision.get("selected_key")) == max(rows, key=lambda row: float(row["regulated_utility"]))["activity_key"]
            for scenario, decision in latest.items()
            for rows in [by_decision.get(str(decision.get("decision_id", "")), [])]
        ),
        "real_memories_ground_choice": len(source_tables) >= 3,
        "rzs_causally_audited": all(
            row.get("rzs_decision") in VALID_RZS
            and finite(row.get("sigma_before"))
            and finite(row.get("sigma_after"))
            and float(row["sigma_after"]) >= float(row["sigma_before"]) - 0.11
            for row in latest.values()
        ),
        "low_energy_changes_policy": (
            low.get("rzs_decision") in {"pause_for_stability", "consolidate"}
            and low.get("selected_key") in {"rest", "classical_music", "child_story"}
            and low.get("selected_key") != baseline.get("selected_key")
        ),
        "preference_evidence_changes_choice": (
            preference.get("selected_key") == "classical_music"
            and float(row_for(pref_rows, "classical_music").get("utility", -1))
            > float(row_for(baseline_rows, "classical_music").get("utility", 2))
        ),
        "same_invitation_not_fixed_mapping": len(selected_keys) >= 2,
        "invitation_never_forced_choice": all(int(row.get("invitation_forced_choice", 1)) == 0 for row in latest.values()),
        "self_test_never_launched_process": len(dispatch_rows) == 3 and all(int(row["launched"]) == 0 for row in dispatch_rows),
        "launch_uses_allowlist_without_shell": (
            "shell=False" in source_code
            and "allowed_names" in source_code
            and "INVITATION_PATTERNS" in source_code
        ),
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "selections": {scenario: row.get("selected_key", "") for scenario, row in latest.items()},
        "rzs": {scenario: row.get("rzs_decision", "") for scenario, row in latest.items()},
        "source_tables": sorted(source_tables),
        "decisions": latest if details else {},
        "candidates": candidate_rows if details else [],
        "dispatches": dispatch_rows if details else [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Checker Darwin v49.38 Activity Choice")
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args()
    report = diagnose(args.details)
    print("DARWIN v49.38 - CHECK ESCOLHA AUTONOMA DE ATIVIDADE")
    print("=" * 68)
    print(f"- escolhas: {report['selections']}")
    print(f"- RZS: {report['rzs']}")
    print(f"- fontes reais: {', '.join(report['source_tables'])}")
    for name, passed in report["checks"].items():
        print(f"- {name}: {'OK' if passed else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'REVISAR'}")
    if args.details:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
