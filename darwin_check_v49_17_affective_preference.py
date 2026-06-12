from __future__ import annotations

"""
DARWIN v49.17 - Diagnostico do Preference & Affective Memory Core

Uso:
    py darwin_check_v49_17_affective_preference.py
    py darwin_check_v49_17_affective_preference.py --details
"""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"

AP_SESSIONS = "affective_preference_sessions_v49_17"
AP_EXPERIENCES = "affective_experiences_v49_17"
AP_PREFERENCES = "affective_preferences_v49_17"
AP_CHOICES = "affective_choice_trials_v49_17"
AP_CONSOLIDATION = "affective_consolidation_v49_17"
SOURCE = "darwin_affective_preference_core_v49_17"


def pj(value: str | None, fallback: Any = None) -> Any:
    try:
        parsed = json.loads(value or "{}")
        return parsed
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
        for key in ("tags_json", "top_evidence_json", "source_kinds_json", "evidence_json"):
            if key in item:
                item[key[:-5]] = pj(str(item.get(key) or "[]"), [])
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
        (SOURCE, f"affective_preference_v49_17:{session_id}"),
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
        (SOURCE, f"affective_preference:{session_id}"),
    ).fetchone()
    return bool(row and int(row["n"]) >= 1)


def metrics_bounded(items: list[dict[str, Any]], keys: tuple[str, ...]) -> bool:
    if not items:
        return False
    for item in items:
        for key in keys:
            value = float(item.get(key) or 0.0)
            if value < 0.0 or value > 1.0:
                return False
    return True


def preference_ordered(preferences: list[dict[str, Any]]) -> bool:
    strengths = [float(p.get("strength") or 0.0) for p in preferences]
    return strengths == sorted(strengths, reverse=True)


def rzs_causal(choices: list[dict[str, Any]]) -> bool:
    if not choices:
        return False
    changed = [c for c in choices if int(c.get("rzs_changed_action") or 0) == 1]
    if not changed:
        return False
    for choice in choices:
        if float(choice.get("sigma_before") or 0.0) <= 0.0:
            return False
        if float(choice.get("sigma_after") or 0.0) <= 0.0:
            return False
        decision = str(choice.get("rzs_decision") or "")
        candidate = str(choice.get("candidate_action") or "")
        chosen = str(choice.get("chosen_action") or "")
        changed_flag = int(choice.get("rzs_changed_action") or 0) == 1
        if changed_flag and candidate == chosen:
            return False
        if decision == "continue" and changed_flag:
            return False
        if decision == "replay_memory" and not chosen.startswith("replay_affective_memory_before_"):
            return False
        if decision == "narrow_focus" and not chosen.startswith("narrow_"):
            return False
        if decision == "consolidate" and chosen != "consolidate_preference_memory":
            return False
    return True


def selected_from_preferences(consolidations: list[dict[str, Any]], preferences: list[dict[str, Any]], choices: list[dict[str, Any]]) -> bool:
    if not consolidations or not preferences or not choices:
        return False
    final = consolidations[-1]
    top_key = str(final.get("top_preference_key") or "")
    selected = str(final.get("selected_action") or "")
    pref_keys = {str(p.get("preference_key")) for p in preferences}
    chosen_actions = {str(c.get("chosen_action")) for c in choices}
    return top_key in pref_keys and selected in chosen_actions


def v49_16_present(conn: sqlite3.Connection) -> bool:
    required = ["music_nursery_sessions_v49_16", "music_reactions_v49_16"]
    if not all(table_exists(conn, t) for t in required):
        return False
    row = conn.execute("SELECT COUNT(*) AS n FROM music_reactions_v49_16").fetchone()
    return bool(row and int(row["n"]) >= 5)


