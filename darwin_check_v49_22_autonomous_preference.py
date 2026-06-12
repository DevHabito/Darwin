from __future__ import annotations

"""
DARWIN v49.22 - Diagnostico do Autonomous Preference Core

Uso:
    py darwin_check_v49_22_autonomous_preference.py
    py darwin_check_v49_22_autonomous_preference.py --details
"""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"

AP_SESSIONS = "autonomous_preference_sessions_v49_22"
AP_EVIDENCE = "autonomous_preference_evidence_v49_22"
AP_CANDIDATES = "autonomous_preference_candidates_v49_22"
AP_DECISIONS = "autonomous_preference_decisions_v49_22"
AP_IDENTITY = "autonomous_preference_identity_v49_22"

SOURCE = "darwin_autonomous_preference_core_v49_22"
EXPECTED_QUESTIONS = ["geral", "musica", "formula", "cor", "atividade"]
EXPECTED_DOMAINS = {"musica", "formula", "cor", "atividade"}
VALID_RZS = {"continue", "narrow_focus", "replay_memory", "consolidate", "pause_for_stability"}


def pj(value: str | None, fallback: Any = None) -> Any:
    try:
        parsed = json.loads(value or "{}")
    except Exception:
        return {} if fallback is None else fallback
    if fallback is not None and isinstance(fallback, list) and not isinstance(parsed, list):
        return fallback
    if fallback is not None and isinstance(fallback, dict) and not isinstance(parsed, dict):
        return fallback
    return parsed


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
        item["payload"] = pj(str(item.get("payload_json") or "{}"), {})
        if "source_refs_json" in item:
            item["source_refs"] = pj(str(item.get("source_refs_json") or "[]"), [])
        out.append(item)
    return out


def latest_completed_session(conn: sqlite3.Connection) -> tuple[str, dict[str, Any]]:
    session_rows = rows(conn, AP_SESSIONS)
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
        (SOURCE, f"autonomous_preference_v49_22:{session_id}"),
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
        (SOURCE, f"autonomous_preference:{session_id}"),
    ).fetchone()
    return bool(row and int(row["n"]) >= 1)


def evidence_ok(evidence: list[dict[str, Any]]) -> bool:
    if len(evidence) < 12:
        return False
    source_tables = {str(e.get("source_table") or "") for e in evidence}
    required_any = [
        "music_reactions_v49_16",
        "geometry_concepts_v49_7",
        "affective_preferences_v49_17",
        "wake_next_handoff_v49_21",
    ]
    if len(source_tables.intersection(required_any)) < 3:
        return False
    for item in evidence:
        if not str(item.get("domain") or "") or not str(item.get("item_key") or ""):
            return False
        if float(item.get("confidence") or 0.0) <= 0.0:
            return False
    return True


def candidates_ok(candidates: list[dict[str, Any]]) -> bool:
    if len(candidates) < 8:
        return False
    domains = {str(c.get("domain") or "") for c in candidates}
    if not EXPECTED_DOMAINS.issubset(domains):
        return False
    for item in candidates:
        if float(item.get("like_score") or 0.0) <= 0.0:
            return False
        if float(item.get("autonomy_score") or 0.0) <= 0.0:
            return False
        if int(item.get("evidence_count") or 0) < 1:
            return False
        payload = item.get("payload", {})
        if payload.get("origin") != "database_evidence_not_hardcoded_like":
            return False
    return True


