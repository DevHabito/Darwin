from __future__ import annotations

"""
DARWIN v49.16 - Diagnostico do bercario musical classico

Uso:
    py darwin_check_v49_16_classical_music.py
    py darwin_check_v49_16_classical_music.py --details
"""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"

MUSIC_SESSIONS = "music_nursery_sessions_v49_16"
MUSIC_PIECES = "music_pieces_v49_16"
MUSIC_EXPOSURES = "music_exposures_v49_16"
MUSIC_REACTIONS = "music_reactions_v49_16"
MUSIC_REPLAY = "music_replay_v49_16"
SOURCE = "darwin_classical_music_nursery_v49_16"


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
        for key in ("feature_json", "safety_json"):
            if key in item:
                item[key[:-5]] = pj(str(item.get(key) or "{}"))
        out.append(item)
    return out


def latest_completed_session(conn: sqlite3.Connection) -> tuple[str, dict[str, Any]]:
    session_rows = rows(conn, MUSIC_SESSIONS)
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
        (SOURCE, f"music_nursery_v49_16:{session_id}"),
    ).fetchone()
    return bool(row and int(row["n"]) >= 1)


def episode_count(conn: sqlite3.Connection, session_id: str) -> int:
    if not table_exists(conn, "episodes"):
        return 0
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM episodes
        WHERE module=? AND context LIKE ?
        """,
        (SOURCE, f"music_nursery:{session_id}:%"),
    ).fetchone()
    return int(row["n"]) if row else 0


def audio_files_exist(pieces: list[dict[str, Any]]) -> bool:
    if not pieces:
        return False
    for piece in pieces:
        path = Path(str(piece.get("wav_path") or ""))
        if not path.exists() or int(piece.get("sample_count") or 0) <= 0:
            return False
    return True


def repertoire_safe(pieces: list[dict[str, Any]]) -> bool:
    if len(pieces) < 5:
        return False
    for piece in pieces:
        safety = piece.get("safety", {})
        if int(piece.get("child_safe") or 0) != 1:
            return False
        violence = float(piece["violence_score"]) if piece.get("violence_score") is not None else 1.0
        dissonance = float(piece["dissonance_score"]) if piece.get("dissonance_score") is not None else 1.0
        tempo = int(piece["tempo_bpm"]) if piece.get("tempo_bpm") is not None else 999
        if violence > 0.05:
            return False
        if dissonance > 0.32:
            return False
        if tempo > 92:
            return False
        if bool(safety.get("external_recording")):
            return False
        if str(safety.get("audio_origin")) != "local_sine_wave_synthesis":
            return False
    return True


def rzs_causality_ok(reactions: list[dict[str, Any]]) -> bool:
    if not reactions:
        return False
    decisions = {str(r.get("rzs_decision")) for r in reactions}
    if not any(decision in decisions for decision in ("narrow_focus", "replay_memory", "consolidate", "pause_for_stability")):
        return False
    for reaction in reactions:
        action = str(reaction.get("cognitive_action") or "")
        decision = str(reaction.get("rzs_decision") or "")
        if float(reaction.get("sigma_before") or 0.0) <= 0.0:
            return False
        if float(reaction.get("sigma_after") or 0.0) <= 0.0:
            return False
        if decision == "narrow_focus" and not action.startswith("focus_"):
            return False
        if decision == "replay_memory" and action != "listen_again_softly":
            return False
        if decision == "consolidate" and action != "consolidate_music_impression":
            return False
        if decision == "pause_for_stability" and action != "pause_and_lower_stimulation":
            return False
    return True


def build_report(conn: sqlite3.Connection) -> dict[str, Any]:
    session_id, complete_row = latest_completed_session(conn)
    pieces = rows(conn, MUSIC_PIECES, " WHERE session_id=?", (session_id,)) if session_id else []
    exposures = rows(conn, MUSIC_EXPOSURES, " WHERE session_id=?", (session_id,)) if session_id else []
    reactions = rows(conn, MUSIC_REACTIONS, " WHERE session_id=?", (session_id,)) if session_id else []
    replays = rows(conn, MUSIC_REPLAY, " WHERE session_id=?", (session_id,)) if session_id else []
    phases = {str(s.get("phase")) for s in rows(conn, MUSIC_SESSIONS, " WHERE session_id=?", (session_id,))} if session_id else set()
    decisions = {str(r.get("rzs_decision")) for r in reactions if r.get("rzs_decision")}
    actions = {str(r.get("cognitive_action")) for r in reactions if r.get("cognitive_action")}
    source_kinds = {str(e.get("source_kind")) for e in exposures if e.get("source_kind")}
    episode_n = episode_count(conn, session_id) if session_id else 0
    payload = complete_row.get("payload", {}) if complete_row else {}

    child_features_ok = all(
        0.0 <= float(r.get("valence") or 0.0) <= 1.0
        and 0.0 <= float(r.get("arousal") or 0.0) <= 1.0
        and 0.0 <= float(r.get("stability") or 0.0) <= 1.0
        and 0.0 <= float(r.get("comfort") or 0.0) <= 1.0
        for r in reactions
    )

    checks = {
        "tables_exist": all(table_exists(conn, t) for t in (MUSIC_SESSIONS, MUSIC_PIECES, MUSIC_EXPOSURES, MUSIC_REACTIONS, MUSIC_REPLAY)),
        "completed_session": bool(session_id) and bool(payload.get("session_complete")),
        "repertoire_child_safe": repertoire_safe(pieces),
        "audio_synthesized_locally": audio_files_exist(pieces),
        "internal_exposures_logged": len(exposures) >= 5 and source_kinds == {"synthesized_classical_nursery"},
        "reactions_measured": len(reactions) >= len(exposures) + 1 and child_features_ok,
        "rzs_influenced_decision": rzs_causality_ok(reactions),
        "replay_logged": len(replays) >= 1 and "replay_memory" in {str(r.get("rzs_decision")) for r in replays},
        "consolidation_logged": "session_consolidated" in phases and "consolidate_music_impression" in actions,
        "semantic_memory_written": semantic_written(conn, session_id) if session_id else False,
        "episodes_written": episode_n >= len(exposures) + 2 if session_id else False,
    }
    return {
        "ok": all(checks.values()),
        "session_id": session_id,
        "checks": checks,
        "counts": {
            "pieces": len(pieces),
            "exposures": len(exposures),
            "reactions": len(reactions),
            "replays": len(replays),
            "episodes": episode_n,
        },
        "decisions": sorted(decisions),
        "actions": sorted(actions),
        "source_kinds": sorted(source_kinds),
        "pieces": [
            {
                "piece_id": p.get("piece_id"),
                "title": p.get("title"),
                "tempo_bpm": p.get("tempo_bpm"),
                "dissonance": round(float(p.get("dissonance_score") or 0.0), 3),
                "violence": round(float(p.get("violence_score") or 0.0), 3),
                "child_safe": bool(p.get("child_safe")),
            }
            for p in pieces
        ],
        "payload": payload,
    }


def print_report(report: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.16 - DIAGNOSTICO MUSICA CLASSICA")
    print("=" * 58)
    print(f"- sessao: {report['session_id'] or 'NENHUMA'}")
    c = report["counts"]
    print(
        f"- pecas={c['pieces']} exposicoes={c['exposures']} "
        f"reacoes={c['reactions']} replays={c['replays']} episodios={c['episodes']}"
    )
    print(f"- RZS: {', '.join(report['decisions']) if report['decisions'] else 'nenhum'}")
    print(f"- acoes: {', '.join(report['actions']) if report['actions'] else 'nenhuma'}")
    print()
    labels = {
        "tables_exist": "tabelas v49.16 existem",
        "completed_session": "sessao completa encontrada",
        "repertoire_child_safe": "repertorio infantil e nao violento",
        "audio_synthesized_locally": "audio sintetizado localmente",
        "internal_exposures_logged": "exposicoes internas registradas",
        "reactions_measured": "reacoes medidas",
        "rzs_influenced_decision": "RZS influenciou decisoes",
        "replay_logged": "replay musical registrado",
        "consolidation_logged": "consolidacao registrada",
        "semantic_memory_written": "memoria semantica escrita",
        "episodes_written": "episodios escritos",
    }
    for key, value in report["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'FALHOU'}")
    if report["ok"]:
        print("Leitura: Darwin ouviu trechos classicos simples e reagiu com regulacao RZS auditavel.")
    else:
        print("Leitura: ainda falta evidencia para aceitar este marco como estavel.")
    if details:
        print("\nJSON:")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.16 Classical Music checker")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    with connect() as conn:
        report = build_report(conn)
    print_report(report, args.details)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
