from __future__ import annotations

"""
DARWIN v49.30 - Diagnostico Learning to Learn

Uso:
    py darwin_check_v49_30_learning_to_learn.py
    py darwin_check_v49_30_learning_to_learn.py --details
"""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"

SOURCE = "darwin_learning_to_learn_v49_30"

L2L_SESSIONS = "learning_to_learn_sessions_v49_30"
L2L_EVIDENCE = "learning_evidence_v49_30"
L2L_STRATEGIES = "learning_strategies_v49_30"
L2L_TRIALS = "learning_trials_v49_30"
L2L_PREDICTIONS = "learning_predictions_v49_30"
L2L_REFLECTIONS = "learning_reflections_v49_30"
L2L_HANDOFFS = "learning_handoffs_v49_30"

REQUIRED_TABLES = [
    L2L_SESSIONS,
    L2L_EVIDENCE,
    L2L_STRATEGIES,
    L2L_TRIALS,
    L2L_PREDICTIONS,
    L2L_REFLECTIONS,
    L2L_HANDOFFS,
]

REQUIRED_EVIDENCE_KINDS = {
    "geometry_error_learning",
    "replay_reduces_error",
    "formula_sketch_correction",
    "cross_domain_formula_fusion",
    "story_affective_learning",
    "music_comfort_pattern",
    "preference_weighted_choice",
    "metacognitive_self_check",
    "operational_self_boundary",
}

REQUIRED_STRATEGIES = {
    "replay_before_retry",
    "narrow_focus_on_conflict",
    "error_as_experience_node",
    "consolidate_after_pattern",
    "cross_domain_fusion",
    "affective_safe_context",
    "evidence_weighted_choice",
    "self_check_before_advance",
}

