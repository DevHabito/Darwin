from __future__ import annotations

"""
DARWIN v49.20 - Diagnostico do Sleep & Consolidation Core

Uso:
    py darwin_check_v49_20_sleep.py
    py darwin_check_v49_20_sleep.py --details
"""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"

SL_SESSIONS = "sleep_sessions_v49_20"
SL_PHASES = "sleep_phase_events_v49_20"
SL_REPLAY = "sleep_replay_items_v49_20"
SL_DREAMS = "sleep_dream_sequences_v49_20"
SL_CONSOLIDATIONS = "sleep_consolidations_v49_20"
SL_WAKE_PLANS = "sleep_wake_plans_v49_20"
SOURCE = "darwin_sleep_consolidation_core_v49_20"

EXPECTED_PHASES = [
    "pre_sleep_scan",
    "commitment_replay",
    "autobiography_replay",
    "dream_simulation",
    "memory_weight_update",
    "identity_consolidation",
    "wake_plan",
]


def pj(value: str | None, fallback: Any = None) -> Any:
    try:
        return json.loads(value or "{}")
    except Exception:
        return {} if fallback is None else fallback


def connect() -> sqlite3.Connection:
    if not DB.exists():
        raise FileNotFoundError(f"Banco Darwin nao encontrado: {DB}")
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


def rows(conn: sqlite3.Connection, table: str, where: str = "", params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    if not table_exists(conn, table):
        return []
    out = []
    for row in conn.execute(f"SELECT * FROM {table}{where} ORDER BY id ASC", params).fetchall():
        item = {k: row[k] for k in row.keys()}
        item["payload"] = pj(str(item.get("payload_json") or "{}"))
        if "fragments_json" in item:
            item["fragments"] = pj(str(item.get("fragments_json") or "[]"), [])
        out.append(item)
    return out


def latest_completed_session(conn: sqlite3.Connection) -> tuple[str, dict[str, Any]]:
    session_rows = rows(conn, SL_SESSIONS)
    completed = [
        r
        for r in session_rows
        if r.get("phase") == "session_complete" and r.get("payload", {}).get("session_complete") is True
    ]
    if not completed:
        return "", {}
    row = completed[-1]
    return str(row["session_id"]), row


def semantic_written(conn: sqlite3.Connection, session_id: str) -> bool:
    if not table_exists(conn, "semantic_memory"):
        return False
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM semantic_memory
        WHERE source=? AND key=?
        """,
        (SOURCE, f"sleep_consolidation_v49_20:{session_id}"),
    ).fetchone()
    return bool(row and int(row["n"]) >= 1)


def episode_written(conn: sqlite3.Connection, session_id: str) -> bool:
    if not table_exists(conn, "episodes"):
        return False
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM episodes
        WHERE module=? AND context=?
        """,
        (SOURCE, f"sleep_consolidation:{session_id}"),
    ).fetchone()
    return bool(row and int(row["n"]) >= 1)


def phases_ok(phases: list[dict[str, Any]]) -> bool:
    if len(phases) != len(EXPECTED_PHASES):
        return False
    names = [str(p.get("phase") or "") for p in phases]
    indices = [int(p.get("phase_index") or 0) for p in phases]
    if names != EXPECTED_PHASES:
        return False
    if indices != list(range(1, len(EXPECTED_PHASES) + 1)):
        return False
    for phase in phases:
        if float(phase.get("sigma_before") or 0.0) <= 0.0:
            return False
        if float(phase.get("sigma_after") or 0.0) <= 0.0:
            return False
        if float(phase.get("energy_after") or 0.0) < float(phase.get("energy_before") or 0.0):
            return False
    return True


def replay_ok(replays: list[dict[str, Any]]) -> bool:
    if len(replays) < 6:
        return False
    kinds = {str(r.get("source_kind") or "") for r in replays}
    required = {"agency_commitment", "autobiography_chapter", "affective_preference"}
    if not required.issubset(kinds):
        return False
    for replay in replays:
        before = float(replay.get("salience_before") or 0.0)
        after = float(replay.get("salience_after") or 0.0)
        if not (0.0 <= before <= 1.0 and 0.0 <= after <= 1.0 and after >= before):
            return False
        if not str(replay.get("replay_reason") or ""):
            return False
    return True


def dreams_ok(dreams: list[dict[str, Any]]) -> bool:
    if len(dreams) < 2:
        return False
    for dream in dreams:
        integration = float(dream.get("integration_score") or 0.0)
        if integration <= 0.0 or integration > 1.0:
            return False
        if not dream.get("fragments"):
            return False
        if not str(dream.get("predicted_wake_effect") or ""):
            return False
    return True


def consolidation_ok(consolidations: list[dict[str, Any]]) -> bool:
    if not consolidations:
        return False
    item = consolidations[-1]
    if float(item.get("memory_delta") or 0.0) <= 0.05:
        return False
    if float(item.get("stability_gain") or 0.0) <= 0.05:
        return False
    if float(item.get("noise_reduction") or 0.0) <= 0.02:
        return False
    return bool(str(item.get("consolidated_focus") or "")) and bool(str(item.get("lesson") or ""))


def wake_plan_ok(plans: list[dict[str, Any]]) -> bool:
    if not plans:
        return False
    item = plans[-1]
    if not str(item.get("next_action") or ""):
        return False
    if not str(item.get("trigger") or ""):
        return False
    if float(item.get("confidence") or 0.0) < 0.65:
        return False
    if float(item.get("sigma_after") or 0.0) <= float(item.get("sigma_before") or 0.0):
        return False
    return bool(str(item.get("plan_summary") or ""))


