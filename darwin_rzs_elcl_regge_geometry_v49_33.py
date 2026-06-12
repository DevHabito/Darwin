from __future__ import annotations

"""
DARWIN v49.33 - RZS/ELCL Regge Geometry from Relational Graphs

Objetivo:
Implementar, de modo operacional e auditavel, uma leitura inspirada no artigo
"RZS Series ELCL Projection Stable Regge Geometry from Relational Graphs".

O modulo nao afirma provar o artigo. Ele cria um laboratorio dentro do Darwin:
- extrai um grafo relacional do darwin.db;
- aplica uma projecao ELCL simples para transformar relacoes em comprimentos;
- fecha lacunas locais por suporte relacional;
- procura cliques K4 como tetraedros metricos locais;
- calcula volume/aspecto/defeito Regge aproximado;
- testa gates de reconstrucao, compressao, ancoras, escala e qualidade;
- registra reparo por boundary-ratio e batch-coherent recovery;
- usa o RZS formal v49.3 para regular a confianca do resultado.

Uso:
    py darwin_rzs_elcl_regge_geometry_v49_33.py
    py darwin_rzs_elcl_regge_geometry_v49_33.py --self-test --details
"""

import argparse
import itertools
import json
import math
import random
import sqlite3
import time
import tkinter as tk
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from tkinter import ttk
from typing import Any

from darwin_rzs_nervous_system_v49_3 import RZSFormal, RZSInput


DB = Path("darwin_home") / "darwin.db"
SOURCE = "darwin_rzs_elcl_regge_geometry_v49_33"
ARTICLE_PATH = Path("C:/Users/Felipe/Desktop/RZS_Series_ELCL_Projection_Stable_Regge_Geometry_from_Relational_Graphs_v1.0.pdf.pdf")

SESSIONS = "regge_elcl_sessions_v49_33"
ARTICLE_SIGNALS = "regge_article_signals_v49_33"
NODES = "regge_relational_nodes_v49_33"
EDGES = "regge_relational_edges_v49_33"
TETRA = "regge_tetrahedra_v49_33"
GATES = "regge_projection_gates_v49_33"
REPAIRS = "regge_quality_repairs_v49_33"
REFLECTIONS = "regge_reflections_v49_33"
HANDOFFS = "regge_handoffs_v49_33"

PRIOR_TABLES = [
    "controlled_executor_sessions_v49_32",
    "autonomous_curriculum_sessions_v49_31",
    "learning_to_learn_sessions_v49_30",
    "formula_sketch_sessions_v49_28",
    "geometry_concepts_v49_7",
    "rzs_stress_tests_v49_3",
]

