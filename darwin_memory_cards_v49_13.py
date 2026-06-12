from __future__ import annotations

"""
DARWIN v49.13 - Memory Cards Autoplay

Objetivo:
Criar um jogo de memoria com cartas viradas para baixo. Darwin joga
sozinho, sem receber a solucao do tabuleiro. Ele so conhece uma carta
depois de vira-la; guarda observacoes; explora cartas desconhecidas;
e usa memoria para encontrar pares.

Uso:
    py darwin_memory_cards_v49_13.py
    py darwin_memory_cards_v49_13.py --self-test --details
"""

import argparse
import json
import math
import random
import sqlite3
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tkinter import ttk
from typing import Any

from darwin_rzs_nervous_system_v49_3 import RZSFormal, RZSInput


DB = Path("darwin_home") / "darwin.db"

MC_SESSIONS = "memory_card_sessions_v49_13"
MC_GAMES = "memory_card_games_v49_13"
MC_MOVES = "memory_card_moves_v49_13"
MC_OBSERVATIONS = "memory_card_observations_v49_13"
MC_AGENT_MEMORY = "memory_card_agent_memory_v49_13"
MC_REPLAY = "memory_card_replay_v49_13"

SYMBOLS = [
    "circle",
    "square",
    "triangle",
    "diamond",
    "star",
    "moon",
    "cross",
    "hexagon",
    "heart",
    "wave",
]

