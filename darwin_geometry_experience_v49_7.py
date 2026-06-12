from __future__ import annotations

"""
DARWIN v49.7 - Geometria como experiencia relacional

Objetivo:
Ensinar fundamentos geometricos ao Darwin como ciclo de experiencia:
- pesos numericos e pesos de aprendizagem;
- angulos, distancias, areas, simetrias, vetores e proporcoes;
- tentativa com erro controlado;
- correcao e replay;
- nos de experiencia gravados em SQLite;
- regulacao obrigatoria pelo RZS.

Uso:
    py darwin_geometry_experience_v49_7.py
    py darwin_geometry_experience_v49_7.py --cycles 96 --details
"""

import argparse
import json
import math
import random
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from darwin_rzs_nervous_system_v49_3 import RZSFormal, RZSInput


DB = Path("darwin_home") / "darwin.db"

SCENARIOS = "geometry_learning_scenarios_v49_7"
CONCEPTS = "geometry_concepts_v49_7"
NODES = "geometry_experience_nodes_v49_7"
EDGES = "geometry_experience_edges_v49_7"
WEIGHTS = "geometry_learning_weights_v49_7"
REPLAYS = "geometry_error_replay_v49_7"

SOURCE_ANGLE = "geometry_measure_curriculum_v48_6"
SOURCE_PLAN = "geometry_multistep_plans_v48_9"
SOURCE_RZS_STRESS = "rzs_stress_tests_v49_3"
SOURCE_RZS_GOV = "brain_rzs_governed_cycles_v49_4"
SOURCE_RZS_PLASTICITY = "rzs_plasticity_cycles_v49_5"
PROTECTED_SOURCE_TABLES = [
    SOURCE_ANGLE,
    SOURCE_PLAN,
    SOURCE_RZS_STRESS,
    SOURCE_RZS_GOV,
    SOURCE_RZS_PLASTICITY,
]

