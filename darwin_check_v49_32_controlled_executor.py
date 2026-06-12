from __future__ import annotations

"""
DARWIN v49.32 - Diagnostico Controlled Autonomous Executor

Uso:
    py darwin_check_v49_32_controlled_executor.py
    py darwin_check_v49_32_controlled_executor.py --details
"""

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"
SOURCE = "darwin_controlled_autonomous_executor_v49_32"

EX_SESSIONS = "controlled_executor_sessions_v49_32"
EX_ALLOWLIST = "executor_allowed_modules_v49_32"
EX_QUEUE = "executor_queue_v49_32"
EX_SAFETY = "executor_safety_checks_v49_32"
EX_DISPATCH = "executor_dispatches_v49_32"
EX_MONITOR = "executor_monitors_v49_32"
EX_REFLECTIONS = "executor_reflections_v49_32"
EX_HANDOFFS = "executor_handoffs_v49_32"

REQUIRED_TABLES = [
    EX_SESSIONS,
    EX_ALLOWLIST,
    EX_QUEUE,
    EX_SAFETY,
    EX_DISPATCH,
    EX_MONITOR,
    EX_REFLECTIONS,
    EX_HANDOFFS,
]

EXPECTED_MODULES = {
    "formula_sketch",
    "child_story",
    "classical_music",
    "memory_cards",
    "first_words",
    "self_review",
    "preference_choice",
    "geometry_error",
    "voice_presence",
}

PRIOR_TABLES = [
    "autonomous_curriculum_sessions_v49_31",
    "curriculum_choices_v49_31",
    "learning_to_learn_sessions_v49_30",
    "affective_preferences_v49_17",
    "formula_sketch_sessions_v49_28",
    "story_nursery_sessions_v49_29",
    "music_reactions_v49_16",
    "memory_card_sessions_v49_13",
    "voice_first_word_nodes_v49_10",
]


def pj(value: str | None, fallback: Any = None) -> Any:
    try:
        parsed = json.loads(value or "{}")
    except Exception:
        return {} if fallback is None else fallback
    if fallback is not None and isinstance(fallback, dict) and not isinstance(parsed, dict):
        return fallback
    if fallback is not None and isinstance(fallback, list) and not isinstance(parsed, list):
        return fallback
    return parsed


def number(value: Any, fallback: float = 0.0) -> float:
    if value is None:
        return fallback
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def connect() -> sqlite3.Connection:
    if not DB.exists():
        raise FileNotFoundError(f"Banco Darwin nao encontrado: {DB}")
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


def rows(conn: sqlite3.Connection, table: str, session_id: str | None = None) -> list[dict[str, Any]]:
    if not table_exists(conn, table):
        return []
    where = ""
    params: tuple[Any, ...] = ()
    if session_id is not None:
        where = " WHERE session_id=?"
        params = (session_id,)
    out = []
    for row in conn.execute(f"SELECT * FROM {table}{where} ORDER BY id ASC", params).fetchall():
        item = {k: row[k] for k in row.keys()}
        if "payload_json" in item:
            item["payload"] = pj(str(item.get("payload_json") or "{}"), {})
        if "command_json" in item:
            item["command"] = pj(str(item.get("command_json") or "[]"), [])
        out.append(item)
    return out


def latest_completed(conn: sqlite3.Connection) -> tuple[str, dict[str, Any]]:
    completed = [
        r
        for r in rows(conn, EX_SESSIONS)
        if r.get("phase") == "executor_complete" and r.get("payload", {}).get("session_complete") is True
    ]
    if not completed:
        return "", {}
    row = completed[-1]
    return str(row["session_id"]), row


def semantic_count(conn: sqlite3.Connection, session_id: str) -> int:
    if not table_exists(conn, "semantic_memory"):
        return 0
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM semantic_memory
        WHERE source=? AND key=?
        """,
        (SOURCE, f"controlled_executor_v49_32:{session_id}"),
    ).fetchone()
    return int(row["n"]) if row else 0


def episode_count(conn: sqlite3.Connection, session_id: str) -> int:
    if not table_exists(conn, "episodes"):
        return 0
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM episodes
        WHERE module=? AND context=?
        """,
        (SOURCE, f"controlled_executor:{session_id}"),
    ).fetchone()
    return int(row["n"]) if row else 0


