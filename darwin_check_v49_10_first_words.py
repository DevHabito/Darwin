from __future__ import annotations

"""
DARWIN v49.10 - Diagnostico do First Words Nursery

Uso:
    py darwin_check_v49_10_first_words.py
    py darwin_check_v49_10_first_words.py --details
"""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"

FW_SESSIONS = "voice_first_word_sessions_v49_10"
FW_ATTEMPTS = "voice_first_word_attempts_v49_10"
FW_NODES = "voice_first_word_nodes_v49_10"
FW_MEANINGS = "voice_word_meanings_v49_10"
FW_LINKS = "voice_phoneme_links_v49_10"

CORE_WORDS = {"mamae", "papai", "felipe", "darwin"}


def pj(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


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
        item["payload"] = pj(str(item.get("payload_json") or "{}"))
        if "syllables_json" in item:
            try:
                item["syllables"] = json.loads(str(item.get("syllables_json") or "[]"))
            except Exception:
                item["syllables"] = []
        out.append(item)
    return out


def latest_completed(conn: sqlite3.Connection) -> tuple[str, dict[str, Any]]:
    session_rows = rows(conn, FW_SESSIONS)
    completed = [
        r
        for r in session_rows
        if r.get("phase") == "first_words_complete" and r.get("payload", {}).get("session_complete") is True
    ]
    if not completed:
        return "", {}
    row = completed[-1]
    return str(row["session_id"]), row


def semantic_count(conn: sqlite3.Connection) -> int:
    if not table_exists(conn, "semantic_memory"):
        return 0
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM semantic_memory
        WHERE source='darwin_first_words_v49_10'
          AND key LIKE 'first_words_v49_10:%'
        """
    ).fetchone()
    return int(row["n"]) if row else 0


def episode_count(conn: sqlite3.Connection, session_id: str) -> int:
    if not table_exists(conn, "episodes"):
        return 0
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM episodes
        WHERE module='darwin_first_words_v49_10'
          AND context LIKE ?
        """,
        (f"first_words:{session_id}:%",),
    ).fetchone()
    return int(row["n"]) if row else 0


def build_report(conn: sqlite3.Connection) -> dict[str, Any]:
    session_id, complete_row = latest_completed(conn)
    attempts = rows(conn, FW_ATTEMPTS, session_id) if session_id else []
    nodes = rows(conn, FW_NODES, session_id) if session_id else []
    meanings = rows(conn, FW_MEANINGS, session_id) if session_id else []
    links = rows(conn, FW_LINKS, session_id) if session_id else []
    payload = complete_row.get("payload", {}) if complete_row else {}
    words = {str(n.get("canonical_word")) for n in nodes if n.get("canonical_word")}
    accepted = [a for a in attempts if int(a.get("accepted") or 0) == 1]
    mamae_nodes = [n for n in nodes if n.get("canonical_word") == "mamae"]
    repeated_mamae = bool(mamae_nodes) and max(int(n.get("exposure_count") or 0) for n in mamae_nodes) >= 3
    confidence_growth = any(
        float(n.get("meaning_confidence_after") or 0.0) > float(n.get("meaning_confidence_before") or 0.0)
        and float(n.get("sound_confidence_after") or 0.0) > float(n.get("sound_confidence_before") or 0.0)
        for n in nodes
    )
    rzs_decisions = {str(n.get("rzs_decision")) for n in nodes if n.get("rzs_decision")}
    syllable_nodes = [n for n in nodes if n.get("syllables")]
    meaning_keys = {str(m.get("meaning_key")) for m in meanings if m.get("meaning_key")}
    sem_n = semantic_count(conn)
    ep_n = episode_count(conn, session_id) if session_id else 0

    checks = {
        "tables_exist": all(table_exists(conn, t) for t in (FW_SESSIONS, FW_ATTEMPTS, FW_NODES, FW_MEANINGS, FW_LINKS)),
        "completed_session": bool(session_id),
        "attempts_logged": len(attempts) >= 8 and len(accepted) >= 7,
        "first_word_nodes_created": len(nodes) >= 7 and all(str(n.get("node_id", "")).startswith("firstword:") for n in nodes),
        "core_words_learned": CORE_WORDS.issubset(words),
        "mamae_repeated_like_child": repeated_mamae,
        "confidence_increases": confidence_growth,
        "meanings_created": len(meanings) >= 5 and {"caregiver_mother", "caregiver_father", "primary_person", "self_name"}.issubset(meaning_keys),
        "sound_units_linked": len(links) >= len(nodes) * 2 and bool(syllable_nodes),
        "rzs_regulated_learning": bool(rzs_decisions) and all(float(n.get("sigma_before") or 0.0) > 0.0 for n in nodes),
        "semantic_memory_written": sem_n >= 5,
        "episodes_written": ep_n >= len(nodes),
        "complete_payload_ok": int(payload.get("learned_count") or 0) >= 5 and int(payload.get("total_exposures") or 0) >= 8,
    }
    return {
        "ok": all(checks.values()),
        "session_id": session_id,
        "checks": checks,
        "counts": {
            "attempts": len(attempts),
            "accepted": len(accepted),
            "nodes": len(nodes),
            "meanings": len(meanings),
            "links": len(links),
            "semantic": sem_n,
            "episodes": ep_n,
        },
        "words": sorted(words),
        "meaning_keys": sorted(meaning_keys),
        "rzs_decisions": sorted(rzs_decisions),
        "payload": payload,
    }


def print_report(report: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.10 - DIAGNOSTICO FIRST WORDS NURSERY")
    print("=" * 62)
    print(f"- sessao v49.10: {report['session_id'] or 'NENHUMA'}")
    c = report["counts"]
    print(
        f"- tentativas={c['attempts']} aceitas={c['accepted']} nos={c['nodes']} "
        f"significados={c['meanings']} links={c['links']}"
    )
    print(f"- palavras: {', '.join(report['words']) if report['words'] else 'nenhuma'}")
    print(f"- decisoes RZS: {', '.join(report['rzs_decisions']) if report['rzs_decisions'] else 'nenhuma'}")
    print()
    labels = {
        "tables_exist": "tabelas v49.10 existem",
        "completed_session": "sessao completa encontrada",
        "attempts_logged": "tentativas de fala registradas",
        "first_word_nodes_created": "nos de primeiras palavras criados",
        "core_words_learned": "mamae/papai/Felipe/Darwin aprendidos",
        "mamae_repeated_like_child": "mamae reforcado por repeticao",
        "confidence_increases": "confianca aumentou com experiencia",
        "meanings_created": "significados relacionais criados",
        "sound_units_linked": "sons/silabas ligados ao significado",
        "rzs_regulated_learning": "RZS regulou aprendizagem",
        "semantic_memory_written": "memoria semantica escrita",
        "episodes_written": "episodios escritos",
        "complete_payload_ok": "payload final consistente",
    }
    for key, value in report["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'FALHOU'}")
    if report["ok"]:
        print("Leitura: Darwin aprendeu primeiras palavras como experiencias sonoras e relacionais.")
    else:
        print("Leitura: ainda falta evidencia para aceitar o bercario de primeiras palavras.")
    if details:
        print("\nJSON:")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.10 First Words checker")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    with connect() as conn:
        report = build_report(conn)
    print_report(report, args.details)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
