from __future__ import annotations

import argparse
import json
import math
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"
MODULE = Path("darwin_activity_outcome_learning_v49_39.py")
CHOICE = Path("darwin_autonomous_activity_choice_v49_38.py")
COMPANION = Path("darwin_companion_shell_v49_8.py")
PENDING = "activity_outcome_pending_v49_39"
OUTCOMES = "activity_outcomes_v49_39"
PREFERENCES = "activity_learned_preferences_v49_39"
UPDATES = "activity_preference_updates_v49_39"
SCENARIOS = {
    "self_test_negative_surprise",
    "self_test_positive_surprise",
    "self_test_accurate_prediction",
}
VALID_RZS = {"continue", "narrow_focus", "replay_memory", "consolidate", "pause_for_stability"}


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def diagnose(details: bool = False) -> dict[str, Any]:
    required = (PENDING, OUTCOMES, PREFERENCES, UPDATES)
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        tables_ok = all(table_exists(conn, table) for table in required)
        latest: dict[str, dict[str, Any]] = {}
        updates: dict[str, dict[str, Any]] = {}
        if tables_ok:
            for scenario in SCENARIOS:
                outcome = conn.execute(
                    f"SELECT * FROM {OUTCOMES} WHERE scenario_kind=? ORDER BY id DESC LIMIT 1",
                    (scenario,),
                ).fetchone()
                update = conn.execute(
                    f"SELECT * FROM {UPDATES} WHERE scenario_kind=? ORDER BY id DESC LIMIT 1",
                    (scenario,),
                ).fetchone()
                latest[scenario] = dict(outcome) if outcome else {}
                updates[scenario] = dict(update) if update else {}
        production_updates = conn.execute(
            f"SELECT COUNT(*) AS n FROM {UPDATES} WHERE scenario_kind LIKE 'self_test_%' AND update_applied=1"
        ).fetchone()["n"] if tables_ok else -1

    negative = updates.get("self_test_negative_surprise", {})
    positive = updates.get("self_test_positive_surprise", {})
    accurate = latest.get("self_test_accurate_prediction", {})
    source = MODULE.read_text(encoding="utf-8") if MODULE.exists() else ""
    choice_source = CHOICE.read_text(encoding="utf-8") if CHOICE.exists() else ""
    companion_source = COMPANION.read_text(encoding="utf-8") if COMPANION.exists() else ""
    checks = {
        "tables_exist": tables_ok,
        "three_controlled_outcomes": all(latest.get(name) and updates.get(name) for name in SCENARIOS),
        "negative_surprise_lowers_preference": (
            float(negative.get("observed_value", 1))
            < float(negative.get("preference_before", 0))
            and float(negative.get("preference_after", 1))
            < float(negative.get("preference_before", 0))
        ),
        "positive_surprise_raises_preference": (
            float(positive.get("observed_value", 0))
            > float(positive.get("preference_before", 1))
            and float(positive.get("preference_after", 0))
            > float(positive.get("preference_before", 1))
        ),
        "prediction_error_signed": (
            float(latest["self_test_negative_surprise"].get("prediction_error", 0)) < 0
            and float(latest["self_test_positive_surprise"].get("prediction_error", 0)) > 0
            and abs(float(accurate.get("prediction_error", 1))) <= 0.02
        ),
        "rzs_gates_learning_rate": all(
            row.get("rzs_decision") in VALID_RZS
            and finite(row.get("sigma_before"))
            and finite(row.get("sigma_after"))
            and finite(updates[name].get("learning_rate"))
            for name, row in latest.items()
        ),
        "self_test_did_not_change_live_preference": production_updates == 0,
        "real_completion_sources_declared": all(
            table in source
            for table in (
                "memory_card_games_v49_13",
                "music_nursery_sessions_v49_16",
                "story_nursery_sessions_v49_29",
                "formula_sketch_sessions_v49_28",
            )
        ),
        "choice_arms_and_polls_outcome": (
            "outcome_learning.arm" in choice_source
            and "poll_pending" in choice_source
            and "activity_learned_preferences_v49_39" in choice_source
        ),
        "companion_answers_grounded_reflection": (
            "is_outcome_question" in companion_source
            and "outcome_reflection" in companion_source
        ),
        "operational_not_consciousness_claim": "Nao e uma afirmacao de sentimento ou consciencia" in source,
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "outcomes": latest if details else {},
        "updates": updates if details else {},
        "production_self_test_updates": int(production_updates),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Checker Darwin v49.39 Activity Outcome Learning")
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args()
    report = diagnose(args.details)
    print("DARWIN v49.39 - CHECK APRENDIZAGEM POR RESULTADO")
    print("=" * 68)
    for name, passed in report["checks"].items():
        print(f"- {name}: {'OK' if passed else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'REVISAR'}")
    if args.details:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
