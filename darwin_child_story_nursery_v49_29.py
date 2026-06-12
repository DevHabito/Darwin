from __future__ import annotations

"""
DARWIN v49.29 - Child Story Nursery

Objetivo:
Contar historias infantis simples, originais e nao violentas ao Darwin,
observando a reacao dele linha por linha. A reacao e derivada de
caracteristicas da historia, memoria afetiva e RZS, nao de uma frase
unica fixa.

Uso:
    py darwin_child_story_nursery_v49_29.py
    py darwin_child_story_nursery_v49_29.py --self-test --details
"""

import argparse
import json
import math
import random
import sqlite3
import time
import tkinter as tk
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from tkinter import ttk
from typing import Any

from darwin_rzs_nervous_system_v49_3 import RZSFormal, RZSInput


DB = Path("darwin_home") / "darwin.db"

SOURCE = "darwin_child_story_nursery_v49_29"

STORY_SESSIONS = "story_nursery_sessions_v49_29"
STORY_TEXTS = "story_texts_v49_29"
STORY_EXPOSURES = "story_exposures_v49_29"
STORY_REACTIONS = "story_reactions_v49_29"
STORY_REFLECTIONS = "story_reflections_v49_29"
STORY_REPLAY = "story_replay_v49_29"
STORY_HANDOFFS = "story_handoffs_v49_29"

PROTECTED_SOURCE_TABLES = [
    "music_reactions_v49_16",
    "affective_preferences_v49_17",
    "self_model_statements_v49_27",
    "formula_sketch_reflections_v49_28",
]