def v49_19_present(conn: sqlite3.Connection) -> bool:
    required = ["agency_commitments_v49_19", "agency_outcomes_v49_19"]
    if not all(table_exists(conn, t) for t in required):
        return False
    row = conn.execute("SELECT COUNT(*) AS n FROM agency_commitments_v49_19").fetchone()
    return bool(row and int(row["n"]) >= 1)


def build_report(conn: sqlite3.Connection) -> dict[str, Any]:
    session_id, complete_row = latest_completed_session(conn)
    phases = rows(conn, SL_PHASES, " WHERE session_id=?", (session_id,)) if session_id else []
    replays = rows(conn, SL_REPLAY, " WHERE session_id=?", (session_id,)) if session_id else []
    dreams = rows(conn, SL_DREAMS, " WHERE session_id=?", (session_id,)) if session_id else []
    consolidations = rows(conn, SL_CONSOLIDATIONS, " WHERE session_id=?", (session_id,)) if session_id else []
    wake_plans = rows(conn, SL_WAKE_PLANS, " WHERE session_id=?", (session_id,)) if session_id else []
    payload = complete_row.get("payload", {}) if complete_row else {}
    replay_kinds = sorted({str(r.get("source_kind") or "") for r in replays})
    phase_decisions = sorted({str(p.get("rzs_decision") or "") for p in phases})
    latest_consolidation = consolidations[-1] if consolidations else {}
    latest_plan = wake_plans[-1] if wake_plans else {}

    checks = {
        "tables_exist": all(table_exists(conn, t) for t in (SL_SESSIONS, SL_PHASES, SL_REPLAY, SL_DREAMS, SL_CONSOLIDATIONS, SL_WAKE_PLANS)),
        "completed_session": bool(session_id) and bool(payload.get("session_complete")),
        "phases_in_order": phases_ok(phases),
        "replay_items_written": replay_ok(replays),
        "dreams_written": dreams_ok(dreams),
        "consolidation_written": consolidation_ok(consolidations),
        "wake_plan_written": wake_plan_ok(wake_plans),
        "rzs_logged": bool(phase_decisions) and all(float(p.get("sigma_before") or 0.0) > 0.0 for p in phases),
        "semantic_memory_written": semantic_written(conn, session_id) if session_id else False,
        "episode_written": episode_written(conn, session_id) if session_id else False,
        "v49_19_data_still_present": v49_19_present(conn),
    }
    return {
        "ok": all(checks.values()),
        "session_id": session_id,
        "checks": checks,
        "counts": {
            "phases": len(phases),
            "replays": len(replays),
            "dreams": len(dreams),
            "consolidations": len(consolidations),
            "wake_plans": len(wake_plans),
        },
        "phase_names": [str(p.get("phase") or "") for p in phases],
        "rzs_decisions": phase_decisions,
        "replay_kinds": replay_kinds,
        "consolidation": {
            "focus": latest_consolidation.get("consolidated_focus", ""),
            "memory_delta": round(float(latest_consolidation.get("memory_delta") or 0.0), 3) if latest_consolidation else 0.0,
            "stability_gain": round(float(latest_consolidation.get("stability_gain") or 0.0), 3) if latest_consolidation else 0.0,
            "noise_reduction": round(float(latest_consolidation.get("noise_reduction") or 0.0), 3) if latest_consolidation else 0.0,
        },
        "wake_plan": {
            "next_action": latest_plan.get("next_action", ""),
            "trigger": latest_plan.get("trigger", ""),
            "confidence": round(float(latest_plan.get("confidence") or 0.0), 3) if latest_plan else 0.0,
            "rzs_decision": latest_plan.get("rzs_decision", ""),
            "sigma_before": round(float(latest_plan.get("sigma_before") or 0.0), 3) if latest_plan else 0.0,
            "sigma_after": round(float(latest_plan.get("sigma_after") or 0.0), 3) if latest_plan else 0.0,
        },
        "payload": payload,
    }


def print_report(report: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.20 - DIAGNOSTICO SLEEP CORE")
    print("=" * 58)
    print(f"- sessao: {report['session_id'] or 'NENHUMA'}")
    c = report["counts"]
    print(f"- fases={c['phases']} replays={c['replays']} sonhos={c['dreams']} consolidacoes={c['consolidations']} planos={c['wake_plans']}")
    print(f"- RZS: {', '.join(report['rzs_decisions']) if report['rzs_decisions'] else 'nenhum'}")
    print(f"- replay: {', '.join(report['replay_kinds']) if report['replay_kinds'] else 'nenhum'}")
    print(f"- acordar: {report['wake_plan']['next_action'] or 'nenhum'}")
    print()
    labels = {
        "tables_exist": "tabelas v49.20 existem",
        "completed_session": "sessao completa encontrada",
        "phases_in_order": "fases de sono em ordem",
        "replay_items_written": "replays escritos",
        "dreams_written": "sonhos internos escritos",
        "consolidation_written": "consolidacao escrita",
        "wake_plan_written": "plano de acordar escrito",
        "rzs_logged": "RZS registrado",
        "semantic_memory_written": "memoria semantica escrita",
        "episode_written": "episodio escrito",
        "v49_19_data_still_present": "dados v49.19 ainda presentes",
    }
    for key, value in report["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'FALHOU'}")
    if report["ok"]:
        print("Leitura: Darwin fez replay, sonho interno, consolidacao e plano de acordar.")
    else:
        print("Leitura: ainda falta evidencia para aceitar sono cognitivo como marco estavel.")
    if details:
        print("\nJSON:")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.20 Sleep checker")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    with connect() as conn:
        report = build_report(conn)
    print_report(report, args.details)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