def prior_count(conn: sqlite3.Connection, table: str) -> int:
    if not table_exists(conn, table):
        return 0
    row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
    return int(row["n"]) if row else 0


def allowlist_ok(allowlist: list[dict[str, Any]]) -> bool:
    modules = {str(r.get("module_key")) for r in allowlist if r.get("module_key")}
    if not EXPECTED_MODULES.issubset(modules):
        return False
    for row in allowlist:
        script = str(row.get("script_name") or "")
        if not script.endswith(".py") or "\\" in script or "/" in script:
            return False
        if int(row.get("script_exists") or 0) != 1:
            return False
        if int(row.get("allow_self_test_simulation") or 0) != 1:
            return False
        if number(row.get("max_runtime_seconds"), 0.0) <= 0:
            return False
        payload = row.get("payload", {})
        if payload.get("no_shell") is not True:
            return False
    return True


def queue_ok(queue: list[dict[str, Any]], allowlist: list[dict[str, Any]]) -> bool:
    allowed_modules = {str(r.get("module_key")) for r in allowlist}
    if len(queue) < 8:
        return False
    modules = {str(q.get("module_key")) for q in queue if q.get("module_key")}
    if len(modules) < 4 or not modules.issubset(allowed_modules):
        return False
    for item in queue:
        if not str(item.get("source_curriculum_session_id") or "") or not str(item.get("source_choice_id") or ""):
            return False
        if not 0.0 <= number(item.get("priority_score"), -1.0) <= 1.0:
            return False
        if not 0.0 <= number(item.get("expected_gain"), -1.0) <= 1.0:
            return False
        if item.get("payload", {}).get("source_phase") != "v49_31_curriculum_choice":
            return False
    return True


def safety_ok(safety_rows: list[dict[str, Any]], queue: list[dict[str, Any]]) -> bool:
    if len(safety_rows) < len(queue):
        return False
    for item in safety_rows:
        if int(item.get("allowed") or 0) != 1:
            return False
        if int(item.get("script_exists") or 0) != 1:
            return False
        if int(item.get("simulation_only") or 0) != 1:
            return False
        if int(item.get("single_process_guard") or 0) != 1:
            return False
        if str(item.get("decision") or "") != "allow_simulated_dispatch":
            return False
        if not 0.0 <= number(item.get("risk_score"), -1.0) <= 1.0:
            return False
    return True


def dispatch_ok(dispatches: list[dict[str, Any]], allowlist: list[dict[str, Any]]) -> bool:
    if len(dispatches) < 8:
        return False
    allowed_scripts = {str(r.get("script_name")) for r in allowlist}
    decisions = {str(d.get("rzs_decision")) for d in dispatches if d.get("rzs_decision")}
    if len(decisions) < 2 or not any(d != "continue" for d in decisions):
        return False
    for item in dispatches:
        command = item.get("command", [])
        if str(item.get("dispatch_mode") or "") != "simulated":
            return False
        if str(item.get("status") or "") != "simulated_complete":
            return False
        if int(item.get("live_pid") or 0) != 0:
            return False
        if len(command) != 2 or str(command[1]) not in allowed_scripts:
            return False
        if str(item.get("script_name") or "") not in allowed_scripts:
            return False
        if number(item.get("sigma_before")) <= 0.0 or number(item.get("sigma_after")) <= 0.0:
            return False
        action = str(item.get("execution_action") or "")
        decision = str(item.get("rzs_decision") or "")
        if decision == "continue" and not action.startswith("open_"):
            return False
        if decision == "replay_memory" and not action.startswith("replay_context_then_open_"):
            return False
        if decision == "narrow_focus" and "_with_focus_guard" not in action:
            return False
        if item.get("payload", {}).get("self_test_never_launches_process") is not True:
            return False
    return True


def monitor_ok(monitors: list[dict[str, Any]], dispatches: list[dict[str, Any]]) -> bool:
    if len(monitors) < len(dispatches):
        return False
    for item in monitors:
        if str(item.get("monitor_status") or "") != "simulated_stable":
            return False
        if not 0.0 <= number(item.get("stability"), -1.0) <= 1.0:
            return False
        if not 0.0 <= number(item.get("energy_after"), -1.0) <= 1.0:
            return False
        if not str(item.get("observed_outcome") or ""):
            return False
    return True


