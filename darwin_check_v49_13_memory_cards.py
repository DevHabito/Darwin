from __future__ import annotations

"""
DARWIN v49.13 - Diagnostico do jogo de memoria

Uso:
    py darwin_check_v49_13_memory_cards.py
    py darwin_check_v49_13_memory_cards.py --details
"""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"

MC_SESSIONS = "memory_card_sessions_v49_13"
MC_GAMES = "memory_card_games_v49_13"
MC_MOVES = "memory_card_moves_v49_13"
MC_OBSERVATIONS = "memory_card_observations_v49_13"
MC_AGENT_MEMORY = "memory_card_agent_memory_v49_13"
MC_REPLAY = "memory_card_replay_v49_13"


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
        for key in ("positions_json", "matched_positions_json"):
            if key in item:
                item[key[:-5]] = pj(str(item.get(key) or "[]"), [])
        out.append(item)
    return out


def latest_completed_game(conn: sqlite3.Connection) -> tuple[str, str, dict[str, Any]]:
    game_rows = rows(conn, MC_GAMES)
    completed = [
        r
        for r in game_rows
        if r.get("phase") == "game_complete" and r.get("payload", {}).get("game_complete") is True
    ]
    if not completed:
        return "", "", {}
    row = completed[-1]
    return str(row["session_id"]), str(row["game_id"]), row


def semantic_written(conn: sqlite3.Connection, game_id: str) -> bool:
    if not table_exists(conn, "semantic_memory"):
        return False
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM semantic_memory
        WHERE source='darwin_memory_cards_v49_13'
          AND key=?
        """,
        (f"memory_cards_v49_13:{game_id}",),
    ).fetchone()
    return bool(row and int(row["n"]) >= 1)


def episode_count(conn: sqlite3.Connection, session_id: str, game_id: str) -> int:
    if not table_exists(conn, "episodes"):
        return 0
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM episodes
        WHERE module='darwin_memory_cards_v49_13'
          AND context LIKE ?
        """,
        (f"memory_cards:{session_id}:{game_id}:%",),
    ).fetchone()
    return int(row["n"]) if row else 0


