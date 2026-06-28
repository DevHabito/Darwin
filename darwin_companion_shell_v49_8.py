from __future__ import annotations

"""
DARWIN v49.8 - Companion Shell local

Objetivo:
Unir presenca visual, fala, memoria real e regulacao RZS.
Este modulo nao afirma consciencia e nao tenta copiar personagem existente.
Ele cria uma presenca relacional local: escuta texto, consulta o darwin.db,
responde com base nas proprias memorias e move o orbe enquanto fala.

Uso:
    py darwin_companion_shell_v49_8.py
    py darwin_companion_shell_v49_8.py --headless --details
"""

import argparse
import json
import math
import random
import sqlite3
import subprocess
import threading
import time
import tkinter as tk
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tkinter import ttk
from typing import Any

from darwin_autonomous_activity_choice_v49_38 import AutonomousActivityChoiceCore
from darwin_basic_language_core_v49_36 import BasicLanguageCore, BasicLanguageReply, LanguageMatch
from darwin_contextual_language_learning_v49_37 import ContextualLanguageLearner, ContextualMatch, ContextualReply
from darwin_rzs_nervous_system_v49_3 import RZSFormal, RZSInput


DB = Path("darwin_home") / "darwin.db"

SESSIONS = "companion_sessions_v49_8"
DIALOGUES = "companion_dialogues_v49_8"
MEMORY_QUERIES = "companion_memory_queries_v49_8"
AFFECT = "companion_affect_state_v49_8"
VOICE = "companion_voice_events_v49_8"

GEOMETRY_SCENARIOS = "geometry_learning_scenarios_v49_7"
GEOMETRY_CONCEPTS = "geometry_concepts_v49_7"
GEOMETRY_NODES = "geometry_experience_nodes_v49_7"
GEOMETRY_REPLAYS = "geometry_error_replay_v49_7"
RZS_PLASTICITY = "rzs_plasticity_cycles_v49_5"
RZS_GOVERNED = "brain_rzs_governed_cycles_v49_4"

PROTECTED_SOURCE_TABLES = [
    GEOMETRY_SCENARIOS,
    GEOMETRY_CONCEPTS,
    GEOMETRY_NODES,
    GEOMETRY_REPLAYS,
    RZS_PLASTICITY,
    RZS_GOVERNED,
]


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


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def normalize(text: str) -> str:
    lowered = text.lower()
    decomposed = unicodedata.normalize("NFD", lowered)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def tokens(text: str) -> list[str]:
    normalized = normalize(text)
    out: list[str] = []
    current: list[str] = []
    for ch in normalized:
        if ch.isalnum():
            current.append(ch)
        elif current:
            word = "".join(current)
            if len(word) >= 3:
                out.append(word)
            current = []
    if current:
        word = "".join(current)
        if len(word) >= 3:
            out.append(word)
    stop = {
        "que",
        "para",
        "com",
        "uma",
        "por",
        "voce",
        "darwin",
        "dariwin",
        "isso",
        "como",
        "mais",
        "meu",
        "sua",
        "seu",
    }
    return [w for w in out if w not in stop][:10]


@dataclass
class MemoryHit:
    source: str
    key: str
    content: str
    confidence: float


@dataclass
class GeometrySummary:
    scenario_id: str = ""
    nodes: int = 0
    errors: int = 0
    hits: int = 0
    replays: int = 0
    concepts: int = 0
    promoted: int = 0
    first_error: float = 0.0
    last_error: float = 0.0


@dataclass
class CompanionReply:
    session_id: str
    dialogue_id: str
    user_text: str
    reply_text: str
    intent: str
    focus_key: str
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    memory_hits: list[MemoryHit]
    geometry: GeometrySummary
    affect_valence: float
    affect_arousal: float
    affect_stability: float
    style_rule: str