def phase_order_ok(events: list[dict[str, Any]], dispatches: list[dict[str, Any]], monitors: list[dict[str, Any]]) -> bool:
    if not events:
        return False
    phases_zero = [str(e.get("phase") or "") for e in events if int(e.get("step_index") or 0) == 0]
    required_start = ["executor_start", "allowlist_loaded", "queue_built"]
    if not all(phase in phases_zero for phase in required_start):
        return False
    by_step: dict[int, list[str]] = {}
    for event in events:
        step = int(event.get("step_index") or 0)
        by_step.setdefault(step, []).append(str(event.get("phase") or ""))
    dispatch_steps = {int(d.get("step_index") or 0) for d in dispatches}
    monitor_steps = {int(m.get("step_index") or 0) for m in monitors}
    if dispatch_steps != monitor_steps:
        return False
    for step in sorted(dispatch_steps):
        phases = by_step.get(step, [])
        try:
            decision_i = phases.index("execution_decision")
            dispatch_i = phases.index("execution_dispatch")
            monitor_i = phases.index("execution_monitor")
        except ValueError:
            return False
        if not (decision_i < dispatch_i < monitor_i):
            return False
    last_step = max(dispatch_steps) if dispatch_steps else 0
    return "executor_complete" in by_step.get(last_step, [])


def build_report(conn: sqlite3.Connection) -> dict[str, Any]:
    session_id, complete_row = latest_completed(conn)
    session_events = rows(conn, EX_SESSIONS, session_id) if session_id else []
    allowlist = rows(conn, EX_ALLOWLIST, session_id) if session_id else []
    queue = rows(conn, EX_QUEUE, session_id) if session_id else []
    safety = rows(conn, EX_SAFETY, session_id) if session_id else []
    dispatches = rows(conn, EX_DISPATCH, session_id) if session_id else []
    monitors = rows(conn, EX_MONITOR, session_id) if session_id else []
    reflections = rows(conn, EX_REFLECTIONS, session_id) if session_id else []
    handoffs = rows(conn, EX_HANDOFFS, session_id) if session_id else []
    payload = complete_row.get("payload", {}) if complete_row else {}

    modules = {str(d.get("module_key")) for d in dispatches if d.get("module_key")}
    decisions = {str(d.get("rzs_decision")) for d in dispatches if d.get("rzs_decision")}
    modes = {str(d.get("dispatch_mode")) for d in dispatches if d.get("dispatch_mode")}
    reflection_kinds = {str(r.get("reflection_kind")) for r in reflections if r.get("reflection_kind")}
    handoff = handoffs[-1] if handoffs else {}
    protected_sources_unchanged = bool(payload.get("protected_sources_unchanged"))
    if not protected_sources_unchanged:
        before = payload.get("protected_counts_before", {})
        after = payload.get("protected_counts_after", {})
        protected_sources_unchanged = bool(before and before == after)

    checks = {
        "tables_exist": all(table_exists(conn, t) for t in REQUIRED_TABLES),
        "completed_session": bool(session_id) and bool(payload.get("session_complete")) and bool(payload.get("controlled_executor_ready")),
        "allowlist_valid": allowlist_ok(allowlist),
        "queue_from_curriculum": queue_ok(queue, allowlist),
        "safety_gate_passed": safety_ok(safety, queue),
        "dispatches_simulated_only": dispatch_ok(dispatches, allowlist),
        "rzs_influenced_dispatch": len(decisions) >= 2 and any(d != "continue" for d in decisions),
        "monitors_stable": monitor_ok(monitors, dispatches),
        "phase_order_valid": phase_order_ok(session_events, dispatches, monitors),
        "reflections_written": len(reflections) >= len(dispatches) + 2 and {"controlled_executor_summary", "epistemic_boundary"}.issubset(reflection_kinds),
        "handoff_written": bool(handoff) and int(handoff.get("controlled_executor_ready") or 0) == 1 and int(handoff.get("safe_dispatch_count") or 0) >= 8,
        "semantic_memory_written": semantic_count(conn, session_id) >= 1 if session_id else False,
        "episode_written": episode_count(conn, session_id) >= 1 if session_id else False,
        "prior_data_still_present": all(prior_count(conn, table) > 0 for table in PRIOR_TABLES),
        "protected_sources_unchanged": protected_sources_unchanged,
    }
    return {
        "ok": all(checks.values()),
        "session_id": session_id,
        "checks": checks,
        "counts": {
            "session_events": len(session_events),
            "allowlist": len(allowlist),
            "queue": len(queue),
            "safety": len(safety),
            "dispatches": len(dispatches),
            "monitors": len(monitors),
            "reflections": len(reflections),
            "handoffs": len(handoffs),
            "semantic": semantic_count(conn, session_id) if session_id else 0,
            "episodes": episode_count(conn, session_id) if session_id else 0,
        },
        "modules": sorted(modules),
        "module_counts": dict(Counter([str(d.get("module_key")) for d in dispatches if d.get("module_key")])),
        "decisions": sorted(decisions),
        "dispatch_modes": sorted(modes),
        "reflection_kinds": sorted(reflection_kinds),
        "executor": {
            "curriculum_session_id": str(payload.get("curriculum_session_id") or ""),
            "avg_monitor_stability": number(payload.get("avg_monitor_stability"), 0.0),
            "final_energy": number(payload.get("final_energy"), 0.0),
            "live_launch_count": int(payload.get("live_launch_count") or 0),
            "self_test_simulation_only": bool(payload.get("self_test_simulation_only")),
            "safe_dispatch_count": int(payload.get("safe_dispatch_count") or 0),
        },
        "handoff": {
            "next_action": handoff.get("next_action", ""),
            "controlled_executor_ready": bool(int(handoff.get("controlled_executor_ready") or 0)) if handoff else False,
            "safe_dispatch_count": int(handoff.get("safe_dispatch_count") or 0) if handoff else 0,
            "confidence": number(handoff.get("confidence"), 0.0) if handoff else 0.0,
        },
        "payload": payload,
    }