def anti_cheat_ok(moves: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    observed: dict[int, str] = {}
    matched: set[int] = set()
    problems: list[str] = []
    turns: dict[int, list[dict[str, Any]]] = {}
    for move in moves:
        turns.setdefault(int(move["turn_id"]), []).append(move)

    for turn_id in sorted(turns):
        turn_moves = sorted(turns[turn_id], key=lambda m: int(m["pick_index"]))
        if len(turn_moves) != 2:
            problems.append(f"turn {turn_id}: expected 2 moves, got {len(turn_moves)}")
            continue
        first, second = turn_moves
        for move in turn_moves:
            pos = int(move["position"])
            source = str(move["decision_source"])
            symbol = str(move["observed_symbol"])
            known_before = move.get("payload", {}).get("known_before", {})
            before_observed = {int(k): v for k, v in known_before.get("observed", {}).items()}
            before_matched = set(int(p) for p in known_before.get("matched_positions", []))
            before_unseen = set(int(p) for p in known_before.get("unseen", []))
            if pos in before_matched:
                problems.append(f"turn {turn_id}: chose already matched position {pos}")
            if source.startswith("explore_unseen") and pos not in before_unseen:
                problems.append(f"turn {turn_id}: explore chose seen position {pos}")
            if source == "known_pair_first":
                pairs = known_before.get("known_pairs", [])
                ok = any(int(p.get("a")) == pos or int(p.get("b")) == pos for p in pairs)
                if not ok:
                    problems.append(f"turn {turn_id}: known_pair_first without known pair for {pos}")
            if source == "match_from_memory_second":
                first_symbol = str(first["observed_symbol"])
                candidates = [
                    p
                    for p, s in before_observed.items()
                    if s == first_symbol and p != int(first["position"]) and p not in before_matched
                ]
                if pos not in candidates:
                    problems.append(f"turn {turn_id}: memory second pick {pos} had no prior observation")
            observed[pos] = symbol
        if int(first["matched"]) == 1:
            matched.add(int(first["position"]))
            matched.add(int(second["position"]))
    return not problems, problems[:12]


def build_report(conn: sqlite3.Connection) -> dict[str, Any]:
    session_id, game_id, game_row = latest_completed_game(conn)
    moves = rows(conn, MC_MOVES, " WHERE session_id=? AND game_id=?", (session_id, game_id)) if game_id else []
    observations = rows(conn, MC_OBSERVATIONS, " WHERE session_id=? AND game_id=?", (session_id, game_id)) if game_id else []
    memories = rows(conn, MC_AGENT_MEMORY, " WHERE session_id=? AND game_id=?", (session_id, game_id)) if game_id else []
    replays = rows(conn, MC_REPLAY, " WHERE session_id=? AND game_id=?", (session_id, game_id)) if game_id else []
    payload = game_row.get("payload", {}) if game_row else {}
    pair_count = int(game_row.get("pair_count") or 0) if game_row else 0
    turns = {int(m.get("turn_id") or 0) for m in moves}
    memory_sources = {str(m.get("decision_source")) for m in moves if "memory" in str(m.get("decision_source")) or "known_pair" in str(m.get("decision_source"))}
    explore_sources = {str(m.get("decision_source")) for m in moves if "explore" in str(m.get("decision_source"))}
    matched_turns = {int(m.get("turn_id") or 0) for m in moves if int(m.get("matched") or 0) == 1}
    rzs_decisions = {str(m.get("rzs_decision")) for m in moves if m.get("rzs_decision")}
    anti_ok, anti_problems = anti_cheat_ok(moves)
    ep_n = episode_count(conn, session_id, game_id) if game_id else 0

    checks = {
        "tables_exist": all(table_exists(conn, t) for t in (MC_SESSIONS, MC_GAMES, MC_MOVES, MC_OBSERVATIONS, MC_AGENT_MEMORY, MC_REPLAY)),
        "completed_game": bool(game_id) and bool(payload.get("game_complete")),
        "all_pairs_found": len(matched_turns) == pair_count and len(payload.get("all_positions_matched", [])) == pair_count * 2,
        "moves_and_observations_logged": len(moves) == len(observations) >= pair_count * 2,
        "agent_explored_unknowns": bool(explore_sources),
        "agent_used_memory": bool(memory_sources) and int(payload.get("memory_picks") or 0) > 0,
        "anti_cheat_observation_only": anti_ok and payload.get("agent_access") == "observations_only",
        "memory_snapshots_written": len(memories) >= len(turns),
        "replay_or_known_pair_logged": len(replays) >= 1 or bool(memory_sources),
        "rzs_logged": bool(rzs_decisions) and all(float(m.get("sigma_before") or 0.0) > 0.0 for m in moves),
        "semantic_memory_written": semantic_written(conn, game_id) if game_id else False,
        "episodes_written": ep_n >= len(turns) if game_id else False,
        "turn_limit_reasonable": len(turns) <= max(1, pair_count * 4),
    }
    return {
        "ok": all(checks.values()),
        "session_id": session_id,
        "game_id": game_id,
        "checks": checks,
        "counts": {
            "pair_count": pair_count,
            "turns": len(turns),
            "moves": len(moves),
            "observations": len(observations),
            "memories": len(memories),
            "replays": len(replays),
            "matched_turns": len(matched_turns),
            "episodes": ep_n,
        },
        "decision_sources": sorted({str(m.get("decision_source")) for m in moves}),
        "rzs_decisions": sorted(rzs_decisions),
        "anti_cheat_problems": anti_problems,
        "payload": payload,
    }


def print_report(report: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.13 - DIAGNOSTICO JOGO DE MEMORIA")
    print("=" * 58)
    print(f"- sessao: {report['session_id'] or 'NENHUMA'}")
    print(f"- jogo: {report['game_id'] or 'NENHUM'}")
    c = report["counts"]
    print(
        f"- pares={c['pair_count']} turnos={c['turns']} movimentos={c['moves']} "
        f"observacoes={c['observations']} replays={c['replays']}"
    )
    print(f"- fontes decisao: {', '.join(report['decision_sources']) if report['decision_sources'] else 'nenhuma'}")
    print(f"- RZS: {', '.join(report['rzs_decisions']) if report['rzs_decisions'] else 'nenhum'}")
    print()
    labels = {
        "tables_exist": "tabelas v49.13 existem",
        "completed_game": "jogo completo encontrado",
        "all_pairs_found": "todos os pares encontrados",
        "moves_and_observations_logged": "movimentos e observacoes registrados",
        "agent_explored_unknowns": "Darwin explorou cartas desconhecidas",
        "agent_used_memory": "Darwin usou memoria observada",
        "anti_cheat_observation_only": "anti-trapaca: apenas observacao",
        "memory_snapshots_written": "snapshots de memoria escritos",
        "replay_or_known_pair_logged": "replay/par conhecido registrado",
        "rzs_logged": "RZS registrado",
        "semantic_memory_written": "memoria semantica escrita",
        "episodes_written": "episodios escritos",
        "turn_limit_reasonable": "turnos dentro de limite razoavel",
    }
    for key, value in report["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'FALHOU'}")
    if report["ok"]:
        print("Leitura: Darwin resolveu o jogo lembrando cartas observadas, sem posicao programada.")
    else:
        print("Leitura: ainda falta evidencia para aceitar o jogo como memoria observacional estavel.")
        if report["anti_cheat_problems"]:
            print("Problemas anti-trapaca:")
            for problem in report["anti_cheat_problems"]:
                print(f"- {problem}")
    if details:
        print("\nJSON:")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.13 Memory Cards checker")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    with connect() as conn:
        report = build_report(conn)
    print_report(report, args.details)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