def decisions_ok(decisions: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> bool:
    if len(decisions) < len(EXPECTED_QUESTIONS):
        return False
    kinds = [str(d.get("question_kind") or "") for d in decisions]
    if kinds[: len(EXPECTED_QUESTIONS)] != EXPECTED_QUESTIONS:
        return False
    candidate_ids = {str(c.get("candidate_id") or "") for c in candidates}
    for item in decisions:
        if str(item.get("rzs_decision") or "") not in VALID_RZS:
            return False
        if float(item.get("sigma_before") or 0.0) <= 0.0:
            return False
        if float(item.get("sigma_after") or 0.0) <= 0.0:
            return False
        if float(item.get("confidence") or 0.0) <= 0.25:
            return False
        if not str(item.get("want_statement") or ""):
            return False
        if str(item.get("chosen_candidate_id") or "") not in candidate_ids:
            return False
    return True


def identity_ok(identity_rows: list[dict[str, Any]]) -> bool:
    if not identity_rows:
        return False
    item = identity_rows[-1]
    required = ["top_want", "top_music", "top_formula", "top_color", "top_activity", "autonomy_statement"]
    return all(bool(str(item.get(key) or "")) for key in required)


def rzs_influenced(decisions: list[dict[str, Any]]) -> bool:
    decisions_set = {str(d.get("rzs_decision") or "") for d in decisions}
    return bool(decisions_set) and decisions_set.issubset(VALID_RZS) and any(d != "continue" for d in decisions_set)


def exploration_present(decisions: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> bool:
    if any(int(d.get("exploration_selected") or 0) == 1 for d in decisions):
        return True
    return any(float(c.get("uncertainty") or 0.0) > 0.20 for c in candidates)


def prior_data_present(conn: sqlite3.Connection) -> bool:
    required = [
        "affective_preferences_v49_17",
        "music_reactions_v49_16",
        "geometry_concepts_v49_7",
        "wake_next_handoff_v49_21",
    ]
    return all(table_exists(conn, table) for table in required)


def build_report(conn: sqlite3.Connection) -> dict[str, Any]:
    session_id, complete_row = latest_completed_session(conn)
    evidence = rows(conn, AP_EVIDENCE, " WHERE session_id=?", (session_id,)) if session_id else []
    candidates = rows(conn, AP_CANDIDATES, " WHERE session_id=?", (session_id,)) if session_id else []
    decisions = rows(conn, AP_DECISIONS, " WHERE session_id=?", (session_id,)) if session_id else []
    identity_rows = rows(conn, AP_IDENTITY, " WHERE session_id=?", (session_id,)) if session_id else []
    payload = complete_row.get("payload", {}) if complete_row else {}
    domains = sorted({str(c.get("domain") or "") for c in candidates})
    source_tables = sorted({str(e.get("source_table") or "") for e in evidence})
    latest_identity = identity_rows[-1] if identity_rows else {}
    checks = {
        "tables_exist": all(table_exists(conn, t) for t in (AP_SESSIONS, AP_EVIDENCE, AP_CANDIDATES, AP_DECISIONS, AP_IDENTITY)),
        "completed_session": bool(session_id) and bool(payload.get("session_complete")),
        "evidence_loaded": evidence_ok(evidence),
        "candidates_from_evidence": candidates_ok(candidates),
        "decisions_written": decisions_ok(decisions, candidates),
        "identity_written": identity_ok(identity_rows),
        "rzs_influenced_decision": rzs_influenced(decisions),
        "exploration_or_uncertainty_present": exploration_present(decisions, candidates),
        "semantic_memory_written": semantic_written(conn, session_id) if session_id else False,
        "episode_written": episode_written(conn, session_id) if session_id else False,
        "prior_data_still_present": prior_data_present(conn),
    }
    decision_map = {
        str(d.get("question_kind") or ""): {
            "label": d.get("chosen_label", ""),
            "domain": d.get("chosen_domain", ""),
            "statement": d.get("want_statement", ""),
            "rzs": d.get("rzs_decision", ""),
            "confidence": round(float(d.get("confidence") or 0.0), 3),
            "exploration": bool(int(d.get("exploration_selected") or 0)),
        }
        for d in decisions
    }
    top_candidates = sorted(
        [
            {
                "domain": c.get("domain", ""),
                "label": c.get("label", ""),
                "autonomy_score": round(float(c.get("autonomy_score") or 0.0), 3),
                "uncertainty": round(float(c.get("uncertainty") or 0.0), 3),
                "evidence_count": int(c.get("evidence_count") or 0),
            }
            for c in candidates
        ],
        key=lambda x: x["autonomy_score"],
        reverse=True,
    )[:8]
    return {
        "ok": all(checks.values()),
        "session_id": session_id,
        "checks": checks,
        "counts": {
            "evidence": len(evidence),
            "candidates": len(candidates),
            "decisions": len(decisions),
            "identity": len(identity_rows),
        },
        "domains": domains,
        "source_tables": source_tables,
        "rzs_decisions": sorted({str(d.get("rzs_decision") or "") for d in decisions}),
        "decisions": decision_map,
        "top_candidates": top_candidates,
        "identity": {
            "top_want": latest_identity.get("top_want", ""),
            "top_music": latest_identity.get("top_music", ""),
            "top_formula": latest_identity.get("top_formula", ""),
            "top_color": latest_identity.get("top_color", ""),
            "top_activity": latest_identity.get("top_activity", ""),
            "autonomy_statement": latest_identity.get("autonomy_statement", ""),
        },
        "payload": payload,
    }


def print_report(report: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.22 - DIAGNOSTICO AUTONOMOUS PREFERENCE")
    print("=" * 68)
    print(f"- sessao: {report['session_id'] or 'NENHUMA'}")
    c = report["counts"]
    print(f"- evidencias={c['evidence']} candidatos={c['candidates']} decisoes={c['decisions']}")
    print(f"- dominios: {', '.join(report['domains']) if report['domains'] else 'nenhum'}")
    print(f"- fontes: {', '.join(report['source_tables']) if report['source_tables'] else 'nenhuma'}")
    print(f"- RZS: {', '.join(report['rzs_decisions']) if report['rzs_decisions'] else 'nenhum'}")
    print()
    labels = {
        "tables_exist": "tabelas v49.22 existem",
        "completed_session": "sessao completa encontrada",
        "evidence_loaded": "evidencias reais carregadas",
        "candidates_from_evidence": "candidatos vieram de evidencia",
        "decisions_written": "decisoes por pergunta escritas",
        "identity_written": "identidade de gosto escrita",
        "rzs_influenced_decision": "RZS influenciou decisao",
        "exploration_or_uncertainty_present": "incerteza/exploracao presente",
        "semantic_memory_written": "memoria semantica escrita",
        "episode_written": "episodio escrito",
        "prior_data_still_present": "dados anteriores ainda presentes",
    }
    for key, value in report["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'FALHOU'}")
    if report["ok"]:
        print("Leitura: Darwin declarou gostos como escolhas autonomas derivadas da propria memoria.")
    else:
        print("Leitura: ainda falta evidencia para aceitar preferencia autonoma como marco estavel.")
    if details:
        print("\nJSON:")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.22 Autonomous Preference checker")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    with connect() as conn:
        report = build_report(conn)
    print_report(report, args.details)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
