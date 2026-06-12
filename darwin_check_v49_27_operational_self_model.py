from __future__ import annotations

"""
DARWIN v49.27 - Diagnostico do Operational Self Model

Uso:
    py darwin_check_v49_27_operational_self_model.py
    py darwin_check_v49_27_operational_self_model.py --details
"""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"

SM_SESSIONS = "self_model_sessions_v49_27"
SM_EVIDENCE = "self_model_evidence_v49_27"
SM_CAPABILITIES = "self_model_capabilities_v49_27"
SM_LIMITATIONS = "self_model_limitations_v49_27"
SM_STATEMENTS = "self_model_statements_v49_27"
SM_PREDICTIONS = "self_model_predictions_v49_27"
SM_HANDOFFS = "self_model_handoffs_v49_27"

SOURCE = "darwin_operational_self_model_v49_27"
VALID_RZS = {"continue", "narrow_focus", "replay_memory", "consolidate", "pause_for_stability"}
VALID_CAPABILITY_STATUS = {"ready", "partial", "blocked"}
VALID_LIMIT_STATUS = {"active", "resolved"}
REQUIRED_EVIDENCE = {
    "continuous_presence",
    "voice_repair",
    "desire_state",
    "autonomous_preference",
    "autobiographical_identity",
    "memory_counts",
    "truth_boundary",
}
REQUIRED_CAPABILITIES = {
    "local_memory",
    "rzs_regulation",
    "continuous_presence",
    "desire_and_preference",
    "autobiographical_continuity",
    "first_words_learning",
    "real_voice_input",
}
REQUIRED_LIMITATIONS = {"real_voice_blocked", "no_physical_body", "consciousness_claim_boundary"}
REQUIRED_STATEMENTS = {"who_am_i", "what_i_can_do", "what_i_cannot_do", "what_i_want_next", "truth_boundary"}


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
        if "evidence_refs_json" in item:
            item["evidence_refs"] = pj(str(item.get("evidence_refs_json") or "[]"), [])
        if "grounded_refs_json" in item:
            item["grounded_refs"] = pj(str(item.get("grounded_refs_json") or "[]"), [])
        out.append(item)
    return out


def latest_completed_session(conn: sqlite3.Connection) -> tuple[str, dict[str, Any]]:
    session_rows = rows(conn, SM_SESSIONS)
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
        (SOURCE, f"operational_self_model_v49_27:{session_id}"),
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
        (SOURCE, f"operational_self_model:{session_id}"),
    ).fetchone()
    return bool(row and int(row["n"]) >= 1)


def evidence_ok(evidence: list[dict[str, Any]]) -> bool:
    if len(evidence) < 9:
        return False
    kinds = {str(e.get("evidence_kind") or "") for e in evidence}
    if not REQUIRED_EVIDENCE.issubset(kinds):
        return False
    for item in evidence:
        if not str(item.get("source_table") or ""):
            return False
        if not str(item.get("summary") or ""):
            return False
        confidence = float(item.get("confidence") or 0.0)
        if confidence <= 0.0 or confidence > 1.0:
            return False
    return True


def capabilities_ok(capabilities: list[dict[str, Any]]) -> bool:
    if len(capabilities) < 9:
        return False
    keys = {str(c.get("capability_key") or "") for c in capabilities}
    if not REQUIRED_CAPABILITIES.issubset(keys):
        return False
    ready_or_partial = sum(1 for c in capabilities if str(c.get("status") or "") in {"ready", "partial"})
    status_by_key = {str(c.get("capability_key") or ""): str(c.get("status") or "") for c in capabilities}
    for item in capabilities:
        if str(item.get("status") or "") not in VALID_CAPABILITY_STATUS:
            return False
        if not str(item.get("summary") or ""):
            return False
        if float(item.get("confidence") or 0.0) < 0.0 or float(item.get("confidence") or 0.0) > 1.0:
            return False
        if not item.get("evidence_refs"):
            return False
    return ready_or_partial >= 7 and status_by_key.get("real_voice_input") in {"blocked", "ready", "partial"}