def build_report(conn: sqlite3.Connection) -> dict[str, Any]:
    session_id, complete_row = latest_completed_session(conn)
    experiences = rows(conn, AP_EXPERIENCES, " WHERE session_id=?", (session_id,)) if session_id else []
    preferences = rows(conn, AP_PREFERENCES, " WHERE session_id=?", (session_id,)) if session_id else []
    choices = rows(conn, AP_CHOICES, " WHERE session_id=?", (session_id,)) if session_id else []
    consolidations = rows(conn, AP_CONSOLIDATION, " WHERE session_id=?", (session_id,)) if session_id else []
    payload = complete_row.get("payload", {}) if complete_row else {}
    source_kinds = sorted({str(e.get("source_kind")) for e in experiences if e.get("source_kind")})
    domains = sorted({str(p.get("domain")) for p in preferences if p.get("domain")})
    decisions = sorted({str(c.get("rzs_decision")) for c in choices if c.get("rzs_decision")})
    changed_count = sum(1 for c in choices if int(c.get("rzs_changed_action") or 0) == 1)
    preference_actions = sorted({str(p.get("candidate_action")) for p in preferences if p.get("candidate_action")})

    checks = {
        "tables_exist": all(table_exists(conn, t) for t in (AP_SESSIONS, AP_EXPERIENCES, AP_PREFERENCES, AP_CHOICES, AP_CONSOLIDATION)),
        "completed_session": bool(session_id) and bool(payload.get("session_complete")),
        "experiences_collected": len(experiences) >= 20 and len(source_kinds) >= 5,
        "affective_metrics_bounded": metrics_bounded(experiences, ("valence", "arousal", "comfort", "curiosity", "stability", "confidence")),
        "preferences_created": len(preferences) >= 5 and len(domains) >= 4,
        "preferences_have_evidence": all(int(p.get("evidence_count") or 0) > 0 and p.get("source_kinds") for p in preferences),
        "preferences_ranked": preference_ordered(preferences),
        "choice_trials_created": len(choices) >= 4,
        "rzs_causal_effect": rzs_causal(choices),
        "selected_from_preferences": selected_from_preferences(consolidations, preferences, choices),
        "consolidation_written": bool(consolidations) and bool(str(consolidations[-1].get("identity_statement") or "")),
        "semantic_memory_written": semantic_written(conn, session_id) if session_id else False,
        "episode_written": episode_written(conn, session_id) if session_id else False,
        "v49_16_data_still_present": v49_16_present(conn),
    }
    return {
        "ok": all(checks.values()),
        "session_id": session_id,
        "checks": checks,
        "counts": {
            "experiences": len(experiences),
            "source_kinds": len(source_kinds),
            "preferences": len(preferences),
            "domains": len(domains),
            "choices": len(choices),
            "changed_by_rzs": changed_count,
            "consolidations": len(consolidations),
        },
        "source_kinds": source_kinds,
        "domains": domains,
        "decisions": decisions,
        "preference_actions": preference_actions,
        "top_preferences": [
            {
                "preference_key": p.get("preference_key"),
                "candidate_action": p.get("candidate_action"),
                "strength": round(float(p.get("strength") or 0.0), 3),
                "evidence_count": int(p.get("evidence_count") or 0),
                "source_kinds": p.get("source_kinds", []),
            }
            for p in preferences[:6]
        ],
        "selected_action": consolidations[-1].get("selected_action") if consolidations else "",
        "identity_statement": consolidations[-1].get("identity_statement") if consolidations else "",
        "payload": payload,
    }


def print_report(report: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.17 - DIAGNOSTICO PREFERENCE CORE")
    print("=" * 62)
    print(f"- sessao: {report['session_id'] or 'NENHUMA'}")
    c = report["counts"]
    print(
        f"- experiencias={c['experiences']} fontes={c['source_kinds']} "
        f"preferencias={c['preferences']} escolhas={c['choices']}"
    )
    print(f"- fontes: {', '.join(report['source_kinds']) if report['source_kinds'] else 'nenhuma'}")
    print(f"- RZS: {', '.join(report['decisions']) if report['decisions'] else 'nenhum'}")
    print(f"- escolhida: {report['selected_action'] or 'nenhuma'}")
    print()
    labels = {
        "tables_exist": "tabelas v49.17 existem",
        "completed_session": "sessao completa encontrada",
        "experiences_collected": "experiencias afetivas coletadas",
        "affective_metrics_bounded": "metricas afetivas entre 0 e 1",
        "preferences_created": "preferencias criadas",
        "preferences_have_evidence": "preferencias tem evidencia",
        "preferences_ranked": "preferencias ranqueadas",
        "choice_trials_created": "ensaios de escolha criados",
        "rzs_causal_effect": "RZS teve efeito causal",
        "selected_from_preferences": "acao veio das preferencias",
        "consolidation_written": "consolidacao escrita",
        "semantic_memory_written": "memoria semantica escrita",
        "episode_written": "episodio escrito",
        "v49_16_data_still_present": "dados v49.16 ainda presentes",
    }
    for key, value in report["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'FALHOU'}")
    if report["ok"]:
        print("Leitura: Darwin transformou experiencias em preferencias e deixou o RZS governar a escolha.")
    else:
        print("Leitura: ainda falta evidencia para aceitar preferencia afetiva como marco estavel.")
    if details:
        print("\nJSON:")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.17 Affective Preference checker")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    with connect() as conn:
        report = build_report(conn)
    print_report(report, args.details)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
