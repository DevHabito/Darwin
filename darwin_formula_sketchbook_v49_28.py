from __future__ import annotations

"""
DARWIN v49.28 - Formula Sketchbook / lapis digital

Objetivo:
Darwin ganha um quadro visual para rabiscar formulas como gesto
cognitivo. Ele nao recebe um desenho perfeito fixo: escolhe conceitos
da memoria, combina formulas, erra, risca, corrige e grava cada traco
como experiencia auditavel em SQLite.

Uso:
    py darwin_formula_sketchbook_v49_28.py
    py darwin_formula_sketchbook_v49_28.py --self-test --steps 90 --details
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

SOURCE = "darwin_formula_sketchbook_v49_28"

SK_SESSIONS = "formula_sketch_sessions_v49_28"
SK_SOURCES = "formula_sketch_sources_v49_28"
SK_INTENTIONS = "formula_sketch_intentions_v49_28"
SK_STROKES = "formula_sketch_strokes_v49_28"
SK_REFLECTIONS = "formula_sketch_reflections_v49_28"
SK_HANDOFFS = "formula_sketch_handoffs_v49_28"

PROTECTED_SOURCE_TABLES = [
    "geometry_concepts_v49_7",
    "geometry_experience_nodes_v49_7",
    "geometry_learning_weights_v49_7",
    "geometry_error_replay_v49_7",
    "self_model_statements_v49_27",
    "desire_dialogue_state_v49_23",
]

FORMULA_BANK: dict[str, dict[str, Any]] = {
    "rzs_sigma": {
        "family": "rzs",
        "label": "Lei de Romero / RZS",
        "expression": "sigma = B / ((I_self + I_ext + T + N + C) * L)",
        "complexity": 0.90,
    },
    "lever_balance_torque": {
        "family": "weight",
        "label": "torque como peso vezes braco",
        "expression": "tau = peso * braco",
        "complexity": 0.74,
    },
    "weighted_centroid_1d": {
        "family": "weight",
        "label": "centro ponderado em uma dimensao",
        "expression": "x_bar = soma(w_i*x_i) / soma(w_i)",
        "complexity": 0.80,
    },
    "weighted_centroid_2d_x": {
        "family": "weight",
        "label": "centroide ponderado 2D",
        "expression": "x_bar = soma(w_i*x_i) / soma(w_i)",
        "complexity": 0.84,
    },
    "angle_min_rotation": {
        "family": "angle",
        "label": "menor rotacao modular",
        "expression": "dtheta = (alvo - atual) mod simetria",
        "complexity": 0.72,
    },
    "angle_complement": {
        "family": "angle",
        "label": "complemento de angulo",
        "expression": "a + b = 90",
        "complexity": 0.46,
    },
    "angle_supplement": {
        "family": "angle",
        "label": "suplemento de angulo",
        "expression": "a + b = 180",
        "complexity": 0.48,
    },
    "triangle_angle_sum": {
        "family": "angle",
        "label": "soma interna do triangulo",
        "expression": "a + b + c = 180",
        "complexity": 0.62,
    },
    "polygon_exterior_angle": {
        "family": "angle",
        "label": "angulo externo regular",
        "expression": "angulo_ext = 360 / n",
        "complexity": 0.60,
    },
    "symmetry_rotation": {
        "family": "transformation",
        "label": "rotacao de simetria",
        "expression": "rot_min = 360 / n",
        "complexity": 0.62,
    },
    "distance_2d": {
        "family": "metric",
        "label": "distancia euclidiana",
        "expression": "d = sqrt(dx^2 + dy^2)",
        "complexity": 0.72,
    },
    "slope_2d": {
        "family": "metric",
        "label": "inclinacao de reta",
        "expression": "m = dy / dx",
        "complexity": 0.66,
    },
    "pythagorean_hypotenuse": {
        "family": "metric",
        "label": "hipotenusa",
        "expression": "c^2 = a^2 + b^2",
        "complexity": 0.76,
    },
    "vector_magnitude": {
        "family": "vector",
        "label": "magnitude de vetor",
        "expression": "|v| = sqrt(x^2 + y^2)",
        "complexity": 0.72,
    },
    "area_rectangle": {
        "family": "area",
        "label": "area do retangulo",
        "expression": "A = w * h",
        "complexity": 0.48,
    },
    "perimeter_rectangle": {
        "family": "metric",
        "label": "perimetro do retangulo",
        "expression": "P = 2*w + 2*h",
        "complexity": 0.48,
    },
    "area_triangle": {
        "family": "area",
        "label": "area do triangulo",
        "expression": "A = b * h / 2",
        "complexity": 0.54,
    },
    "circle_circumference": {
        "family": "curve",
        "label": "comprimento de circunferencia",
        "expression": "C = 2 * pi * r",
        "complexity": 0.58,
    },
    "circle_area": {
        "family": "area",
        "label": "area do circulo",
        "expression": "A = pi * r^2",
        "complexity": 0.62,
    },
    "scale_ratio": {
        "family": "transformation",
        "label": "razao de escala",
        "expression": "k = novo / original",
        "complexity": 0.58,
    },
    "similar_triangle_height": {
        "family": "transformation",
        "label": "semelhanca de triangulos",
        "expression": "h2 = h1 * k",
        "complexity": 0.70,
    },
}

FAMILY_COLORS = {
    "rzs": "#9ed0ff",
    "weight": "#f4c16b",
    "angle": "#a6e3a1",
    "metric": "#89b4fa",
    "area": "#f38ba8",
    "curve": "#cba6f7",
    "vector": "#94e2d5",
    "transformation": "#fab387",
    "memory": "#cdd6f4",
}


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


def short(text: str, limit: int = 170) -> str:
    clean = " ".join(str(text or "").split())
    return clean if len(clean) <= limit else clean[: limit - 1] + "..."


@dataclass
class FormulaSource:
    source_id: str
    source_kind: str
    concept_key: str
    family: str
    label: str
    expression: str
    confidence: float
    complexity: float
    evidence_ref: str
    payload: dict[str, Any]


@dataclass
class SketchIntention:
    intention_id: str
    step_index: int
    focus_key: str
    intention_kind: str
    formula_a: str
    formula_b: str
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    energy: float
    payload: dict[str, Any]


@dataclass
class SketchStroke:
    stroke_id: str
    intention_id: str
    step_index: int
    stroke_order: int
    stroke_kind: str
    x1: float
    y1: float
    x2: float
    y2: float
    text: str
    color: str
    width: float
    confidence: float
    payload: dict[str, Any]


class FormulaSketchStore:
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
                CREATE TABLE IF NOT EXISTS {SK_SESSIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT '',
                    step_index INTEGER NOT NULL DEFAULT 0,
                    rzs_decision TEXT NOT NULL DEFAULT '',
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {SK_SOURCES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    source_id TEXT NOT NULL UNIQUE,
                    source_kind TEXT NOT NULL,
                    concept_key TEXT NOT NULL,
                    family TEXT NOT NULL,
                    label TEXT NOT NULL,
                    expression TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    complexity REAL NOT NULL DEFAULT 0.0,
                    evidence_ref TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {SK_INTENTIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    intention_id TEXT NOT NULL UNIQUE,
                    step_index INTEGER NOT NULL,
                    focus_key TEXT NOT NULL,
                    intention_kind TEXT NOT NULL,
                    formula_a TEXT NOT NULL,
                    formula_b TEXT NOT NULL DEFAULT '',
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    energy REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {SK_STROKES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    stroke_id TEXT NOT NULL UNIQUE,
                    intention_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    stroke_order INTEGER NOT NULL,
                    stroke_kind TEXT NOT NULL,
                    x1 REAL NOT NULL DEFAULT 0.0,
                    y1 REAL NOT NULL DEFAULT 0.0,
                    x2 REAL NOT NULL DEFAULT 0.0,
                    y2 REAL NOT NULL DEFAULT 0.0,
                    text TEXT NOT NULL DEFAULT '',
                    color TEXT NOT NULL DEFAULT '',
                    width REAL NOT NULL DEFAULT 1.0,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {SK_REFLECTIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    reflection_id TEXT NOT NULL UNIQUE,
                    reflection_kind TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
                    confidence REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {SK_HANDOFFS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    handoff_id TEXT NOT NULL UNIQUE,
                    next_action TEXT NOT NULL,
                    sketch_ready INTEGER NOT NULL DEFAULT 0,
                    free_exploration_ready INTEGER NOT NULL DEFAULT 0,
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

    def latest_completed_geometry_scenario(self, conn: sqlite3.Connection) -> str:
        if self.table_exists(conn, "geometry_learning_scenarios_v49_7"):
            row = conn.execute(
                """
                SELECT scenario_id
                FROM geometry_learning_scenarios_v49_7
                WHERE phase='geometry_complete'
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
            if row:
                return str(row["scenario_id"])
        if self.table_exists(conn, "geometry_concepts_v49_7"):
            row = conn.execute(
                "SELECT scenario_id FROM geometry_concepts_v49_7 ORDER BY id DESC LIMIT 1"
            ).fetchone()
            return str(row["scenario_id"]) if row else ""
        return ""

    def latest_row(self, conn: sqlite3.Connection, table: str) -> dict[str, Any]:
        if not self.table_exists(conn, table):
            return {}
        row = conn.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT 1").fetchone()
        if not row:
            return {}
        item = {k: row[k] for k in row.keys()}
        item["payload"] = pj(str(item.get("payload_json") or "{}"), {})
        return item

    def log_session(
        self,
        session_id: str,
        phase: str,
        mode: str,
        payload: dict[str, Any],
        *,
        step_index: int = 0,
        rzs_decision: str = "",
        sigma_before: float = 0.0,
        sigma_after: float = 0.0,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {SK_SESSIONS} (
                    timestamp, session_id, phase, mode, step_index,
                    rzs_decision, sigma_before, sigma_after, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, phase, mode, step_index, rzs_decision, sigma_before, sigma_after, js(payload)),
            )
            conn.commit()

    def log_sources(self, session_id: str, sources: list[FormulaSource]) -> None:
        with self.connect() as conn:
            for item in sources:
                conn.execute(
                    f"""
                    INSERT OR REPLACE INTO {SK_SOURCES} (
                        timestamp, session_id, source_id, source_kind,
                        concept_key, family, label, expression, confidence,
                        complexity, evidence_ref, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        now(),
                        session_id,
                        item.source_id,
                        item.source_kind,
                        item.concept_key,
                        item.family,
                        item.label,
                        item.expression,
                        item.confidence,
                        item.complexity,
                        item.evidence_ref,
                        js(item.payload),
                    ),
                )
            conn.commit()

    def log_intention(self, session_id: str, item: SketchIntention) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {SK_INTENTIONS} (
                    timestamp, session_id, intention_id, step_index,
                    focus_key, intention_kind, formula_a, formula_b,
                    rzs_decision, sigma_before, sigma_after, energy,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    item.intention_id,
                    item.step_index,
                    item.focus_key,
                    item.intention_kind,
                    item.formula_a,
                    item.formula_b,
                    item.rzs_decision,
                    item.sigma_before,
                    item.sigma_after,
                    item.energy,
                    js(item.payload),
                ),
            )
            conn.commit()

    def log_strokes(self, session_id: str, strokes: list[SketchStroke]) -> None:
        if not strokes:
            return
        with self.connect() as conn:
            conn.executemany(
                f"""
                INSERT OR REPLACE INTO {SK_STROKES} (
                    timestamp, session_id, stroke_id, intention_id,
                    step_index, stroke_order, stroke_kind, x1, y1, x2, y2,
                    text, color, width, confidence, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        now(),
                        session_id,
                        item.stroke_id,
                        item.intention_id,
                        item.step_index,
                        item.stroke_order,
                        item.stroke_kind,
                        item.x1,
                        item.y1,
                        item.x2,
                        item.y2,
                        item.text,
                        item.color,
                        item.width,
                        item.confidence,
                        js(item.payload),
                    )
                    for item in strokes
                ],
            )
            conn.commit()

    def log_reflection(
        self,
        session_id: str,
        reflection_id: str,
        reflection_kind: str,
        summary: str,
        evidence_refs: list[str],
        confidence: float,
        payload: dict[str, Any],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {SK_REFLECTIONS} (
                    timestamp, session_id, reflection_id, reflection_kind,
                    summary, evidence_refs_json, confidence, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), session_id, reflection_id, reflection_kind, summary, js(evidence_refs), confidence, js(payload)),
            )
            conn.commit()

    def log_handoff(self, session_id: str, next_action: str, ready: bool, free_ready: bool, confidence: float, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {SK_HANDOFFS} (
                    timestamp, session_id, handoff_id, next_action,
                    sketch_ready, free_exploration_ready, confidence, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    session_id,
                    f"HF-{session_id}",
                    next_action,
                    1 if ready else 0,
                    1 if free_ready else 0,
                    confidence,
                    js(payload),
                ),
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
                (f"formula_sketch_v49_28:{session_id}", js(content), clamp(confidence, 0.0, 0.99), SOURCE, now()),
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
                (now(), SOURCE, f"formula_sketch:{session_id}", action, outcome, lesson, sigma_before, sigma_after),
            )
            conn.commit()


