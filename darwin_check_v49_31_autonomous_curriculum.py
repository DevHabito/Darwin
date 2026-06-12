from __future__ import annotations

"""
DARWIN v49.31 - Diagnostico Autonomous Curriculum

Uso:
    py darwin_check_v49_31_autonomous_curriculum.py
    py darwin_check_v49_31_autonomous_curriculum.py --details
"""

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"
SOURCE = "darwin_autonomous_curriculum_v49_31"

AC_SESSIONS = "autonomous_curriculum_sessions_v49_31"
AC_CANDIDATES = "curriculum_candidates_v49_31"
AC_CHOICES = "curriculum_choices_v49_31"
AC_TRIALS = "curriculum_trials_v49_31"
AC_REFLECTIONS = "curriculum_reflections_v49_31"
AC_HANDOFFS = "curriculum_handoffs_v49_31"

REQUIRED_TABLES = [
    AC_SESSIONS,
    AC_CANDIDATES,
    AC_CHOICES,
    AC_TRIALS,
    AC_REFLECTIONS,
    AC_HANDOFFS,
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
    "learning_to_learn_sessions_v49_30",
    "learning_strategies_v49_30",
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
        if "evidence_json" in item:
            item["evidence"] = pj(str(item.get("evidence_json") or "{}"), {})
        out.append(item)
    return out


def latest_completed(conn: sqlite3.Connection) -> tuple[str, dict[str, Any]]:
    completed = [
        r
        for r in rows(conn, AC_SESSIONS)
        if r.get("phase") == "curriculum_complete" and r.get("payload", {}).get("session_complete") is True
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
        (SOURCE, f"autonomous_curriculum_v49_31:{session_id}"),
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
        (SOURCE, f"autonomous_curriculum:{session_id}"),
    ).fetchone()
    return int(row["n"]) if row else 0


def prior_count(conn: sqlite3.Connection, table: str) -> int:
    if not table_exists(conn, table):
        return 0
    row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
    return int(row["n"]) if row else 0


def bounded_candidates(candidates: list[dict[str, Any]]) -> bool:
    if not candidates:
        return False
    fields = [
        "preference_strength",
        "expected_gain",
        "novelty",
        "stability",
        "cost",
        "readiness",
        "score_before_rzs",
        "score_after_rzs",
    ]
    for item in candidates:
        for field in fields:
            value = number(item.get(field), -1.0)
            if value < 0.0 or value > 1.0:
                return False
        if number(item.get("sigma_before")) <= 0.0 or number(item.get("sigma_after")) <= 0.0:
            return False
        if not str(item.get("module_key") or "") or not str(item.get("candidate_action") or ""):
            return False
        evidence = item.get("evidence", {})
        if not evidence or not evidence.get("learning_session_id") or not evidence.get("preference_session_id"):
            return False
        if "romero_formula" not in item.get("payload", {}):
            return False
    return True


def bounded_trials(trials: list[dict[str, Any]]) -> bool:
    if not trials:
        return False
    for trial in trials:
        if str(trial.get("trial_kind") or "") != "internal_curriculum_probe":
            return False
        for field in ["predicted_gain", "observed_gain", "autonomy_score", "stability_after", "energy_after"]:
            value = number(trial.get(field), -1.0)
            if value < 0.0 or value > 1.0:
                return False
        if not str(trial.get("chosen_action") or "") or not str(trial.get("outcome") or ""):
            return False
    return True


def rzs_causality_ok(choices: list[dict[str, Any]]) -> bool:
    decisions = {str(c.get("rzs_decision")) for c in choices if c.get("rzs_decision")}
    if len(decisions) < 2 or not any(d != "continue" for d in decisions):
        return False
    for choice in choices:
        decision = str(choice.get("rzs_decision") or "")
        action = str(choice.get("chosen_action") or "")
        if decision == "continue" and action.startswith(("narrow_", "replay_before_", "consolidate_before_", "pause_")):
            return False
        if decision == "narrow_focus" and not action.startswith("narrow_"):
            return False
        if decision == "replay_memory" and not action.startswith("replay_before_"):
            return False
        if decision == "consolidate" and not action.startswith("consolidate_before_"):
            return False
        if decision == "pause_for_stability" and action != "pause_curriculum_for_stability":
            return False
    return True


def autonomous_choice_ok(choices: list[dict[str, Any]], payload: dict[str, Any]) -> bool:
    modules = [str(c.get("module_key")) for c in choices if c.get("module_key")]
    if len(choices) < 12 or len(set(modules)) < 6:
        return False
    counts = Counter(modules)
    dominant = max(counts.values()) if counts else 0
    if dominant > max(4, len(choices) // 2):
        return False
    summary_modules = set(payload.get("selected_modules", []))
    return set(modules).issubset(summary_modules) and bool(payload.get("top_module"))


def source_integration_ok(candidates: list[dict[str, Any]]) -> bool:
    modules = {str(c.get("module_key")) for c in candidates if c.get("module_key")}
    strategies = {str(c.get("learning_strategy")) for c in candidates if c.get("learning_strategy")}
    preferenceful = [c for c in candidates if number(c.get("preference_strength")) > 0.0 and str(c.get("preference_key") or "")]
    sources = {str(c.get("source_kind")) for c in candidates if c.get("source_kind")}
    return (
        EXPECTED_MODULES.issubset(modules)
        and len(strategies) >= 6
        and len(preferenceful) >= len(candidates) * 0.80
        and {"formula_sketch_v49_28", "child_story_v49_29", "music_reactions_v49_16", "memory_cards_v49_13", "first_words_v49_10"}.issubset(sources)
    )


def phase_order_ok(session_events: list[dict[str, Any]], choices: list[dict[str, Any]], trials: list[dict[str, Any]]) -> bool:
    if not session_events:
        return False
    by_step: dict[int, list[str]] = {}
    for event in session_events:
        step = int(event.get("step_index") or 0)
        by_step.setdefault(step, []).append(str(event.get("phase") or ""))
    if "curriculum_start" not in by_step.get(0, []):
        return False
    choice_steps = {int(c.get("step_index") or 0) for c in choices}
    trial_steps = {int(t.get("step_index") or 0) for t in trials}
    for step in sorted(choice_steps):
        phases = by_step.get(step, [])
        try:
            scan_i = phases.index("candidate_scan")
            choice_i = phases.index("curriculum_choice")
            trial_i = phases.index("curriculum_trial")
        except ValueError:
            return False
        if not (scan_i < choice_i < trial_i):
            return False
    return choice_steps == trial_steps and "curriculum_complete" in by_step.get(max(choice_steps) if choice_steps else 0, [])


def build_report(conn: sqlite3.Connection) -> dict[str, Any]:
    session_id, complete_row = latest_completed(conn)
    session_events = rows(conn, AC_SESSIONS, session_id) if session_id else []
    candidates = rows(conn, AC_CANDIDATES, session_id) if session_id else []
    choices = rows(conn, AC_CHOICES, session_id) if session_id else []
    trials = rows(conn, AC_TRIALS, session_id) if session_id else []
    reflections = rows(conn, AC_REFLECTIONS, session_id) if session_id else []
    handoffs = rows(conn, AC_HANDOFFS, session_id) if session_id else []
    payload = complete_row.get("payload", {}) if complete_row else {}

    candidate_modules = {str(c.get("module_key")) for c in candidates if c.get("module_key")}
    selected_modules = {str(c.get("module_key")) for c in choices if c.get("module_key")}
    decisions = {str(c.get("rzs_decision")) for c in choices if c.get("rzs_decision")}
    reflection_kinds = {str(r.get("reflection_kind")) for r in reflections if r.get("reflection_kind")}
    handoff = handoffs[-1] if handoffs else {}
    protected_sources_unchanged = bool(payload.get("protected_sources_unchanged"))
    if not protected_sources_unchanged:
        before = payload.get("protected_counts_before", {})
        after = payload.get("protected_counts_after", {})
        protected_sources_unchanged = bool(before and before == after)

    checks = {
        "tables_exist": all(table_exists(conn, t) for t in REQUIRED_TABLES),
        "completed_session": bool(session_id) and bool(payload.get("session_complete")) and bool(payload.get("autonomous_curriculum_ready")),
        "candidates_scanned": len(candidates) >= 96 and source_integration_ok(candidates),
        "candidate_metrics_bounded": bounded_candidates(candidates),
        "choices_not_fixed": autonomous_choice_ok(choices, payload),
        "rzs_influenced_choices": rzs_causality_ok(choices),
        "trials_internal_and_bounded": len(trials) >= len(choices) >= 12 and bounded_trials(trials),
        "phase_order_valid": phase_order_ok(session_events, choices, trials),
        "reflections_written": len(reflections) >= len(choices) + 2 and {"curriculum_autonomy_summary", "epistemic_boundary"}.issubset(reflection_kinds),
        "handoff_written": bool(handoff) and int(handoff.get("autonomous_curriculum_ready") or 0) == 1 and int(handoff.get("selected_module_count") or 0) >= 4,
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
            "candidates": len(candidates),
            "choices": len(choices),
            "trials": len(trials),
            "reflections": len(reflections),
            "handoffs": len(handoffs),
            "semantic": semantic_count(conn, session_id) if session_id else 0,
            "episodes": episode_count(conn, session_id) if session_id else 0,
        },
        "candidate_modules": sorted(candidate_modules),
        "selected_modules": sorted(selected_modules),
        "module_counts": dict(Counter([str(c.get("module_key")) for c in choices if c.get("module_key")])),
        "decisions": sorted(decisions),
        "reflection_kinds": sorted(reflection_kinds),
        "learning": {
            "avg_observed_gain": number(payload.get("avg_observed_gain"), 0.0),
            "avg_autonomy_score": number(payload.get("avg_autonomy_score"), 0.0),
            "avg_choice_score": number(payload.get("avg_choice_score"), 0.0),
            "top_module": str(payload.get("top_module") or ""),
            "learning_session_id": str(payload.get("learning_session_id") or ""),
            "preference_session_id": str(payload.get("preference_session_id") or ""),
        },
        "handoff": {
            "next_action": handoff.get("next_action", ""),
            "autonomous_curriculum_ready": bool(int(handoff.get("autonomous_curriculum_ready") or 0)) if handoff else False,
            "selected_module_count": int(handoff.get("selected_module_count") or 0) if handoff else 0,
            "confidence": number(handoff.get("confidence"), 0.0) if handoff else 0.0,
        },
        "payload": payload,
    }


def print_report(report: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.31 - DIAGNOSTICO AUTONOMOUS CURRICULUM")
    print("=" * 74)
    print(f"- sessao: {report['session_id'] or 'NENHUMA'}")
    c = report["counts"]
    print(
        f"- candidatos={c['candidates']} escolhas={c['choices']} ensaios={c['trials']} "
        f"reflexoes={c['reflections']}"
    )
    l = report["learning"]
    print(
        f"- ganho medio={l['avg_observed_gain']:.3f} autonomia media={l['avg_autonomy_score']:.3f} "
        f"score medio={l['avg_choice_score']:.3f}"
    )
    print(f"- top modulo: {l['top_module'] or 'nenhum'}")
    print(f"- modulos escolhidos: {', '.join(report['selected_modules']) if report['selected_modules'] else 'nenhum'}")
    print(f"- RZS: {', '.join(report['decisions']) if report['decisions'] else 'nenhum'}")
    print()
    labels = {
        "tables_exist": "tabelas v49.31 existem",
        "completed_session": "sessao completa e pronta",
        "candidates_scanned": "candidatos amplos foram escaneados",
        "candidate_metrics_bounded": "metricas dos candidatos validas",
        "choices_not_fixed": "escolha nao ficou fixa",
        "rzs_influenced_choices": "RZS influenciou escolhas",
        "trials_internal_and_bounded": "ensaios internos validos",
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
        print("Leitura: Darwin escolheu o proprio treino por evidencia, preferencia, custo, novidade e RZS.")
    else:
        print("Leitura: ainda falta evidencia para aceitar o curriculo autonomo como marco completo.")
    if details:
        print("\nJSON:")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.31 Autonomous Curriculum checker")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    with connect() as conn:
        report = build_report(conn)
    print_report(report, args.details)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