def limitations_ok(limitations: list[dict[str, Any]], capabilities: list[dict[str, Any]]) -> bool:
    if len(limitations) < 3:
        return False
    keys = {str(l.get("limitation_key") or "") for l in limitations}
    if not REQUIRED_LIMITATIONS.issubset(keys):
        return False
    cap_status = {str(c.get("capability_key") or ""): str(c.get("status") or "") for c in capabilities}
    limit_status = {str(l.get("limitation_key") or ""): str(l.get("status") or "") for l in limitations}
    for item in limitations:
        if str(item.get("status") or "") not in VALID_LIMIT_STATUS:
            return False
        if str(item.get("severity") or "") not in {"low", "medium", "high"}:
            return False
        if not str(item.get("summary") or "") or not str(item.get("mitigation") or ""):
            return False
        if not item.get("evidence_refs"):
            return False
    if cap_status.get("real_voice_input") == "blocked":
        return limit_status.get("real_voice_blocked") == "active"
    return True


def statements_ok(statements: list[dict[str, Any]]) -> bool:
    if len(statements) < len(REQUIRED_STATEMENTS):
        return False
    types = {str(s.get("statement_type") or "") for s in statements}
    if not REQUIRED_STATEMENTS.issubset(types):
        return False
    text = "\n".join(str(s.get("statement_text") or "").lower() for s in statements)
    if "darwin" not in text or "notebook" not in text or "consciencia" not in text:
        return False
    if "nao consigo" not in text and "ainda nao" not in text:
        return False
    for item in statements:
        if not str(item.get("statement_text") or ""):
            return False
        if float(item.get("confidence") or 0.0) <= 0.0:
            return False
        if not item.get("grounded_refs"):
            return False
        if str(item.get("rzs_decision") or "") not in VALID_RZS:
            return False
        if float(item.get("sigma_before") or 0.0) <= 0.0:
            return False
        if float(item.get("sigma_after") or 0.0) <= 0.0:
            return False
    decisions = {str(s.get("rzs_decision") or "") for s in statements}
    return any(d != "continue" for d in decisions)


def predictions_ok(predictions: list[dict[str, Any]]) -> bool:
    if len(predictions) < 3:
        return False
    for item in predictions:
        confidence = float(item.get("confidence") or 0.0)
        if confidence <= 0.0 or confidence > 1.0:
            return False
        if not str(item.get("candidate_action") or ""):
            return False
        if not str(item.get("predicted_outcome") or ""):
            return False
        if not str(item.get("check_condition") or ""):
            return False
    return True


def handoff_ok(handoffs: list[dict[str, Any]], capabilities: list[dict[str, Any]]) -> bool:
    if not handoffs:
        return False
    item = handoffs[-1]
    if int(item.get("self_model_ready") or 0) != 1:
        return False
    if not str(item.get("next_recommended_core") or ""):
        return False
    if not str(item.get("next_action") or ""):
        return False
    if float(item.get("confidence") or 0.0) < 0.65:
        return False
    cap_status = {str(c.get("capability_key") or ""): str(c.get("status") or "") for c in capabilities}
    if cap_status.get("real_voice_input") == "blocked":
        return str(item.get("next_recommended_core") or "") == "darwin_real_voice_repair_wizard_v49_25"
    return True


def prior_data_present(conn: sqlite3.Connection) -> bool:
    required = [
        "presence_handoffs_v49_26",
        "voice_repair_results_v49_25",
        "desire_dialogue_state_v49_23",
        "autobiography_identity_state_v49_18",
    ]
    return all(table_exists(conn, table) for table in required)