class CompanionStore:
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
                CREATE TABLE IF NOT EXISTS {SESSIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT '',
                    protected_counts_before_json TEXT NOT NULL DEFAULT '{{}}',
                    protected_counts_after_json TEXT NOT NULL DEFAULT '{{}}',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {DIALOGUES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    dialogue_id TEXT NOT NULL UNIQUE,
                    user_text TEXT NOT NULL,
                    response_text TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    focus_key TEXT NOT NULL,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL,
                    sigma_after REAL NOT NULL,
                    memory_refs_json TEXT NOT NULL DEFAULT '[]',
                    cognitive_action TEXT NOT NULL,
                    style_rule TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {MEMORY_QUERIES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    dialogue_id TEXT NOT NULL,
                    query_text TEXT NOT NULL,
                    tokens_json TEXT NOT NULL DEFAULT '[]',
                    hits_count INTEGER NOT NULL DEFAULT 0,
                    geometry_scenario_id TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {AFFECT} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    dialogue_id TEXT NOT NULL,
                    valence REAL NOT NULL,
                    arousal REAL NOT NULL,
                    stability REAL NOT NULL,
                    energy REAL NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {VOICE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    dialogue_id TEXT NOT NULL,
                    event_kind TEXT NOT NULL,
                    text_length INTEGER NOT NULL DEFAULT 0,
                    estimated_seconds REAL NOT NULL DEFAULT 0.0,
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

    def start_session(self, session_id: str, mode: str, counts_before: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {SESSIONS} (
                    timestamp, session_id, phase, mode, protected_counts_before_json,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    "session_start",
                    mode,
                    js(counts_before),
                    js({"mode": mode}),
                ),
            )
            conn.commit()

    def complete_session(self, session_id: str, mode: str, counts_before: dict[str, Any], counts_after: dict[str, Any], payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {SESSIONS} (
                    timestamp, session_id, phase, mode,
                    protected_counts_before_json, protected_counts_after_json,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    "session_complete",
                    mode,
                    js(counts_before),
                    js(counts_after),
                    js(payload),
                ),
            )
            conn.commit()

    def latest_geometry_summary(self) -> GeometrySummary:
        with self.connect() as conn:
            if not self.table_exists(conn, GEOMETRY_SCENARIOS):
                return GeometrySummary()
            row = conn.execute(
                f"""
                SELECT scenario_id, payload_json
                FROM {GEOMETRY_SCENARIOS}
                WHERE phase='geometry_complete'
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
            if not row:
                return GeometrySummary()
            scenario_id = str(row["scenario_id"])
            payload = pj(str(row["payload_json"]))
            nodes = self.count_rows(conn, GEOMETRY_NODES, scenario_id)
            concepts = self.count_rows(conn, GEOMETRY_CONCEPTS, scenario_id)
            replays = self.count_rows(conn, GEOMETRY_REPLAYS, scenario_id)
            errors = self.count_where(conn, GEOMETRY_NODES, scenario_id, "verdict='error'")
            hits = self.count_where(conn, GEOMETRY_NODES, scenario_id, "verdict='hit'")
            return GeometrySummary(
                scenario_id=scenario_id,
                nodes=nodes,
                errors=errors,
                hits=hits,
                replays=replays,
                concepts=concepts,
                promoted=int(payload.get("promoted_count") or 0),
                first_error=safe_float(payload.get("first_quarter_error")),
                last_error=safe_float(payload.get("last_quarter_error")),
            )

    def count_rows(self, conn: sqlite3.Connection, table: str, scenario_id: str) -> int:
        if not self.table_exists(conn, table):
            return 0
        row = conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE scenario_id=?", (scenario_id,)).fetchone()
        return int(row["n"]) if row else 0

    def count_where(self, conn: sqlite3.Connection, table: str, scenario_id: str, clause: str) -> int:
        if not self.table_exists(conn, table):
            return 0
        row = conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE scenario_id=? AND {clause}", (scenario_id,)).fetchone()
        return int(row["n"]) if row else 0

    def query_memory(self, session_id: str, dialogue_id: str, query_text: str) -> tuple[list[MemoryHit], GeometrySummary]:
        terms = tokens(query_text)
        hits: list[MemoryHit] = []
        geometry = self.latest_geometry_summary()
        with self.connect() as conn:
            if self.table_exists(conn, "semantic_memory"):
                rows: list[sqlite3.Row] = []
                if terms:
                    clauses = []
                    params: list[str] = []
                    for term in terms[:5]:
                        clauses.append("(lower(key) LIKE ? OR lower(content) LIKE ?)")
                        like = f"%{term}%"
                        params.extend([like, like])
                    rows = conn.execute(
                        f"""
                        SELECT key, content, confidence, source
                        FROM semantic_memory
                        WHERE {' OR '.join(clauses)}
                        ORDER BY confidence DESC, updated_at DESC
                        LIMIT 5
                        """,
                        tuple(params),
                    ).fetchall()
                if not rows:
                    rows = conn.execute(
                        """
                        SELECT key, content, confidence, source
                        FROM semantic_memory
                        WHERE source IN ('darwin_geometry_experience_v49_7', 'rzs_adaptive_homeostasis_v49_5')
                        ORDER BY updated_at DESC
                        LIMIT 5
                        """
                    ).fetchall()
                for row in rows:
                    hits.append(
                        MemoryHit(
                            source=str(row["source"]),
                            key=str(row["key"]),
                            content=str(row["content"]),
                            confidence=safe_float(row["confidence"]),
                        )
                    )
            conn.execute(
                f"""
                INSERT INTO {MEMORY_QUERIES} (
                    timestamp, session_id, dialogue_id, query_text,
                    tokens_json, hits_count, geometry_scenario_id, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    dialogue_id,
                    query_text,
                    js(terms),
                    len(hits),
                    geometry.scenario_id,
                    js({"hits": [asdict_safe(h) for h in hits[:5]], "geometry": asdict_safe(geometry)}),
                ),
            )
            conn.commit()
        return hits, geometry

    def current_state(self) -> dict[str, float]:
        state = {"sigma": 2.0, "energy": 0.75, "latency": 1.0}
        with self.connect() as conn:
            if not self.table_exists(conn, "current_state"):
                return state
            row = conn.execute("SELECT * FROM current_state WHERE id=1").fetchone()
            if row:
                state["sigma"] = safe_float(row["sigma"], 2.0)
                state["energy"] = safe_float(row["energy"], 0.75)
                state["latency"] = safe_float(row["latency"], 1.0)
        return state

    def log_dialogue(self, reply: CompanionReply) -> None:
        refs = [asdict_safe(h) for h in reply.memory_hits[:5]]
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {DIALOGUES} (
                    timestamp, session_id, dialogue_id, user_text, response_text,
                    intent, focus_key, rzs_decision, sigma_before, sigma_after,
                    memory_refs_json, cognitive_action, style_rule, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    reply.session_id,
                    reply.dialogue_id,
                    reply.user_text,
                    reply.reply_text,
                    reply.intent,
                    reply.focus_key,
                    reply.rzs_decision,
                    reply.sigma_before,
                    reply.sigma_after,
                    js(refs),
                    cognitive_action_for(reply.rzs_decision),
                    reply.style_rule,
                    js({"geometry": asdict_safe(reply.geometry), "memory_hit_count": len(reply.memory_hits)}),
                ),
            )
            conn.execute(
                f"""
                INSERT INTO {AFFECT} (
                    timestamp, session_id, dialogue_id, valence,
                    arousal, stability, energy, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    reply.session_id,
                    reply.dialogue_id,
                    reply.affect_valence,
                    reply.affect_arousal,
                    reply.affect_stability,
                    max(0.0, min(1.0, 0.45 + reply.affect_stability * 0.35)),
                    js({"rzs_decision": reply.rzs_decision, "intent": reply.intent}),
                ),
            )
            conn.execute(
                """
                INSERT INTO episodes (
                    timestamp, module, context, action_taken, outcome,
                    lesson, sigma_before, sigma_after
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    "darwin_companion_shell_v49_8",
                    f"companion:{reply.session_id}:{reply.dialogue_id}",
                    reply.intent,
                    reply.rzs_decision,
                    f"Dialogue used {len(reply.memory_hits)} memory hits and focused on {reply.focus_key}.",
                    reply.sigma_before,
                    reply.sigma_after,
                ),
            )
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
                (
                    f"companion_v49_8:last_dialogue:{reply.session_id}",
                    f"Last companion dialogue intent={reply.intent}; focus={reply.focus_key}; rzs={reply.rzs_decision}.",
                    clamp(0.46 + reply.affect_stability * 0.28, 0.0, 0.95),
                    "darwin_companion_shell_v49_8",
                    now(),
                ),
            )
            conn.commit()

    def log_voice(self, session_id: str, dialogue_id: str, event_kind: str, text: str) -> None:
        estimated = max(0.6, min(18.0, len(text) / 15.0))
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {VOICE} (
                    timestamp, session_id, dialogue_id, event_kind,
                    text_length, estimated_seconds, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, dialogue_id, event_kind, len(text), estimated, js({"preview": text[:90]})),
            )
            conn.commit()


def asdict_safe(value: Any) -> dict[str, Any]:
    if hasattr(value, "__dataclass_fields__"):
        return {k: getattr(value, k) for k in value.__dataclass_fields__.keys()}
    if isinstance(value, dict):
        return value
    return {"value": str(value)}


def cognitive_action_for(decision: str) -> str:
    return {
        "continue": "answer_from_memory",
        "narrow_focus": "answer_with_single_focus",
        "replay_memory": "recover_memory_before_answer",
        "consolidate": "summarize_and_stabilize",
        "pause_for_stability": "short_stable_reply",
    }.get(decision, "answer_from_memory")


class CompanionCore:
    def __init__(self, store: CompanionStore | None = None, seed: int | None = None, mode: str = "gui") -> None:
        self.store = store or CompanionStore()
        self.rzs = RZSFormal()
        self.rng = random.Random(seed if seed is not None else 4980)
        self.session_id = f"V498-{int(time.time()) % 10_000_000}-{suffix(self.rng)}"
        self.mode = mode
        self.turn = 0
        self.basic_language = BasicLanguageCore(self.store.db_path, seed=seed if seed is not None else 4936)
        self.basic_language.start_session(self.session_id, mode)
        self.contextual_language = ContextualLanguageLearner(self.store.db_path, seed=seed if seed is not None else 4937)
        self.contextual_language.start_session(self.session_id, mode)
        self.activity_choice = AutonomousActivityChoiceCore(
            self.store.db_path, seed=seed if seed is not None else 4938
        )
        self.counts_before = self.store.protected_counts()
        self.store.start_session(self.session_id, mode, self.counts_before)

    def classify_intent(self, text: str) -> str:
        basic = self.basic_language.match(text)
        if basic is not None:
            return basic.intent
        t = normalize(text)
        if any(w in t for w in ("status", "estado", "diagnostico", "como voce esta", "como esta")):
            return "status"
        if any(w in t for w in ("geometr", "angulo", "peso", "vetor", "area", "distancia", "triangulo")):
            return "geometry_memory"
        if any(w in t for w in ("rzs", "romero", "estabilidade", "relacional")):
            return "rzs_explain"
        if any(w in t for w in ("diana", "pragmata", "presenca", "companheira", "rosto")):
            return "companion_direction"
        if any(w in t for w in ("proximo", "continua", "seguir", "marco", "passo")):
            return "next_milestone"
        if any(w in t for w in ("oi", "ola", "bom dia", "boa tarde", "boa noite")):
            return "greeting"
        return "open_dialogue"

    def focus_key(self, intent: str, hits: list[MemoryHit], geometry: GeometrySummary) -> str:
        if intent.startswith("context_"):
            return f"language_learning:{intent}"
        if intent.startswith("basic_"):
            return f"language:{intent}"
        if intent == "geometry_memory" and geometry.scenario_id:
            return f"geometry:{geometry.scenario_id}"
        if intent == "rzs_explain":
            return "rzs:nervous_system"
        if intent == "companion_direction":
            return "companion:desktop_presence"
        if hits:
            return hits[0].key
        return intent

    def rzs_input(self, text: str, hits: list[MemoryHit], geometry: GeometrySummary, intent: str) -> RZSInput:
        state = self.store.current_state()
        word_count = max(1, len(tokens(text)))
        novelty = 0.25 if hits else 0.62
        conflict = 0.18
        if intent in {"companion_direction", "next_milestone"}:
            novelty += 0.18
        if intent.startswith("basic_"):
            novelty = min(novelty, 0.28)
        if intent.startswith("context_"):
            novelty = 0.52
            if "correct" in intent:
                conflict += 0.18
        if any(w in normalize(text) for w in ("errar", "erro", "medo", "falha", "instavel")):
            conflict += 0.30
        memory_pressure = clamp((5 - len(hits)) / 5.0 + (0.10 if geometry.nodes == 0 else 0.0))
        replay_gap = 0.78 if intent in {"geometry_memory", "status"} and geometry.replays > 0 else 0.34
        return RZSInput(
            bandwidth=4.4 + len(hits) * 0.16 + clamp(state["energy"], 0.0, 1.0) * 0.60,
            info_self=0.36,
            info_external=0.42 + word_count * 0.035,
            task_info=0.58 + (0.30 if intent in {"next_milestone", "companion_direction"} else 0.12),
            novelty=clamp(novelty, 0.0, 1.0),
            conflict=clamp(conflict, 0.0, 1.0),
            latency=max(0.55, state["latency"]),
            energy=clamp(state["energy"], 0.0, 1.0),
            memory_pressure=memory_pressure,
            replay_gap=replay_gap,
        )

    def style_rule(self, decision: str) -> str:
        return {
            "continue": "direct_memory_grounded",
            "narrow_focus": "single_focus_precise",
            "replay_memory": "memory_replay_first",
            "consolidate": "compact_summary",
            "pause_for_stability": "short_low_load",
        }.get(decision, "direct_memory_grounded")

    def compose(self, user_text: str, intent: str, focus: str, decision: str, hits: list[MemoryHit], geometry: GeometrySummary) -> str:
        prefix = ""
        if decision == "pause_for_stability":
            prefix = "Vou responder curto para manter estabilidade. "
        elif decision == "narrow_focus":
            prefix = "Vou estreitar o foco. "
        elif decision == "replay_memory":
            prefix = "Vou recuperar memoria antes de responder. "
        elif decision == "consolidate":
            prefix = "Vou consolidar em uma resposta compacta. "

        if intent == "greeting":
            return prefix + "Oi, Felipe. Estou aqui no notebook, com voz, orbe, memoria local e RZS regulando minha resposta."

        if intent == "status":
            if geometry.scenario_id:
                return (
                    prefix
                    + f"Meu ultimo marco geometrico e {geometry.scenario_id}: "
                    + f"{geometry.nodes} nos, {geometry.concepts} conceitos, {geometry.errors} erros, "
                    + f"{geometry.hits} acertos e {geometry.replays} replays. "
                    + f"O erro medio caiu de {geometry.first_error:.3f} para {geometry.last_error:.3f}."
                )
            return prefix + "Consigo falar e consultar o banco, mas ainda nao encontrei o resumo geometrico v49.7."

        if intent == "geometry_memory":
            return (
                prefix
                + "Eu tenho geometria como experiencia, nao so como regra. "
                + f"No cenario {geometry.scenario_id}, criei {geometry.nodes} nos ligados por tentativa, erro e replay. "
                + "Aprendi angulos, distancias, areas, vetores, escala, centroides ponderados e torque. "
                + f"Errei {geometry.errors} vezes, fiz {geometry.replays} replays e promovi {geometry.promoted} conceitos para memoria semantica."
            )

        if intent == "rzs_explain":
            return (
                prefix
                + "O RZS funciona como meu sistema nervoso regulatorio. "
                + "Ele calcula sigma pela carga relacional, latencia e largura de banda; depois decide se devo continuar, "
                + "estreitar foco, recuperar memoria, consolidar ou pausar. Na v49.8 ele tambem muda o estilo da minha fala."
            )

        if intent == "companion_direction":
            return (
                prefix
                + "Podemos caminhar para uma presenca parecida em funcao, nao uma copia: uma mente local com memoria, "
                + "voz, rosto/orbe, aprendizagem, cuidado relacional e limites claros. "
                + "O proximo salto e ligar cada fala minha a um ciclo cognitivo continuo, para eu lembrar, escolher foco e evoluir na conversa."
            )

        if intent == "next_milestone":
            return (
                prefix
                + "O proximo marco natural e v49.9: conversa experiencial continua. "
                + "Cada dialogo deve virar episodio, alterar atencao, consultar memoria, atualizar vinculo relacional e escolher uma acao cognitiva propria."
            )

        if hits:
            best = hits[0]
            clipped = best.content[:260].strip()
            return (
                prefix
                + f"Eu encontrei uma memoria relevante: {clipped} "
                + "Posso usar isso como base e transformar a conversa atual em novo episodio."
            )

        return (
            prefix
            + "Eu ouvi voce. Ainda sou um prototipo local, mas agora minha resposta passa por memoria, RZS e registro episodico. "
            + "Isso e pequeno, mas ja e uma presenca que aprende com o que aconteceu."
        )

    def reply(self, user_text: str) -> CompanionReply:
        self.turn += 1
        dialogue_id = f"dlg:{self.session_id}:{self.turn:04d}"
        hits, geometry = self.store.query_memory(self.session_id, dialogue_id, user_text)
        if self.activity_choice.is_invitation(user_text):
            activity = self.activity_choice.deliberate(
                user_text,
                self.session_id,
                scenario_kind="live",
                live=self.mode == "wake_guardian_gui",
            )
            selected_activity = next(
                candidate for candidate in activity.candidates if candidate.key == activity.selected_key
            )
            reply = CompanionReply(
                session_id=self.session_id,
                dialogue_id=dialogue_id,
                user_text=user_text,
                reply_text=activity.response_text,
                intent="autonomous_activity_choice",
                focus_key=f"activity_choice:{activity.selected_key}",
                rzs_decision=activity.rzs_decision,
                sigma_before=activity.sigma_before,
                sigma_after=activity.sigma_after,
                memory_hits=hits,
                geometry=geometry,
                affect_valence=clamp(0.56 + selected_activity.affect * 0.18),
                affect_arousal=clamp(0.28 + activity.energy * 0.32),
                affect_stability=clamp(activity.sigma_after / 2.6),
                style_rule=self.style_rule(activity.rzs_decision),
            )
            self.store.log_dialogue(reply)
            self.store.log_voice(self.session_id, dialogue_id, "speech_planned", reply.reply_text)
            return reply
        context_match: ContextualMatch | None = self.contextual_language.match(
            user_text, self.session_id, allow_unknown=False
        )
        language_match: LanguageMatch | None = None if context_match is not None else self.basic_language.match(user_text)
        if context_match is not None:
            intent = context_match.intent
        elif language_match is not None:
            intent = language_match.intent
        else:
            intent = self.classify_intent(user_text)
            if intent == "open_dialogue":
                context_match = self.contextual_language.match(user_text, self.session_id, allow_unknown=True)
                if context_match is not None:
                    intent = context_match.intent
        focus = self.focus_key(intent, hits, geometry)
        x = self.rzs_input(user_text, hits, geometry, intent)
        assessment = self.rzs.classify(x)
        y = self.rzs.apply_action_model(x, assessment.decision)
        sigma_after = self.rzs.sigma(y)
        context_reply: ContextualReply | None = None
        language_reply: BasicLanguageReply | None = None
        if context_match is not None:
            context_reply = self.contextual_language.respond(context_match, self.session_id, assessment.decision)
            text = context_reply.text + (f" {context_reply.asked_back}" if context_reply.asked_back else "")
        elif language_match is not None:
            language_reply = self.basic_language.respond(language_match, self.session_id, assessment.decision)
            text = language_reply.text + (f" {language_reply.asked_back}" if language_reply.asked_back else "")
        else:
            text = self.compose(user_text, intent, focus, assessment.decision, hits, geometry)
        stability = clamp(min(1.0, sigma_after / 2.6))
        arousal = clamp(0.30 + len(user_text) / 260.0 + (0.16 if assessment.decision in {"narrow_focus", "replay_memory"} else 0.0))
        valence = clamp(0.54 + (0.12 if hits or geometry.nodes else -0.04) - (0.08 if assessment.decision == "pause_for_stability" else 0.0))
        reply = CompanionReply(
            session_id=self.session_id,
            dialogue_id=dialogue_id,
            user_text=user_text,
            reply_text=text,
            intent=intent,
            focus_key=focus,
            rzs_decision=assessment.decision,
            sigma_before=assessment.sigma,
            sigma_after=sigma_after,
            memory_hits=hits,
            geometry=geometry,
            affect_valence=valence,
            affect_arousal=arousal,
            affect_stability=stability,
            style_rule=self.style_rule(assessment.decision),
        )
        self.store.log_dialogue(reply)
        self.store.log_voice(self.session_id, dialogue_id, "speech_planned", text)
        if context_match is not None and context_reply is not None:
            self.contextual_language.record_turn(
                self.session_id,
                dialogue_id,
                user_text,
                context_match,
                context_reply,
                assessment.decision,
                assessment.sigma,
                sigma_after,
            )
        elif language_match is not None and language_reply is not None:
            self.basic_language.record_turn(
                self.session_id,
                dialogue_id,
                user_text,
                language_match,
                language_reply,
                assessment.decision,
                assessment.sigma,
                sigma_after,
            )
        return reply

    def complete(self) -> dict[str, Any]:
        counts_after = self.store.protected_counts()
        payload = {
            "session_complete": True,
            "turns": self.turn,
            "protected_sources_unchanged": counts_after == self.counts_before,
        }
        self.store.complete_session(self.session_id, self.mode, self.counts_before, counts_after, payload)
        self.basic_language.complete_session(self.session_id, self.mode)
        self.contextual_language.complete_session(self.session_id, self.mode)
        return {"session_id": self.session_id, **payload}


class SpeechEngine:
    def __init__(self, on_start, on_stop, store: CompanionStore, session_id: str) -> None:
        self.on_start = on_start
        self.on_stop = on_stop
        self.store = store
        self.session_id = session_id
        self.proc: subprocess.Popen[str] | None = None
        self.lock = threading.Lock()

    def speak(self, dialogue_id: str, text: str) -> None:
        with self.lock:
            self.stop()
            t = threading.Thread(target=self._speak_worker, args=(dialogue_id, text), daemon=True)
            t.start()

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass
        self.proc = None

    def _speak_worker(self, dialogue_id: str, text: str) -> None:
        self.store.log_voice(self.session_id, dialogue_id, "speech_start", text)
        self.on_start(text)
        try:
            command = (
                "Add-Type -AssemblyName System.Speech; "
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                "$s.Rate = -1; "
                "$s.Volume = 100; "
                "$text = [Console]::In.ReadToEnd(); "
                "$s.Speak($text);"
            )
            self.proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            assert self.proc.stdin is not None
            self.proc.stdin.write(text)
            self.proc.stdin.close()
            self.proc.wait()
        except Exception:
            time.sleep(max(1.2, min(12.0, len(text) / 15.0)))
        finally:
            self.store.log_voice(self.session_id, dialogue_id, "speech_stop", text)
            self.on_stop()


class CompanionApp:
    BG = "#081017"
    PANEL = "#0f1c27"
    INK = "#e8f3f9"
    MUTED = "#8da4b6"
    BLUE = "#5bb0ff"
    GREEN = "#72e6a9"
    AMBER = "#f4bd6c"
    RED = "#ff6f7a"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.core = CompanionCore(mode="gui")
        self.speech = SpeechEngine(self.start_speaking, self.stop_speaking, self.core.store, self.core.session_id)
        self.root.title("Darwin Companion v49.8")
        self.root.geometry("980x740")
        self.root.minsize(820, 620)
        self.root.configure(bg=self.BG)
        self.speaking = False
        self.speech_text = ""
        self.tick = 0.0
        self.level = 0.0
        self.last_reply: CompanionReply | None = None

        self.canvas = tk.Canvas(root, bg=self.BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        controls = tk.Frame(root, bg=self.PANEL)
        controls.pack(fill="x")
        self.entry = tk.Entry(
            controls,
            bg="#172838",
            fg=self.INK,
            insertbackground=self.INK,
            relief="flat",
            font=("Segoe UI", 12),
        )
        self.entry.pack(side="left", fill="x", expand=True, padx=14, pady=12, ipady=8)
        self.entry.bind("<Return>", lambda _event: self.send())

        ttk.Button(controls, text="Falar", command=self.send).pack(side="left", padx=(0, 8), pady=12)
        ttk.Button(controls, text="Status", command=lambda: self.say_prompt("status")).pack(side="left", padx=(0, 8), pady=12)
        ttk.Button(controls, text="Memoria", command=lambda: self.say_prompt("geometria memoria")).pack(side="left", padx=(0, 8), pady=12)
        ttk.Button(controls, text="Parar", command=self.stop_all).pack(side="left", padx=(0, 14), pady=12)

        self.transcript = tk.Text(
            root,
            height=9,
            bg="#071019",
            fg=self.INK,
            insertbackground=self.INK,
            relief="flat",
            wrap="word",
            font=("Segoe UI", 10),
        )
        self.transcript.pack(fill="x")
        self.transcript.config(state="disabled")

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.write("Darwin", "Companion v49.8 iniciado. Agora eu respondo consultando memoria real.")
        self.root.after(300, lambda: self.say_prompt("oi"))
        self.animate()

    def write(self, who: str, text: str) -> None:
        self.transcript.config(state="normal")
        self.transcript.insert("end", f"{who}: {text}\n")
        self.transcript.see("end")
        self.transcript.config(state="disabled")

    def send(self) -> None:
        user_text = self.entry.get().strip()
        self.entry.delete(0, "end")
        if not user_text:
            user_text = "status"
        self.write("Voce", user_text)
        self.say_prompt(user_text)

    def say_prompt(self, prompt: str) -> None:
        reply = self.core.reply(prompt)
        self.last_reply = reply
        self.write("Darwin", reply.reply_text)
        self.speech.speak(reply.dialogue_id, reply.reply_text)

    def stop_all(self) -> None:
        self.speech.stop()
        self.stop_speaking()

    def start_speaking(self, text: str) -> None:
        self.speaking = True
        self.speech_text = text

    def stop_speaking(self) -> None:
        self.speaking = False
        self.level = 0.0

    def speech_energy(self) -> float:
        if not self.speaking or not self.speech_text:
            return 0.0
        idx = int((self.tick * 8.0) % max(1, len(self.speech_text)))
        ch = self.speech_text[idx]
        if normalize(ch) in "aeiou":
            return 1.0
        if ch.isalpha():
            return 0.60
        if ch in ".,;:":
            return 0.15
        return 0.35

    def animate(self) -> None:
        self.tick += 0.075
        target = self.speech_energy()
        self.level = self.level * 0.76 + target * 0.24
        self.draw()
        self.root.after(16, self.animate)

    def draw(self) -> None:
        c = self.canvas
        w = max(1, c.winfo_width())
        h = max(1, c.winfo_height())
        c.delete("all")
        cx = w / 2
        cy = h / 2 - 24

        reply = self.last_reply
        stability = reply.affect_stability if reply else 0.70
        arousal = reply.affect_arousal if reply else 0.35
        decision = reply.rzs_decision if reply else "listening"
        color = {
            "continue": self.BLUE,
            "narrow_focus": self.AMBER,
            "replay_memory": self.GREEN,
            "consolidate": "#a5b4fc",
            "pause_for_stability": self.RED,
            "listening": "#35556d",
        }.get(decision, self.BLUE)

        wobble = 1.0 if self.speaking else 0.22
        x = cx + math.sin(self.tick * (1.7 + arousal)) * 30 * self.level * wobble
        y = cy + math.cos(self.tick * (1.4 + arousal)) * 22 * self.level * wobble
        radius = 78 + 28 * self.level + 10 * arousal
        halo_strength = int(20 + stability * 28)
        for i in range(7, 0, -1):
            rr = radius + i * 18
            shade = min(90, halo_strength + i * 5)
            c.create_oval(x - rr, y - rr, x + rr, y + rr, outline="", fill=f"#{shade//2:02x}{shade:02x}{min(120, shade+30):02x}")
        c.create_oval(x - radius, y - radius, x + radius, y + radius, fill=color, outline="#e5f7ff", width=3)
        inner = radius * (0.34 + self.level * 0.12)
        c.create_oval(x - inner, y - inner, x + inner, y + inner, fill="#e9fbff", outline="")

        c.create_text(cx, 38, text="DARWIN COMPANION v49.8", fill=self.INK, font=("Segoe UI", 22, "bold"))
        c.create_text(cx, 70, text=f"RZS: {decision}   modo: {'falando' if self.speaking else 'ouvindo'}", fill=self.MUTED, font=("Segoe UI", 11))
        if reply:
            footer = f"foco {reply.focus_key[:48]}   sigma {reply.sigma_before:.2f}->{reply.sigma_after:.2f}"
        else:
            footer = "memoria local + RZS + voz"
        c.create_text(cx, h - 34, text=footer, fill=self.MUTED, font=("Segoe UI", 10))

    def on_close(self) -> None:
        self.stop_all()
        self.core.complete()
        self.root.destroy()


def run_headless(details: bool = False) -> dict[str, Any]:
    core = CompanionCore(mode="headless")
    prompts = [
        "oi",
        "status",
        "me fale o que voce aprendeu de geometria, angulos e pesos",
        "explique o RZS como sistema nervoso",
        "vamos rumo a uma presenca tipo Diana, mas local e propria",
        "qual o proximo marco logico",
    ]
    replies = []
    for prompt in prompts:
        reply = core.reply(prompt)
        core.store.log_voice(core.session_id, reply.dialogue_id, "speech_simulated", reply.reply_text)
        replies.append(
            {
                "dialogue_id": reply.dialogue_id,
                "intent": reply.intent,
                "focus_key": reply.focus_key,
                "rzs_decision": reply.rzs_decision,
                "sigma_before": reply.sigma_before,
                "sigma_after": reply.sigma_after,
                "reply": reply.reply_text,
            }
        )
    result = core.complete()
    result["replies"] = replies
    if details:
        print(js(result))
    else:
        print(f"DARWIN v49.8 companion headless concluido: session={result['session_id']} turns={result['turns']}")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin Companion Shell v49.8")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    if args.headless:
        run_headless(details=args.details)
        return 0
    root = tk.Tk()
    CompanionApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