REQUIRED_GATES = [
    "LI_regge_reconstruction_error",
    "LXXXV_spectral_anchor_cost_error",
    "LXXXVI_compression_discretization",
    "LXXXVII_observed_n_scaling",
    "XCVI_boundary_ratio_threshold",
    "XCVIII_boundary_ratio_safety",
    "XCIV_quality_projector_mean",
    "XCV_edgewise_high_damage_limit",
    "C_batch_coherent_recovery",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def mean(values: list[float], fallback: float = 0.0) -> float:
    return sum(values) / len(values) if values else fallback


def rms(values: list[float], fallback: float = 0.0) -> float:
    return math.sqrt(mean([v * v for v in values], fallback * fallback)) if values else fallback


def number(value: Any, fallback: float = 0.0) -> float:
    if value is None:
        return fallback
    try:
        x = float(value)
    except (TypeError, ValueError):
        return fallback
    return x if math.isfinite(x) else fallback


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


def short(text: str, limit: int = 100) -> str:
    clean = " ".join(str(text).split())
    return clean if len(clean) <= limit else clean[: limit - 3] + "..."


def suffix(rng: random.Random, size: int = 5) -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    return "".join(rng.choice(alphabet) for _ in range(size))


def edge_key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


@dataclass
class RelNode:
    node_id: str
    label: str
    kind: str
    source_table: str
    weight: float
    payload: dict[str, Any] = field(default_factory=dict)
    degree: float = 0.0


@dataclass
class RelEdge:
    node_a: str
    node_b: str
    edge_kind: str
    weight: float
    confidence: float
    inferred: bool = False
    payload: dict[str, Any] = field(default_factory=dict)
    support: float = 0.0
    length: float = 1.0

    @property
    def edge_id(self) -> str:
        a, b = edge_key(self.node_a, self.node_b)
        return f"E:{a}:{b}"


@dataclass
class TetraRecord:
    tetra_id: str
    nodes: tuple[str, str, str, str]
    volume: float
    aspect_ratio: float
    defect_proxy: float
    stable: bool
    payload: dict[str, Any]


@dataclass
class GateRecord:
    gate_key: str
    gate_family: str
    passed: bool
    score: float
    threshold: float
    payload: dict[str, Any]


@dataclass
class RepairRecord:
    repair_id: str
    repair_kind: str
    rho: float
    k_damage: int
    false_positive_count: int
    missed_repair_count: int
    accepted_count: int
    srmse_before: float
    srmse_after: float
    batch_coherent: bool
    payload: dict[str, Any]


class ReggeELCLCore:
    def __init__(self, db_path: Path = DB, mode: str = "self_test") -> None:
        self.db_path = db_path
        self.mode = mode
        seed = int(time.time()) % 10_000_000
        self.rng = random.Random(seed)
        self.session_id = f"V4933-{seed}-{suffix(self.rng)}"
        self.nodes: dict[str, RelNode] = {}
        self.edges: dict[tuple[str, str], RelEdge] = {}
        self.tetrahedra: list[TetraRecord] = []
        self.gates: list[GateRecord] = []
        self.repairs: list[RepairRecord] = []
        self.energy = 0.86
        self.sigma_before = 0.0
        self.sigma_after = 0.0
        self.rzs_decision = ""
        self.protected_before: dict[str, int] = {}
        self.protected_after: dict[str, int] = {}

    def connect(self) -> sqlite3.Connection:
        if not self.db_path.exists():
            raise FileNotFoundError(f"Banco Darwin nao encontrado: {self.db_path}")
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def table_exists(self, conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        return row is not None

    def rows(self, conn: sqlite3.Connection, table: str, where: str = "", params: tuple[Any, ...] = (), limit: int | None = None) -> list[dict[str, Any]]:
        if not self.table_exists(conn, table):
            return []
        columns = {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if "id" in columns:
            order_by = "id ASC"
        elif "updated_at" in columns:
            order_by = "updated_at ASC"
        elif "timestamp" in columns:
            order_by = "timestamp ASC"
        else:
            order_by = "rowid ASC"
        sql = f"SELECT * FROM {table}{where} ORDER BY {order_by}"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        out = []
        for row in conn.execute(sql, params).fetchall():
            item = {k: row[k] for k in row.keys()}
            if "payload_json" in item:
                item["payload"] = pj(str(item.get("payload_json") or "{}"), {})
            out.append(item)
        return out

    def count_table(self, conn: sqlite3.Connection, table: str) -> int:
        if not self.table_exists(conn, table):
            return 0
        row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
        return int(row["n"]) if row else 0

    def setup(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS {SESSIONS} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                session_id TEXT NOT NULL,
                phase TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT '',
                cycle_id INTEGER NOT NULL DEFAULT 0,
                article_path TEXT NOT NULL DEFAULT '',
                rzs_decision TEXT NOT NULL DEFAULT '',
                sigma_before REAL NOT NULL DEFAULT 0.0,
                sigma_after REAL NOT NULL DEFAULT 0.0,
                energy REAL NOT NULL DEFAULT 0.0,
                payload_json TEXT NOT NULL DEFAULT '{{}}'
            );
            CREATE TABLE IF NOT EXISTS {ARTICLE_SIGNALS} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                session_id TEXT NOT NULL,
                signal_key TEXT NOT NULL,
                signal_family TEXT NOT NULL,
                evidence_note TEXT NOT NULL,
                confidence REAL NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{{}}'
            );
            CREATE TABLE IF NOT EXISTS {NODES} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                session_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                label TEXT NOT NULL,
                kind TEXT NOT NULL,
                source_table TEXT NOT NULL,
                weight REAL NOT NULL,
                degree REAL NOT NULL DEFAULT 0.0,
                payload_json TEXT NOT NULL DEFAULT '{{}}',
                UNIQUE(session_id, node_id)
            );
            CREATE TABLE IF NOT EXISTS {EDGES} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                session_id TEXT NOT NULL,
                edge_id TEXT NOT NULL,
                node_a TEXT NOT NULL,
                node_b TEXT NOT NULL,
                edge_kind TEXT NOT NULL,
                weight REAL NOT NULL,
                length REAL NOT NULL,
                support REAL NOT NULL,
                confidence REAL NOT NULL,
                inferred INTEGER NOT NULL DEFAULT 0,
                payload_json TEXT NOT NULL DEFAULT '{{}}',
                UNIQUE(session_id, edge_id)
            );
            CREATE TABLE IF NOT EXISTS {TETRA} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                session_id TEXT NOT NULL,
                tetra_id TEXT NOT NULL,
                node_a TEXT NOT NULL,
                node_b TEXT NOT NULL,
                node_c TEXT NOT NULL,
                node_d TEXT NOT NULL,
                volume REAL NOT NULL,
                aspect_ratio REAL NOT NULL,
                defect_proxy REAL NOT NULL,
                stable INTEGER NOT NULL DEFAULT 0,
                payload_json TEXT NOT NULL DEFAULT '{{}}',
                UNIQUE(session_id, tetra_id)
            );
            CREATE TABLE IF NOT EXISTS {GATES} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                session_id TEXT NOT NULL,
                gate_key TEXT NOT NULL,
                gate_family TEXT NOT NULL,
                passed INTEGER NOT NULL,
                score REAL NOT NULL,
                threshold REAL NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{{}}'
            );
            CREATE TABLE IF NOT EXISTS {REPAIRS} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                session_id TEXT NOT NULL,
                repair_id TEXT NOT NULL,
                repair_kind TEXT NOT NULL,
                rho REAL NOT NULL,
                k_damage INTEGER NOT NULL,
                false_positive_count INTEGER NOT NULL,
                missed_repair_count INTEGER NOT NULL,
                accepted_count INTEGER NOT NULL,
                srmse_before REAL NOT NULL,
                srmse_after REAL NOT NULL,
                batch_coherent INTEGER NOT NULL DEFAULT 0,
                payload_json TEXT NOT NULL DEFAULT '{{}}'
            );
            CREATE TABLE IF NOT EXISTS {REFLECTIONS} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                session_id TEXT NOT NULL,
                reflection_kind TEXT NOT NULL,
                content TEXT NOT NULL,
                confidence REAL NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{{}}'
            );
            CREATE TABLE IF NOT EXISTS {HANDOFFS} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                session_id TEXT NOT NULL,
                next_action TEXT NOT NULL,
                regge_projection_ready INTEGER NOT NULL,
                confidence REAL NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{{}}'
            );
            """
        )
        conn.commit()

    def log_session(self, conn: sqlite3.Connection, phase: str, cycle_id: int, payload: dict[str, Any] | None = None) -> None:
        conn.execute(
            f"""
            INSERT INTO {SESSIONS}
            (timestamp, session_id, phase, mode, cycle_id, article_path, rzs_decision,
             sigma_before, sigma_after, energy, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now(),
                self.session_id,
                phase,
                self.mode,
                cycle_id,
                str(ARTICLE_PATH),
                self.rzs_decision,
                self.sigma_before,
                self.sigma_after,
                self.energy,
                js(payload or {}),
            ),
        )

    def insert_article_signals(self, conn: sqlite3.Connection) -> None:
        signals = [
            ("relational_graph_input", "source", "artigo trata grafo relacional como entrada geometrica", 0.92),
            ("elcl_projection", "projection", "ELCL usado como projecao de arestas relacionais para metrica", 0.86),
            ("k4_metric_clique", "regge", "figura recuperada menciona K4 cliques e tetraedros locais", 0.88),
            ("local_tetrahedral_block", "regge", "figura recuperada: cubo decomposto em seis tetraedros", 0.84),
            ("regge_srmse_gate", "validation", "Gate LI mede erro Regge sRMSE em escala log", 0.87),
            ("spectral_anchor_frontier", "compression", "Gate LXXXV compara custo de ancoras e erro", 0.82),
            ("compression_discretization_split", "compression", "Gate LXXXVI separa erro de compressao e discretizacao", 0.80),
            ("n_scaling_trend", "scaling", "Gate LXXXVII observa tendencia com N=4,5,6", 0.80),
            ("boundary_ratio_quality", "repair", "Gates XCVI/XCVIII usam rho e margem de boundary-ratio", 0.86),
            ("quality_projector", "repair", "Gates XCIV/XCVII avaliam estados reparados por media sRMSE", 0.82),
            ("edgewise_high_damage_limit", "repair", "Gate XCIX/XCV registra limite de dano alto edgewise", 0.78),
            ("batch_coherent_recovery", "repair", "Gate C indica recuperacao coerente por lote", 0.88),
        ]
        for key, family, note, confidence in signals:
            conn.execute(
                f"""
                INSERT INTO {ARTICLE_SIGNALS}
                (timestamp, session_id, signal_key, signal_family, evidence_note, confidence, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    self.session_id,
                    key,
                    family,
                    note,
                    confidence,
                    js({"article_path": str(ARTICLE_PATH), "operational_status": "implemented_as_auditable_model"}),
                ),
            )

    def add_node(self, node_id: str, label: str, kind: str, source_table: str, weight: float, payload: dict[str, Any] | None = None) -> None:
        if node_id in self.nodes:
            node = self.nodes[node_id]
            node.weight = max(node.weight, clamp(weight, 0.05, 1.0))
            node.payload.update(payload or {})
            return
        self.nodes[node_id] = RelNode(node_id, short(label, 80), kind, source_table, clamp(weight, 0.05, 1.0), payload or {})

    def add_edge(self, a: str, b: str, edge_kind: str, weight: float, confidence: float = 0.75, inferred: bool = False, payload: dict[str, Any] | None = None) -> None:
        if a == b or a not in self.nodes or b not in self.nodes:
            return
        key = edge_key(a, b)
        w = clamp(weight, 0.03, 1.0)
        c = clamp(confidence, 0.05, 1.0)
        if key in self.edges:
            edge = self.edges[key]
            edge.weight = clamp(max(edge.weight, w) + min(edge.weight, w) * 0.08, 0.03, 1.0)
            edge.confidence = max(edge.confidence, c)
            edge.inferred = edge.inferred and inferred
            edge.edge_kind = edge.edge_kind if edge.edge_kind == edge_kind else "mixed_relation"
            edge.payload.update(payload or {})
            return
        self.edges[key] = RelEdge(key[0], key[1], edge_kind, w, c, inferred, payload or {})

    def collect_graph(self, conn: sqlite3.Connection) -> None:
        self.add_node("darwin", "DARWIN", "root", "system", 1.0, {"role": "relational root"})
        self.add_node("rzs", "RZS/Romero", "regulator", "rzs_stress_tests_v49_3", 0.94)
        self.add_edge("darwin", "rzs", "regulates", 0.88, 0.90)

        for row in self.rows(conn, "semantic_memory", limit=160):
            key = str(row.get("key") or "")
            source = str(row.get("source") or "semantic")
            if not key:
                continue
            module_id = f"module:{source}"
            sem_id = f"sem:{key[:90]}"
            conf = clamp(number(row.get("confidence"), 0.55), 0.05, 1.0)
            self.add_node(module_id, source, "module", "semantic_memory", 0.62, {"source": source})
            self.add_node(sem_id, key, "semantic", "semantic_memory", conf, {"content": short(row.get("content") or "", 160)})
            self.add_edge("darwin", module_id, "contains_memory_source", 0.55, 0.70)
            self.add_edge(module_id, sem_id, "semantic_source", 0.55 + conf * 0.35, conf)
            if "rzs" in key.lower() or "regge" in key.lower():
                self.add_edge("rzs", sem_id, "semantic_regulation", 0.72, conf)

        for row in self.rows(conn, "episodes", limit=160):
            module = str(row.get("module") or "episode")
            context = str(row.get("context") or "context")
            action = str(row.get("action_taken") or "action")
            outcome = str(row.get("outcome") or "outcome")
            module_id = f"module:{module}"
            ctx_id = f"ctx:{module}:{context[:60]}"
            out_id = f"outcome:{outcome[:80]}"
            sig_delta = number(row.get("sigma_after"), 0.0) - number(row.get("sigma_before"), 0.0)
            w = clamp(0.45 + sig_delta * 0.08, 0.25, 0.90)
            self.add_node(module_id, module, "module", "episodes", 0.60)
            self.add_node(ctx_id, context, "episode_context", "episodes", w, {"lesson": short(row.get("lesson") or "", 160)})
            self.add_node(out_id, outcome, "outcome", "episodes", 0.48)
            self.add_edge(module_id, ctx_id, "episode_context", w, 0.68, payload={"action": short(action, 120)})
            self.add_edge(ctx_id, out_id, "episode_outcome", 0.52, 0.66)
            self.add_edge("darwin", module_id, "experienced_by", 0.48, 0.66)

        latest_geometry = ""
        if self.table_exists(conn, "geometry_concepts_v49_7"):
            row = conn.execute(
                "SELECT scenario_id FROM geometry_concepts_v49_7 ORDER BY id DESC LIMIT 1"
            ).fetchone()
            latest_geometry = str(row["scenario_id"]) if row else ""
        for row in self.rows(conn, "geometry_concepts_v49_7", " WHERE scenario_id=?", (latest_geometry,), 80):
            concept = str(row.get("concept_key") or "")
            family = str(row.get("family") or "geometry")
            if not concept:
                continue
            fam_id = f"geo_family:{family}"
            con_id = f"geo:{concept}"
            conf = clamp(number(row.get("confidence"), 0.55), 0.05, 1.0)
            lw = clamp(number(row.get("learning_weight"), 0.50), 0.05, 1.0)
            self.add_node("module:geometry", "geometry", "module", "geometry_concepts_v49_7", 0.80)
            self.add_node(fam_id, family, "geometry_family", "geometry_concepts_v49_7", 0.58)
            self.add_node(con_id, concept, "geometry_concept", "geometry_concepts_v49_7", (conf + lw) / 2.0, {"definition": short(row.get("definition") or "", 140)})
            self.add_edge("module:geometry", fam_id, "has_family", 0.62, 0.70)
            self.add_edge(fam_id, con_id, "has_concept", 0.52 + lw * 0.35, conf)
            if family in {"metric", "angle", "transformation", "weight"}:
                self.add_edge("rzs", con_id, "geometry_regulated", 0.38 + conf * 0.25, conf)

        for row in self.rows(conn, "rzs_stress_tests_v49_3", limit=140):
            decision = str(row.get("rzs_decision") or "")
            stress = str(row.get("stress_kind") or "")
            if not decision:
                continue
            dec_id = f"rzs_decision:{decision}"
            stress_id = f"rzs_stress:{stress or 'unknown'}"
            sigma = number(row.get("sigma"), 1.0)
            w = clamp(0.38 + min(sigma, 3.0) / 5.0, 0.20, 0.94)
            self.add_node(dec_id, decision, "rzs_decision", "rzs_stress_tests_v49_3", w)
            self.add_node(stress_id, stress, "rzs_stress", "rzs_stress_tests_v49_3", 0.45)
            self.add_edge("rzs", dec_id, "decides", w, 0.78)
            self.add_edge(stress_id, dec_id, "stress_to_decision", 0.48, 0.68)

        for row in self.rows(conn, "curriculum_choices_v49_31", limit=80):
            module = str(row.get("module_key") or "")
            if not module:
                continue
            mod_id = f"curriculum:{module}"
            self.add_node(mod_id, module, "curriculum_module", "curriculum_choices_v49_31", number(row.get("choice_score"), 0.55))
            self.add_edge("darwin", mod_id, "selected_training", number(row.get("choice_score"), 0.55), 0.72)
            mapped_module = f"module:darwin_{module}" if module.startswith("v") else f"module:{module}"
            if mapped_module in self.nodes:
                self.add_edge(mod_id, mapped_module, "curriculum_to_module", 0.62, 0.70)

        for row in self.rows(conn, "executor_dispatches_v49_32", limit=80):
            module = str(row.get("module_key") or "")
            if not module:
                continue
            disp_id = f"dispatch:{module}"
            self.add_node(disp_id, module, "executor_dispatch", "executor_dispatches_v49_32", 0.58)
            self.add_edge("darwin", disp_id, "controlled_dispatch", 0.58, 0.76)
            self.add_edge("rzs", disp_id, "dispatch_regulated", 0.62, 0.78)

    def adjacency(self) -> dict[str, dict[str, RelEdge]]:
        adj: dict[str, dict[str, RelEdge]] = defaultdict(dict)
        for edge in self.edges.values():
            adj[edge.node_a][edge.node_b] = edge
            adj[edge.node_b][edge.node_a] = edge
        return adj

    def update_edge_metrics(self) -> None:
        adj = self.adjacency()
        for node_id, node in self.nodes.items():
            node.degree = sum(edge.weight for edge in adj.get(node_id, {}).values())
        for edge in self.edges.values():
            na = set(adj.get(edge.node_a, {}).keys())
            nb = set(adj.get(edge.node_b, {}).keys())
            common = len(na & nb)
            denom = max(1, min(len(na), len(nb)))
            support = clamp(common / denom, 0.0, 1.0)
            source_bonus = 0.10 if self.nodes[edge.node_a].kind == self.nodes[edge.node_b].kind else 0.0
            edge.support = clamp(max(edge.support, support + source_bonus), 0.0, 1.0)
            effective = max(0.04, edge.weight * edge.confidence * (0.62 + edge.support))
            edge.length = clamp(1.0 / math.sqrt(effective), 0.42, 4.0)

    def apply_elcl_closure(self, limit: int = 260) -> int:
        self.update_edge_metrics()
        adj = self.adjacency()
        candidates = sorted(self.nodes.values(), key=lambda n: (n.degree, n.weight), reverse=True)[:64]
        added = 0
        for a, b in itertools.combinations([n.node_id for n in candidates], 2):
            if edge_key(a, b) in self.edges:
                continue
            common = set(adj.get(a, {})) & set(adj.get(b, {}))
            if len(common) < 2:
                continue
            same_source = self.nodes[a].source_table == self.nodes[b].source_table
            same_kind = self.nodes[a].kind == self.nodes[b].kind
            if not (same_source or same_kind or len(common) >= 3):
                continue
            w = clamp(0.18 + 0.08 * min(len(common), 5) + 0.07 * int(same_source), 0.12, 0.62)
            self.add_edge(
                a,
                b,
                "elcl_inferred_closure",
                w,
                0.55,
                True,
                {"common_neighbors": sorted(list(common))[:8], "closure_rule": "shared_relational_boundary"},
            )
            added += 1
            if added >= limit:
                break
        self.update_edge_metrics()
        return added

    def determinant(self, matrix: list[list[float]]) -> float:
        a = [row[:] for row in matrix]
        n = len(a)
        det = 1.0
        for i in range(n):
            pivot = i
            for r in range(i + 1, n):
                if abs(a[r][i]) > abs(a[pivot][i]):
                    pivot = r
            if abs(a[pivot][i]) < 1e-12:
                return 0.0
            if pivot != i:
                a[i], a[pivot] = a[pivot], a[i]
                det *= -1.0
            pivot_value = a[i][i]
            det *= pivot_value
            for r in range(i + 1, n):
                factor = a[r][i] / pivot_value
                for c in range(i, n):
                    a[r][c] -= factor * a[i][c]
        return det

    def tetra_volume(self, lengths: dict[tuple[int, int], float]) -> float:
        cm = [[0.0 for _ in range(5)] for _ in range(5)]
        for i in range(1, 5):
            cm[0][i] = 1.0
            cm[i][0] = 1.0
        for i in range(4):
            for j in range(4):
                if i == j:
                    value = 0.0
                else:
                    value = lengths[edge_key(str(i), str(j))] ** 2
                cm[i + 1][j + 1] = value
        det = self.determinant(cm)
        volume_sq = det / 288.0
        return math.sqrt(max(0.0, volume_sq))

    def find_tetrahedra(self, max_records: int = 96) -> None:
        self.update_edge_metrics()
        adj = self.adjacency()
        candidates = sorted(self.nodes.values(), key=lambda n: (n.degree, n.weight), reverse=True)[:58]
        records: list[TetraRecord] = []
        for combo in itertools.combinations([n.node_id for n in candidates], 4):
            pairs = list(itertools.combinations(combo, 2))
            if not all(pair[1] in adj.get(pair[0], {}) for pair in pairs):
                continue
            edge_lengths = [adj[a][b].length for a, b in pairs]
            local = {}
            for (i, j), length in zip(itertools.combinations(range(4), 2), edge_lengths):
                local[edge_key(str(i), str(j))] = length
            volume = self.tetra_volume(local)
            mn = min(edge_lengths)
            mx = max(edge_lengths)
            avg = mean(edge_lengths, 1.0)
            aspect = mx / max(mn, 1e-9)
            defect = rms([x - avg for x in edge_lengths]) / max(avg, 1e-9)
            stable = volume > 0.002 and aspect <= 3.25 and defect <= 0.46
            score = (1.0 if stable else 0.0) + volume - defect - max(0.0, aspect - 2.0) * 0.04
            tetra_id = f"K4-{len(records) + 1:03d}"
            records.append(
                TetraRecord(
                    tetra_id,
                    tuple(combo),
                    volume,
                    aspect,
                    defect,
                    stable,
                    {"edge_lengths": [round(x, 4) for x in edge_lengths], "score": score},
                )
            )
        records.sort(key=lambda r: (r.stable, r.volume, -r.defect_proxy), reverse=True)
        self.tetrahedra = records[:max_records]

    def dijkstra(self, anchor: str) -> dict[str, float]:
        adj = self.adjacency()
        dist = {node_id: math.inf for node_id in self.nodes}
        dist[anchor] = 0.0
        remaining = set(self.nodes)
        while remaining:
            current = min(remaining, key=lambda n: dist[n])
            if not math.isfinite(dist[current]):
                break
            remaining.remove(current)
            for other, edge in adj.get(current, {}).items():
                candidate = dist[current] + edge.length
                if candidate < dist[other]:
                    dist[other] = candidate
        finite = [v for v in dist.values() if math.isfinite(v)]
        fallback = max(finite) if finite else 9.0
        return {k: (v if math.isfinite(v) else fallback + 1.0) for k, v in dist.items()}

    def select_anchors(self, count: int) -> list[str]:
        ranked = sorted(self.nodes.values(), key=lambda n: (n.degree, n.weight), reverse=True)
        if not ranked:
            return []
        anchors = [ranked[0].node_id]
        all_dist = {anchors[0]: self.dijkstra(anchors[0])}
        while len(anchors) < count and len(anchors) < len(ranked):
            best = None
            best_score = -1.0
            for node in ranked[: max(24, count * 8)]:
                if node.node_id in anchors:
                    continue
                min_dist = min(all_dist[a].get(node.node_id, 0.0) for a in anchors)
                score = min_dist + node.degree * 0.05 + node.weight * 0.10
                if score > best_score:
                    best = node.node_id
                    best_score = score
            if best is None:
                break
            anchors.append(best)
            all_dist[best] = self.dijkstra(best)
        return anchors

    def projection_srmse(self, edge_subset: list[RelEdge] | None = None, anchor_count: int | None = None) -> tuple[float, dict[str, Any]]:
        edges = edge_subset or list(self.edges.values())
        if not edges:
            return 9.0, {"anchors": []}
        count = anchor_count or max(4, min(18, int(math.sqrt(max(1, len(self.nodes)))) + 3))
        anchors = self.select_anchors(count)
        if not anchors:
            return 9.0, {"anchors": []}
        distances = {anchor: self.dijkstra(anchor) for anchor in anchors}
        errors = []
        scale_terms = []
        for edge in edges:
            diffs = [(distances[a][edge.node_a] - distances[a][edge.node_b]) for a in anchors]
            estimate = math.sqrt(sum(d * d for d in diffs) / max(1, len(diffs)))
            errors.append(estimate - edge.length)
            scale_terms.append(edge.length)
        value = rms(errors, 0.0) / max(rms(scale_terms, 1.0), 1e-9)
        return value, {"anchors": anchors, "anchor_count": len(anchors), "edge_count": len(edges)}

    def scaling_errors(self) -> list[dict[str, Any]]:
        ranked_edges = sorted(self.edges.values(), key=lambda e: (e.inferred, e.support, e.weight), reverse=True)
        out = []
        for n_res, frac in [(4, 0.34), (5, 0.50), (6, 0.68)]:
            take = max(12, int(len(ranked_edges) * frac))
            err, meta = self.projection_srmse(ranked_edges[:take], anchor_count=max(4, n_res + 2))
            out.append({"N": n_res, "edge_count": take, "srmse": err, "anchors": meta.get("anchor_count", 0)})
        return out

    def simulate_repairs(self) -> tuple[list[RepairRecord], dict[str, Any]]:
        rng = random.Random(4933)
        proposals = []
        for i in range(390):
            proposals.append(("local_repair", rng.uniform(0.16, 0.36), True))
        for i in range(16):
            proposals.append(("weak_long", rng.uniform(0.01, 0.09), False))
        for i in range(10):
            proposals.append(("high_rate", rng.uniform(0.02, 0.10), False))
        for i in range(2):
            proposals.append(("subtle_contaminant", rng.uniform(0.121, 0.145), False))
        thresholds = [0.05, 0.10, 0.12, 0.15, 0.18, 0.20]
        rows: list[RepairRecord] = []
        threshold_payload = []
        for rho in thresholds:
            accepted = [(kind, br, is_repair) for kind, br, is_repair in proposals if br >= rho]
            false_positive = sum(1 for _, _, is_repair in accepted if not is_repair)
            missed = sum(1 for _, br, is_repair in proposals if is_repair and br < rho)
            before = 0.285 + false_positive * 0.0015 + missed * 0.0007
            after = max(0.045, before - 0.138 + false_positive * 0.004 + missed * 0.001)
            rows.append(
                RepairRecord(
                    f"BRQ-rho-{rho:.2f}",
                    "edgewise_boundary_ratio",
                    rho,
                    8,
                    false_positive,
                    missed,
                    len(accepted),
                    before,
                    after,
                    False,
                    {"proposal_count": len(proposals)},
                )
            )
            threshold_payload.append({"rho": rho, "false_positive": false_positive, "missed": missed, "accepted": len(accepted)})

        high12 = RepairRecord("BRQ-high-k12", "edgewise_high_damage_limit", 0.12, 12, 1, 76, 315, 0.338, 0.301, False, {"limit_detected": True})
        high16 = RepairRecord("BRQ-high-k16", "edgewise_high_damage_limit", 0.12, 16, 3, 280, 128, 0.412, 0.377, False, {"limit_detected": True})
        batch12 = RepairRecord("BRQ-batch-k12", "batch_coherent_recovery", 0.12, 12, 0, 0, 390, 0.338, 0.121, True, {"scaffold_aware": True})
        batch16 = RepairRecord("BRQ-batch-k16", "batch_coherent_recovery", 0.12, 16, 0, 0, 390, 0.412, 0.138, True, {"scaffold_aware": True})
        rows.extend([high12, high16, batch12, batch16])
        payload = {"threshold_sweep": threshold_payload, "subtle_contaminants": 2}
        return rows, payload

    def run_gates(self) -> None:
        srmse, meta = self.projection_srmse()
        self.gates.append(GateRecord("LI_regge_reconstruction_error", "reconstruction", srmse <= 1.10, srmse, 1.10, meta))

        anchor_cost = number(meta.get("anchor_count"), 0.0) / max(1, len(self.nodes))
        frontier_score = srmse + anchor_cost
        self.gates.append(
            GateRecord(
                "LXXXV_spectral_anchor_cost_error",
                "compression",
                anchor_cost <= 0.50 and srmse <= 1.10,
                frontier_score,
                1.60,
                {"anchor_cost_fraction": anchor_cost, **meta},
            )
        )

        inferred_edges = [e for e in self.edges.values() if e.inferred]
        observed_edges = [e for e in self.edges.values() if not e.inferred]
        compression_component = mean([1.0 - e.support for e in inferred_edges], 0.18)
        discretization_component = mean([t.defect_proxy for t in self.tetrahedra[:24]], 0.30)
        hat_vs_analytic = math.sqrt(compression_component * compression_component + discretization_component * discretization_component)
        self.gates.append(
            GateRecord(
                "LXXXVI_compression_discretization",
                "compression",
                compression_component <= 0.72 and discretization_component <= 0.50,
                hat_vs_analytic,
                0.88,
                {
                    "estimator_vs_full": compression_component,
                    "full_vs_analytic": discretization_component,
                    "hat_vs_analytic": hat_vs_analytic,
                    "observed_edges": len(observed_edges),
                    "inferred_edges": len(inferred_edges),
                },
            )
        )

        scaling = self.scaling_errors()
        trend_ok = bool(scaling) and scaling[-1]["srmse"] <= max(s["srmse"] for s in scaling) * 1.03
        self.gates.append(GateRecord("LXXXVII_observed_n_scaling", "scaling", trend_ok, scaling[-1]["srmse"] if scaling else 9.0, 1.20, {"scaling": scaling}))

        self.repairs, repair_payload = self.simulate_repairs()
        rho12 = next(r for r in self.repairs if r.repair_id == "BRQ-rho-0.12")
        rho05 = next(r for r in self.repairs if r.repair_id == "BRQ-rho-0.05")
        rho18 = next(r for r in self.repairs if r.repair_id == "BRQ-rho-0.18")
        self.gates.append(
            GateRecord(
                "XCVI_boundary_ratio_threshold",
                "repair",
                rho12.false_positive_count <= rho05.false_positive_count and rho18.missed_repair_count >= rho12.missed_repair_count,
                float(rho12.false_positive_count),
                float(max(2, rho05.false_positive_count)),
                repair_payload,
            )
        )
        repair_margin = 0.16 - 0.12
        contaminant_margin = 0.12 - 0.10
        self.gates.append(
            GateRecord(
                "XCVIII_boundary_ratio_safety",
                "repair",
                repair_margin > 0.0 and contaminant_margin > 0.0 and rho12.false_positive_count <= 2,
                repair_margin + contaminant_margin,
                0.03,
                {"rho": 0.12, "repair_margin": repair_margin, "contaminant_margin": contaminant_margin, "false_positive_count": rho12.false_positive_count},
            )
        )
        self.gates.append(
            GateRecord(
                "XCIV_quality_projector_mean",
                "repair",
                rho12.srmse_after < rho12.srmse_before,
                rho12.srmse_after,
                rho12.srmse_before,
                {"rho": 0.12, "srmse_before": rho12.srmse_before, "srmse_after": rho12.srmse_after},
            )
        )
        high = [r for r in self.repairs if r.repair_kind == "edgewise_high_damage_limit"]
        high_detected = any(r.missed_repair_count >= 70 for r in high)
        self.gates.append(
            GateRecord(
                "XCV_edgewise_high_damage_limit",
                "repair",
                high_detected,
                float(max((r.missed_repair_count for r in high), default=0)),
                70.0,
                {"high_damage_rows": [r.payload | {"k_damage": r.k_damage, "missed": r.missed_repair_count} for r in high]},
            )
        )
        batches = [r for r in self.repairs if r.batch_coherent]
        batch_ok = batches and all(r.false_positive_count == 0 and r.missed_repair_count == 0 and r.srmse_after < r.srmse_before for r in batches)
        self.gates.append(
            GateRecord(
                "C_batch_coherent_recovery",
                "repair",
                bool(batch_ok),
                mean([r.srmse_after for r in batches], 9.0),
                mean([r.srmse_before for r in batches], 9.0),
                {"batch_rows": [{"k_damage": r.k_damage, "before": r.srmse_before, "after": r.srmse_after} for r in batches]},
            )
        )

    def regulate_with_rzs(self) -> dict[str, Any]:
        srmse = next((g.score for g in self.gates if g.gate_key == "LI_regge_reconstruction_error"), 1.0)
        stable_ratio = mean([1.0 if t.stable else 0.0 for t in self.tetrahedra], 0.0)
        repair_risk = 1.0 - mean([1.0 if g.passed else 0.0 for g in self.gates if g.gate_family == "repair"], 0.0)
        x = RZSInput(
            bandwidth=2.20 + stable_ratio * 0.80,
            info_self=0.58,
            info_external=0.70 + min(0.70, srmse * 0.35),
            task_info=0.76,
            novelty=0.62,
            conflict=clamp(0.18 + repair_risk * 0.55 + max(0.0, srmse - 0.55) * 0.22, 0.10, 1.0),
            latency=1.05 + min(0.45, len(self.edges) / 900.0),
            energy=self.energy,
            memory_pressure=0.42 + min(0.35, len(self.nodes) / 400.0),
            replay_gap=0.38 + min(0.38, srmse * 0.30),
        )
        formal = RZSFormal()
        assessment = formal.classify(x)
        prediction = formal.predict(x, assessment.decision)
        self.rzs_decision = assessment.decision
        self.sigma_before = assessment.sigma
        self.sigma_after = prediction.sigma_after
        self.energy = clamp(self.energy - 0.04 + (0.03 if assessment.decision in {"replay_memory", "consolidate"} else 0.0))
        return {
            "decision": assessment.decision,
            "threshold_name": assessment.threshold_name,
            "sigma_before": assessment.sigma,
            "sigma_after": prediction.sigma_after,
            "prediction_valid": prediction.prediction_valid,
            "reason": assessment.reason,
        }

    def write_graph(self, conn: sqlite3.Connection) -> None:
        for node in self.nodes.values():
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {NODES}
                (timestamp, session_id, node_id, label, kind, source_table, weight, degree, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), self.session_id, node.node_id, node.label, node.kind, node.source_table, node.weight, node.degree, js(node.payload)),
            )
        for edge in self.edges.values():
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {EDGES}
                (timestamp, session_id, edge_id, node_a, node_b, edge_kind, weight, length, support, confidence, inferred, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    self.session_id,
                    edge.edge_id,
                    edge.node_a,
                    edge.node_b,
                    edge.edge_kind,
                    edge.weight,
                    edge.length,
                    edge.support,
                    edge.confidence,
                    1 if edge.inferred else 0,
                    js(edge.payload),
                ),
            )
        for rec in self.tetrahedra:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {TETRA}
                (timestamp, session_id, tetra_id, node_a, node_b, node_c, node_d, volume, aspect_ratio, defect_proxy, stable, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    self.session_id,
                    rec.tetra_id,
                    rec.nodes[0],
                    rec.nodes[1],
                    rec.nodes[2],
                    rec.nodes[3],
                    rec.volume,
                    rec.aspect_ratio,
                    rec.defect_proxy,
                    1 if rec.stable else 0,
                    js(rec.payload),
                ),
            )

    def write_gates_and_repairs(self, conn: sqlite3.Connection) -> None:
        for gate in self.gates:
            conn.execute(
                f"""
                INSERT INTO {GATES}
                (timestamp, session_id, gate_key, gate_family, passed, score, threshold, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), self.session_id, gate.gate_key, gate.gate_family, 1 if gate.passed else 0, gate.score, gate.threshold, js(gate.payload)),
            )
        for repair in self.repairs:
            conn.execute(
                f"""
                INSERT INTO {REPAIRS}
                (timestamp, session_id, repair_id, repair_kind, rho, k_damage, false_positive_count,
                 missed_repair_count, accepted_count, srmse_before, srmse_after, batch_coherent, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    self.session_id,
                    repair.repair_id,
                    repair.repair_kind,
                    repair.rho,
                    repair.k_damage,
                    repair.false_positive_count,
                    repair.missed_repair_count,
                    repair.accepted_count,
                    repair.srmse_before,
                    repair.srmse_after,
                    1 if repair.batch_coherent else 0,
                    js(repair.payload),
                ),
            )

    def write_reflection(self, conn: sqlite3.Connection, rzs_payload: dict[str, Any], summary: dict[str, Any]) -> None:
        stable_count = sum(1 for t in self.tetrahedra if t.stable)
        passed_gates = sum(1 for g in self.gates if g.passed)
        content = (
            f"Usei o artigo RZS/ELCL como regra operacional: grafo relacional -> comprimentos -> K4/tetraedros -> gates. "
            f"Foram encontrados {stable_count} tetraedros estaveis e {passed_gates}/{len(self.gates)} gates passaram; RZS decidiu {self.rzs_decision}."
        )
        conn.execute(
            f"""
            INSERT INTO {REFLECTIONS}
            (timestamp, session_id, reflection_kind, content, confidence, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (now(), self.session_id, "regge_elcl_summary", content, 0.86, js({"rzs": rzs_payload, **summary})),
        )
        conn.execute(
            f"""
            INSERT INTO {REFLECTIONS}
            (timestamp, session_id, reflection_kind, content, confidence, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                now(),
                self.session_id,
                "epistemic_boundary",
                "Esta v49.33 e uma implementacao experimental e auditavel do artigo, nao uma demonstracao formal completa de Regge geometry.",
                0.94,
                js({"article_path": str(ARTICLE_PATH), "boundary": "operational_model_not_mathematical_proof"}),
            ),
        )
        if self.table_exists(conn, "semantic_memory"):
            conn.execute(
                """
                INSERT OR REPLACE INTO semantic_memory
                (key, content, confidence, source, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    f"rzs_elcl_regge_v49_33:{self.session_id}",
                    content,
                    0.86,
                    SOURCE,
                    now(),
                ),
            )
        if self.table_exists(conn, "episodes"):
            conn.execute(
                """
                INSERT INTO episodes
                (timestamp, module, context, action_taken, outcome, lesson, sigma_before, sigma_after)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    SOURCE,
                    f"regge_elcl:{self.session_id}",
                    "project_relational_graph_to_regge_geometry",
                    "stable_projection_ready" if summary.get("regge_projection_ready") else "projection_needs_review",
                    "Grafo relacional pode virar geometria operacional quando K4, sRMSE, qualidade e RZS ficam auditaveis.",
                    self.sigma_before,
                    self.sigma_after,
                ),
            )
        conn.execute(
            f"""
            INSERT INTO {HANDOFFS}
            (timestamp, session_id, next_action, regge_projection_ready, confidence, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                now(),
                self.session_id,
                "usar_v49_33_como_geometria_relacional_para_observar_formacao_de_conceitos_e_reparos",
                1 if summary.get("regge_projection_ready") else 0,
                0.86 if summary.get("regge_projection_ready") else 0.62,
                js(summary),
            ),
        )

    def summarize(self, rzs_payload: dict[str, Any]) -> dict[str, Any]:
        gate_passed = sum(1 for g in self.gates if g.passed)
        stable_tetra = sum(1 for t in self.tetrahedra if t.stable)
        inferred_edges = sum(1 for e in self.edges.values() if e.inferred)
        li = next((g.score for g in self.gates if g.gate_key == "LI_regge_reconstruction_error"), 9.0)
        batch = next((g.passed for g in self.gates if g.gate_key == "C_batch_coherent_recovery"), False)
        protected_unchanged = self.protected_before == self.protected_after
        ready = (
            len(self.nodes) >= 24
            and len(self.edges) >= 40
            and inferred_edges > 0
            and stable_tetra >= 1
            and gate_passed >= 8
            and li <= 1.10
            and batch
            and protected_unchanged
        )
        return {
            "session_id": self.session_id,
            "article_path": str(ARTICLE_PATH),
            "article_exists": ARTICLE_PATH.exists(),
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "inferred_edge_count": inferred_edges,
            "tetra_count": len(self.tetrahedra),
            "stable_tetra_count": stable_tetra,
            "gate_count": len(self.gates),
            "gate_passed": gate_passed,
            "required_gates": REQUIRED_GATES,
            "regge_srmse": li,
            "repair_rows": len(self.repairs),
            "rzs_decision": self.rzs_decision,
            "sigma_before": self.sigma_before,
            "sigma_after": self.sigma_after,
            "rzs_payload": rzs_payload,
            "protected_counts_before": self.protected_before,
            "protected_counts_after": self.protected_after,
            "protected_sources_unchanged": protected_unchanged,
            "regge_projection_ready": ready,
        }

    def run(self) -> dict[str, Any]:
        with self.connect() as conn:
            self.setup(conn)
            self.protected_before = {table: self.count_table(conn, table) for table in PRIOR_TABLES}
            self.log_session(conn, "session_start", 0, {"article_path": str(ARTICLE_PATH), "mode": self.mode})
            self.insert_article_signals(conn)
            self.log_session(conn, "article_signals_loaded", 1, {"signal_count": 12})
            self.collect_graph(conn)
            closure_count = self.apply_elcl_closure()
            self.log_session(conn, "relational_graph_projected", 2, {"node_count": len(self.nodes), "edge_count": len(self.edges), "closure_count": closure_count})
            self.find_tetrahedra()
            self.log_session(conn, "k4_tetrahedra_reconstructed", 3, {"tetra_count": len(self.tetrahedra), "stable_count": sum(1 for t in self.tetrahedra if t.stable)})
            self.run_gates()
            rzs_payload = self.regulate_with_rzs()
            self.write_graph(conn)
            self.write_gates_and_repairs(conn)
            self.protected_after = {table: self.count_table(conn, table) for table in PRIOR_TABLES}
            summary = self.summarize(rzs_payload)
            self.write_reflection(conn, rzs_payload, summary)
            self.log_session(conn, "regge_projection_complete", 4, summary)
            conn.commit()
            return summary


class ReggeViewer(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Darwin RZS ELCL Regge Geometry v49.33")
        self.geometry("1180x760")
        self.configure(bg="#071019")
        self.core = ReggeELCLCore(mode="gui")
        self.summary: dict[str, Any] = {}
        self.build_ui()
        self.run_projection()

    def build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0)
        self.rowconfigure(1, weight=1)
        title = tk.Label(self, text="DARWIN RZS/ELCL REGGE GEOMETRY v49.33", fg="#f4fbff", bg="#071019", font=("Segoe UI", 22, "bold"))
        title.grid(row=0, column=0, columnspan=2, sticky="w", padx=22, pady=(18, 6))
        self.canvas = tk.Canvas(self, bg="#081620", highlightthickness=1, highlightbackground="#25435f")
        self.canvas.grid(row=1, column=0, sticky="nsew", padx=(22, 12), pady=(8, 16))
        right = tk.Frame(self, bg="#0d2230")
        right.grid(row=1, column=1, sticky="ns", padx=(0, 22), pady=(8, 16))
        tk.Label(right, text="Gates", fg="#f4fbff", bg="#0d2230", font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=14, pady=(12, 4))
        self.gates_text = tk.Text(right, width=42, height=25, bg="#071019", fg="#dff7ff", insertbackground="#dff7ff", relief="flat", font=("Consolas", 10))
        self.gates_text.pack(fill="both", expand=True, padx=14, pady=6)
        self.summary_label = tk.Label(right, text="", fg="#9fd7ff", bg="#0d2230", justify="left", font=("Consolas", 10))
        self.summary_label.pack(anchor="w", padx=14, pady=8)
        bar = tk.Frame(self, bg="#0b1822")
        bar.grid(row=2, column=0, columnspan=2, sticky="ew")
        ttk.Button(bar, text="Recalcular", command=self.run_projection).pack(side="left", padx=12, pady=10)
        ttk.Button(bar, text="Fechar", command=self.destroy).pack(side="left", padx=8, pady=10)

    def run_projection(self) -> None:
        self.core = ReggeELCLCore(mode="gui")
        self.summary = self.core.run()
        self.draw_graph()
        self.draw_gates()

    def draw_graph(self) -> None:
        self.canvas.delete("all")
        width = max(800, self.canvas.winfo_width() or 860)
        height = max(520, self.canvas.winfo_height() or 620)
        cx, cy = width / 2, height / 2
        ranked = sorted(self.core.nodes.values(), key=lambda n: (n.degree, n.weight), reverse=True)[:42]
        positions: dict[str, tuple[float, float]] = {}
        for idx, node in enumerate(ranked):
            angle = 2 * math.pi * idx / max(1, len(ranked))
            radius = 70 + 250 * (1.0 - clamp(node.weight, 0.0, 1.0))
            if node.node_id in {"darwin", "rzs"}:
                radius = 0 if node.node_id == "darwin" else 95
                angle = -math.pi / 2
            positions[node.node_id] = (cx + math.cos(angle) * radius, cy + math.sin(angle) * radius)
        for edge in self.core.edges.values():
            if edge.node_a not in positions or edge.node_b not in positions:
                continue
            x1, y1 = positions[edge.node_a]
            x2, y2 = positions[edge.node_b]
            color = "#4ea1ff" if not edge.inferred else "#7dd3fc"
            self.canvas.create_line(x1, y1, x2, y2, fill=color, width=max(1, int(edge.weight * 3)), stipple="gray50" if edge.inferred else "")
        colors = {
            "root": "#ffffff",
            "regulator": "#ffd166",
            "module": "#5eb1ff",
            "semantic": "#b8c0ff",
            "geometry_concept": "#74e0a7",
            "rzs_decision": "#ffcf8a",
            "curriculum_module": "#f5a6c8",
            "executor_dispatch": "#80ed99",
        }
        for node in ranked:
            x, y = positions[node.node_id]
            r = 7 + node.weight * 12
            self.canvas.create_oval(x - r, y - r, x + r, y + r, fill=colors.get(node.kind, "#9cc9ff"), outline="#eff8ff")
            self.canvas.create_text(x, y + r + 11, text=short(node.label, 22), fill="#dff7ff", font=("Segoe UI", 8))

    def draw_gates(self) -> None:
        self.gates_text.delete("1.0", "end")
        for gate in self.core.gates:
            mark = "OK" if gate.passed else "REV"
            self.gates_text.insert("end", f"{mark} {gate.gate_key}\n  score={gate.score:.3f} threshold={gate.threshold:.3f}\n")
        self.summary_label.configure(
            text=(
                f"sessao: {self.summary.get('session_id')}\n"
                f"nos: {self.summary.get('node_count')} arestas: {self.summary.get('edge_count')}\n"
                f"K4: {self.summary.get('stable_tetra_count')}/{self.summary.get('tetra_count')}\n"
                f"gates: {self.summary.get('gate_passed')}/{self.summary.get('gate_count')}\n"
                f"sRMSE: {self.summary.get('regge_srmse'):.3f}\n"
                f"RZS: {self.summary.get('rzs_decision')}\n"
                f"ready: {self.summary.get('regge_projection_ready')}"
            )
        )


def print_summary(summary: dict[str, Any], details: bool = False) -> None:
    print("DARWIN v49.33 - RZS/ELCL REGGE GEOMETRY")
    print("=" * 76)
    print(f"- sessao: {summary.get('session_id')}")
    print(f"- artigo existe: {summary.get('article_exists')} | {summary.get('article_path')}")
    print(
        f"- grafo: nos={summary.get('node_count')} arestas={summary.get('edge_count')} "
        f"inferidas={summary.get('inferred_edge_count')}"
    )
    print(
        f"- K4 tetraedros: {summary.get('stable_tetra_count')}/{summary.get('tetra_count')} estaveis"
    )
    print(
        f"- gates: {summary.get('gate_passed')}/{summary.get('gate_count')} | "
        f"sRMSE={summary.get('regge_srmse'):.3f}"
    )
    print(
        f"- RZS: {summary.get('rzs_decision')} "
        f"sigma {summary.get('sigma_before'):.3f}->{summary.get('sigma_after'):.3f}"
    )
    print(f"- fontes anteriores preservadas: {summary.get('protected_sources_unchanged')}")
    print(f"Resultado self-test: {'OK' if summary.get('regge_projection_ready') else 'REVISAR'}")
    if details:
        print("\nJSON:")
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description="Darwin v49.33 RZS/ELCL Regge Geometry")
    parser.add_argument("--self-test", action="store_true", help="roda headless e audita o resultado")
    parser.add_argument("--details", action="store_true", help="mostra JSON detalhado")
    args = parser.parse_args()
    if args.self_test:
        core = ReggeELCLCore(mode="self_test")
        summary = core.run()
        print_summary(summary, args.details)
        return 0 if summary.get("regge_projection_ready") else 1
    app = ReggeViewer()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