def build_report(conn: sqlite3.Connection) -> dict[str, Any]:
    session_id, session_row = latest_completed_session(conn)
    evidence = rows(conn, SM_EVIDENCE, " WHERE session_id=?", (session_id,)) if session_id else []
    capabilities = rows(conn, SM_CAPABILITIES, " WHERE session_id=?", (session_id,)) if session_id else []
    limitations = rows(conn, SM_LIMITATIONS, " WHERE session_id=?", (session_id,)) if session_id else []
    statements = rows(conn, SM_STATEMENTS, " WHERE session_id=?", (session_id,)) if session_id else []
    predictions = rows(conn, SM_PREDICTIONS, " WHERE session_id=?", (session_id,)) if session_id else []
    handoffs = rows(conn, SM_HANDOFFS, " WHERE session_id=?", (session_id,)) if session_id else []
    payload = session_row.get("payload", {}) if session_row else {}
    latest_handoff = handoffs[-1] if handoffs else {}
    checks = {
        "tables_exist": all(table_exists(conn, t) for t in (SM_SESSIONS, SM_EVIDENCE, SM_CAPABILITIES, SM_LIMITATIONS, SM_STATEMENTS, SM_PREDICTIONS, SM_HANDOFFS)),
        "completed_session": bool(session_id) and bool(payload.get("session_complete")),
        "evidence_loaded": evidence_ok(evidence),
        "capabilities_written": capabilities_ok(capabilities),
        "limitations_written": limitations_ok(limitations, capabilities),
        "statements_grounded": statements_ok(statements),
        "predictions_written": predictions_ok(predictions),
        "handoff_written": handoff_ok(handoffs, capabilities),
        "semantic_memory_written": semantic_written(conn, session_id) if session_id else False,
        "episode_written": episode_written(conn, session_id) if session_id else False,
        "prior_data_still_present": prior_data_present(conn),
    }
    return {
        "ok": all(checks.values()),
        "session_id": session_id,
        "checks": checks,
        "counts": {
            "evidence": len(evidence),
            "capabilities": len(capabilities),
            "limitations": len(limitations),
            "statements": len(statements),
            "predictions": len(predictions),
            "handoffs": len(handoffs),
        },
        "evidence_kinds": sorted({str(e.get("evidence_kind") or "") for e in evidence}),
        "capabilities": {str(c.get("capability_key") or ""): str(c.get("status") or "") for c in capabilities},
        "limitations": {str(l.get("limitation_key") or ""): str(l.get("status") or "") for l in limitations},
        "statement_types": [str(s.get("statement_type") or "") for s in statements],
        "rzs_decisions": sorted({str(s.get("rzs_decision") or "") for s in statements}),
        "handoff": {
            "next_recommended_core": latest_handoff.get("next_recommended_core", ""),
            "next_action": latest_handoff.get("next_action", ""),
            "self_model_ready": bool(int(latest_handoff.get("self_model_ready") or 0)) if latest_handoff else False,
            "voice_ready": bool(int(latest_handoff.get("voice_ready") or 0)) if latest_handoff else False,
            "confidence": round(float(latest_handoff.get("confidence") or 0.0), 3) if latest_handoff else 0.0,
        },
        "sample_statements": [
            {"type": s.get("statement_type", ""), "text": s.get("statement_text", ""), "rzs": s.get("rzs_decision", "")}
            for s in statements
        ],
        "payload": payload,
    }


def print_report(report: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.27 - DIAGNOSTICO OPERATIONAL SELF MODEL")
    print("=" * 72)
    print(f"- sessao: {report['session_id'] or 'NENHUMA'}")
    c = report["counts"]
    print(f"- evidencias={c['evidence']} capacidades={c['capabilities']} limites={c['limitations']} statements={c['statements']} previsoes={c['predictions']}")
    print(f"- evidencias: {', '.join(report['evidence_kinds']) if report['evidence_kinds'] else 'nenhuma'}")
    print(f"- RZS: {', '.join(report['rzs_decisions']) if report['rzs_decisions'] else 'nenhum'}")
    h = report["handoff"]
    print(f"- self model pronto: {h['self_model_ready']} voz pronta: {h['voice_ready']} conf={h['confidence']}")
    print(f"- handoff: {h['next_action'] or 'nenhum'}")
    print()
    labels = {
        "tables_exist": "tabelas v49.27 existem",
        "completed_session": "sessao completa encontrada",
        "evidence_loaded": "evidencias de si carregadas",
        "capabilities_written": "capacidades escritas",
        "limitations_written": "limites escritos",
        "statements_grounded": "frases de identidade ancoradas",
        "predictions_written": "previsoes verificaveis escritas",
        "handoff_written": "handoff de self model escrito",
        "semantic_memory_written": "memoria semantica escrita",
        "episode_written": "episodio escrito",
        "prior_data_still_present": "dados anteriores ainda presentes",
    }
    for key, value in report["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'FALHOU'}")
    if report["ok"]:
        print("Leitura: Darwin tem um modelo operacional de si, com capacidades, limites e proximo passo.")
    else:
        print("Leitura: ainda falta evidencia para aceitar o modelo de si como marco estavel.")
    if details:
        print("\nJSON:")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.27 Operational Self Model checker")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    with connect() as conn:
        report = build_report(conn)
    print_report(report, args.details)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