PHASES = [
    "geometry_start",
    "source_memory_read",
    "curriculum_seed",
    "experience_cycle",
    "error_replay",
    "concept_consolidation",
    "geometry_complete",
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


def mean(values: list[float]) -> float:
    return sum(values) / max(1, len(values))


def min_rotation(angle: float, target: float, symmetry: float) -> float:
    d = (target - angle) % symmetry
    if d > symmetry / 2:
        d -= symmetry
    return round(d, 4)


@dataclass(frozen=True)
class ConceptSpec:
    concept_key: str
    family: str
    definition: str
    answer_kind: str
    tolerance: float
    complexity: float
    prerequisites: tuple[str, ...]


@dataclass
class ConceptState:
    spec: ConceptSpec
    learning_weight: float
    confidence: float
    bias: float
    exposure_count: int = 0
    error_count: int = 0
    inherited_from: str = ""


@dataclass
class AttemptResult:
    node_id: str
    cycle_id: int
    concept_key: str
    family: str
    task_kind: str
    prompt: dict[str, Any]
    expected_value: float
    predicted_value: float
    absolute_error: float
    normalized_error: float
    verdict: str
    cognitive_action: str
    learning_weight_before: float
    learning_weight_after: float
    confidence_before: float
    confidence_after: float
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    experience_weight: float


def curriculum() -> list[ConceptSpec]:
    return [
        ConceptSpec("angle_min_rotation", "angle", "menor rotacao modular entre angulo atual e alvo", "degrees", 2.5, 0.72, ()),
        ConceptSpec("angle_complement", "angle", "angulo que completa 90 graus", "degrees", 1.5, 0.50, ()),
        ConceptSpec("angle_supplement", "angle", "angulo que completa 180 graus", "degrees", 1.5, 0.52, ()),
        ConceptSpec("triangle_angle_sum", "angle", "terceiro angulo pela soma interna de triangulo", "degrees", 1.5, 0.68, ("angle_supplement",)),
        ConceptSpec("polygon_exterior_angle", "angle", "angulo externo regular igual a 360/n", "degrees", 1.0, 0.62, ("angle_min_rotation",)),
        ConceptSpec("symmetry_rotation", "transformation", "rotacao minima de simetria regular igual a 360/n", "degrees", 1.0, 0.63, ("polygon_exterior_angle",)),
        ConceptSpec("distance_2d", "metric", "distancia euclidiana entre dois pontos", "units", 0.12, 0.76, ()),
        ConceptSpec("slope_2d", "metric", "inclinacao dy/dx de uma reta", "ratio", 0.08, 0.70, ("distance_2d",)),
        ConceptSpec("perimeter_rectangle", "metric", "perimetro de retangulo 2w+2h", "units", 0.08, 0.48, ()),
        ConceptSpec("area_rectangle", "area", "area de retangulo w*h", "square_units", 0.12, 0.50, ("perimeter_rectangle",)),
        ConceptSpec("area_triangle", "area", "area de triangulo b*h/2", "square_units", 0.12, 0.54, ("area_rectangle",)),
        ConceptSpec("circle_circumference", "curve", "comprimento de circunferencia 2*pi*r", "units", 0.16, 0.58, ()),
        ConceptSpec("circle_area", "area", "area de circulo pi*r^2", "square_units", 0.20, 0.62, ("circle_circumference",)),
        ConceptSpec("pythagorean_hypotenuse", "metric", "hipotenusa pela raiz de a^2+b^2", "units", 0.12, 0.74, ("distance_2d",)),
        ConceptSpec("vector_magnitude", "vector", "magnitude de vetor pela norma euclidiana", "units", 0.12, 0.72, ("distance_2d",)),
        ConceptSpec("scale_ratio", "transformation", "razao de escala entre medida original e transformada", "ratio", 0.06, 0.60, ()),
        ConceptSpec("similar_triangle_height", "transformation", "altura transferida por semelhanca de triangulos", "units", 0.10, 0.72, ("scale_ratio", "triangle_angle_sum")),
        ConceptSpec("weighted_centroid_1d", "weight", "centro ponderado em uma dimensao", "units", 0.10, 0.78, ()),
        ConceptSpec("weighted_centroid_2d_x", "weight", "coordenada x de centroide ponderado 2D", "units", 0.12, 0.82, ("weighted_centroid_1d",)),
        ConceptSpec("lever_balance_torque", "weight", "torque como peso vezes braco de alavanca", "torque", 0.16, 0.80, ("weighted_centroid_1d",)),
    ]


class GeometryStore:
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
                CREATE TABLE IF NOT EXISTS {SCENARIOS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    cycle_id INTEGER NOT NULL DEFAULT 0,
                    rzs_decision TEXT NOT NULL DEFAULT '',
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {CONCEPTS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    concept_key TEXT NOT NULL,
                    family TEXT NOT NULL,
                    definition TEXT NOT NULL,
                    answer_kind TEXT NOT NULL,
                    tolerance REAL NOT NULL,
                    complexity REAL NOT NULL,
                    learning_weight REAL NOT NULL,
                    confidence REAL NOT NULL,
                    bias REAL NOT NULL,
                    exposure_count INTEGER NOT NULL DEFAULT 0,
                    error_count INTEGER NOT NULL DEFAULT 0,
                    inherited_from TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}',
                    UNIQUE(scenario_id, concept_key)
                );

                CREATE TABLE IF NOT EXISTS {NODES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    node_id TEXT NOT NULL UNIQUE,
                    cycle_id INTEGER NOT NULL,
                    concept_key TEXT NOT NULL,
                    family TEXT NOT NULL,
                    task_kind TEXT NOT NULL,
                    prompt_json TEXT NOT NULL DEFAULT '{{}}',
                    expected_value REAL NOT NULL,
                    predicted_value REAL NOT NULL,
                    absolute_error REAL NOT NULL,
                    normalized_error REAL NOT NULL,
                    verdict TEXT NOT NULL,
                    cognitive_action TEXT NOT NULL,
                    learning_weight_before REAL NOT NULL,
                    learning_weight_after REAL NOT NULL,
                    confidence_before REAL NOT NULL,
                    confidence_after REAL NOT NULL,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL,
                    sigma_after REAL NOT NULL,
                    experience_weight REAL NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {EDGES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    from_node_id TEXT NOT NULL,
                    to_node_id TEXT NOT NULL,
                    edge_kind TEXT NOT NULL,
                    strength REAL NOT NULL,
                    reason TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {WEIGHTS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    cycle_id INTEGER NOT NULL,
                    concept_key TEXT NOT NULL,
                    weight_before REAL NOT NULL,
                    weight_after REAL NOT NULL,
                    confidence_before REAL NOT NULL,
                    confidence_after REAL NOT NULL,
                    error_signal REAL NOT NULL,
                    learning_rate REAL NOT NULL,
                    update_reason TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {REPLAYS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    replay_id TEXT NOT NULL UNIQUE,
                    cycle_id INTEGER NOT NULL,
                    source_node_id TEXT NOT NULL,
                    concept_key TEXT NOT NULL,
                    error_before REAL NOT NULL,
                    error_after REAL NOT NULL,
                    correction_applied REAL NOT NULL,
                    confidence_after REAL NOT NULL,
                    learning_weight_after REAL NOT NULL,
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

    def latest_scenario(self, table: str, scenario_column: str = "scenario_id") -> str:
        with self.connect() as conn:
            if not self.table_exists(conn, table):
                return ""
            row = conn.execute(
                f"SELECT {scenario_column} AS scenario_id FROM {table} WHERE {scenario_column} <> '' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            return str(row["scenario_id"]) if row else ""

    def latest_prior_concept(self, concept_key: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                f"""
                SELECT * FROM {CONCEPTS}
                WHERE concept_key=?
                ORDER BY id DESC
                LIMIT 1
                """,
                (concept_key,),
            ).fetchone()
            if not row:
                return None
            return {k: row[k] for k in row.keys()}

    def log_event(
        self,
        scenario_id: str,
        phase: str,
        payload: dict[str, Any],
        *,
        cycle_id: int = 0,
        rzs_decision: str = "",
        sigma_before: float = 0.0,
        sigma_after: float = 0.0,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {SCENARIOS} (
                    timestamp, scenario_id, phase, cycle_id, rzs_decision,
                    sigma_before, sigma_after, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), scenario_id, phase, cycle_id, rzs_decision, sigma_before, sigma_after, js(payload)),
            )
            conn.commit()

    def upsert_concept(self, scenario_id: str, state: ConceptState, payload: dict[str, Any] | None = None) -> None:
        spec = state.spec
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {CONCEPTS} (
                    timestamp, scenario_id, concept_key, family, definition,
                    answer_kind, tolerance, complexity, learning_weight,
                    confidence, bias, exposure_count, error_count,
                    inherited_from, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scenario_id, concept_key) DO UPDATE SET
                    timestamp=excluded.timestamp,
                    learning_weight=excluded.learning_weight,
                    confidence=excluded.confidence,
                    bias=excluded.bias,
                    exposure_count=excluded.exposure_count,
                    error_count=excluded.error_count,
                    payload_json=excluded.payload_json
                """,
                (
                    now(),
                    scenario_id,
                    spec.concept_key,
                    spec.family,
                    spec.definition,
                    spec.answer_kind,
                    spec.tolerance,
                    spec.complexity,
                    state.learning_weight,
                    state.confidence,
                    state.bias,
                    state.exposure_count,
                    state.error_count,
                    state.inherited_from,
                    js(payload or {"prerequisites": list(spec.prerequisites)}),
                ),
            )
            conn.commit()

    def log_node(self, scenario_id: str, result: AttemptResult, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {NODES} (
                    timestamp, scenario_id, node_id, cycle_id, concept_key,
                    family, task_kind, prompt_json, expected_value,
                    predicted_value, absolute_error, normalized_error, verdict,
                    cognitive_action, learning_weight_before, learning_weight_after,
                    confidence_before, confidence_after, rzs_decision,
                    sigma_before, sigma_after, experience_weight, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    scenario_id,
                    result.node_id,
                    result.cycle_id,
                    result.concept_key,
                    result.family,
                    result.task_kind,
                    js(result.prompt),
                    result.expected_value,
                    result.predicted_value,
                    result.absolute_error,
                    result.normalized_error,
                    result.verdict,
                    result.cognitive_action,
                    result.learning_weight_before,
                    result.learning_weight_after,
                    result.confidence_before,
                    result.confidence_after,
                    result.rzs_decision,
                    result.sigma_before,
                    result.sigma_after,
                    result.experience_weight,
                    js(payload),
                ),
            )
            conn.commit()

    def log_edge(self, scenario_id: str, from_node_id: str, to_node_id: str, edge_kind: str, strength: float, reason: str, payload: dict[str, Any]) -> None:
        if not from_node_id or not to_node_id or from_node_id == to_node_id:
            return
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {EDGES} (
                    timestamp, scenario_id, from_node_id, to_node_id,
                    edge_kind, strength, reason, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), scenario_id, from_node_id, to_node_id, edge_kind, clamp(strength), reason, js(payload)),
            )
            conn.commit()

    def log_weight_update(
        self,
        scenario_id: str,
        cycle_id: int,
        concept_key: str,
        weight_before: float,
        weight_after: float,
        confidence_before: float,
        confidence_after: float,
        error_signal: float,
        learning_rate: float,
        update_reason: str,
        payload: dict[str, Any],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {WEIGHTS} (
                    timestamp, scenario_id, cycle_id, concept_key, weight_before,
                    weight_after, confidence_before, confidence_after,
                    error_signal, learning_rate, update_reason, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    scenario_id,
                    cycle_id,
                    concept_key,
                    weight_before,
                    weight_after,
                    confidence_before,
                    confidence_after,
                    error_signal,
                    learning_rate,
                    update_reason,
                    js(payload),
                ),
            )
            conn.commit()

    def log_replay(
        self,
        scenario_id: str,
        replay_id: str,
        cycle_id: int,
        source_node_id: str,
        concept_key: str,
        error_before: float,
        error_after: float,
        correction_applied: float,
        confidence_after: float,
        learning_weight_after: float,
        payload: dict[str, Any],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {REPLAYS} (
                    timestamp, scenario_id, replay_id, cycle_id, source_node_id,
                    concept_key, error_before, error_after, correction_applied,
                    confidence_after, learning_weight_after, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    scenario_id,
                    replay_id,
                    cycle_id,
                    source_node_id,
                    concept_key,
                    error_before,
                    error_after,
                    correction_applied,
                    confidence_after,
                    learning_weight_after,
                    js(payload),
                ),
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
                (key, content, clamp(confidence, 0.0, 0.99), "darwin_geometry_experience_v49_7", now()),
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
                (
                    now(),
                    "darwin_geometry_experience_v49_7",
                    context,
                    action,
                    outcome,
                    lesson,
                    sigma_before,
                    sigma_after,
                ),
            )
            conn.commit()


class GeometryExperienceLearner:
    def __init__(self, seed: int | None = None) -> None:
        self.store = GeometryStore()
        self.rzs = RZSFormal()
        self.rng = random.Random(seed if seed is not None else 4970)
        self.scenario_id = f"V497-{int(time.time()) % 10_000_000}-{suffix(self.rng)}"
        self.source_counts_before = self.store.protected_counts()
        self.source_angle = self.store.latest_scenario(SOURCE_ANGLE)
        self.source_plans = self.store.latest_scenario(SOURCE_PLAN)
        self.source_homeostasis = self.store.latest_scenario(SOURCE_RZS_PLASTICITY)
        self.energy = 0.86
        self.last_replay_cycle = 0
        self.last_node_id = ""
        self.last_by_concept: dict[str, str] = {}
        self.recent_errors: list[AttemptResult] = []
        self.all_results: list[AttemptResult] = []
        self.replay_count = 0
        self.concepts = self.seed_concepts()

    def seed_concepts(self) -> dict[str, ConceptState]:
        states: dict[str, ConceptState] = {}
        for index, spec in enumerate(curriculum()):
            prior = self.store.latest_prior_concept(spec.concept_key)
            base_weight = clamp(0.32 + (1.0 - spec.complexity) * 0.12, 0.24, 0.48)
            base_confidence = clamp(0.16 + (1.0 - spec.complexity) * 0.10, 0.12, 0.32)
            inherited_from = ""
            if prior:
                base_weight = clamp(float(prior["learning_weight"]) * 0.86 + 0.06, 0.24, 0.78)
                base_confidence = clamp(float(prior["confidence"]) * 0.84 + 0.05, 0.14, 0.72)
                inherited_from = str(prior["scenario_id"])
            direction = -1.0 if index % 2 else 1.0
            bias = direction * spec.tolerance * self.rng.uniform(1.8, 3.5)
            states[spec.concept_key] = ConceptState(spec, base_weight, base_confidence, bias, inherited_from=inherited_from)
        return states

    def make_task(self, spec: ConceptSpec, difficulty: float) -> dict[str, Any]:
        r = self.rng
        if spec.concept_key == "angle_min_rotation":
            symmetry = r.choice([90.0, 120.0, 180.0, 360.0])
            angle = r.randrange(0, int(symmetry))
            target = r.randrange(0, int(symmetry))
            expected = min_rotation(angle, target, symmetry)
            values = {"angle": angle, "target": target, "symmetry": symmetry}
        elif spec.concept_key == "angle_complement":
            angle = r.randrange(8, 83)
            expected = 90.0 - angle
            values = {"angle": angle}
        elif spec.concept_key == "angle_supplement":
            angle = r.randrange(18, 164)
            expected = 180.0 - angle
            values = {"angle": angle}
        elif spec.concept_key == "triangle_angle_sum":
            a = r.randrange(25, 85)
            b = r.randrange(35, min(95, 170 - a))
            expected = 180.0 - a - b
            values = {"angle_a": a, "angle_b": b}
        elif spec.concept_key == "polygon_exterior_angle":
            n = r.randrange(3, 13)
            expected = 360.0 / n
            values = {"sides": n}
        elif spec.concept_key == "symmetry_rotation":
            n = r.randrange(3, 11)
            expected = 360.0 / n
            values = {"regular_parts": n}
        elif spec.concept_key == "distance_2d":
            x1, y1 = r.randrange(-6, 7), r.randrange(-6, 7)
            x2, y2 = r.randrange(-6, 7), r.randrange(-6, 7)
            expected = math.hypot(x2 - x1, y2 - y1)
            values = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
        elif spec.concept_key == "slope_2d":
            dx = r.choice([v for v in range(-8, 9) if v not in (0,)])
            dy = r.randrange(-8, 9)
            expected = dy / dx
            values = {"dx": dx, "dy": dy}
        elif spec.concept_key == "perimeter_rectangle":
            w, h = r.uniform(1.5, 9.5), r.uniform(1.5, 9.5)
            expected = 2.0 * (w + h)
            values = {"width": round(w, 3), "height": round(h, 3)}
        elif spec.concept_key == "area_rectangle":
            w, h = r.uniform(1.2, 9.0), r.uniform(1.2, 9.0)
            expected = w * h
            values = {"width": round(w, 3), "height": round(h, 3)}
        elif spec.concept_key == "area_triangle":
            b, h = r.uniform(2.0, 11.0), r.uniform(1.5, 9.0)
            expected = 0.5 * b * h
            values = {"base": round(b, 3), "height": round(h, 3)}
        elif spec.concept_key == "circle_circumference":
            radius = r.uniform(1.0, 7.0)
            expected = 2.0 * math.pi * radius
            values = {"radius": round(radius, 3)}
        elif spec.concept_key == "circle_area":
            radius = r.uniform(1.0, 7.0)
            expected = math.pi * radius * radius
            values = {"radius": round(radius, 3)}
        elif spec.concept_key == "pythagorean_hypotenuse":
            a, b = r.randrange(3, 13), r.randrange(4, 15)
            expected = math.hypot(a, b)
            values = {"leg_a": a, "leg_b": b}
        elif spec.concept_key == "vector_magnitude":
            x, y = r.randrange(-9, 10), r.randrange(-9, 10)
            expected = math.hypot(x, y)
            values = {"x": x, "y": y}
        elif spec.concept_key == "scale_ratio":
            original = r.uniform(1.5, 8.0)
            factor = r.uniform(0.4, 2.8)
            transformed = original * factor
            expected = transformed / original
            values = {"original": round(original, 3), "transformed": round(transformed, 3)}
        elif spec.concept_key == "similar_triangle_height":
            height = r.uniform(1.5, 9.0)
            scale = r.uniform(0.5, 2.5)
            expected = height * scale
            values = {"known_height": round(height, 3), "scale_ratio": round(scale, 3)}
        elif spec.concept_key == "weighted_centroid_1d":
            x1, x2 = r.uniform(-6.0, 2.0), r.uniform(2.0, 9.0)
            w1, w2 = r.uniform(0.5, 4.0), r.uniform(0.5, 4.0)
            expected = (w1 * x1 + w2 * x2) / (w1 + w2)
            values = {"x1": round(x1, 3), "x2": round(x2, 3), "weight1": round(w1, 3), "weight2": round(w2, 3)}
        elif spec.concept_key == "weighted_centroid_2d_x":
            x1, x2, x3 = r.uniform(-6.0, 0.0), r.uniform(0.0, 5.0), r.uniform(5.0, 10.0)
            w1, w2, w3 = r.uniform(0.5, 3.5), r.uniform(0.5, 3.5), r.uniform(0.5, 3.5)
            expected = (w1 * x1 + w2 * x2 + w3 * x3) / (w1 + w2 + w3)
            values = {
                "x1": round(x1, 3),
                "x2": round(x2, 3),
                "x3": round(x3, 3),
                "weight1": round(w1, 3),
                "weight2": round(w2, 3),
                "weight3": round(w3, 3),
            }
        elif spec.concept_key == "lever_balance_torque":
            weight = r.uniform(1.0, 12.0)
            arm = r.uniform(0.4, 3.5)
            expected = weight * arm
            values = {"weight": round(weight, 3), "arm": round(arm, 3)}
        else:
            raise KeyError(spec.concept_key)

        scale = max(abs(expected), spec.tolerance * 6.0, 1.0)
        return {
            "concept_key": spec.concept_key,
            "family": spec.family,
            "task_kind": spec.answer_kind,
            "difficulty": round(difficulty, 3),
            "values": values,
            "expected": round(float(expected), 5),
            "tolerance": spec.tolerance,
            "scale": scale,
            "definition": spec.definition,
        }

    def rzs_input(self, cycle_id: int) -> RZSInput:
        avg_conf = mean([s.confidence for s in self.concepts.values()])
        weak_count = sum(1 for s in self.concepts.values() if s.confidence < 0.42)
        recent_error_pressure = mean([min(1.0, r.normalized_error) for r in self.recent_errors[-6:]]) if self.recent_errors else 0.0
        weak_ratio = weak_count / max(1, len(self.concepts))
        novelty = clamp(0.08 + weak_ratio * 0.44)
        replay_gap = clamp((cycle_id - self.last_replay_cycle) / 18.0)
        memory_pressure = clamp(len(self.recent_errors) / 8.0)
        return RZSInput(
            bandwidth=5.15 + avg_conf * 2.10,
            info_self=0.24 + (1.0 - avg_conf) * 0.28,
            info_external=0.26 + novelty * 0.26,
            task_info=0.42 + weak_ratio * 0.42,
            novelty=novelty,
            conflict=clamp(0.08 + recent_error_pressure * 0.58),
            latency=0.72 + recent_error_pressure * 0.46 + memory_pressure * 0.20,
            energy=self.energy,
            memory_pressure=memory_pressure,
            replay_gap=replay_gap,
        )

    def choose_concept(self, cycle_id: int, decision: str) -> ConceptState:
        unexposed = [s for s in self.concepts.values() if s.exposure_count == 0]
        if unexposed:
            return sorted(unexposed, key=lambda s: (s.spec.family, s.spec.concept_key))[0]
        if decision in {"narrow_focus", "pause_for_stability"}:
            return min(self.concepts.values(), key=lambda s: (s.confidence, -s.error_count, s.spec.complexity))
        if decision == "consolidate":
            return max(self.concepts.values(), key=lambda s: (s.exposure_count, s.confidence))
        if decision == "replay_memory" and self.recent_errors:
            return self.concepts[self.recent_errors[-1].concept_key]
        ordered = sorted(self.concepts.values(), key=lambda s: (s.exposure_count, s.confidence, s.spec.concept_key))
        return ordered[(cycle_id + len(self.recent_errors)) % len(ordered)]

    def cognitive_action(self, decision: str) -> str:
        return {
            "continue": "explore_geometry_problem",
            "narrow_focus": "focus_weak_geometry_concept",
            "replay_memory": "replay_then_retry_geometry",
            "consolidate": "consolidate_then_test_geometry",
            "pause_for_stability": "stability_pause_then_simple_geometry",
        }.get(decision, "explore_geometry_problem")

    def predict(self, state: ConceptState, task: dict[str, Any], cycle_id: int, decision: str) -> float:
        expected = float(task["expected"])
        tolerance = float(task["tolerance"])
        scale = float(task["scale"])
        force_error = state.exposure_count == 0 or cycle_id <= 10
        decision_noise = {
            "continue": 1.0,
            "narrow_focus": 0.72,
            "replay_memory": 0.58,
            "consolidate": 0.52,
            "pause_for_stability": 0.45,
        }.get(decision, 1.0)
        mistake_probability = clamp(0.48 - state.confidence * 0.34 + state.spec.complexity * 0.12, 0.10, 0.62)
        if force_error or self.rng.random() < mistake_probability:
            direction = -1.0 if (cycle_id + len(state.spec.concept_key)) % 2 else 1.0
            miss = tolerance * self.rng.uniform(1.35, 3.8) + scale * self.rng.uniform(0.025, 0.085) * (1.0 - state.confidence)
            predicted = expected + direction * miss * decision_noise + state.bias
        else:
            noise = scale * self.rng.uniform(-0.018, 0.018) * (1.0 - state.confidence) * decision_noise
            predicted = expected + state.bias * self.rng.uniform(0.18, 0.45) + noise
        return round(predicted, 5)

    def update_state(
        self,
        state: ConceptState,
        expected: float,
        predicted: float,
        tolerance: float,
        decision: str,
    ) -> tuple[float, float, float, float, str]:
        weight_before = state.learning_weight
        confidence_before = state.confidence
        absolute_error = abs(predicted - expected)
        normalized_error = absolute_error / max(tolerance, abs(expected) * 0.035, 1.0)
        error_signal = clamp(normalized_error / 3.0)
        learning_rate = 0.18 if decision in {"replay_memory", "consolidate"} else 0.13
        if decision == "narrow_focus":
            learning_rate += 0.03
        if absolute_error <= tolerance:
            mastery = 1.0
            reason = "hit_within_tolerance"
        elif absolute_error <= tolerance * 2.5:
            mastery = 0.62
            reason = "near_miss_corrected"
        else:
            mastery = 0.34
            reason = "error_corrected_into_experience"
            state.error_count += 1
        correction = (expected - predicted) * min(0.10, learning_rate * 0.42)
        state.bias = state.bias * (1.0 - learning_rate * 0.55) + correction
        state.learning_weight = clamp(state.learning_weight + learning_rate * (mastery - state.learning_weight), 0.05, 0.99)
        state.confidence = clamp(state.confidence + learning_rate * 0.85 * (mastery - state.confidence), 0.05, 0.98)
        state.exposure_count += 1
        return weight_before, confidence_before, error_signal, learning_rate, reason

    def verdict(self, absolute_error: float, tolerance: float) -> str:
        if absolute_error <= tolerance:
            return "hit"
        if absolute_error <= tolerance * 2.5:
            return "near_miss"
        return "error"

    def run_cycle(self, cycle_id: int) -> AttemptResult:
        x = self.rzs_input(cycle_id)
        assessment = self.rzs.classify(x)
        y = self.rzs.apply_action_model(x, assessment.decision)
        sigma_after = self.rzs.sigma(y)
        self.energy = clamp(y.energy - 0.018, 0.10, 1.0)
        if assessment.decision == "replay_memory" and self.recent_errors:
            self.replay_error(cycle_id, assessment.sigma, sigma_after, assessment.decision)
        state = self.choose_concept(cycle_id, assessment.decision)
        difficulty = clamp(0.45 + state.spec.complexity * 0.45 + state.exposure_count * 0.018, 0.0, 1.0)
        task = self.make_task(state.spec, difficulty)
        predicted = self.predict(state, task, cycle_id, assessment.decision)
        expected = float(task["expected"])
        tolerance = float(task["tolerance"])
        weight_before, confidence_before, error_signal, learning_rate, update_reason = self.update_state(
            state,
            expected,
            predicted,
            tolerance,
            assessment.decision,
        )
        absolute_error = abs(predicted - expected)
        normalized_error = absolute_error / max(tolerance, abs(expected) * 0.035, 1.0)
        verdict = self.verdict(absolute_error, tolerance)
        if verdict == "error":
            self.energy = clamp(self.energy - 0.025, 0.10, 1.0)
        else:
            self.energy = clamp(self.energy + 0.006, 0.10, 1.0)

        node_id = f"geo:{self.scenario_id}:{cycle_id:04d}:{state.spec.concept_key}"
        experience_weight = clamp(state.learning_weight * 0.52 + state.confidence * 0.30 + min(1.0, normalized_error) * 0.18)
        result = AttemptResult(
            node_id=node_id,
            cycle_id=cycle_id,
            concept_key=state.spec.concept_key,
            family=state.spec.family,
            task_kind=state.spec.answer_kind,
            prompt=task,
            expected_value=expected,
            predicted_value=predicted,
            absolute_error=round(absolute_error, 5),
            normalized_error=round(normalized_error, 5),
            verdict=verdict,
            cognitive_action=self.cognitive_action(assessment.decision),
            learning_weight_before=weight_before,
            learning_weight_after=state.learning_weight,
            confidence_before=confidence_before,
            confidence_after=state.confidence,
            rzs_decision=assessment.decision,
            sigma_before=assessment.sigma,
            sigma_after=sigma_after,
            experience_weight=experience_weight,
        )
        self.store.log_node(
            self.scenario_id,
            result,
            {
                "update_reason": update_reason,
                "error_signal": error_signal,
                "learning_rate": learning_rate,
                "rzs_reason": assessment.reason,
                "state_bias_after": state.bias,
            },
        )
        self.store.log_weight_update(
            self.scenario_id,
            cycle_id,
            state.spec.concept_key,
            weight_before,
            state.learning_weight,
            confidence_before,
            state.confidence,
            error_signal,
            learning_rate,
            update_reason,
            {"verdict": verdict, "normalized_error": normalized_error},
        )
        self.store.upsert_concept(
            self.scenario_id,
            state,
            {
                "last_node_id": node_id,
                "last_verdict": verdict,
                "last_error": absolute_error,
                "prerequisites": list(state.spec.prerequisites),
            },
        )
        self.link_node(result, state)
        self.store.log_event(
            self.scenario_id,
            "experience_cycle",
            {
                "node_id": node_id,
                "concept_key": state.spec.concept_key,
                "verdict": verdict,
                "cognitive_action": result.cognitive_action,
                "absolute_error": absolute_error,
                "normalized_error": normalized_error,
            },
            cycle_id=cycle_id,
            rzs_decision=assessment.decision,
            sigma_before=assessment.sigma,
            sigma_after=sigma_after,
        )
        self.all_results.append(result)
        if verdict == "error":
            self.recent_errors.append(result)
            self.recent_errors = self.recent_errors[-12:]
        self.last_node_id = node_id
        self.last_by_concept[state.spec.concept_key] = node_id
        if cycle_id % 14 == 0 and self.recent_errors:
            self.replay_error(cycle_id, assessment.sigma, sigma_after, "scheduled_replay")
        return result

    def link_node(self, result: AttemptResult, state: ConceptState) -> None:
        if self.last_node_id:
            relation = "temporal_sequence"
            strength = 0.22
            if result.verdict == "error":
                strength += 0.14
            self.store.log_edge(
                self.scenario_id,
                self.last_node_id,
                result.node_id,
                relation,
                strength,
                "experiences are ordered by learning time",
                {"cycle_id": result.cycle_id},
            )
        previous_same = self.last_by_concept.get(result.concept_key, "")
        if previous_same:
            self.store.log_edge(
                self.scenario_id,
                previous_same,
                result.node_id,
                "same_concept_refinement",
                0.56 if result.verdict != "error" else 0.70,
                "new attempt refines the same geometric concept",
                {"concept_key": result.concept_key},
            )
        for prereq in state.spec.prerequisites:
            prior = self.last_by_concept.get(prereq, "")
            if prior:
                self.store.log_edge(
                    self.scenario_id,
                    prior,
                    result.node_id,
                    "prerequisite_transfer",
                    0.62,
                    "prior concept supports current geometric operation",
                    {"prerequisite": prereq, "target": result.concept_key},
                )

    def replay_error(self, cycle_id: int, sigma_before: float, sigma_after: float, decision: str) -> None:
        if not self.recent_errors:
            return
        source = max(self.recent_errors, key=lambda r: (r.normalized_error, r.experience_weight))
        state = self.concepts[source.concept_key]
        old_error = source.absolute_error
        correction_applied = old_error * (0.58 + 0.16 * (1.0 - state.confidence))
        new_error = max(0.0, old_error - correction_applied)
        state.bias *= 0.70
        state.confidence = clamp(state.confidence + 0.055, 0.05, 0.98)
        state.learning_weight = clamp(state.learning_weight + 0.042, 0.05, 0.99)
        replay_id = f"replay:{self.scenario_id}:{self.replay_count + 1:03d}:{source.concept_key}"
        self.replay_count += 1
        self.last_replay_cycle = cycle_id
        self.store.log_replay(
            self.scenario_id,
            replay_id,
            cycle_id,
            source.node_id,
            source.concept_key,
            old_error,
            new_error,
            correction_applied,
            state.confidence,
            state.learning_weight,
            {
                "rzs_decision": decision,
                "source_verdict": source.verdict,
                "correction_rule": "reduce_bias_and_raise_salience",
            },
        )
        self.store.log_event(
            self.scenario_id,
            "error_replay",
            {
                "replay_id": replay_id,
                "source_node_id": source.node_id,
                "concept_key": source.concept_key,
                "error_before": old_error,
                "error_after": new_error,
            },
            cycle_id=cycle_id,
            rzs_decision=decision,
            sigma_before=sigma_before,
            sigma_after=sigma_after,
        )
        self.store.upsert_concept(
            self.scenario_id,
            state,
            {"replay_id": replay_id, "source_node_id": source.node_id, "bias_after_replay": state.bias},
        )
        self.recent_errors = [r for r in self.recent_errors if r.node_id != source.node_id]

    def consolidate(self) -> dict[str, Any]:
        promoted = []
        for state in self.concepts.values():
            if state.exposure_count >= 2 and state.confidence >= 0.33:
                content = (
                    f"Geometry concept {state.spec.concept_key}: {state.spec.definition}; "
                    f"family={state.spec.family}; confidence={state.confidence:.3f}; "
                    f"learning_weight={state.learning_weight:.3f}; exposures={state.exposure_count}; "
                    f"errors={state.error_count}."
                )
                key = f"geometry_v49_7:{state.spec.concept_key}"
                self.store.write_memory(key, content, state.confidence)
                promoted.append(state.spec.concept_key)
        first_quarter = [r.normalized_error for r in self.all_results[: max(1, len(self.all_results) // 4)]]
        last_quarter = [r.normalized_error for r in self.all_results[-max(1, len(self.all_results) // 4) :]]
        summary_confidence = mean([s.confidence for s in self.concepts.values()])
        summary = {
            "promoted_concepts": promoted,
            "promoted_count": len(promoted),
            "mean_confidence": summary_confidence,
            "mean_weight": mean([s.learning_weight for s in self.concepts.values()]),
            "first_quarter_error": mean(first_quarter),
            "last_quarter_error": mean(last_quarter),
            "total_errors": sum(1 for r in self.all_results if r.verdict == "error"),
            "total_near_misses": sum(1 for r in self.all_results if r.verdict == "near_miss"),
            "total_hits": sum(1 for r in self.all_results if r.verdict == "hit"),
            "replay_count": self.replay_count,
        }
        self.store.write_memory(
            f"brain_v49_7:geometry_experience:{self.scenario_id}",
            (
                f"Darwin v49.7 learned geometry as experience nodes: "
                f"nodes={len(self.all_results)}, errors={summary['total_errors']}, "
                f"replays={self.replay_count}, promoted={len(promoted)}, "
                f"first_quarter_error={summary['first_quarter_error']:.3f}, "
                f"last_quarter_error={summary['last_quarter_error']:.3f}."
            ),
            clamp(summary_confidence, 0.20, 0.95),
        )
        self.store.write_episode(
            context=f"geometry_v49_7:{self.scenario_id}",
            action="learn_geometry_by_error_nodes",
            outcome=f"nodes={len(self.all_results)} errors={summary['total_errors']} replays={self.replay_count}",
            lesson="Geometric knowledge becomes stronger when wrong predictions are corrected and linked as experience nodes.",
            sigma_before=self.all_results[0].sigma_before if self.all_results else 0.0,
            sigma_after=self.all_results[-1].sigma_after if self.all_results else 0.0,
        )
        self.store.log_event(self.scenario_id, "concept_consolidation", summary)
        return summary

    def run(self, cycles: int = 96) -> dict[str, Any]:
        cycles = max(24, int(cycles))
        self.store.log_event(
            self.scenario_id,
            "geometry_start",
            {
                "cycles_requested": cycles,
                "protected_counts_before": self.source_counts_before,
                "formula": "sigma = bandwidth / ((info_self + info_external + task_info + novelty + conflict) * latency)",
            },
        )
        self.store.log_event(
            self.scenario_id,
            "source_memory_read",
            {
                "source_angle": self.source_angle,
                "source_plans": self.source_plans,
                "source_homeostasis": self.source_homeostasis,
                "protected_source_tables": PROTECTED_SOURCE_TABLES,
            },
        )
        for state in self.concepts.values():
            self.store.upsert_concept(
                self.scenario_id,
                state,
                {"seeded": True, "prerequisites": list(state.spec.prerequisites), "inherited_from": state.inherited_from},
            )
        self.store.log_event(
            self.scenario_id,
            "curriculum_seed",
            {
                "concept_count": len(self.concepts),
                "families": sorted({s.spec.family for s in self.concepts.values()}),
                "concepts": [s.spec.concept_key for s in self.concepts.values()],
            },
        )
        for cycle_id in range(1, cycles + 1):
            self.run_cycle(cycle_id)
        if self.recent_errors:
            self.replay_error(cycles, self.all_results[-1].sigma_before, self.all_results[-1].sigma_after, "final_replay")
        summary = self.consolidate()
        counts_after = self.store.protected_counts()
        source_unchanged = counts_after == self.source_counts_before
        complete = {
            **summary,
            "scenario_complete": True,
            "cycles_completed": len(self.all_results),
            "protected_counts_before": self.source_counts_before,
            "protected_counts_after": counts_after,
            "protected_sources_unchanged": source_unchanged,
            "source_angle": self.source_angle,
            "source_plans": self.source_plans,
            "source_homeostasis": self.source_homeostasis,
        }
        self.store.log_event(self.scenario_id, "geometry_complete", complete)
        return {"scenario_id": self.scenario_id, **complete}


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin Geometry Experience Learner v49.7")
    ap.add_argument("--cycles", type=int, default=96)
    ap.add_argument("--seed", type=int, default=4970)
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    learner = GeometryExperienceLearner(seed=args.seed)
    result = learner.run(cycles=args.cycles)
    print(f"DARWIN v49.7 geometria experiencial concluida: scenario={result['scenario_id']}")
    print(f"ciclos={result['cycles_completed']} erros={result['total_errors']} replays={result['replay_count']} promovidos={result['promoted_count']}")
    print(f"erro_inicio={result['first_quarter_error']:.4f} erro_final={result['last_quarter_error']:.4f}")
    if args.details:
        print(js(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