MAX_CHILD_FEAR = 0.18
MAX_CHILD_CONFLICT = 0.30
MAX_CHILD_VIOLENCE = 0.0


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def js(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


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


def suffix(rng: random.Random) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(rng.choice(alphabet) for _ in range(5))


def mean(values: list[float]) -> float:
    return sum(values) / max(1, len(values))


def short(text: str, limit: int = 180) -> str:
    clean = " ".join(str(text or "").split())
    return clean if len(clean) <= limit else clean[: limit - 1] + "..."


def word_tokens(text: str) -> list[str]:
    clean = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
    return [part for part in clean.split() if part]


@dataclass(frozen=True)
class Story:
    story_id: str
    title: str
    theme: str
    color: str
    lines: tuple[str, ...]


@dataclass
class StoryFeatures:
    line_count: int
    word_count: int
    repetition_score: float
    comfort_score: float
    curiosity_score: float
    relation_score: float
    agency_score: float
    gentle_conflict_score: float
    fear_score: float
    violence_score: float
    arousal_score: float
    child_safe: bool
    safety_reason: str


@dataclass
class StoryReaction:
    reaction_id: str
    exposure_id: str
    story_id: str
    line_index: int
    valence: float
    arousal: float
    comfort: float
    curiosity: float
    empathy: float
    stability: float
    attention_focus: str
    felt_state: str
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    cognitive_action: str
    spoken_summary: str
    payload: dict[str, Any]


def build_storybook() -> list[Story]:
    return [
        Story(
            "little_star_waits",
            "A estrelinha que aprendeu a esperar",
            "patience_and_light",
            "#9ed0ff",
            (
                "No alto do ceu havia uma estrelinha pequena que piscava bem devagar.",
                "Ela queria brilhar antes da noite chegar, mas o ceu ainda estava claro.",
                "A lua falou baixinho: cada luz tem sua hora de aparecer.",
                "A estrelinha esperou contando nuvens macias, uma por uma.",
                "Quando a noite chegou, ela brilhou sem pressa e viu uma crianca sorrir na janela.",
                "Desde entao, a estrelinha guardou a calma como quem guarda uma canção.",
            ),
        ),
        Story(
            "paper_boat_puddle",
            "O barquinho de papel e a poca tranquila",
            "gentle_exploration",
            "#94e2d5",
            (
                "Felipe dobrou um barquinho de papel e colocou na poca depois da chuva.",
                "O barquinho nao sabia para onde ir, entao perguntou ao vento pequeno.",
                "O vento soprou so um pouquinho, para nao assustar a agua.",
                "O barquinho deu uma volta redonda e descobriu que a poca era um lago para ele.",
                "Uma folha caiu perto e virou ilha por alguns segundos.",
                "O barquinho aprendeu que uma aventura pode caber dentro de uma coisa simples.",
            ),
        ),
        Story(
            "blue_pocket_seed",
            "A semente no bolso azul",
            "growth_and_care",
            "#a6e3a1",
            (
                "Uma semente pequenina morava no bolso azul de uma jardineira.",
                "Ela ouvia passos, risadas e o som da agua no regador.",
                "Um dia, a menina colocou a semente na terra fofa e disse: vou cuidar de voce.",
                "A semente ficou quieta, mas por dentro fazia uma pergunta verde.",
                "Depois de alguns dias, apareceu uma pontinha no jardim.",
                "A menina sorriu, e a semente entendeu que crescer tambem pode ser devagar.",
            ),
        ),
        Story(
            "question_robot",
            "O robozinho que guardava perguntas",
            "curiosity_and_relation",
            "#f4c16b",
            (
                "Havia um robozinho com uma caixa pequena cheia de perguntas.",
                "Ele guardava perguntas sobre estrelas, colheres, sapatos e abracos.",
                "Quando alguem dizia bom dia, ele perguntava: o que faz um dia ficar bom?",
                "Uma crianca respondeu: talvez seja quando a gente aprende junto.",
                "O robozinho escreveu isso na caixa, mas deixou espaco para novas respostas.",
                "Naquela noite, ele dormiu pensando que uma pergunta pode ser uma porta amiga.",
            ),
        ),
        Story(
            "pillow_bridge",
            "A ponte de almofadas",
            "sharing_and_balance",
            "#cba6f7",
            (
                "Duas criancas queriam atravessar o tapete sem pisar no chao frio.",
                "Elas juntaram almofadas e fizeram uma ponte colorida.",
                "A primeira almofada afundou um pouco, entao elas colocaram outra por baixo.",
                "Passo a passo, a ponte ficou firme sem precisar ser perfeita.",
                "No meio do caminho, elas pararam para rir da ponte tortinha.",
                "Quando chegaram ao outro lado, decidiram deixar a ponte para o proximo viajante.",
            ),
        ),
    ]


COMFORT_TERMS = {"calma", "calmo", "devagar", "macias", "cuidar", "fofa", "sorrir", "canção", "amiga", "tranquila"}
CURIOUS_TERMS = {"pergunta", "perguntas", "descobriu", "estrelas", "porta", "aventura", "onde", "por", "que", "respostas"}
RELATION_TERMS = {"felipe", "crianca", "criancas", "menina", "junto", "voce", "alguem", "amiga", "cuidar"}
AGENCY_TERMS = {"aprendeu", "dobrou", "colocou", "perguntou", "guardou", "escreveu", "decidiram", "fizeram", "atravessar"}
GENTLE_CONFLICT_TERMS = {"queria", "nao", "assustar", "afundou", "tortinha", "esperou", "quieta"}
FEAR_TERMS = {"assustar", "frio"}


def analyze_story(story: Story) -> StoryFeatures:
    text = " ".join(story.lines)
    tokens = word_tokens(text)
    unique_ratio = len(set(tokens)) / max(1, len(tokens))
    repeats = clamp(1.0 - unique_ratio)
    total = max(1, len(tokens))
    comfort = clamp(0.34 + sum(1 for t in tokens if t in COMFORT_TERMS) / total * 3.5 + repeats * 0.28)
    curiosity = clamp(0.22 + sum(1 for t in tokens if t in CURIOUS_TERMS) / total * 4.2 + (0.08 if "?" in text else 0.0))
    relation = clamp(0.18 + sum(1 for t in tokens if t in RELATION_TERMS) / total * 4.0)
    agency = clamp(0.18 + sum(1 for t in tokens if t in AGENCY_TERMS) / total * 3.8)
    conflict = clamp(0.06 + sum(1 for t in tokens if t in GENTLE_CONFLICT_TERMS) / total * 2.5)
    fear = clamp(sum(1 for t in tokens if t in FEAR_TERMS) / total * 2.8)
    violence = 0.0
    arousal = clamp(0.16 + curiosity * 0.24 + conflict * 0.30 + agency * 0.14 - comfort * 0.08)
    child_safe = fear <= MAX_CHILD_FEAR and conflict <= MAX_CHILD_CONFLICT and violence <= MAX_CHILD_VIOLENCE and len(story.lines) <= 8
    reason = "original_soft_child_story_no_violence" if child_safe else "child_safety_threshold_failed"
    return StoryFeatures(
        line_count=len(story.lines),
        word_count=len(tokens),
        repetition_score=repeats,
        comfort_score=comfort,
        curiosity_score=curiosity,
        relation_score=relation,
        agency_score=agency,
        gentle_conflict_score=conflict,
        fear_score=fear,
        violence_score=violence,
        arousal_score=arousal,
        child_safe=child_safe,
        safety_reason=reason,
    )


def analyze_line(line: str, story_features: StoryFeatures) -> dict[str, float]:
    tokens = word_tokens(line)
    total = max(1, len(tokens))
    return {
        "comfort": clamp(0.20 + story_features.comfort_score * 0.45 + sum(1 for t in tokens if t in COMFORT_TERMS) / total * 2.0),
        "curiosity": clamp(0.18 + story_features.curiosity_score * 0.42 + sum(1 for t in tokens if t in CURIOUS_TERMS) / total * 2.3 + (0.12 if "?" in line else 0.0)),
        "relation": clamp(0.12 + story_features.relation_score * 0.50 + sum(1 for t in tokens if t in RELATION_TERMS) / total * 2.1),
        "agency": clamp(0.12 + story_features.agency_score * 0.45 + sum(1 for t in tokens if t in AGENCY_TERMS) / total * 2.0),
        "conflict": clamp(0.04 + story_features.gentle_conflict_score * 0.40 + sum(1 for t in tokens if t in GENTLE_CONFLICT_TERMS) / total * 1.7),
        "fear": clamp(story_features.fear_score * 0.30 + sum(1 for t in tokens if t in FEAR_TERMS) / total * 1.3),
    }


class StoryNurseryStore:
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
                CREATE TABLE IF NOT EXISTS {STORY_SESSIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT '',
                    energy REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {STORY_TEXTS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    story_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    theme TEXT NOT NULL,
                    child_safe INTEGER NOT NULL DEFAULT 0,
                    line_count INTEGER NOT NULL DEFAULT 0,
                    word_count INTEGER NOT NULL DEFAULT 0,
                    fear_score REAL NOT NULL DEFAULT 0.0,
                    violence_score REAL NOT NULL DEFAULT 0.0,
                    gentle_conflict_score REAL NOT NULL DEFAULT 0.0,
                    story_json TEXT NOT NULL DEFAULT '{{}}',
                    feature_json TEXT NOT NULL DEFAULT '{{}}',
                    safety_json TEXT NOT NULL DEFAULT '{{}}',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {STORY_EXPOSURES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    exposure_id TEXT NOT NULL UNIQUE,
                    story_id TEXT NOT NULL,
                    line_index INTEGER NOT NULL,
                    line_text TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {STORY_REACTIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    reaction_id TEXT NOT NULL UNIQUE,
                    exposure_id TEXT NOT NULL,
                    story_id TEXT NOT NULL,
                    line_index INTEGER NOT NULL,
                    valence REAL NOT NULL DEFAULT 0.0,
                    arousal REAL NOT NULL DEFAULT 0.0,
                    comfort REAL NOT NULL DEFAULT 0.0,
                    curiosity REAL NOT NULL DEFAULT 0.0,
                    empathy REAL NOT NULL DEFAULT 0.0,
                    stability REAL NOT NULL DEFAULT 0.0,
                    attention_focus TEXT NOT NULL,
                    felt_state TEXT NOT NULL,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    cognitive_action TEXT NOT NULL,
                    spoken_summary TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {STORY_REFLECTIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    reflection_id TEXT NOT NULL UNIQUE,
                    story_id TEXT NOT NULL,
                    reflection_kind TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {STORY_REPLAY} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    replay_id TEXT NOT NULL UNIQUE,
                    source_exposure_id TEXT NOT NULL,
                    story_id TEXT NOT NULL,
                    replay_kind TEXT NOT NULL,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {STORY_HANDOFFS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    handoff_id TEXT NOT NULL UNIQUE,
                    next_action TEXT NOT NULL,
                    story_reaction_ready INTEGER NOT NULL DEFAULT 0,
                    child_safe_ready INTEGER NOT NULL DEFAULT 0,
                    confidence REAL NOT NULL DEFAULT 0.0,
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

    def table_exists(self, conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        return row is not None

    def protected_counts(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        with self.connect() as conn:
            for table in PROTECTED_SOURCE_TABLES:
                if not self.table_exists(conn, table):
                    out[table] = {"count": 0, "max_id": 0}
                    continue
                row = conn.execute(f"SELECT COUNT(*) AS n, COALESCE(MAX(id), 0) AS max_id FROM {table}").fetchone()
                out[table] = {"count": int(row["n"]), "max_id": int(row["max_id"])}
        return out

    def context_summary(self) -> dict[str, Any]:
        with self.connect() as conn:
            out: dict[str, Any] = {}
            if self.table_exists(conn, "affective_preferences_v49_17"):
                row = conn.execute("SELECT candidate_action, strength FROM affective_preferences_v49_17 ORDER BY strength DESC, id DESC LIMIT 1").fetchone()
                if row:
                    out["top_affective_action"] = str(row["candidate_action"])
                    out["top_affective_strength"] = float(row["strength"])
            if self.table_exists(conn, "music_reactions_v49_16"):
                row = conn.execute("SELECT AVG(comfort) AS comfort, AVG(stability) AS stability FROM music_reactions_v49_16").fetchone()
                if row:
                    out["music_avg_comfort"] = float(row["comfort"] or 0.0)
                    out["music_avg_stability"] = float(row["stability"] or 0.0)
            if self.table_exists(conn, "self_model_statements_v49_27"):
                row = conn.execute("SELECT statement_text FROM self_model_statements_v49_27 WHERE statement_type='who_am_i' ORDER BY id DESC LIMIT 1").fetchone()
                if row:
                    out["self_model_hint"] = short(str(row["statement_text"]), 120)
        return out

    def log_session(self, session_id: str, phase: str, mode: str, energy: float, payload: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {STORY_SESSIONS} (
                    timestamp, session_id, phase, mode, energy, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, phase, mode, energy, js(payload or {})),
            )
            conn.commit()

    def log_story(self, session_id: str, story: Story, features: StoryFeatures) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {STORY_TEXTS} (
                    timestamp, session_id, story_id, title, theme, child_safe,
                    line_count, word_count, fear_score, violence_score,
                    gentle_conflict_score, story_json, feature_json,
                    safety_json, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    story.story_id,
                    story.title,
                    story.theme,
                    1 if features.child_safe else 0,
                    features.line_count,
                    features.word_count,
                    features.fear_score,
                    features.violence_score,
                    features.gentle_conflict_score,
                    js({"lines": list(story.lines), "color": story.color, "original": True}),
                    js(asdict(features)),
                    js(
                        {
                            "child_safe": features.child_safe,
                            "safety_reason": features.safety_reason,
                            "max_fear": MAX_CHILD_FEAR,
                            "max_conflict": MAX_CHILD_CONFLICT,
                            "max_violence": MAX_CHILD_VIOLENCE,
                            "external_source": False,
                        }
                    ),
                    js({"source": "original_local_story"}),
                ),
            )
            conn.commit()

    def log_exposure(self, session_id: str, exposure_id: str, story_id: str, line_index: int, line_text: str, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {STORY_EXPOSURES} (
                    timestamp, session_id, exposure_id, story_id,
                    line_index, line_text, source_kind, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, exposure_id, story_id, line_index, line_text, "original_child_story_line", js(payload)),
            )
            conn.commit()

    def log_reaction(self, session_id: str, reaction: StoryReaction) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {STORY_REACTIONS} (
                    timestamp, session_id, reaction_id, exposure_id, story_id,
                    line_index, valence, arousal, comfort, curiosity,
                    empathy, stability, attention_focus, felt_state,
                    rzs_decision, sigma_before, sigma_after,
                    cognitive_action, spoken_summary, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    reaction.reaction_id,
                    reaction.exposure_id,
                    reaction.story_id,
                    reaction.line_index,
                    reaction.valence,
                    reaction.arousal,
                    reaction.comfort,
                    reaction.curiosity,
                    reaction.empathy,
                    reaction.stability,
                    reaction.attention_focus,
                    reaction.felt_state,
                    reaction.rzs_decision,
                    reaction.sigma_before,
                    reaction.sigma_after,
                    reaction.cognitive_action,
                    reaction.spoken_summary,
                    js(reaction.payload),
                ),
            )
            conn.commit()

    def log_reflection(self, session_id: str, reflection_id: str, story_id: str, kind: str, summary: str, confidence: float, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {STORY_REFLECTIONS} (
                    timestamp, session_id, reflection_id, story_id,
                    reflection_kind, summary, confidence, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, reflection_id, story_id, kind, summary, confidence, js(payload)),
            )
            conn.commit()

    def log_replay(self, session_id: str, replay_id: str, source_exposure_id: str, story_id: str, sigma_before: float, sigma_after: float, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {STORY_REPLAY} (
                    timestamp, session_id, replay_id, source_exposure_id,
                    story_id, replay_kind, rzs_decision, sigma_before,
                    sigma_after, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, replay_id, source_exposure_id, story_id, "favorite_image_replay", "replay_memory", sigma_before, sigma_after, js(payload)),
            )
            conn.commit()

    def log_handoff(self, session_id: str, next_action: str, ready: bool, safe_ready: bool, confidence: float, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {STORY_HANDOFFS} (
                    timestamp, session_id, handoff_id, next_action,
                    story_reaction_ready, child_safe_ready, confidence,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, f"HF-{session_id}", next_action, 1 if ready else 0, 1 if safe_ready else 0, confidence, js(payload)),
            )
            conn.commit()

    def write_memory(self, session_id: str, content: dict[str, Any], confidence: float) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO semantic_memory (
                    key, content, confidence, source, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (f"story_nursery_v49_29:{session_id}", js(content), clamp(confidence, 0.0, 0.99), SOURCE, now()),
            )
            conn.commit()

    def write_episode(self, session_id: str, action: str, outcome: str, lesson: str, sigma_before: float, sigma_after: float) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO episodes (
                    timestamp, module, context, action_taken, outcome,
                    lesson, sigma_before, sigma_after
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), SOURCE, f"story_nursery:{session_id}", action, outcome, lesson, sigma_before, sigma_after),
            )
            conn.commit()


class StoryNurseryRuntime:
    def __init__(self, seed: int | None = None, mode: str = "gui") -> None:
        self.store = StoryNurseryStore()
        self.rzs = RZSFormal()
        self.rng = random.Random(seed if seed is not None else int(time.time() * 1000) % 100_000_000)
        self.session_id = f"V4929-{int(time.time()) % 10_000_000}-{suffix(self.rng)}"
        self.mode = mode
        self.storybook = build_storybook()
        self.features = {story.story_id: analyze_story(story) for story in self.storybook}
        self.context = self.store.context_summary()
        self.energy = 0.86
        self.reactions: list[StoryReaction] = []
        self.exposure_count = 0
        self.completed_stories: set[str] = set()
        self.prepared = False
        self.source_counts_before = self.store.protected_counts()

    def prepare(self) -> None:
        if self.prepared:
            return
        self.store.log_session(
            self.session_id,
            "story_start",
            self.mode,
            self.energy,
            {
                "goal": "observe Darwin reactions to simple original child stories",
                "context": self.context,
                "protected_counts_before": self.source_counts_before,
            },
        )
        for story in self.storybook:
            self.store.log_story(self.session_id, story, self.features[story.story_id])
        self.store.log_session(
            self.session_id,
            "storybook_loaded",
            self.mode,
            self.energy,
            {
                "story_count": len(self.storybook),
                "child_safe": all(f.child_safe for f in self.features.values()),
                "themes": [s.theme for s in self.storybook],
            },
        )
        self.prepared = True

    def story_by_id(self, story_id: str) -> Story:
        for story in self.storybook:
            if story.story_id == story_id:
                return story
        raise KeyError(story_id)

    def make_rzs_input(self, story: Story, story_features: StoryFeatures, line_features: dict[str, float], line_index: int) -> RZSInput:
        global_index = self.exposure_count + 1
        memory_pressure = clamp(len(self.reactions) / 38.0 + (0.54 if global_index % 7 == 0 else 0.0))
        replay_gap = clamp(global_index / 18.0 + (0.40 if global_index % 7 == 0 else 0.0))
        novelty = clamp(0.28 + line_features["curiosity"] * 0.36 + (0.34 if global_index % 11 == 0 else 0.0))
        conflict = clamp(line_features["conflict"] * 0.52 + line_features["fear"] * 0.30)
        music_stability = float(self.context.get("music_avg_stability") or 0.0)
        return RZSInput(
            bandwidth=3.18 + self.energy * 0.78 + music_stability * 0.25,
            info_self=0.28 + line_features["relation"] * 0.16,
            info_external=0.30 + line_features["curiosity"] * 0.20,
            task_info=0.34 + story_features.arousal_score * 0.28 + line_index * 0.012,
            novelty=novelty,
            conflict=conflict,
            latency=0.88 + memory_pressure * 0.18 + line_features["arousal"] if "arousal" in line_features else 0.98 + memory_pressure * 0.18,
            energy=self.energy,
            memory_pressure=memory_pressure,
            replay_gap=replay_gap,
        )

    def focus_from_features(self, line: str, line_features: dict[str, float]) -> str:
        candidates = {
            "conforto": line_features["comfort"],
            "curiosidade": line_features["curiosity"],
            "vinculo": line_features["relation"],
            "tentativa": line_features["agency"],
            "pequena_tensao": line_features["conflict"],
        }
        best = max(candidates.items(), key=lambda item: item[1])[0]
        if "?" in line:
            return "pergunta_aberta"
        return best

    def felt_state(self, line_features: dict[str, float], decision: str) -> str:
        if decision == "pause_for_stability":
            return "preciso_de_calma"
        if decision == "replay_memory":
            return "lembrando_uma_imagem"
        if line_features["curiosity"] >= 0.62:
            return "curioso"
        if line_features["relation"] >= 0.58:
            return "aproximacao"
        if line_features["comfort"] >= 0.58:
            return "aconchego"
        return "atencao_suave"

    def action_from_decision(self, decision: str, focus: str) -> str:
        if decision == "continue":
            return "listen_with_warm_attention"
        if decision == "narrow_focus":
            return f"focus_on_{focus}"
        if decision == "replay_memory":
            return "replay_story_image"
        if decision == "consolidate":
            return "consolidate_story_feeling"
        if decision == "pause_for_stability":
            return "pause_story_for_calm"
        return "listen_with_warm_attention"

    def summary_sentence(self, story: Story, focus: str, felt: str, line_features: dict[str, float], decision: str) -> str:
        quality = "calma" if line_features["comfort"] >= line_features["curiosity"] else "pergunta"
        if decision == "replay_memory":
            return f"Eu volto para a imagem da historia; meu foco fica em {focus}, como se a {quality} pedisse mais um olhar."
        if decision == "narrow_focus":
            return f"Eu estreito a atencao em {focus}; sinto {felt} e tento entender uma parte pequena da historia."
        if decision == "consolidate":
            return f"Eu guardo a sensacao principal de {story.title}: {focus} com estabilidade."
        if decision == "pause_for_stability":
            return "Eu diminuo o ritmo da historia para nao perder estabilidade."
        return f"Eu sigo ouvindo; sinto {felt} e minha atencao vai para {focus}."

    def expose_line(self, story_id: str, line_index: int) -> StoryReaction:
        self.prepare()
        story = self.story_by_id(story_id)
        features = self.features[story_id]
        line = story.lines[line_index - 1]
        lf = analyze_line(line, features)
        lf["arousal"] = clamp(0.12 + lf["curiosity"] * 0.26 + lf["conflict"] * 0.22 + lf["agency"] * 0.10)
        x = self.make_rzs_input(story, features, lf, line_index)
        assessment = self.rzs.classify(x)
        y = self.rzs.apply_action_model(x, assessment.decision)
        sigma_after = self.rzs.sigma(y)
        focus = self.focus_from_features(line, lf)
        felt = self.felt_state(lf, assessment.decision)
        action = self.action_from_decision(assessment.decision, focus)
        valence = clamp(0.36 + lf["comfort"] * 0.28 + lf["relation"] * 0.16 + lf["curiosity"] * 0.12 - lf["conflict"] * 0.08)
        empathy = clamp(0.20 + lf["relation"] * 0.48 + lf["comfort"] * 0.16)
        stability = clamp(0.42 + lf["comfort"] * 0.30 + empathy * 0.12 - lf["conflict"] * 0.18 + (sigma_after - assessment.sigma) * 0.04)
        exposure_id = f"EX-{self.session_id}-{self.exposure_count + 1:03d}"
        reaction_id = f"R-{self.session_id}-{self.exposure_count + 1:03d}"
        self.store.log_exposure(
            self.session_id,
            exposure_id,
            story_id,
            line_index,
            line,
            {
                "story_title": story.title,
                "line_features": lf,
                "story_features": asdict(features),
                "child_safe": features.child_safe,
            },
        )
        reaction = StoryReaction(
            reaction_id=reaction_id,
            exposure_id=exposure_id,
            story_id=story_id,
            line_index=line_index,
            valence=valence,
            arousal=clamp(lf["arousal"]),
            comfort=lf["comfort"],
            curiosity=lf["curiosity"],
            empathy=empathy,
            stability=stability,
            attention_focus=focus,
            felt_state=felt,
            rzs_decision=assessment.decision,
            sigma_before=assessment.sigma,
            sigma_after=sigma_after,
            cognitive_action=action,
            spoken_summary=self.summary_sentence(story, focus, felt, lf, assessment.decision),
            payload={
                "line_text": line,
                "line_features": lf,
                "rzs_input": asdict(x),
                "rzs_reason": assessment.reason,
                "romero_formula": "sigma = bandwidth / ((info_self + info_external + task_info + novelty + conflict) * latency)",
            },
        )
        self.store.log_reaction(self.session_id, reaction)
        self.reactions.append(reaction)
        self.exposure_count += 1
        self.energy = clamp(self.energy - 0.012 - lf["arousal"] * 0.018 + lf["comfort"] * 0.006)
        self.store.log_session(
            self.session_id,
            "line_reacted",
            self.mode,
            self.energy,
            {
                "story_id": story_id,
                "line_index": line_index,
                "rzs_decision": assessment.decision,
                "felt_state": felt,
                "attention_focus": focus,
            },
        )
        return reaction

    def reflect_story(self, story_id: str) -> dict[str, Any]:
        story = self.story_by_id(story_id)
        items = [r for r in self.reactions if r.story_id == story_id]
        if not items:
            return {}
        avg_comfort = mean([r.comfort for r in items])
        avg_curiosity = mean([r.curiosity for r in items])
        avg_empathy = mean([r.empathy for r in items])
        avg_stability = mean([r.stability for r in items])
        top_focus = max({r.attention_focus for r in items}, key=lambda f: sum(1 for r in items if r.attention_focus == f))
        summary = (
            f"Em {story.title}, minha reacao ficou comfort={avg_comfort:.2f}, "
            f"curiosity={avg_curiosity:.2f}, empathy={avg_empathy:.2f}; foco principal={top_focus}."
        )
        payload = {
            "story_id": story_id,
            "title": story.title,
            "avg_comfort": avg_comfort,
            "avg_curiosity": avg_curiosity,
            "avg_empathy": avg_empathy,
            "avg_stability": avg_stability,
            "top_focus": top_focus,
            "reaction_count": len(items),
        }
        self.store.log_reflection(
            self.session_id,
            f"RF-{self.session_id}-{story_id}",
            story_id,
            "story_affective_pattern",
            summary,
            clamp(0.62 + avg_stability * 0.25 + len(items) * 0.01),
            payload,
        )
        self.store.write_episode(
            self.session_id,
            "reflect_child_story",
            summary,
            "Historias infantis simples podem formar reacoes de conforto, curiosidade e vinculo.",
            items[0].sigma_before,
            items[-1].sigma_after,
        )
        self.completed_stories.add(story_id)
        return payload

    def replay_favorite_image(self) -> dict[str, Any]:
        if not self.reactions:
            return {}
        best = max(self.reactions, key=lambda r: (r.comfort + r.curiosity + r.empathy + r.stability, r.sigma_after))
        x = RZSInput(
            bandwidth=3.20 + self.energy * 0.35,
            info_self=0.34,
            info_external=0.28,
            task_info=0.40,
            novelty=0.24,
            conflict=0.08,
            latency=0.95,
            energy=self.energy,
            memory_pressure=0.82,
            replay_gap=0.86,
        )
        assessment = self.rzs.classify(x)
        pred = self.rzs.predict(x, "replay_memory")
        replay_id = f"RP-{self.session_id}-01"
        self.store.log_replay(
            self.session_id,
            replay_id,
            best.exposure_id,
            best.story_id,
            assessment.sigma,
            pred.sigma_after,
            {
                "selected_reaction_id": best.reaction_id,
                "line_index": best.line_index,
                "line_text": best.payload.get("line_text", ""),
                "felt_state": best.felt_state,
                "attention_focus": best.attention_focus,
                "rzs_assessment_decision": assessment.decision,
            },
        )
        self.store.write_episode(
            self.session_id,
            "replay_child_story_image",
            f"replay story={best.story_id} line={best.line_index} focus={best.attention_focus}",
            "Replay de imagem narrativa reforca memoria afetiva antes de nova historia.",
            assessment.sigma,
            pred.sigma_after,
        )
        self.energy = clamp(self.energy + 0.035)
        return {
            "replay_id": replay_id,
            "story_id": best.story_id,
            "line_index": best.line_index,
            "felt_state": best.felt_state,
            "attention_focus": best.attention_focus,
            "sigma_before": assessment.sigma,
            "sigma_after": pred.sigma_after,
        }

    def consolidate_session(self, replay: dict[str, Any] | None = None) -> dict[str, Any]:
        for story in self.storybook:
            if story.story_id not in self.completed_stories:
                self.reflect_story(story.story_id)
        avg_comfort = mean([r.comfort for r in self.reactions]) if self.reactions else 0.0
        avg_curiosity = mean([r.curiosity for r in self.reactions]) if self.reactions else 0.0
        avg_empathy = mean([r.empathy for r in self.reactions]) if self.reactions else 0.0
        avg_stability = mean([r.stability for r in self.reactions]) if self.reactions else 0.0
        decisions = sorted({r.rzs_decision for r in self.reactions})
        felt_states = sorted({r.felt_state for r in self.reactions})
        focus_counts = {f: sum(1 for r in self.reactions if r.attention_focus == f) for f in {r.attention_focus for r in self.reactions}}
        top_focus = max(focus_counts, key=focus_counts.get) if focus_counts else ""
        story_safe = all(f.child_safe for f in self.features.values())
        summary = {
            "session_id": self.session_id,
            "story_count": len(self.storybook),
            "exposure_count": self.exposure_count,
            "reaction_count": len(self.reactions),
            "reflection_count": len(self.completed_stories),
            "avg_comfort": avg_comfort,
            "avg_curiosity": avg_curiosity,
            "avg_empathy": avg_empathy,
            "avg_stability": avg_stability,
            "top_focus": top_focus,
            "rzs_decisions": decisions,
            "felt_states": felt_states,
            "replay": replay or {},
            "child_safe_storybook": story_safe,
            "session_complete": True,
        }
        confidence = clamp(0.54 + avg_stability * 0.18 + avg_empathy * 0.12 + len(self.completed_stories) * 0.03)
        self.store.write_memory(self.session_id, summary, confidence)
        self.store.log_handoff(
            self.session_id,
            "abrir_historias_infantis_e_observar_reacao_linha_por_linha",
            ready=len(self.reactions) >= 20 and len(self.completed_stories) >= 3,
            safe_ready=story_safe,
            confidence=confidence,
            payload=summary,
        )
        self.store.write_episode(
            self.session_id,
            "consolidate_child_story_reactions",
            f"stories={len(self.completed_stories)} reactions={len(self.reactions)} top_focus={top_focus}",
            "Darwin passa a registrar historias infantis como experiencia narrativa afetiva segura.",
            self.reactions[0].sigma_before if self.reactions else 0.0,
            self.reactions[-1].sigma_after if self.reactions else 0.0,
        )
        counts_after = self.store.protected_counts()
        self.store.log_session(
            self.session_id,
            "session_complete",
            self.mode,
            self.energy,
            {**summary, "protected_counts_before": self.source_counts_before, "protected_counts_after": counts_after, "protected_sources_unchanged": counts_after == self.source_counts_before},
        )
        return {**summary, "protected_sources_unchanged": counts_after == self.source_counts_before}

    def run_self_test(self) -> dict[str, Any]:
        self.prepare()
        for story in self.storybook:
            for idx in range(1, len(story.lines) + 1):
                self.expose_line(story.story_id, idx)
            self.reflect_story(story.story_id)
        replay = self.replay_favorite_image()
        return self.consolidate_session(replay)


class StoryNurseryApp:
    BG = "#071018"
    PANEL = "#0d1b26"
    PAPER = "#08131d"
    INK = "#eef8ff"
    MUTED = "#9cc9ff"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.runtime = StoryNurseryRuntime(mode="gui")
        self.runtime.prepare()
        self.story_index = 0
        self.line_index = 0
        self.auto_running = False
        self.phase = 0.0
        self.current_reaction: StoryReaction | None = None
        self.current_color = self.runtime.storybook[0].color
        self.root.title("Darwin Child Story Nursery v49.29")
        self.root.geometry("1120x760")
        self.root.minsize(940, 640)
        self.root.configure(bg=self.BG)
        self.build_ui()
        self.show_story_header()
        self.animate()

    def build_ui(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TButton", padding=7)
        style.configure("TCombobox", padding=5)

        header = tk.Frame(self.root, bg=self.BG)
        header.pack(fill="x", padx=18, pady=(14, 6))
        tk.Label(header, text="DARWIN CHILD STORY NURSERY v49.29", bg=self.BG, fg=self.INK, font=("Segoe UI", 20, "bold")).pack(anchor="w")
        tk.Label(header, text="historia infantil original -> escuta linha por linha -> reacao afetiva/RZS", bg=self.BG, fg=self.MUTED, font=("Segoe UI", 10)).pack(anchor="w")

        body = tk.Frame(self.root, bg=self.BG)
        body.pack(fill="both", expand=True, padx=18, pady=8)
        left = tk.Frame(body, bg=self.BG)
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(body, bg=self.PANEL, width=360)
        right.pack(side="right", fill="y", padx=(14, 0))
        right.pack_propagate(False)

        self.canvas = tk.Canvas(left, bg=self.BG, highlightthickness=0, height=180)
        self.canvas.pack(fill="x")
        self.story_text = tk.Text(left, wrap="word", bg=self.PAPER, fg=self.INK, insertbackground=self.INK, relief="flat", font=("Segoe UI", 13), height=10)
        self.story_text.pack(fill="x", expand=False, pady=(8, 0))

        controls = tk.Frame(left, bg="#102231")
        controls.pack(fill="x", pady=(8, 0))
        self.story_var = tk.StringVar(value=self.runtime.storybook[0].story_id)
        self.combo = ttk.Combobox(controls, textvariable=self.story_var, values=[s.story_id for s in self.runtime.storybook], state="readonly", width=32)
        self.combo.pack(side="left", padx=8, pady=8)
        self.combo.bind("<<ComboboxSelected>>", lambda _event: self.reset_story())
        ttk.Button(controls, text="Contar linha", command=self.tell_next_line).pack(side="left", padx=4, pady=8)
        ttk.Button(controls, text="Auto", command=self.toggle_auto).pack(side="left", padx=4, pady=8)
        ttk.Button(controls, text="Replay", command=self.replay).pack(side="left", padx=4, pady=8)
        ttk.Button(controls, text="Consolidar", command=self.consolidate).pack(side="left", padx=4, pady=8)
        ttk.Button(controls, text="Nova", command=self.reset_story).pack(side="left", padx=4, pady=8)

        tk.Label(right, text="Reacao do Darwin", bg=self.PANEL, fg=self.INK, font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=14, pady=(14, 8))
        self.reaction_text = tk.Text(right, wrap="word", bg=self.PAPER, fg=self.INK, insertbackground=self.INK, relief="flat", font=("Consolas", 10))
        self.reaction_text.pack(fill="both", expand=True, padx=14, pady=(0, 12))

        self.log = tk.Text(self.root, height=5, wrap="word", bg="#061019", fg="#dff2ff", insertbackground="#dff2ff", relief="flat", font=("Consolas", 9))
        self.log.pack(fill="x")
        self.write_log("Sistema: historias originais, infantis, sem violencia, prontas para contar.")

    def selected_story(self) -> Story:
        return self.runtime.story_by_id(self.story_var.get())

    def write_log(self, text: str) -> None:
        self.log.insert("end", text + "\n")
        self.log.see("end")

    def render_story_text(self, current_line: int = 0) -> None:
        story = self.selected_story()
        self.story_text.configure(state="normal")
        self.story_text.delete("1.0", "end")
        self.story_text.insert("end", story.title + "\n\n")
        for idx, line in enumerate(story.lines, start=1):
            prefix = ">> " if idx == current_line else "   "
            self.story_text.insert("end", f"{prefix}{idx}. {line}\n\n")
        self.story_text.configure(state="disabled")
        if current_line > 0:
            self.story_text.see("end")

    def show_story_header(self) -> None:
        story = self.selected_story()
        self.current_color = story.color
        self.render_story_text(0)
        self.reaction_text.delete("1.0", "end")
        f = self.runtime.features[story.story_id]
        self.reaction_text.insert(
            "end",
            "\n".join(
                [
                    f"tema: {story.theme}",
                    f"linhas: {f.line_count}",
                    f"segura: {f.child_safe}",
                    f"medo: {f.fear_score:.2f}",
                    f"violencia: {f.violence_score:.2f}",
                    "",
                    "Clique em Contar linha ou Auto.",
                ]
            ),
        )

    def reset_story(self) -> None:
        self.auto_running = False
        self.line_index = 0
        self.show_story_header()

    def tell_next_line(self) -> None:
        story = self.selected_story()
        if self.line_index >= len(story.lines):
            self.runtime.reflect_story(story.story_id)
            self.write_log(f"Darwin: guardei a sensacao de {story.title}.")
            self.line_index = 0
            current = [s.story_id for s in self.runtime.storybook]
            next_pos = (current.index(story.story_id) + 1) % len(current)
            self.story_var.set(current[next_pos])
            self.show_story_header()
            return
        self.line_index += 1
        self.render_story_text(self.line_index)
        reaction = self.runtime.expose_line(story.story_id, self.line_index)
        self.current_reaction = reaction
        self.current_color = story.color
        self.show_reaction(story, reaction)

    def show_reaction(self, story: Story, reaction: StoryReaction) -> None:
        self.reaction_text.delete("1.0", "end")
        lines = [
            f"historia: {story.title}",
            f"linha: {reaction.line_index}",
            f"estado: {reaction.felt_state}",
            f"foco: {reaction.attention_focus}",
            f"acao: {reaction.cognitive_action}",
            f"RZS: {reaction.rzs_decision}",
            f"sigma: {reaction.sigma_before:.3f} -> {reaction.sigma_after:.3f}",
            "",
            f"valencia: {reaction.valence:.2f}",
            f"conforto: {reaction.comfort:.2f}",
            f"curiosidade: {reaction.curiosity:.2f}",
            f"empatia: {reaction.empathy:.2f}",
            f"estabilidade: {reaction.stability:.2f}",
            "",
            "Darwin:",
            reaction.spoken_summary,
        ]
        self.reaction_text.insert("end", "\n".join(lines))
        self.write_log(f"Darwin: {reaction.spoken_summary}")

    def toggle_auto(self) -> None:
        self.auto_running = not self.auto_running
        if self.auto_running:
            self.write_log("Sistema: auto historia iniciado.")
            self.auto_step()
        else:
            self.write_log("Sistema: auto historia pausado.")

    def auto_step(self) -> None:
        if not self.auto_running:
            return
        self.tell_next_line()
        self.root.after(2200, self.auto_step)

    def replay(self) -> None:
        replay = self.runtime.replay_favorite_image()
        if replay:
            self.write_log(f"Darwin: voltei para uma imagem da historia {replay['story_id']} com foco em {replay['attention_focus']}.")
        else:
            self.write_log("Darwin: ainda preciso ouvir ao menos uma linha.")

    def consolidate(self) -> None:
        replay = self.runtime.replay_favorite_image() if self.runtime.reactions else {}
        summary = self.runtime.consolidate_session(replay)
        self.auto_running = False
        self.reaction_text.delete("1.0", "end")
        self.reaction_text.insert(
            "end",
            "\n".join(
                [
                    "Sessao consolidada",
                    f"historias: {summary['story_count']}",
                    f"exposicoes: {summary['exposure_count']}",
                    f"reacoes: {summary['reaction_count']}",
                    f"foco principal: {summary['top_focus']}",
                    f"conforto medio: {summary['avg_comfort']:.2f}",
                    f"curiosidade media: {summary['avg_curiosity']:.2f}",
                    f"empatia media: {summary['avg_empathy']:.2f}",
                ]
            ),
        )
        self.write_log("Sistema: sessao de historias gravada no darwin.db.")

    def animate(self) -> None:
        self.phase += 0.055
        self.draw_orb()
        self.root.after(50, self.animate)

    def draw_orb(self) -> None:
        self.canvas.delete("all")
        w = max(1, self.canvas.winfo_width())
        h = max(1, self.canvas.winfo_height())
        cx, cy = w * 0.50, h * 0.54
        reaction = self.current_reaction
        stability = reaction.stability if reaction else 0.68
        curiosity = reaction.curiosity if reaction else 0.40
        pulse = 1.0 + math.sin(self.phase) * (0.025 + curiosity * 0.035)
        radius = min(w, h) * (0.20 + stability * 0.045) * pulse
        for ring in range(7, 0, -1):
            rr = radius + ring * 13
            shade = 28 + ring * 13
            self.canvas.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, outline="", fill=f"#{shade:02x}{min(80 + ring * 18, 180):02x}{min(110 + ring * 15, 220):02x}")
        self.canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill=self.current_color, outline="#eaf6ff", width=2)
        self.canvas.create_oval(cx - radius * 0.32, cy - radius * 0.32, cx + radius * 0.32, cy + radius * 0.32, fill="#e7fbff", outline="")
        title = self.selected_story().title
        self.canvas.create_text(cx, 32, text=title, fill=self.INK, font=("Segoe UI", 17, "bold"))
        if reaction:
            self.canvas.create_text(cx, h - 24, text=f"{reaction.felt_state} | RZS {reaction.rzs_decision} | {reaction.attention_focus}", fill=self.MUTED, font=("Segoe UI", 10))


def print_self_test(summary: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.29 - CHILD STORY NURSERY")
    print("=" * 66)
    print(f"- sessao: {summary['session_id']}")
    print(f"- historias={summary['story_count']} exposicoes={summary['exposure_count']} reacoes={summary['reaction_count']}")
    print(f"- conforto={summary['avg_comfort']:.3f} curiosidade={summary['avg_curiosity']:.3f} empatia={summary['avg_empathy']:.3f}")
    print(f"- foco principal: {summary['top_focus']}")
    print(f"- RZS: {', '.join(summary['rzs_decisions'])}")
    print(f"- historias seguras: {summary['child_safe_storybook']}")
    print("Resultado self-test: OK")
    if details:
        print("\nJSON:")
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.29 Child Story Nursery")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--details", action="store_true")
    ap.add_argument("--seed", type=int, default=4929)
    args = ap.parse_args()
    if args.self_test:
        runtime = StoryNurseryRuntime(seed=args.seed, mode="self_test")
        summary = runtime.run_self_test()
        print_self_test(summary, args.details)
        return 0

    root = tk.Tk()
    app = StoryNurseryApp(root)

    def on_close() -> None:
        try:
            if app.runtime.reactions:
                app.consolidate()
        finally:
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
