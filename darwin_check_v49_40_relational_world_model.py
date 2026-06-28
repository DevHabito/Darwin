from __future__ import annotations

import argparse
import json
import math
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"
MODULE = Path("darwin_relational_world_model_v49_40.py")
CHOICE = Path("darwin_autonomous_activity_choice_v49_38.py")
EXPERIENCES = "world_experiences_v49_40"
RELATIONS = "world_relations_v49_40"
PREDICTIONS = "world_predictions_v49_40"
TRANSFERS = "world_transfer_tests_v49_40"
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
    required = (EXPERIENCES, RELATIONS, PREDICTIONS, TRANSFERS)
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        tables_ok = all(exists(conn, table) for table in required)
        experiences = [dict(row) for row in conn.execute(f"SELECT * FROM {EXPERIENCES}").fetchall()] if tables_ok else []
        relations = [dict(row) for row in conn.execute(f"SELECT * FROM {RELATIONS}").fetchall()] if tables_ok else []
        transfer_row = conn.execute(f"SELECT * FROM {TRANSFERS} ORDER BY id DESC LIMIT 1").fetchone() if tables_ok else None
        transfer = dict(transfer_row) if transfer_row else {}
        predictions = [dict(row) for row in conn.execute(
            f"SELECT * FROM {PREDICTIONS} WHERE scenario_kind LIKE 'self_test_%' ORDER BY id DESC LIMIT 2"
        ).fetchall()] if tables_ok else []
    domains = {str(item.get("domain")) for item in experiences}
    sources = {str(item.get("source_table")) for item in experiences}
    module_source = MODULE.read_text(encoding="utf-8") if MODULE.exists() else ""
    choice_source = CHOICE.read_text(encoding="utf-8") if CHOICE.exists() else ""
    checks = {
        "tables_exist": tables_ok,
        "multiple_real_domains_normalized": len(domains) >= 4 and len(sources) >= 4,
        "common_feature_language": all(
            key in module_source
            for key in ("memory", "symbolic", "auditory", "narrative", "creative", "social", "calm", "cognitive_load")
        ),
        "relations_learned_from_evidence": len(relations) == 8 and all(int(row["evidence_count"]) >= 4 for row in relations),
        "held_out_transfer_beats_mean_baseline": (
            bool(transfer)
            and float(transfer["model_error"]) < float(transfer["baseline_error"])
            and float(transfer["transfer_gain"]) > 0.0
        ),
        "counterfactual_changes_prediction": (
            bool(transfer)
            and abs(float(transfer["counterfactual_value"]) - float(transfer["predicted_value"])) >= 0.02
        ),
        "cross_domain_contributors": (
            bool(transfer)
            and len(json.loads(transfer["training_domains_json"])) >= 4
        ),
        "predictions_rzs_audited": (
            len(predictions) == 2
            and all(
                row["rzs_decision"] in VALID_RZS
                and finite(row["sigma_before"])
                and finite(row["sigma_after"])
                for row in predictions
            )
        ),
        "world_prediction_influences_choice": (
            "RelationalWorldModel" in choice_source
            and "world_prediction" in choice_source
            and "predict_activity" in choice_source
        ),
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "domains": sorted(domains),
        "sources": sorted(sources),
        "transfer": transfer,
        "experiences": experiences if details else [],
        "relations": relations if details else [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Checker Darwin v49.40 Relational World Model")
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args()
    report = diagnose(args.details)
    print("DARWIN v49.40 - CHECK MODELO DE MUNDO RELACIONAL")
    print("=" * 68)
    print(f"- dominios reais: {', '.join(report['domains'])}")
    for name, passed in report["checks"].items():
        print(f"- {name}: {'OK' if passed else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'REVISAR'}")
    if args.details:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