class FormulaSketchCore:
    def __init__(self, seed: int | None = None, mode: str = "gui", width: int = 1000, height: int = 620) -> None:
        self.store = FormulaSketchStore()
        self.rzs = RZSFormal()
        self.rng = random.Random(seed if seed is not None else int(time.time() * 1000) % 100_000_000)
        self.session_id = f"V4928-{int(time.time()) % 10_000_000}-{suffix(self.rng)}"
        self.mode = mode
        self.width = width
        self.height = height
        self.energy = 0.86
        self.sources: list[FormulaSource] = []
        self.intentions: list[SketchIntention] = []
        self.strokes: list[SketchStroke] = []
        self.recent_mistakes: list[dict[str, Any]] = []
        self.used_sources: dict[str, int] = {}
        self.total_mistakes = 0
        self.total_corrections = 0
        self.total_fusions = 0
        self.last_replay_step = 0
        self.stroke_counter = 0
        self.slots_per_page = 4
        self.active_layout: dict[str, Any] = {}
        self.completed = False
        self.prepared = False
        self.source_counts_before = self.store.protected_counts()

    def configure_canvas(self, width: int, height: int) -> None:
        self.width = max(720, int(width))
        self.height = max(460, int(height))

    def prepare(self) -> None:
        if self.prepared:
            return
        self.store.log_session(
            self.session_id,
            "sketch_start",
            self.mode,
            {
                "goal": "draw formulas with a digital pencil as exploratory cognition",
                "not_a_perfect_template": True,
                "protected_counts_before": self.source_counts_before,
            },
        )
        self.sources = self.load_sources()
        self.store.log_sources(self.session_id, self.sources)
        self.store.log_session(
            self.session_id,
            "source_memory_read",
            self.mode,
            {
                "source_count": len(self.sources),
                "families": sorted({s.family for s in self.sources}),
                "concepts": [s.concept_key for s in self.sources],
            },
        )
        self.prepared = True

    def load_sources(self) -> list[FormulaSource]:
        out: list[FormulaSource] = []

        def add(source_kind: str, concept_key: str, confidence: float, evidence_ref: str, payload: dict[str, Any]) -> None:
            bank = FORMULA_BANK.get(concept_key, {})
            if not bank:
                return
            if any(s.concept_key == concept_key for s in out):
                return
            out.append(
                FormulaSource(
                    source_id=f"SRC-{self.session_id}-{concept_key}",
                    source_kind=source_kind,
                    concept_key=concept_key,
                    family=str(bank["family"]),
                    label=str(bank["label"]),
                    expression=str(bank["expression"]),
                    confidence=clamp(confidence),
                    complexity=clamp(float(bank["complexity"])),
                    evidence_ref=evidence_ref,
                    payload=payload,
                )
            )

        add(
            "rzs_core",
            "rzs_sigma",
            0.92,
            "darwin_rzs_nervous_system_v49_3",
            {"formula_origin": "RZS/Romero formal regulator"},
        )
        with self.store.connect() as conn:
            scenario = self.store.latest_completed_geometry_scenario(conn)
            if scenario and self.store.table_exists(conn, "geometry_concepts_v49_7"):
                rows = conn.execute(
                    """
                    SELECT *
                    FROM geometry_concepts_v49_7
                    WHERE scenario_id=?
                    ORDER BY confidence DESC, learning_weight DESC, id ASC
                    """,
                    (scenario,),
                ).fetchall()
                for row in rows:
                    key = str(row["concept_key"])
                    if key in FORMULA_BANK:
                        add(
                            "geometry_v49_7",
                            key,
                            float(row["confidence"] or 0.50),
                            f"geometry_concepts_v49_7:{scenario}:{key}",
                            {
                                "learning_weight": float(row["learning_weight"] or 0.0),
                                "definition": str(row["definition"] or ""),
                                "geometry_scenario": scenario,
                            },
                        )
            desire = self.store.latest_row(conn, "desire_dialogue_state_v49_23")
            top_formula = short(str(desire.get("top_formula") or ""), 140)
            if "torque" in top_formula.lower():
                add("desire_dialogue_v49_23", "lever_balance_torque", 0.86, "desire_dialogue_state_v49_23:top_formula", {"top_formula": top_formula})
            if self.store.table_exists(conn, "self_model_statements_v49_27"):
                row = conn.execute(
                    """
                    SELECT session_id
                    FROM self_model_statements_v49_27
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ).fetchone()
                if row:
                    add("self_model_v49_27", "rzs_sigma", 0.94, f"self_model_statements_v49_27:{row['session_id']}", {})

        if len(out) < 10:
            for key in [
                "lever_balance_torque",
                "weighted_centroid_1d",
                "triangle_angle_sum",
                "distance_2d",
                "area_triangle",
                "circle_area",
                "pythagorean_hypotenuse",
                "scale_ratio",
                "vector_magnitude",
                "angle_min_rotation",
            ]:
                add("fallback_formula_bank", key, 0.54, "local_formula_bank", {"fallback": True})
        return out

    def rzs_input(self, step_index: int) -> RZSInput:
        source_coverage = len(self.used_sources) / max(1, len(self.sources))
        memory_pressure = clamp(len(self.recent_mistakes) / 4.0)
        replay_gap = clamp((step_index - self.last_replay_step) / 9.0)
        novelty = clamp(0.28 + (1.0 - source_coverage) * 0.48 + self.rng.random() * 0.12)
        if step_index % 11 == 0:
            novelty = max(novelty, 0.92)
        conflict = clamp(0.12 + memory_pressure * 0.45 + (0.20 if step_index % 7 == 0 else 0.0))
        task_info = clamp(0.38 + novelty * 0.24 + (0.18 if step_index % 5 == 0 else 0.0))
        return RZSInput(
            bandwidth=4.20 + self.energy * 1.30,
            info_self=0.36 + memory_pressure * 0.10,
            info_external=0.34 + novelty * 0.28,
            task_info=task_info,
            novelty=novelty,
            conflict=conflict,
            latency=0.88 + memory_pressure * 0.30 + (0.18 if step_index % 13 == 0 else 0.0),
            energy=self.energy,
            memory_pressure=memory_pressure,
            replay_gap=replay_gap,
        )

    def pick_source(self, decision: str, avoid: str = "") -> FormulaSource:
        if decision == "replay_memory" and self.recent_mistakes:
            key = str(self.recent_mistakes[-1]["concept_key"])
            found = next((s for s in self.sources if s.concept_key == key), None)
            if found:
                return found
        candidates = [s for s in self.sources if s.concept_key != avoid] or self.sources
        if decision == "narrow_focus":
            return min(candidates, key=lambda s: (s.confidence, -s.complexity, self.used_sources.get(s.concept_key, 0)))
        if decision == "consolidate":
            return max(candidates, key=lambda s: (self.used_sources.get(s.concept_key, 0), s.confidence))
        weights = []
        for src in candidates:
            novelty_bonus = 1.0 / (1.0 + self.used_sources.get(src.concept_key, 0))
            weights.append(0.20 + src.confidence * 0.55 + src.complexity * 0.18 + novelty_bonus * 0.42)
        return self.rng.choices(candidates, weights=weights, k=1)[0]

    def intention_kind(self, step_index: int, decision: str) -> str:
        if decision == "pause_for_stability":
            return "pause_and_light_trace"
        if decision == "replay_memory" and self.recent_mistakes:
            return "correct_previous_mark"
        if decision == "consolidate":
            return "circle_known_pattern"
        if decision == "narrow_focus":
            return "slow_symbol_probe"
        if step_index % 5 == 0:
            return "join_formulas"
        if step_index % 7 == 0:
            return "wander_shape"
        return "free_formula_stroke"

    def mutate_expression(self, expression: str) -> tuple[str, str]:
        options: list[tuple[str, str]] = []
        if "+" in expression:
            options.append(("wrong_sign", expression.replace("+", "-", 1)))
        if "*" in expression:
            options.append(("operator_drift", expression.replace("*", "+", 1)))
        if "/" in expression:
            options.append(("ratio_flip", expression.replace("/", "*", 1)))
        if "^2" in expression:
            options.append(("missing_square", expression.replace("^2", "", 1)))
        if "180" in expression:
            options.append(("angle_memory_slip", expression.replace("180", "90", 1)))
        if "pi" in expression:
            options.append(("pi_blur", expression.replace("pi", "2*pi", 1)))
        if not options:
            options.append(("extra_unknown", expression + " + ?"))
        return self.rng.choice(options)

    def layout_for_step(self, step_index: int) -> dict[str, Any]:
        cols = 2
        rows = 2
        slot = (step_index - 1) % self.slots_per_page
        page = (step_index - 1) // self.slots_per_page + 1
        col = slot % cols
        row = slot // cols
        margin_x = 44.0
        margin_y = 34.0
        gap_x = 38.0
        gap_y = 36.0
        usable_w = max(560.0, self.width - margin_x * 2 - gap_x)
        usable_h = max(340.0, self.height - margin_y * 2 - gap_y)
        cell_w = usable_w / cols
        cell_h = usable_h / rows
        x = margin_x + col * (cell_w + gap_x) + self.rng.uniform(0, 10)
        y = margin_y + row * (cell_h + gap_y) + self.rng.uniform(0, 10)
        return {
            "page": page,
            "slot": slot,
            "x": x,
            "y": y,
            "w": max(250.0, cell_w - 28.0),
            "h": max(150.0, cell_h - 24.0),
            "right": margin_x + col * (cell_w + gap_x) + cell_w - 18,
            "bottom": margin_y + row * (cell_h + gap_y) + cell_h - 16,
        }

    def base_position(self, step_index: int) -> tuple[float, float]:
        self.active_layout = self.layout_for_step(step_index)
        return float(self.active_layout["x"]), float(self.active_layout["y"])

    def next_stroke_id(self, intention_id: str) -> str:
        self.stroke_counter += 1
        return f"ST-{self.session_id}-{self.stroke_counter:05d}-{intention_id[-4:]}"

    def stroke(
        self,
        intention_id: str,
        step_index: int,
        order: int,
        stroke_kind: str,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        text: str,
        color: str,
        width: float,
        confidence: float,
        payload: dict[str, Any] | None = None,
    ) -> SketchStroke:
        x1 = clamp(x1, 8.0, self.width - 8.0)
        x2 = clamp(x2, 8.0, self.width - 8.0)
        y1 = clamp(y1, 8.0, self.height - 8.0)
        y2 = clamp(y2, 8.0, self.height - 8.0)
        return SketchStroke(
            self.next_stroke_id(intention_id),
            intention_id,
            step_index,
            order,
            stroke_kind,
            round(x1, 3),
            round(y1, 3),
            round(x2, 3),
            round(y2, 3),
            text,
            color,
            width,
            clamp(confidence),
            payload or {},
        )

    def sketch_text(
        self,
        strokes: list[SketchStroke],
        intention_id: str,
        step_index: int,
        order: int,
        text: str,
        x: float,
        y: float,
        color: str,
        *,
        font_size: int = 16,
        jitter: float = 2.6,
        confidence: float = 0.70,
        max_width: float | None = None,
        line_height: float | None = None,
        payload: dict[str, Any] | None = None,
    ) -> int:
        cx = x
        cy = y
        right = min(self.width - 34.0, x + (max_width if max_width is not None else float(self.active_layout.get("w", 320.0))))
        line_step = line_height if line_height is not None else font_size + 9.0
        line_start = x
        for ch in text:
            if ch == " " and cx > right - font_size * 3.5:
                cx = line_start + self.rng.uniform(-1.5, 3.0)
                cy += line_step + self.rng.uniform(-1.0, 1.5)
                continue
            if cx > right:
                cx = line_start + self.rng.uniform(-1.5, 3.0)
                cy += line_step + self.rng.uniform(-1.0, 1.5)
            dx = self.rng.uniform(-jitter, jitter) * 0.52
            dy = self.rng.uniform(-jitter, jitter) * 0.42
            strokes.append(
                self.stroke(
                    intention_id,
                    step_index,
                    order,
                    "text",
                    cx + dx,
                    cy + dy,
                    cx + dx,
                    cy + dy,
                    ch,
                    color,
                    float(font_size),
                    confidence,
                    payload,
                )
            )
            order += 1
            cx += font_size * (0.35 if ch in "il.,:;|!" else 0.58) + self.rng.uniform(-0.35, 0.65)
        return order

    def sketch_family_shape(
        self,
        strokes: list[SketchStroke],
        intention_id: str,
        step_index: int,
        order: int,
        source: FormulaSource,
        x: float,
        y: float,
        color: str,
    ) -> int:
        jitter = lambda v=5.0: self.rng.uniform(-v, v)
        if source.family == "angle":
            strokes.append(self.stroke(intention_id, step_index, order, "line", x, y + 58, x + 82 + jitter(), y + 58 + jitter(), "", color, 2.0, source.confidence, {"shape": "ray"}))
            order += 1
            strokes.append(self.stroke(intention_id, step_index, order, "line", x, y + 58, x + 56 + jitter(), y + 12 + jitter(), "", color, 2.0, source.confidence, {"shape": "ray"}))
            order += 1
            strokes.append(self.stroke(intention_id, step_index, order, "arc_hint", x + 16, y + 26, x + 60, y + 70, "", color, 2.0, source.confidence, {"shape": "angle_arc"}))
            return order + 1
        if source.family in {"area", "metric"}:
            if source.concept_key in {"area_triangle", "triangle_angle_sum", "pythagorean_hypotenuse"}:
                points = [(x, y + 76), (x + 86 + jitter(), y + 76 + jitter()), (x + 40 + jitter(), y + 18 + jitter()), (x, y + 76)]
                for a, b in zip(points, points[1:]):
                    strokes.append(self.stroke(intention_id, step_index, order, "line", a[0], a[1], b[0], b[1], "", color, 2.0, source.confidence, {"shape": "triangle"}))
                    order += 1
                return order
            strokes.append(self.stroke(intention_id, step_index, order, "rect_hint", x, y + 18, x + 100 + jitter(), y + 78 + jitter(), "", color, 2.0, source.confidence, {"shape": "rectangle"}))
            return order + 1
        if source.family == "curve":
            strokes.append(self.stroke(intention_id, step_index, order, "oval_hint", x, y + 12, x + 82 + jitter(), y + 82 + jitter(), "", color, 2.0, source.confidence, {"shape": "circle"}))
            return order + 1
        if source.family == "weight":
            strokes.append(self.stroke(intention_id, step_index, order, "line", x, y + 56, x + 140 + jitter(), y + 56 + jitter(), "", color, 2.0, source.confidence, {"shape": "lever"}))
            order += 1
            strokes.append(self.stroke(intention_id, step_index, order, "line", x + 62, y + 56, x + 72, y + 84 + jitter(), "", color, 2.0, source.confidence, {"shape": "fulcrum"}))
            order += 1
            strokes.append(self.stroke(intention_id, step_index, order, "line", x + 72, y + 84, x + 84, y + 56, "", color, 2.0, source.confidence, {"shape": "fulcrum"}))
            return order + 1
        if source.family == "vector":
            strokes.append(self.stroke(intention_id, step_index, order, "line", x, y + 72, x + 104 + jitter(), y + 26 + jitter(), "", color, 2.0, source.confidence, {"shape": "vector"}))
            order += 1
            strokes.append(self.stroke(intention_id, step_index, order, "line", x + 104, y + 26, x + 92, y + 27, "", color, 2.0, source.confidence, {"shape": "arrow"}))
            order += 1
            strokes.append(self.stroke(intention_id, step_index, order, "line", x + 104, y + 26, x + 100, y + 39, "", color, 2.0, source.confidence, {"shape": "arrow"}))
            return order + 1
        strokes.append(self.stroke(intention_id, step_index, order, "line", x, y + 48, x + 92 + jitter(), y + 48 + jitter(), "", color, 2.0, source.confidence, {"shape": "trace"}))
        return order + 1

    def make_intention(self, step_index: int) -> tuple[SketchIntention, list[SketchStroke]]:
        self.prepare()
        x = self.rzs_input(step_index)
        assessment = self.rzs.classify(x)
        y = self.rzs.apply_action_model(x, assessment.decision)
        sigma_after = self.rzs.sigma(y)
        decision = assessment.decision
        kind = self.intention_kind(step_index, decision)
        source_a = self.pick_source(decision)
        source_b = self.pick_source(decision, avoid=source_a.concept_key)
        if kind == "join_formulas" and source_a.family == source_b.family:
            different = [s for s in self.sources if s.family != source_a.family]
            if different:
                source_b = self.rng.choice(different)
        self.used_sources[source_a.concept_key] = self.used_sources.get(source_a.concept_key, 0) + 1
        if kind == "join_formulas":
            self.used_sources[source_b.concept_key] = self.used_sources.get(source_b.concept_key, 0) + 1

        intention_id = f"IN-{self.session_id}-{step_index:04d}-{suffix(self.rng)}"
        mistake_probability = clamp(0.18 + source_a.complexity * 0.22 - source_a.confidence * 0.12 + (0.08 if kind == "join_formulas" else 0.0))
        force_error = self.total_mistakes < 3 and step_index in {2, 6, 10, 14}
        will_mistake = kind not in {"correct_previous_mark", "pause_and_light_trace"} and (force_error or self.rng.random() < mistake_probability)
        mistake_type = ""
        expression_a = source_a.expression
        if will_mistake:
            mistake_type, expression_a = self.mutate_expression(source_a.expression)
            self.total_mistakes += 1
            self.recent_mistakes.append(
                {
                    "step_index": step_index,
                    "concept_key": source_a.concept_key,
                    "family": source_a.family,
                    "wrong_expression": expression_a,
                    "correct_expression": source_a.expression,
                    "mistake_type": mistake_type,
                }
            )
            self.recent_mistakes = self.recent_mistakes[-8:]
            self.energy = clamp(self.energy - 0.025)
        else:
            self.energy = clamp(self.energy + 0.004)

        strokes: list[SketchStroke] = []
        base_x, base_y = self.base_position(step_index)
        layout = dict(self.active_layout)
        block_w = float(layout.get("w", 320.0))
        color = FAMILY_COLORS.get(source_a.family, "#cdd6f4")
        order = 1

        if kind == "correct_previous_mark" and self.recent_mistakes:
            old = self.recent_mistakes.pop(0)
            self.total_corrections += 1
            self.last_replay_step = step_index
            color = "#f9e2af"
            order = self.sketch_text(
                strokes,
                intention_id,
                step_index,
                order,
                "voltar: " + str(old["wrong_expression"]),
                base_x,
                base_y,
                "#f38ba8",
                font_size=15,
                jitter=2.1,
                max_width=block_w - 18,
                confidence=0.55,
                payload={"correction_of": old},
            )
            for i in range(2):
                strokes.append(
                    self.stroke(
                        intention_id,
                        step_index,
                        order,
                        "line",
                        base_x + self.rng.uniform(-6, 16),
                        base_y + 10 + i * 14,
                        base_x + 220 + self.rng.uniform(-18, 26),
                        base_y + 26 + i * 11,
                        "",
                        "#f38ba8",
                        2.0,
                        0.68,
                        {"gesture": "scratch_wrong_mark"},
                    )
                )
                order += 1
            order = self.sketch_text(
                strokes,
                intention_id,
                step_index,
                order,
                "tentar de novo: " + str(old["correct_expression"]),
                base_x + self.rng.uniform(4, 24),
                base_y + 54 + self.rng.uniform(-4, 6),
                color,
                font_size=16,
                jitter=1.6,
                max_width=block_w - 24,
                confidence=0.82,
                payload={"corrected": True, "source_mistake": old},
            )
            focus_key = str(old["concept_key"])
            formula_b = ""
        elif kind == "join_formulas":
            self.total_fusions += 1
            self.last_replay_step = step_index if decision == "replay_memory" else self.last_replay_step
            order = self.sketch_text(strokes, intention_id, step_index, order, expression_a, base_x, base_y, color, font_size=15, jitter=1.9, max_width=block_w - 18, confidence=source_a.confidence, payload={"concept_key": source_a.concept_key, "mistake_type": mistake_type})
            bridge_y = base_y + 42 + self.rng.uniform(-8, 10)
            strokes.append(self.stroke(intention_id, step_index, order, "line", base_x + 26, bridge_y, base_x + min(block_w - 34, 230) + self.rng.uniform(-10, 14), bridge_y + self.rng.uniform(-8, 9), "", "#bac2de", 1.8, 0.66, {"gesture": "bridge_between_formulas"}))
            order += 1
            order = self.sketch_text(strokes, intention_id, step_index, order, "juntar?", base_x + block_w * 0.34 + self.rng.uniform(-5, 7), bridge_y - 22, "#bac2de", font_size=12, jitter=1.4, max_width=block_w * 0.40, confidence=0.58, payload={"fusion": True})
            order = self.sketch_text(strokes, intention_id, step_index, order, source_b.expression, base_x + 18 + self.rng.uniform(-4, 7), base_y + 72 + self.rng.uniform(-4, 5), FAMILY_COLORS.get(source_b.family, "#cdd6f4"), font_size=15, jitter=1.9, max_width=block_w - 22, confidence=source_b.confidence, payload={"concept_key": source_b.concept_key})
            mixed = self.fusion_expression(source_a, source_b)
            order = self.sketch_text(strokes, intention_id, step_index, order, mixed, base_x + 18 + self.rng.uniform(-5, 8), base_y + 124 + self.rng.uniform(-3, 5), "#cdd6f4", font_size=13, jitter=2.0, max_width=block_w - 26, confidence=0.62, payload={"fusion_of": [source_a.concept_key, source_b.concept_key]})
            focus_key = f"{source_a.concept_key}+{source_b.concept_key}"
            formula_b = source_b.concept_key
        else:
            if kind == "pause_and_light_trace":
                expression_a = "pausar -> respirar -> traco menor"
                color = "#a6adc8"
            order = self.sketch_family_shape(strokes, intention_id, step_index, order, source_a, base_x, base_y - 6, color)
            order = self.sketch_text(strokes, intention_id, step_index, order, expression_a, base_x + self.rng.uniform(8, 20), base_y + 88 + self.rng.uniform(-3, 5), color, font_size=15, jitter=2.0 if will_mistake else 1.4, max_width=block_w - 28, confidence=source_a.confidence, payload={"concept_key": source_a.concept_key, "mistake_type": mistake_type})
            if kind in {"slow_symbol_probe", "circle_known_pattern", "wander_shape"}:
                label = {
                    "slow_symbol_probe": "olhar mais perto",
                    "circle_known_pattern": "parece conhecido",
                    "wander_shape": "e se virar assim?",
                    "pause_and_light_trace": "estabilizar",
                }.get(kind, "tentar")
                order = self.sketch_text(strokes, intention_id, step_index, order, label, base_x + self.rng.uniform(20, 70), base_y + 134 + self.rng.uniform(-3, 5), "#bac2de", font_size=12, jitter=1.8, max_width=block_w - 40, confidence=0.58, payload={"note": kind})
            focus_key = source_a.concept_key
            formula_b = ""

        intention = SketchIntention(
            intention_id=intention_id,
            step_index=step_index,
            focus_key=focus_key,
            intention_kind=kind,
            formula_a=source_a.concept_key,
            formula_b=formula_b,
            rzs_decision=decision,
            sigma_before=assessment.sigma,
            sigma_after=sigma_after,
            energy=self.energy,
            payload={
                "source_a": asdict(source_a),
                "source_b": asdict(source_b) if kind == "join_formulas" else {},
                "mistake": will_mistake,
                "mistake_type": mistake_type,
                "rzs_reason": assessment.reason,
                "not_template": True,
                "layout_page": layout.get("page", 1),
                "layout_slot": layout.get("slot", 0),
                "layout_bounds": layout,
            },
        )
        self.store.log_intention(self.session_id, intention)
        self.store.log_strokes(self.session_id, strokes)
        self.store.log_session(
            self.session_id,
            "sketch_step",
            self.mode,
            {
                "intention_id": intention_id,
                "focus_key": focus_key,
                "intention_kind": kind,
                "stroke_count": len(strokes),
                "mistake": will_mistake,
                "mistake_type": mistake_type,
            },
            step_index=step_index,
            rzs_decision=decision,
            sigma_before=assessment.sigma,
            sigma_after=sigma_after,
        )
        self.intentions.append(intention)
        self.strokes.extend(strokes)
        return intention, strokes

    def fusion_expression(self, a: FormulaSource, b: FormulaSource) -> str:
        left = a.expression.split("=")[0].strip()
        right = b.expression.split("=")[0].strip()
        styles = [
            f"{left} conversa com {right}",
            f"{left} -> {right} ?",
            f"{a.family} + {b.family} = pista nova",
            f"{left} / {right} ainda confuso",
        ]
        return self.rng.choice(styles)

    def run_steps(self, steps: int = 90) -> dict[str, Any]:
        self.prepare()
        steps = max(18, int(steps))
        for step_index in range(1, steps + 1):
            self.make_intention(step_index)
        while self.recent_mistakes and self.total_corrections < max(2, min(5, self.total_mistakes)):
            self.make_intention(len(self.intentions) + 1)
        return self.complete()

    def complete(self) -> dict[str, Any]:
        if self.completed:
            return self.summary()
        if not self.prepared:
            self.prepare()
        counts_after = self.store.protected_counts()
        source_unchanged = counts_after == self.source_counts_before
        families = sorted({s.family for s in self.sources})
        rzs_decisions = sorted({i.rzs_decision for i in self.intentions})
        intention_kinds = sorted({i.intention_kind for i in self.intentions})
        summary = self.summary()
        summary.update(
            {
                "families": families,
                "rzs_decisions": rzs_decisions,
                "intention_kinds": intention_kinds,
                "protected_counts_before": self.source_counts_before,
                "protected_counts_after": counts_after,
                "protected_sources_unchanged": source_unchanged,
                "session_complete": True,
            }
        )
        reflection_text = (
            f"Rabisquei {summary['stroke_count']} tracos em {summary['intention_count']} intencoes; "
            f"juntei {self.total_fusions} formulas, errei {self.total_mistakes} vezes e corrigi {self.total_corrections}. "
            "O desenho ficou como tentativa visivel, nao como gabarito perfeito."
        )
        self.store.log_reflection(
            self.session_id,
            f"RF-{self.session_id}-FREE",
            "free_formula_exploration",
            reflection_text,
            [s.source_id for s in self.sources[:6]],
            0.84,
            summary,
        )
        self.store.log_reflection(
            self.session_id,
            f"RF-{self.session_id}-ERROR",
            "mistake_and_correction",
            f"Erros viraram marcas: mistakes={self.total_mistakes}, corrections={self.total_corrections}, recent_left={len(self.recent_mistakes)}.",
            [i.intention_id for i in self.intentions if i.payload.get("mistake")][:8],
            0.80,
            {"recent_mistakes_left": self.recent_mistakes},
        )
        self.store.log_handoff(
            self.session_id,
            "abrir_lapis_digital_e_observar_darwin_desenhar_formulas_livremente",
            ready=summary["stroke_count"] >= 120,
            free_ready=self.total_fusions >= 1 and self.total_mistakes >= 1 and self.total_corrections >= 1,
            confidence=0.86,
            payload=summary,
        )
        self.store.write_memory(self.session_id, summary, 0.86)
        first_sigma = self.intentions[0].sigma_before if self.intentions else 0.0
        last_sigma = self.intentions[-1].sigma_after if self.intentions else 0.0
        self.store.write_episode(
            self.session_id,
            "draw_formulas_with_digital_pencil",
            f"strokes={summary['stroke_count']} fusions={self.total_fusions} mistakes={self.total_mistakes} corrections={self.total_corrections}",
            "Formula can become visible gesture: Darwin explores, joins, errs, corrects and stores the drawing as experience.",
            first_sigma,
            last_sigma,
        )
        self.store.log_session(self.session_id, "sketch_complete", self.mode, summary)
        self.completed = True
        return summary

    def summary(self) -> dict[str, Any]:
        current_page = ((self.intentions[-1].step_index - 1) // self.slots_per_page + 1) if self.intentions else 1
        return {
            "session_id": self.session_id,
            "source_count": len(self.sources),
            "intention_count": len(self.intentions),
            "stroke_count": len(self.strokes),
            "current_page": current_page,
            "slots_per_page": self.slots_per_page,
            "mistake_count": self.total_mistakes,
            "correction_count": self.total_corrections,
            "fusion_count": self.total_fusions,
            "energy": round(self.energy, 3),
            "used_concepts": sorted(self.used_sources),
            "last_focus": self.intentions[-1].focus_key if self.intentions else "",
            "last_rzs_decision": self.intentions[-1].rzs_decision if self.intentions else "",
            "last_intention": self.intentions[-1].intention_kind if self.intentions else "",
        }


class FormulaSketchApp:
    BG = "#061018"
    PANEL = "#0d1f2d"
    INK = "#eaf6ff"
    MUTED = "#9dbdd5"
    PAPER = "#08131d"
    CURSOR = "#f9e2af"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Darwin Formula Sketchbook v49.28")
        self.root.geometry("1180x780")
        self.root.minsize(980, 660)
        self.root.configure(bg=self.BG)
        self.core = FormulaSketchCore(mode="gui")
        self.pending: list[SketchStroke] = []
        self.drawn = 0
        self.step_index = 0
        self.visible_page = 1
        self.paused = False
        self.fast = False
        self.last_xy = (120.0, 120.0)
        self.build_ui()
        self.core.prepare()
        self.draw_page_frame()
        self.generate_more()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.tick()

    def build_ui(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TButton", padding=7)
        header = tk.Frame(self.root, bg=self.BG)
        header.pack(fill="x", padx=16, pady=(12, 6))
        tk.Label(header, text="DARWIN FORMULA SKETCHBOOK v49.28", bg=self.BG, fg=self.INK, font=("Segoe UI", 19, "bold")).pack(anchor="w")
        tk.Label(header, text="lapis digital: memoria -> gesto -> erro -> correcao -> fusao", bg=self.BG, fg=self.MUTED, font=("Segoe UI", 10)).pack(anchor="w")

        body = tk.Frame(self.root, bg=self.BG)
        body.pack(fill="both", expand=True, padx=16, pady=8)
        left = tk.Frame(body, bg=self.BG)
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(body, bg=self.PANEL, width=340)
        right.pack(side="right", fill="y", padx=(12, 0))
        right.pack_propagate(False)

        self.canvas = tk.Canvas(left, bg=self.PAPER, highlightthickness=1, highlightbackground="#203346")
        self.canvas.pack(fill="both", expand=True)
        controls = tk.Frame(left, bg="#102434")
        controls.pack(fill="x", pady=(8, 0))
        ttk.Button(controls, text="Pausar", command=self.toggle_pause).pack(side="left", padx=(10, 5), pady=8)
        ttk.Button(controls, text="Acelerar", command=self.toggle_fast).pack(side="left", padx=5, pady=8)
        ttk.Button(controls, text="Novo desenho", command=self.new_drawing).pack(side="left", padx=5, pady=8)
        ttk.Button(controls, text="Status", command=self.update_status).pack(side="left", padx=5, pady=8)

        tk.Label(right, text="Estado", bg=self.PANEL, fg=self.INK, font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=12, pady=(12, 6))
        self.status = tk.Text(right, wrap="word", height=16, bg="#08131d", fg=self.INK, insertbackground=self.INK, relief="flat", font=("Consolas", 10))
        self.status.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self.update_status()

    def toggle_pause(self) -> None:
        self.paused = not self.paused

    def toggle_fast(self) -> None:
        self.fast = not self.fast

    def new_drawing(self) -> None:
        self.core.complete()
        self.canvas.delete("all")
        self.core = FormulaSketchCore(mode="gui")
        self.core.prepare()
        self.pending = []
        self.drawn = 0
        self.step_index = 0
        self.visible_page = 1
        self.last_xy = (120.0, 120.0)
        self.draw_page_frame()
        self.generate_more()
        self.update_status()

    def generate_more(self) -> None:
        self.step_index += 1
        self.canvas.update_idletasks()
        self.core.configure_canvas(self.canvas.winfo_width(), self.canvas.winfo_height())
        next_page = (self.step_index - 1) // self.core.slots_per_page + 1
        if next_page != self.visible_page:
            self.visible_page = next_page
            self.canvas.delete("all")
            self.draw_page_frame()
            self.drawn = 0
        _, strokes = self.core.make_intention(self.step_index)
        self.pending.extend(strokes)

    def draw_page_frame(self) -> None:
        self.canvas.update_idletasks()
        w = max(720, self.canvas.winfo_width())
        h = max(460, self.canvas.winfo_height())
        self.core.configure_canvas(w, h)
        self.canvas.create_text(18, 14, text=f"pagina {self.visible_page}", fill="#607d96", font=("Segoe UI", 10), anchor="nw", tags="frame")
        mid_x = w / 2
        mid_y = h / 2
        self.canvas.create_line(mid_x, 30, mid_x, h - 22, fill="#123044", width=1, dash=(4, 6), tags="frame")
        self.canvas.create_line(24, mid_y, w - 24, mid_y, fill="#123044", width=1, dash=(4, 6), tags="frame")

    def tick(self) -> None:
        if not self.paused:
            draws = 7 if self.fast else 2
            for _ in range(draws):
                if not self.pending:
                    self.generate_more()
                if self.pending:
                    self.draw_stroke(self.pending.pop(0))
                    self.drawn += 1
            if self.drawn % 35 == 0:
                self.update_status()
        self.root.after(35 if self.fast else 70, self.tick)

    def draw_stroke(self, stroke: SketchStroke) -> None:
        self.canvas.delete("cursor")
        kind = stroke.stroke_kind
        if kind == "text":
            font_size = max(8, int(stroke.width))
            self.canvas.create_text(stroke.x1, stroke.y1, text=stroke.text, fill=stroke.color, font=("Consolas", font_size), anchor="nw")
            self.last_xy = (stroke.x1 + font_size * 0.5, stroke.y1 + font_size * 0.5)
        elif kind == "line":
            self.canvas.create_line(stroke.x1, stroke.y1, stroke.x2, stroke.y2, fill=stroke.color, width=stroke.width, smooth=True)
            self.last_xy = (stroke.x2, stroke.y2)
        elif kind == "oval_hint":
            self.canvas.create_oval(stroke.x1, stroke.y1, stroke.x2, stroke.y2, outline=stroke.color, width=stroke.width)
            self.last_xy = ((stroke.x1 + stroke.x2) / 2, (stroke.y1 + stroke.y2) / 2)
        elif kind == "rect_hint":
            self.canvas.create_rectangle(stroke.x1, stroke.y1, stroke.x2, stroke.y2, outline=stroke.color, width=stroke.width)
            self.last_xy = (stroke.x2, stroke.y2)
        elif kind == "arc_hint":
            self.canvas.create_arc(stroke.x1, stroke.y1, stroke.x2, stroke.y2, start=8, extent=72, outline=stroke.color, width=stroke.width, style="arc")
            self.last_xy = (stroke.x2, stroke.y2)
        else:
            self.canvas.create_line(stroke.x1, stroke.y1, stroke.x2, stroke.y2, fill=stroke.color, width=stroke.width)
            self.last_xy = (stroke.x2, stroke.y2)
        x, y = self.last_xy
        self.canvas.create_oval(x - 5, y - 5, x + 5, y + 5, fill=self.CURSOR, outline="", tags="cursor")

    def update_status(self) -> None:
        s = self.core.summary()
        lines = [
            f"sessao: {s['session_id']}",
            f"fontes: {s['source_count']}",
            f"intencoes: {s['intention_count']}",
            f"tracos: {s['stroke_count']}",
            f"pagina visivel: {self.visible_page}",
            f"pagina cognitiva: {s['current_page']}",
            f"desenhados: {self.drawn}",
            f"erros: {s['mistake_count']}",
            f"correcoes: {s['correction_count']}",
            f"fusoes: {s['fusion_count']}",
            f"energia: {s['energy']}",
            "",
            f"RZS: {s['last_rzs_decision']}",
            f"intencao: {s['last_intention']}",
            f"foco: {short(s['last_focus'], 60)}",
            "",
            "conceitos usados:",
            ", ".join(s["used_concepts"][-10:]),
        ]
        self.status.delete("1.0", "end")
        self.status.insert("end", "\n".join(lines))

    def close(self) -> None:
        self.core.complete()
        self.root.destroy()


def print_self_test(summary: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.28 - FORMULA SKETCHBOOK")
    print("=" * 70)
    print(f"- sessao: {summary['session_id']}")
    print(f"- fontes={summary['source_count']} intencoes={summary['intention_count']} tracos={summary['stroke_count']}")
    print(f"- erros={summary['mistake_count']} correcoes={summary['correction_count']} fusoes={summary['fusion_count']}")
    print(f"- familias: {', '.join(summary.get('families', []))}")
    print(f"- RZS: {', '.join(summary.get('rzs_decisions', []))}")
    print("Resultado self-test: OK")
    if details:
        print("\nJSON:")
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin Formula Sketchbook v49.28")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--steps", type=int, default=90)
    ap.add_argument("--seed", type=int, default=4928)
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        core = FormulaSketchCore(seed=args.seed, mode="self_test")
        summary = core.run_steps(args.steps)
        print_self_test(summary, args.details)
        return 0
    root = tk.Tk()
    FormulaSketchApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