def print_report(report: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.32 - DIAGNOSTICO CONTROLLED AUTONOMOUS EXECUTOR")
    print("=" * 78)
    print(f"- sessao: {report['session_id'] or 'NENHUMA'}")
    c = report["counts"]
    print(
        f"- allowlist={c['allowlist']} fila={c['queue']} safety={c['safety']} "
        f"dispatches={c['dispatches']} monitors={c['monitors']}"
    )
    ex = report["executor"]
    print(
        f"- curriculo={ex['curriculum_session_id'] or 'nenhum'} estabilidade={ex['avg_monitor_stability']:.3f} "
        f"live_launches={ex['live_launch_count']}"
    )
    print(f"- modulos: {', '.join(report['modules']) if report['modules'] else 'nenhum'}")
    print(f"- modos: {', '.join(report['dispatch_modes']) if report['dispatch_modes'] else 'nenhum'}")
    print(f"- RZS: {', '.join(report['decisions']) if report['decisions'] else 'nenhum'}")
    print()
    labels = {
        "tables_exist": "tabelas v49.32 existem",
        "completed_session": "sessao completa e pronta",
        "allowlist_valid": "allowlist valida",
        "queue_from_curriculum": "fila veio do curriculo v49.31",
        "safety_gate_passed": "safety gate passou",
        "dispatches_simulated_only": "self-test nao abriu processo real",
        "rzs_influenced_dispatch": "RZS influenciou dispatch",
        "monitors_stable": "monitores estaveis",
        "phase_order_valid": "ordem causal das fases valida",
        "reflections_written": "reflexoes escritas",
        "handoff_written": "handoff escrito",
        "semantic_memory_written": "memoria semantica escrita",
        "episode_written": "episodio escrito",
        "prior_data_still_present": "dados anteriores ainda presentes",
        "protected_sources_unchanged": "fontes anteriores preservadas",
    }
    for key, value in report["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'FALHOU'}")
    if report["ok"]:
        print("Leitura: Darwin despachou treinos escolhidos com allowlist, safety gate, RZS e monitoramento.")
    else:
        print("Leitura: ainda falta evidencia para aceitar o executor controlado como marco completo.")
    if details:
        print("\nJSON:")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.32 Controlled Executor checker")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    with connect() as conn:
        report = build_report(conn)
    print_report(report, args.details)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