PRIOR_TABLES = [
    "geometry_experience_nodes_v49_7",
    "formula_sketch_intentions_v49_28",
    "story_reactions_v49_29",
    "music_reactions_v49_16",
    "brain_meta_cycles_v49_1",
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
        item["payload"] = pj(str(item.get("payload_json") or "{}"), {})
        if "tags_json" in item:
            item["tags"] = pj(str(item.get("tags_json") or "[]"), [])
        if "evidence_refs_json" in item:
            item["evidence_refs"] = pj(str(item.get("evidence_refs_json") or "[]"), [])
        out.append(item)
    return out


def latest_completed(conn: sqlite3.Connection) -> tuple[str, dict[str, Any]]:
    completed = [
        r
        for r in rows(conn, L2L_SESSIONS)
        if r.get("phase") == "session_complete" and r.get("payload", {}).get("session_complete") is True
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
        (SOURCE, f"learning_to_learn_v49_30:{session_id}"),
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
        (SOURCE, f"learning_to_learn:{session_id}"),
    ).fetchone()
    return int(row["n"]) if row else 0


def prior_count(conn: sqlite3.Connection, table: str) -> int:
    if not table_exists(conn, table):
        return 0
    row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
    return int(row["n"]) if row else 0


def bounded_trials(trials: list[dict[str, Any]]) -> bool:
    if not trials:
        return False
    for trial in trials:
        for field in ["predicted_gain", "observed_gain", "transfer_score", "confidence_before", "confidence_after"]:
            value = number(trial.get(field), -1.0)
            if value < 0.0 or value > 1.0:
                return False
        if number(trial.get("sigma_before")) <= 0.0 or number(trial.get("sigma_after")) <= 0.0:
            return False
        if not str(trial.get("strategy_key") or "") or not str(trial.get("context_kind") or ""):
            return False
        if "romero_formula" not in trial.get("payload", {}):
            return False
    return True


def rzs_causality_ok(trials: list[dict[str, Any]]) -> bool:
    decisions = {str(t.get("rzs_decision")) for t in trials if t.get("rzs_decision")}
    if len(decisions) < 2 or not any(d != "continue" for d in decisions):
        return False
    for trial in trials:
        decision = str(trial.get("rzs_decision") or "")
        action = str(trial.get("chosen_action") or "")
        if decision == "continue" and not action.startswith("apply_"):
            return False
        if decision == "narrow_focus" and not action.startswith("narrow_apply_"):
            return False
        if decision == "replay_memory" and not action.startswith("replay_then_apply_"):
            return False
        if decision == "consolidate" and not action.startswith("consolidate_"):
            return False
        if decision == "pause_for_stability" and not action.startswith("pause_before_"):
            return False
    return True


def strategy_learning_ok(strategies: list[dict[str, Any]], trials: list[dict[str, Any]], payload: dict[str, Any]) -> bool:
    strategy_keys = {str(s.get("strategy_key")) for s in strategies}
    if not REQUIRED_STRATEGIES.issubset(strategy_keys):
        return False
    if not all(len(s.get("evidence_refs", [])) >= 1 for s in strategies):
        return False
    changed = [
        t
        for t in trials
        if abs(number(t.get("confidence_after")) - number(t.get("confidence_before"))) >= 0.0001
    ]
    ranked = payload.get("ranked_strategies", [])
    top = str(payload.get("top_strategy") or "")
    return len(changed) >= max(8, len(trials) // 3) and isinstance(ranked, list) and bool(ranked) and top in strategy_keys


def learning_curve_ok(trials: list[dict[str, Any]], payload: dict[str, Any]) -> bool:
    if len(trials) < 24:
        return False
    first = number(payload.get("first_quarter_gain"), -1.0)
    last = number(payload.get("last_quarter_gain"), -1.0)
    if first < 0.0 or last < 0.0:
        return False
    if last + 0.05 < first:
        return False
    observed = [number(t.get("observed_gain"), -1.0) for t in trials]
    predicted = [number(t.get("predicted_gain"), -1.0) for t in trials]
    return min(observed) >= 0.0 and min(predicted) >= 0.0 and sum(observed) / len(observed) >= 0.08


def build_report(conn: sqlite3.Connection) -> dict[str, Any]:
    session_id, complete_row = latest_completed(conn)
    evidence = rows(conn, L2L_EVIDENCE, session_id) if session_id else []
    strategies = rows(conn, L2L_STRATEGIES, session_id) if session_id else []
    trials = rows(conn, L2L_TRIALS, session_id) if session_id else []
    predictions = rows(conn, L2L_PREDICTIONS, session_id) if session_id else []
    reflections = rows(conn, L2L_REFLECTIONS, session_id) if session_id else []
    handoffs = rows(conn, L2L_HANDOFFS, session_id) if session_id else []
    payload = complete_row.get("payload", {}) if complete_row else {}

    evidence_kinds = {str(e.get("source_kind")) for e in evidence if e.get("source_kind")}
    domains = {str(e.get("domain")) for e in evidence if e.get("domain")}
    strategy_keys = {str(s.get("strategy_key")) for s in strategies if s.get("strategy_key")}
    contexts = {str(t.get("context_kind")) for t in trials if t.get("context_kind")}
    decisions = {str(t.get("rzs_decision")) for t in trials if t.get("rzs_decision")}
    used_strategies = {str(t.get("strategy_key")) for t in trials if t.get("strategy_key")}
    reflection_kinds = {str(r.get("reflection_kind")) for r in reflections if r.get("reflection_kind")}
    handoff = handoffs[-1] if handoffs else {}

    protected_sources_unchanged = bool(payload.get("protected_sources_unchanged"))
    if not protected_sources_unchanged:
        before = payload.get("protected_counts_before", {})
        after = payload.get("protected_counts_after", {})
        protected_sources_unchanged = bool(before and before == after)

    checks = {
        "tables_exist": all(table_exists(conn, t) for t in REQUIRED_TABLES),
        "completed_session": bool(session_id) and bool(payload.get("session_complete")),
        "evidence_loaded": len(evidence) >= 9 and REQUIRED_EVIDENCE_KINDS.issubset(evidence_kinds) and len(domains) >= 7,
        "strategies_derived_from_evidence": strategy_learning_ok(strategies, trials, payload),
        "trials_ran_across_contexts": len(trials) >= 48 and len(contexts) >= 8 and len(used_strategies) >= 6,
        "trials_are_bounded": bounded_trials(trials),
        "rzs_influenced_learning": rzs_causality_ok(trials),
        "predictions_written": len(predictions) >= 3 and all(number(p.get("confidence")) > 0.0 for p in predictions),
        "reflections_written": len(reflections) >= 2 and {"meta_learning_summary", "epistemic_boundary"}.issubset(reflection_kinds),
        "handoff_written": bool(handoff) and int(handoff.get("meta_learning_ready") or 0) == 1 and int(handoff.get("strategy_count") or 0) >= 8,
        "learning_curve_valid": learning_curve_ok(trials, payload),
        "semantic_memory_written": semantic_count(conn, session_id) >= 1 if session_id else False,
        "episodes_written": episode_count(conn, session_id) >= 1 if session_id else False,
        "prior_data_still_present": all(prior_count(conn, table) > 0 for table in PRIOR_TABLES),
        "protected_sources_unchanged": protected_sources_unchanged,
    }
    return {
        "ok": all(checks.values()),
        "session_id": session_id,
        "checks": checks,
        "counts": {
            "evidence": len(evidence),
            "strategies": len(strategies),
            "trials": len(trials),
            "predictions": len(predictions),
            "reflections": len(reflections),
            "handoffs": len(handoffs),
            "semantic": semantic_count(conn, session_id) if session_id else 0,
            "episodes": episode_count(conn, session_id) if session_id else 0,
        },
        "evidence_kinds": sorted(evidence_kinds),
        "domains": sorted(domains),
        "strategy_keys": sorted(strategy_keys),
        "used_strategies": sorted(used_strategies),
        "contexts": sorted(contexts),
        "decisions": sorted(decisions),
        "reflection_kinds": sorted(reflection_kinds),
        "learning": {
            "first_quarter_gain": number(payload.get("first_quarter_gain"), 0.0),
            "last_quarter_gain": number(payload.get("last_quarter_gain"), 0.0),
            "learning_gain_delta": number(payload.get("learning_gain_delta"), 0.0),
            "top_strategy": str(payload.get("top_strategy") or ""),
        },
        "handoff": {
            "next_action": handoff.get("next_action", ""),
            "meta_learning_ready": bool(int(handoff.get("meta_learning_ready") or 0)) if handoff else False,
            "strategy_count": int(handoff.get("strategy_count") or 0) if handoff else 0,
            "confidence": number(handoff.get("confidence"), 0.0) if handoff else 0.0,
        },
        "payload": payload,
    }


def print_report(report: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.30 - DIAGNOSTICO LEARNING TO LEARN")
    print("=" * 72)
    print(f"- sessao: {report['session_id'] or 'NENHUMA'}")
    c = report["counts"]
    print(
        f"- evidencias={c['evidence']} estrategias={c['strategies']} ensaios={c['trials']} "
        f"predicoes={c['predictions']} reflexoes={c['reflections']}"
    )
    l = report["learning"]
    print(
        f"- ganho inicio={l['first_quarter_gain']:.3f} ganho final={l['last_quarter_gain']:.3f} "
        f"delta={l['learning_gain_delta']:.3f}"
    )
    print(f"- melhor estrategia: {l['top_strategy'] or 'nenhuma'}")
    print(f"- RZS: {', '.join(report['decisions']) if report['decisions'] else 'nenhum'}")
    print(f"- contextos: {', '.join(report['contexts']) if report['contexts'] else 'nenhum'}")
    print()
    labels = {
        "tables_exist": "tabelas v49.30 existem",
        "completed_session": "sessao completa encontrada",
        "evidence_loaded": "evidencia historica carregada",
        "strategies_derived_from_evidence": "estrategias derivadas de evidencia",
        "trials_ran_across_contexts": "ensaios rodaram em varios contextos",
        "trials_are_bounded": "ensaios numericamente validos",
        "rzs_influenced_learning": "RZS influenciou aprendizagem",
        "predictions_written": "predicoes escritas",
        "reflections_written": "reflexoes escritas",
        "handoff_written": "handoff escrito",
        "learning_curve_valid": "curva de aprendizagem plausivel",
        "semantic_memory_written": "memoria semantica escrita",
        "episodes_written": "episodio escrito",
        "prior_data_still_present": "dados anteriores ainda presentes",
        "protected_sources_unchanged": "fontes anteriores preservadas",
    }
    for key, value in report["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'FALHOU'}")
    if report["ok"]:
        print("Leitura: Darwin comparou metodos, previu resultados, atualizou confianca e escolheu estrategias por evidencia.")
    else:
        print("Leitura: ainda falta evidencia para aceitar o marco aprendendo a aprender como completo.")
    if details:
        print("\nJSON:")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.30 Learning to Learn checker")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    with connect() as conn:
        report = build_report(conn)
    print_report(report, args.details)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