COLORS = {
    "circle": "#58b0ff",
    "square": "#75e7a8",
    "triangle": "#f2bf72",
    "diamond": "#b197fc",
    "star": "#f5d76e",
    "moon": "#8fd3ff",
    "cross": "#ff707a",
    "hexagon": "#7ee787",
    "heart": "#ff8ab3",
    "wave": "#5eead4",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def js(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def pj(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def suffix(rng: random.Random) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(rng.choice(alphabet) for _ in range(5))


def mean(values: list[float]) -> float:
    return sum(values) / max(1, len(values))


@dataclass
class Card:
    position: int
    symbol: str
    matched: bool = False
    face_up: bool = False


@dataclass
class Observation:
    position: int
    symbol: str
    turn_id: int


@dataclass
class MoveDecision:
    position: int
    decision_source: str
    reason: str
    known_before: dict[str, Any]
    rzs_decision: str
    sigma_before: float


@dataclass
class TurnResult:
    turn_id: int
    first: MoveDecision
    second: MoveDecision
    first_symbol: str
    second_symbol: str
    matched: bool
    match_symbol: str
    sigma_after: float


class MemoryCardsStore:
    def __init__(self, db_path: Path = DB) -> None:
        self.db_path = db_path
        self.ensure()

    def connect(self) -> sqlite3.Connection:
        if not self.db_path.exists():
            raise FileNotFoundError(f"Banco Darwin nao encontrado: {self.db_path}")
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS {MC_SESSIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {MC_GAMES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    game_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    rows INTEGER NOT NULL,
                    cols INTEGER NOT NULL,
                    pair_count INTEGER NOT NULL,
                    shuffle_seed INTEGER NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {MC_MOVES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    game_id TEXT NOT NULL,
                    turn_id INTEGER NOT NULL,
                    pick_index INTEGER NOT NULL,
                    position INTEGER NOT NULL,
                    observed_symbol TEXT NOT NULL,
                    decision_source TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    matched INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {MC_OBSERVATIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    game_id TEXT NOT NULL,
                    turn_id INTEGER NOT NULL,
                    position INTEGER NOT NULL,
                    observed_symbol TEXT NOT NULL,
                    observation_kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {MC_AGENT_MEMORY} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    game_id TEXT NOT NULL,
                    turn_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    positions_json TEXT NOT NULL DEFAULT '[]',
                    matched_positions_json TEXT NOT NULL DEFAULT '[]',
                    known_pair_available INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {MC_REPLAY} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    game_id TEXT NOT NULL,
                    replay_id TEXT NOT NULL UNIQUE,
                    replay_kind TEXT NOT NULL,
                    known_pairs_count INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS semantic_memory (
                    key TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    source TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    module TEXT NOT NULL,
                    context TEXT NOT NULL,
                    action_taken TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    lesson TEXT NOT NULL,
                    sigma_before REAL NOT NULL,
                    sigma_after REAL NOT NULL
                );
                """
            )
            conn.commit()

    def log_session(self, session_id: str, phase: str, mode: str, payload: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                f"INSERT INTO {MC_SESSIONS} (timestamp, session_id, phase, mode, payload_json) VALUES (?, ?, ?, ?, ?)",
                (now(), session_id, phase, mode, js(payload or {})),
            )
            conn.commit()

    def log_game(self, session_id: str, game_id: str, phase: str, rows: int, cols: int, pair_count: int, shuffle_seed: int, payload: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {MC_GAMES} (
                    timestamp, session_id, game_id, phase, rows, cols,
                    pair_count, shuffle_seed, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, game_id, phase, rows, cols, pair_count, shuffle_seed, js(payload or {})),
            )
            conn.commit()

    def log_move(self, session_id: str, game_id: str, turn: TurnResult, pick_index: int) -> None:
        decision = turn.first if pick_index == 1 else turn.second
        symbol = turn.first_symbol if pick_index == 1 else turn.second_symbol
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {MC_MOVES} (
                    timestamp, session_id, game_id, turn_id, pick_index,
                    position, observed_symbol, decision_source, reason,
                    rzs_decision, sigma_before, sigma_after, matched,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    game_id,
                    turn.turn_id,
                    pick_index,
                    decision.position,
                    symbol,
                    decision.decision_source,
                    decision.reason,
                    decision.rzs_decision,
                    decision.sigma_before,
                    turn.sigma_after,
                    1 if turn.matched else 0,
                    js({"known_before": decision.known_before, "match_symbol": turn.match_symbol}),
                ),
            )
            conn.commit()

    def log_observation(self, session_id: str, game_id: str, turn_id: int, obs: Observation, kind: str) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {MC_OBSERVATIONS} (
                    timestamp, session_id, game_id, turn_id, position,
                    observed_symbol, observation_kind, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, game_id, turn_id, obs.position, obs.symbol, kind, js({"source": "card_reveal"})),
            )
            conn.commit()

    def log_agent_memory(self, session_id: str, game_id: str, turn_id: int, snapshot: dict[str, Any]) -> None:
        with self.connect() as conn:
            for symbol, positions in snapshot.get("symbol_positions", {}).items():
                matched = snapshot.get("matched_by_symbol", {}).get(symbol, [])
                available = 1 if len([p for p in positions if p not in matched]) >= 2 else 0
                conn.execute(
                    f"""
                    INSERT INTO {MC_AGENT_MEMORY} (
                        timestamp, session_id, game_id, turn_id, symbol,
                        positions_json, matched_positions_json,
                        known_pair_available, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (now(), session_id, game_id, turn_id, symbol, js(positions), js(matched), available, js(snapshot)),
                )
            conn.commit()

    def log_replay(self, session_id: str, game_id: str, replay_id: str, kind: str, known_pairs: int, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {MC_REPLAY} (
                    timestamp, session_id, game_id, replay_id, replay_kind,
                    known_pairs_count, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, game_id, replay_id, kind, known_pairs, js(payload)),
            )
            conn.commit()

    def write_episode(self, context: str, action: str, outcome: str, lesson: str, sigma_before: float, sigma_after: float) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO episodes (
                    timestamp, module, context, action_taken, outcome,
                    lesson, sigma_before, sigma_after
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), "darwin_memory_cards_v49_13", context, action, outcome, lesson, sigma_before, sigma_after),
            )
            conn.commit()

    def write_memory(self, key: str, content: str, confidence: float) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO semantic_memory (key, content, confidence, source, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    content=excluded.content,
                    confidence=max(semantic_memory.confidence, excluded.confidence),
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                (key, content, clamp(confidence, 0.0, 0.99), "darwin_memory_cards_v49_13", now()),
            )
            conn.commit()


class MemoryCardEnvironment:
    def __init__(self, rows: int = 4, cols: int = 4, seed: int = 4913) -> None:
        if rows * cols % 2:
            raise ValueError("O tabuleiro precisa ter numero par de cartas.")
        self.rows = rows
        self.cols = cols
        self.seed = seed
        self.rng = random.Random(seed)
        self.cards: list[Card] = []
        self.reset(seed)

    @property
    def size(self) -> int:
        return self.rows * self.cols

    @property
    def pair_count(self) -> int:
        return self.size // 2

    def reset(self, seed: int | None = None) -> None:
        if seed is not None:
            self.seed = seed
            self.rng = random.Random(seed)
        symbols = SYMBOLS[: self.pair_count]
        deck = symbols + symbols
        self.rng.shuffle(deck)
        self.cards = [Card(i, symbol) for i, symbol in enumerate(deck)]

    def reveal(self, position: int) -> Observation:
        card = self.cards[position]
        if card.matched:
            raise ValueError(f"Carta ja encontrada: {position}")
        card.face_up = True
        return Observation(position, card.symbol, 0)

    def hide_unmatched(self, positions: list[int]) -> None:
        for position in positions:
            card = self.cards[position]
            if not card.matched:
                card.face_up = False

    def mark_match(self, a: int, b: int) -> bool:
        ca = self.cards[a]
        cb = self.cards[b]
        ok = ca.symbol == cb.symbol and a != b
        if ok:
            ca.matched = True
            cb.matched = True
            ca.face_up = True
            cb.face_up = True
        return ok

    def is_complete(self) -> bool:
        return all(card.matched for card in self.cards)

    def matched_positions(self) -> set[int]:
        return {card.position for card in self.cards if card.matched}

    def visible_state(self) -> list[dict[str, Any]]:
        out = []
        for card in self.cards:
            out.append(
                {
                    "position": card.position,
                    "matched": card.matched,
                    "face_up": card.face_up,
                    "symbol": card.symbol if card.face_up or card.matched else "",
                }
            )
        return out


class DarwinMemoryCardAgent:
    def __init__(self, size: int, seed: int = 4913) -> None:
        self.size = size
        self.rng = random.Random(seed)
        self.rzs = RZSFormal()
        self.observed: dict[int, str] = {}
        self.symbol_positions: dict[str, set[int]] = {}
        self.matched_positions: set[int] = set()
        self.turn_id = 0
        self.mismatch_count = 0
        self.match_count = 0

    def reset(self) -> None:
        self.observed.clear()
        self.symbol_positions.clear()
        self.matched_positions.clear()
        self.turn_id = 0
        self.mismatch_count = 0
        self.match_count = 0

    def unseen_unmatched(self) -> list[int]:
        return [p for p in range(self.size) if p not in self.observed and p not in self.matched_positions]

    def known_unmatched_positions(self, symbol: str) -> list[int]:
        return sorted([p for p in self.symbol_positions.get(symbol, set()) if p not in self.matched_positions])

    def known_pairs(self) -> list[tuple[str, int, int]]:
        pairs = []
        for symbol, positions in self.symbol_positions.items():
            open_positions = [p for p in positions if p not in self.matched_positions]
            if len(open_positions) >= 2:
                pairs.append((symbol, min(open_positions), max(open_positions)))
        return sorted(pairs, key=lambda x: (x[0], x[1], x[2]))

    def memory_snapshot(self) -> dict[str, Any]:
        matched_by_symbol: dict[str, list[int]] = {}
        for symbol, positions in self.symbol_positions.items():
            matched_by_symbol[symbol] = sorted([p for p in positions if p in self.matched_positions])
        return {
            "observed": {str(k): v for k, v in sorted(self.observed.items())},
            "symbol_positions": {s: sorted(v) for s, v in sorted(self.symbol_positions.items())},
            "matched_positions": sorted(self.matched_positions),
            "matched_by_symbol": matched_by_symbol,
            "known_pairs": [{"symbol": s, "a": a, "b": b} for s, a, b in self.known_pairs()],
            "unseen": self.unseen_unmatched(),
        }

    def rzs_input(self) -> RZSInput:
        unseen_ratio = len(self.unseen_unmatched()) / max(1, self.size - len(self.matched_positions))
        known_pair_count = len(self.known_pairs())
        memory_pressure = clamp((len(self.observed) - len(self.matched_positions)) / max(1, self.size))
        recent_conflict = clamp(self.mismatch_count / max(1, self.turn_id + 1))
        return RZSInput(
            bandwidth=4.2 + known_pair_count * 0.20,
            info_self=0.30 + memory_pressure * 0.30,
            info_external=0.42 + unseen_ratio * 0.26,
            task_info=0.62,
            novelty=clamp(unseen_ratio),
            conflict=clamp(0.12 + recent_conflict * 0.48),
            latency=0.76 + memory_pressure * 0.32,
            energy=0.84,
            memory_pressure=memory_pressure,
            replay_gap=0.82 if known_pair_count else 0.30,
        )

    def choose_first(self) -> MoveDecision:
        x = self.rzs_input()
        assessment = self.rzs.classify(x)
        snapshot = self.memory_snapshot()
        pairs = self.known_pairs()
        if pairs:
            symbol, a, _b = pairs[0]
            source = "known_pair_first"
            reason = f"memory_has_pair:{symbol}"
            position = a
        else:
            unseen = self.unseen_unmatched()
            if unseen:
                source = "explore_unseen_first"
                reason = "no_known_pair_explore_lowest_unseen"
                position = unseen[0]
            else:
                candidates = [p for p in range(self.size) if p not in self.matched_positions]
                source = "review_known_single_first"
                reason = "all_cards_seen_review_memory"
                position = candidates[0]
        return MoveDecision(position, source, reason, snapshot, assessment.decision, assessment.sigma)

    def choose_second(self, first_position: int, first_symbol: str) -> MoveDecision:
        x = self.rzs_input()
        assessment = self.rzs.classify(x)
        snapshot = self.memory_snapshot()
        candidates = [p for p in self.known_unmatched_positions(first_symbol) if p != first_position]
        if candidates:
            source = "match_from_memory_second"
            reason = f"seen_same_symbol:{first_symbol}"
            position = candidates[0]
        else:
            unseen = [p for p in self.unseen_unmatched() if p != first_position]
            if unseen:
                source = "explore_unseen_second"
                reason = "no_seen_partner_explore_next_unseen"
                position = unseen[0]
            else:
                candidates = [p for p in range(self.size) if p not in self.matched_positions and p != first_position]
                source = "review_known_single_second"
                reason = "all_cards_seen_choose_remaining_memory"
                position = candidates[0]
        return MoveDecision(position, source, reason, snapshot, assessment.decision, assessment.sigma)

    def observe(self, obs: Observation) -> None:
        self.observed[obs.position] = obs.symbol
        self.symbol_positions.setdefault(obs.symbol, set()).add(obs.position)

    def apply_turn_outcome(self, first: Observation, second: Observation, matched: bool) -> None:
        if matched:
            self.match_count += 1
            self.matched_positions.add(first.position)
            self.matched_positions.add(second.position)
        else:
            self.mismatch_count += 1


class MemoryCardsRuntime:
    def __init__(self, rows: int = 4, cols: int = 4, seed: int = 4913, mode: str = "gui") -> None:
        self.rows = rows
        self.cols = cols
        self.seed = seed
        self.mode = mode
        self.rng = random.Random(seed)
        self.store = MemoryCardsStore()
        self.session_id = f"V4913-{int(time.time()) % 10_000_000}-{suffix(self.rng)}"
        self.game_index = 0
        self.game_id = ""
        self.env = MemoryCardEnvironment(rows, cols, seed)
        self.agent = DarwinMemoryCardAgent(self.env.size, seed)
        self.turns: list[TurnResult] = []
        self.store.log_session(self.session_id, "memory_cards_start", mode, {"rows": rows, "cols": cols})
        self.new_game(seed)

    def new_game(self, seed: int | None = None) -> None:
        self.game_index += 1
        game_seed = seed if seed is not None else self.rng.randrange(1, 9999999)
        self.game_id = f"game:{self.session_id}:{self.game_index:03d}"
        self.env.reset(game_seed)
        self.agent.reset()
        self.turns.clear()
        self.store.log_game(
            self.session_id,
            self.game_id,
            "game_start",
            self.rows,
            self.cols,
            self.env.pair_count,
            game_seed,
            {"deck_commitment": "hidden_from_agent", "agent_access": "observations_only"},
        )

    def step(self, keep_mismatch_visible: bool = False) -> TurnResult | None:
        if self.env.is_complete():
            return None
        self.agent.turn_id += 1
        turn_id = self.agent.turn_id
        first_decision = self.agent.choose_first()
        first_obs = self.env.reveal(first_decision.position)
        first_obs.turn_id = turn_id
        self.agent.observe(first_obs)
        self.store.log_observation(self.session_id, self.game_id, turn_id, first_obs, "first_pick")
        second_decision = self.agent.choose_second(first_obs.position, first_obs.symbol)
        second_obs = self.env.reveal(second_decision.position)
        second_obs.turn_id = turn_id
        self.agent.observe(second_obs)
        self.store.log_observation(self.session_id, self.game_id, turn_id, second_obs, "second_pick")
        matched = self.env.mark_match(first_obs.position, second_obs.position)
        self.agent.apply_turn_outcome(first_obs, second_obs, matched)
        if not matched and not keep_mismatch_visible:
            self.env.hide_unmatched([first_obs.position, second_obs.position])
        x_after = self.agent.rzs_input()
        sigma_after = self.agent.rzs.sigma(x_after)
        turn = TurnResult(
            turn_id=turn_id,
            first=first_decision,
            second=second_decision,
            first_symbol=first_obs.symbol,
            second_symbol=second_obs.symbol,
            matched=matched,
            match_symbol=first_obs.symbol if matched else "",
            sigma_after=sigma_after,
        )
        self.turns.append(turn)
        self.store.log_move(self.session_id, self.game_id, turn, 1)
        self.store.log_move(self.session_id, self.game_id, turn, 2)
        self.store.log_agent_memory(self.session_id, self.game_id, turn_id, self.agent.memory_snapshot())
        if len(self.agent.known_pairs()) > 0:
            self.store.log_replay(
                self.session_id,
                self.game_id,
                f"memory_replay:{self.game_id}:{turn_id:04d}",
                "known_pair_available",
                len(self.agent.known_pairs()),
                {"known_pairs": self.agent.memory_snapshot()["known_pairs"]},
            )
        self.store.write_episode(
            f"memory_cards:{self.session_id}:{self.game_id}:{turn_id:04d}",
            "flip_two_cards",
            f"{first_obs.position}:{first_obs.symbol},{second_obs.position}:{second_obs.symbol},matched={matched}",
            "A hidden pair can be found only after observed positions are held in working memory.",
            first_decision.sigma_before,
            sigma_after,
        )
        if self.env.is_complete():
            self.complete_game()
        return turn

    def complete_game(self) -> dict[str, Any]:
        matches = sum(1 for t in self.turns if t.matched)
        mismatches = len(self.turns) - matches
        memory_picks = sum(
            1
            for t in self.turns
            for d in (t.first, t.second)
            if d.decision_source in {"known_pair_first", "match_from_memory_second", "review_known_single_first", "review_known_single_second"}
        )
        explore_picks = len(self.turns) * 2 - memory_picks
        payload = {
            "game_complete": True,
            "turn_count": len(self.turns),
            "pair_count": self.env.pair_count,
            "matches": matches,
            "mismatches": mismatches,
            "memory_picks": memory_picks,
            "explore_picks": explore_picks,
            "all_positions_matched": sorted(self.agent.matched_positions),
            "agent_access": "observations_only",
        }
        self.store.log_game(
            self.session_id,
            self.game_id,
            "game_complete",
            self.rows,
            self.cols,
            self.env.pair_count,
            self.env.seed,
            payload,
        )
        confidence = clamp(matches / max(1, len(self.turns)))
        self.store.write_memory(
            f"memory_cards_v49_13:{self.game_id}",
            (
                f"Darwin completed memory card game with {self.env.pair_count} pairs; "
                f"turns={len(self.turns)}; mismatches={mismatches}; memory_picks={memory_picks}; "
                f"agent_access=observations_only."
            ),
            confidence,
        )
        return payload

    def run_to_completion(self, max_turns: int = 200) -> dict[str, Any]:
        while not self.env.is_complete() and len(self.turns) < max_turns:
            self.step()
        if not self.env.is_complete():
            raise RuntimeError("Darwin nao concluiu o jogo dentro do limite de turnos.")
        self.store.log_session(
            self.session_id,
            "memory_cards_complete",
            self.mode,
            {"game_id": self.game_id, "turn_count": len(self.turns), "game_complete": True},
        )
        return {
            "session_id": self.session_id,
            "game_id": self.game_id,
            "turn_count": len(self.turns),
            "pair_count": self.env.pair_count,
            "complete": True,
        }


class MemoryCardsApp:
    BG = "#071018"
    PANEL = "#10202d"
    CARD_BACK = "#1d3550"
    CARD_EDGE = "#d7f5ff"
    INK = "#edf7fb"
    MUTED = "#93aabd"
    GREEN = "#75e7a8"
    RED = "#ff707a"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Darwin Memory Cards v49.13")
        self.root.geometry("1080x780")
        self.root.minsize(900, 680)
        self.root.configure(bg=self.BG)
        self.runtime = MemoryCardsRuntime(mode="gui")
        self.auto_running = True
        self.delay_ms = 520
        self.last_turn: TurnResult | None = None
        self.pending_hide: list[int] = []
        self.tick = 0.0

        self.canvas = tk.Canvas(root, bg=self.BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        controls = tk.Frame(root, bg=self.PANEL)
        controls.pack(fill="x")
        ttk.Button(controls, text="Auto", command=self.start_auto).pack(side="left", padx=(14, 8), pady=10)
        ttk.Button(controls, text="Pausar", command=self.pause_auto).pack(side="left", padx=(0, 8), pady=10)
        ttk.Button(controls, text="Passo", command=self.step_once).pack(side="left", padx=(0, 8), pady=10)
        ttk.Button(controls, text="Embaralhar", command=self.shuffle).pack(side="left", padx=(0, 8), pady=10)
        ttk.Button(controls, text="Mais rapido", command=self.faster).pack(side="left", padx=(0, 8), pady=10)
        ttk.Button(controls, text="Mais lento", command=self.slower).pack(side="left", padx=(0, 14), pady=10)
        self.log = tk.Text(root, height=8, bg="#061019", fg=self.INK, insertbackground=self.INK, relief="flat", wrap="word", font=("Segoe UI", 10))
        self.log.pack(fill="x")
        self.log.config(state="disabled")
        self.write("Darwin", "Jogo iniciado. Vou encontrar os pares usando memoria observada.")
        self.animate()
        self.root.after(self.delay_ms, self.auto_step)

    def write(self, who: str, text: str) -> None:
        self.log.config(state="normal")
        self.log.insert("end", f"{who}: {text}\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def start_auto(self) -> None:
        self.auto_running = True
        self.write("Sistema", "Auto ligado.")

    def pause_auto(self) -> None:
        self.auto_running = False
        self.write("Sistema", "Auto pausado.")

    def faster(self) -> None:
        self.delay_ms = max(90, self.delay_ms - 120)
        self.write("Sistema", f"Velocidade {self.delay_ms} ms.")

    def slower(self) -> None:
        self.delay_ms = min(1600, self.delay_ms + 120)
        self.write("Sistema", f"Velocidade {self.delay_ms} ms.")

    def shuffle(self) -> None:
        self.runtime.new_game(random.randrange(1, 9999999))
        self.last_turn = None
        self.pending_hide = []
        self.auto_running = True
        self.write("Felipe", "embaralhou o tabuleiro.")
        self.write("Darwin", "Memoria do jogo anterior foi encerrada. Vou explorar de novo.")
        self.draw()

    def step_once(self) -> None:
        if self.pending_hide:
            self.runtime.env.hide_unmatched(self.pending_hide)
            self.pending_hide = []
            self.write("Darwin", "Virei de volta as cartas que nao formaram par.")
            self.draw()
            return
        if self.runtime.env.is_complete():
            self.write("Darwin", "Terminei. Pode embaralhar quando quiser.")
            return
        turn = self.runtime.step(keep_mismatch_visible=True)
        if turn:
            self.last_turn = turn
            if turn.matched:
                self.write("Darwin", f"Par encontrado: {turn.match_symbol} nas posicoes {turn.first.position} e {turn.second.position}.")
            else:
                self.pending_hide = [turn.first.position, turn.second.position]
                self.write("Darwin", f"Observei {turn.first_symbol} e {turn.second_symbol}; vou guardar as posicoes.")
        if self.runtime.env.is_complete():
            self.write("Darwin", "Encontrei todos os pares. Pode embaralhar.")
        self.draw()

    def auto_step(self) -> None:
        if self.auto_running and not self.runtime.env.is_complete():
            self.step_once()
        self.root.after(self.delay_ms, self.auto_step)

    def animate(self) -> None:
        self.tick += 0.07
        self.draw()
        self.root.after(60, self.animate)

    def draw_symbol(self, c: tk.Canvas, symbol: str, cx: float, cy: float, size: float) -> None:
        color = COLORS.get(symbol, "#8ab4f8")
        if symbol == "circle":
            c.create_oval(cx - size, cy - size, cx + size, cy + size, fill=color, outline="")
        elif symbol == "square":
            c.create_rectangle(cx - size, cy - size, cx + size, cy + size, fill=color, outline="")
        elif symbol == "triangle":
            c.create_polygon(cx, cy - size, cx - size, cy + size, cx + size, cy + size, fill=color, outline="")
        elif symbol == "diamond":
            c.create_polygon(cx, cy - size, cx - size, cy, cx, cy + size, cx + size, cy, fill=color, outline="")
        elif symbol == "star":
            points = []
            for i in range(10):
                r = size if i % 2 == 0 else size * 0.42
                a = -math.pi / 2 + i * math.pi / 5
                points.extend([cx + math.cos(a) * r, cy + math.sin(a) * r])
            c.create_polygon(points, fill=color, outline="")
        elif symbol == "moon":
            c.create_oval(cx - size, cy - size, cx + size, cy + size, fill=color, outline="")
            c.create_oval(cx - size * 0.25, cy - size, cx + size * 1.2, cy + size, fill=self.BG, outline="")
        elif symbol == "cross":
            w = size * 0.36
            c.create_rectangle(cx - w, cy - size, cx + w, cy + size, fill=color, outline="")
            c.create_rectangle(cx - size, cy - w, cx + size, cy + w, fill=color, outline="")
        elif symbol == "hexagon":
            pts = []
            for i in range(6):
                a = math.pi / 6 + i * math.pi / 3
                pts.extend([cx + math.cos(a) * size, cy + math.sin(a) * size])
            c.create_polygon(pts, fill=color, outline="")
        elif symbol == "heart":
            c.create_oval(cx - size, cy - size * 0.8, cx, cy + size * 0.2, fill=color, outline="")
            c.create_oval(cx, cy - size * 0.8, cx + size, cy + size * 0.2, fill=color, outline="")
            c.create_polygon(cx - size, cy - size * 0.25, cx + size, cy - size * 0.25, cx, cy + size * 1.15, fill=color, outline="")
        elif symbol == "wave":
            for i in range(3):
                y = cy - size * 0.6 + i * size * 0.55
                c.create_arc(cx - size, y - size * 0.35, cx + size, y + size * 0.35, start=0, extent=180, outline=color, width=5)
        else:
            c.create_text(cx, cy, text=symbol[:2], fill=color, font=("Segoe UI", 18, "bold"))

    def draw(self) -> None:
        c = self.canvas
        w = max(1, c.winfo_width())
        h = max(1, c.winfo_height())
        c.delete("all")
        c.create_text(w / 2, 34, text="DARWIN MEMORY CARDS v49.13", fill=self.INK, font=("Segoe UI", 22, "bold"))
        c.create_text(w / 2, 64, text="cartas ocultas; Darwin so aprende quando vira", fill=self.MUTED, font=("Segoe UI", 11))
        board_w = min(w - 120, 640)
        board_h = min(h - 160, 540)
        card_w = board_w / self.runtime.cols - 14
        card_h = board_h / self.runtime.rows - 14
        start_x = (w - board_w) / 2
        start_y = 100
        for card in self.runtime.env.cards:
            row = card.position // self.runtime.cols
            col = card.position % self.runtime.cols
            x1 = start_x + col * (card_w + 14)
            y1 = start_y + row * (card_h + 14)
            x2 = x1 + card_w
            y2 = y1 + card_h
            fill = "#203852" if not (card.face_up or card.matched) else "#0f2534"
            outline = self.GREEN if card.matched else self.CARD_EDGE
            c.create_rectangle(x1, y1, x2, y2, fill=fill, outline=outline, width=3)
            if card.face_up or card.matched:
                self.draw_symbol(c, card.symbol, (x1 + x2) / 2, (y1 + y2) / 2, min(card_w, card_h) * 0.25)
            else:
                c.create_text((x1 + x2) / 2, (y1 + y2) / 2, text="?", fill="#8fb4d6", font=("Segoe UI", 22, "bold"))
        status = f"turnos {len(self.runtime.turns)}   pares {self.runtime.agent.match_count}/{self.runtime.env.pair_count}   erros {self.runtime.agent.mismatch_count}"
        if self.runtime.env.is_complete():
            status += "   completo"
        c.create_text(w / 2, h - 36, text=status, fill=self.MUTED, font=("Segoe UI", 10))


def run_self_test(rows: int = 4, cols: int = 4, seed: int = 4913, details: bool = False) -> dict[str, Any]:
    runtime = MemoryCardsRuntime(rows=rows, cols=cols, seed=seed, mode="self_test")
    result = runtime.run_to_completion(max_turns=rows * cols * 4)
    result["mismatches"] = runtime.agent.mismatch_count
    result["matches"] = runtime.agent.match_count
    if details:
        print(js(result))
    else:
        print(
            f"DARWIN v49.13 memory cards self-test concluido: "
            f"session={result['session_id']} game={result['game_id']} turns={result['turn_count']}"
        )
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin Memory Cards v49.13")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--rows", type=int, default=4)
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--seed", type=int, default=4913)
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        run_self_test(rows=args.rows, cols=args.cols, seed=args.seed, details=args.details)
        return 0
    root = tk.Tk()
    MemoryCardsApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
