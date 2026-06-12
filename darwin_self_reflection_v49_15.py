from __future__ import annotations

"""
DARWIN v49.15 - Self Reflection Planner

Objetivo:
Depois de visualizar o grafo mental (v49.14), Darwin passa a usar
esse grafo para refletir sobre si: encontrar forcas, lacunas, riscos
e proximas metas de aprendizagem. O plano e gravado no darwin.db e
regulado pelo RZS.

Uso:
    py darwin_self_reflection_v49_15.py
    py darwin_self_reflection_v49_15.py --self-test --details
"""

import argparse
import json
import math
import random
import sqlite3
import time
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tkinter import ttk
from typing import Any

from darwin_mind_graph_v49_14 import MindGraph, MindGraphBuilder
from darwin_rzs_nervous_system_v49_3 import RZSFormal, RZSInput


DB = Path("darwin_home") / "darwin.db"

REFL_SESSIONS = "mind_reflection_sessions_v49_15"
REFL_FINDINGS = "mind_reflection_findings_v49_15"
REFL_GOALS = "mind_learning_goals_v49_15"
REFL_REHEARSALS = "mind_goal_rehearsals_v49_15"


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


def short(text: str, limit: int = 80) -> str:
    clean = " ".join(str(text).split())
    return clean if len(clean) <= limit else clean[: limit - 1] + "..."


@dataclass
class ReflectionFinding:
    finding_id: str
    finding_kind: str
    module_key: str
    target_node_id: str
    score: float
    summary: str
    evidence: dict[str, Any]


@dataclass
class LearningGoal:
    goal_id: str
    module_key: str
    target_node_id: str
    goal_kind: str
    priority: float
    action_plan: str
    success_criterion: str
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    status: str = "proposed"


class SelfReflectionStore:
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
                CREATE TABLE IF NOT EXISTS {REFL_SESSIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    reflection_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    graph_nodes INTEGER NOT NULL DEFAULT 0,
                    graph_edges INTEGER NOT NULL DEFAULT 0,
                    mode TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {REFL_FINDINGS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    reflection_id TEXT NOT NULL,
                    finding_id TEXT NOT NULL UNIQUE,
                    finding_kind TEXT NOT NULL,
                    module_key TEXT NOT NULL,
                    target_node_id TEXT NOT NULL,
                    score REAL NOT NULL DEFAULT 0.0,
                    summary TEXT NOT NULL,
                    evidence_json TEXT NOT NULL DEFAULT '{{}}',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {REFL_GOALS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    reflection_id TEXT NOT NULL,
                    goal_id TEXT NOT NULL UNIQUE,
                    module_key TEXT NOT NULL,
                    target_node_id TEXT NOT NULL,
                    goal_kind TEXT NOT NULL,
                    priority REAL NOT NULL DEFAULT 0.0,
                    action_plan TEXT NOT NULL,
                    success_criterion TEXT NOT NULL,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL DEFAULT 0.0,
                    sigma_after REAL NOT NULL DEFAULT 0.0,
                    status TEXT NOT NULL DEFAULT 'proposed',
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );

                CREATE TABLE IF NOT EXISTS {REFL_REHEARSALS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    reflection_id TEXT NOT NULL,
                    goal_id TEXT NOT NULL,
                    rehearsal_id TEXT NOT NULL UNIQUE,
                    step_index INTEGER NOT NULL,
                    step_text TEXT NOT NULL,
                    predicted_effect TEXT NOT NULL,
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

    def log_session(self, reflection_id: str, phase: str, nodes: int, edges: int, mode: str, payload: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {REFL_SESSIONS} (
                    timestamp, reflection_id, phase, graph_nodes,
                    graph_edges, mode, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), reflection_id, phase, nodes, edges, mode, js(payload or {})),
            )
            conn.commit()

    def log_finding(self, reflection_id: str, finding: ReflectionFinding) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {REFL_FINDINGS} (
                    timestamp, reflection_id, finding_id, finding_kind,
                    module_key, target_node_id, score, summary,
                    evidence_json, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    reflection_id,
                    finding.finding_id,
                    finding.finding_kind,
                    finding.module_key,
                    finding.target_node_id,
                    finding.score,
                    finding.summary,
                    js(finding.evidence),
                    js({"summary": finding.summary}),
                ),
            )
            conn.commit()

    def log_goal(self, reflection_id: str, goal: LearningGoal) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {REFL_GOALS} (
                    timestamp, reflection_id, goal_id, module_key,
                    target_node_id, goal_kind, priority, action_plan,
                    success_criterion, rzs_decision, sigma_before,
                    sigma_after, status, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(),
                    reflection_id,
                    goal.goal_id,
                    goal.module_key,
                    goal.target_node_id,
                    goal.goal_kind,
                    goal.priority,
                    goal.action_plan,
                    goal.success_criterion,
                    goal.rzs_decision,
                    goal.sigma_before,
                    goal.sigma_after,
                    goal.status,
                    js({"priority": goal.priority}),
                ),
            )
            conn.commit()

    def log_rehearsal(self, reflection_id: str, goal_id: str, step_index: int, step_text: str, predicted_effect: str) -> None:
        rehearsal_id = f"rehearsal:{goal_id}:{step_index:02d}"
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {REFL_REHEARSALS} (
                    timestamp, reflection_id, goal_id, rehearsal_id,
                    step_index, step_text, predicted_effect, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), reflection_id, goal_id, rehearsal_id, step_index, step_text, predicted_effect, js({})),
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
                (key, content, clamp(confidence, 0.0, 0.99), "darwin_self_reflection_v49_15", now()),
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
                (now(), "darwin_self_reflection_v49_15", context, action, outcome, lesson, sigma_before, sigma_after),
            )
            conn.commit()

    def recognizer_missing_count(self) -> int:
        with self.connect() as conn:
            total = 0
            if self.table_exists(conn, "voice_first_word_sessions_v49_10"):
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM voice_first_word_sessions_v49_10 WHERE phase IN ('recognizer_missing','recognizer_error')"
                ).fetchone()
                total += int(row["n"]) if row else 0
            if self.table_exists(conn, "voice_presence_events_v49_9"):
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM voice_presence_events_v49_9 WHERE event_kind='listener_error'"
                ).fetchone()
                total += int(row["n"]) if row else 0
        return total


class SelfReflectionPlanner:
    def __init__(self, store: SelfReflectionStore | None = None, seed: int = 4915, mode: str = "gui") -> None:
        self.store = store or SelfReflectionStore()
        self.rng = random.Random(seed)
        self.rzs = RZSFormal()
        self.mode = mode
        self.reflection_id = f"V4915-{int(time.time()) % 10_000_000}-{suffix(self.rng)}"
        self.graph: MindGraph = MindGraph()
        self.findings: list[ReflectionFinding] = []
        self.goals: list[LearningGoal] = []

    def reflect(self) -> dict[str, Any]:
        self.graph = MindGraphBuilder().build()
        self.store.log_session(
            self.reflection_id,
            "reflection_start",
            len(self.graph.nodes),
            len(self.graph.edges),
            self.mode,
            {"source": "mind_graph_v49_14"},
        )
        self.findings = self.analyze_graph()
        for finding in self.findings:
            self.store.log_finding(self.reflection_id, finding)
        self.goals = self.make_goals(self.findings)
        for goal in self.goals:
            self.store.log_goal(self.reflection_id, goal)
            for idx, (step, effect) in enumerate(self.rehearsal_steps(goal), 1):
                self.store.log_rehearsal(self.reflection_id, goal.goal_id, idx, step, effect)
        summary = self.complete_summary()
        self.store.log_session(
            self.reflection_id,
            "reflection_complete",
            len(self.graph.nodes),
            len(self.graph.edges),
            self.mode,
            summary,
        )
        self.store.write_memory(
            f"self_reflection_v49_15:{self.reflection_id}",
            (
                f"Darwin reflected on mind graph: nodes={len(self.graph.nodes)}, edges={len(self.graph.edges)}, "
                f"findings={len(self.findings)}, goals={len(self.goals)}, top_goal={self.goals[0].goal_kind if self.goals else 'none'}."
            ),
            0.82,
        )
        if self.goals:
            self.store.write_episode(
                f"self_reflection:{self.reflection_id}",
                "inspect_mind_graph",
                f"goals={len(self.goals)} top={self.goals[0].goal_kind}",
                "A mind becomes more useful when it can inspect its own graph and choose the next training need.",
                self.goals[0].sigma_before,
                self.goals[0].sigma_after,
            )
        return {"reflection_id": self.reflection_id, **summary}

    def node_degree(self) -> dict[str, int]:
        degree = {node_id: 0 for node_id in self.graph.nodes}
        for edge in self.graph.edges:
            degree[edge.source] = degree.get(edge.source, 0) + 1
            degree[edge.target] = degree.get(edge.target, 0) + 1
        return degree

    def count_kind(self, kind: str) -> int:
        return sum(1 for node in self.graph.nodes.values() if node.kind == kind)

    def children_of(self, parent_id: str) -> list[str]:
        return [node.node_id for node in self.graph.nodes.values() if node.parent_id == parent_id]

    def analyze_graph(self) -> list[ReflectionFinding]:
        findings: list[ReflectionFinding] = []
        degree = self.node_degree()

        def add(kind: str, module: str, target: str, score: float, summary: str, evidence: dict[str, Any]) -> None:
            idx = len(findings) + 1
            findings.append(
                ReflectionFinding(
                    finding_id=f"finding:{self.reflection_id}:{idx:03d}",
                    finding_kind=kind,
                    module_key=module,
                    target_node_id=target,
                    score=clamp(score),
                    summary=summary,
                    evidence=evidence,
                )
            )

        nodes = len(self.graph.nodes)
        edges = len(self.graph.edges)
        add("strength", "mind_graph", "darwin", min(1.0, nodes / 140.0), "O grafo mental ja integra muitos marcos da jornada.", {"nodes": nodes, "edges": edges})

        geometry_concepts = self.count_kind("concept")
        if geometry_concepts >= 20:
            add("strength", "geometry", "geometry", 0.82, "Geometria tem curriculo amplo e conceitos consolidados.", {"concept_nodes": geometry_concepts})
        else:
            add("gap", "geometry", "geometry", 0.72, "Geometria ainda tem poucos conceitos no grafo.", {"concept_nodes": geometry_concepts})

        word_nodes = self.count_kind("word")
        if word_nodes < 12:
            add("gap", "first_words", "first_words", 0.78, "Vocabulario inicial ainda e pequeno para uma presenca relacional.", {"word_nodes": word_nodes, "target": 12})
        else:
            add("strength", "first_words", "first_words", 0.70, "Vocabulario inicial tem massa suficiente para novas associacoes.", {"word_nodes": word_nodes})

        entity_nodes = self.count_kind("entity")
        grounded_edges = [e for e in self.graph.edges if e.kind in {"grounded_reference", "refers_to"}]
        if entity_nodes >= 4 and len(grounded_edges) >= 4:
            add("strength", "joint_attention", "joint_attention", 0.76, "Atencao compartilhada ja liga palavras a entidades.", {"entities": entity_nodes, "grounded_edges": len(grounded_edges)})
        else:
            add("gap", "joint_attention", "joint_attention", 0.76, "Faltam referencias palavra-objeto suficientes.", {"entities": entity_nodes, "grounded_edges": len(grounded_edges)})

        symbol_nodes = self.count_kind("symbol")
        if symbol_nodes >= 8:
            add("strength", "memory_cards", "memory_cards", 0.74, "Memoria observacional ja resolve jogo de pares.", {"symbols": symbol_nodes})

        missing_recognizer = self.store.recognizer_missing_count()
        if missing_recognizer:
            add("risk", "voice", "first_words", 0.88, "Reconhecimento de fala real do Windows falhou ou esta ausente.", {"missing_events": missing_recognizer})

        sparse = sorted(
            [node for node in self.graph.nodes.values() if node.kind in {"memory", "concept", "word", "entity"}],
            key=lambda node: (degree.get(node.node_id, 0), node.weight),
        )
        for node in sparse[:5]:
            if degree.get(node.node_id, 0) <= 1:
                add("gap", node.parent_id or "semantic", node.node_id, 0.58, f"No pouco conectado: {node.label}.", {"degree": degree.get(node.node_id, 0), "kind": node.kind})

        semantic_nodes = self.children_of("semantic")
        if len(semantic_nodes) >= 25:
            add("opportunity", "semantic", "semantic", 0.66, "Ha muita memoria semantica; ela pode guiar conversa e treino.", {"semantic_children": len(semantic_nodes)})

        companion_intents = self.children_of("companion")
        if companion_intents and len(companion_intents) < 8:
            add("gap", "companion", "companion", 0.63, "Companion ainda tem poucas intencoes conversacionais.", {"intent_nodes": len(companion_intents)})

        return sorted(findings, key=lambda f: (-f.score, f.finding_kind, f.module_key))

    def rzs_for_goal(self, finding: ReflectionFinding) -> tuple[str, float, float]:
        novelty = 0.38 + finding.score * 0.45
        conflict = 0.18
        memory_pressure = 0.34
        if finding.finding_kind == "risk":
            conflict += 0.36
            memory_pressure += 0.10
        if finding.finding_kind == "gap":
            conflict += 0.22
            memory_pressure += 0.18
        x = RZSInput(
            bandwidth=4.3,
            info_self=0.38,
            info_external=0.42,
            task_info=0.68 + finding.score * 0.26,
            novelty=clamp(novelty),
            conflict=clamp(conflict),
            latency=0.86 + finding.score * 0.18,
            energy=0.84,
            memory_pressure=clamp(memory_pressure),
            replay_gap=0.54 if finding.finding_kind in {"gap", "risk"} else 0.28,
        )
        assessment = self.rzs.classify(x)
        y = self.rzs.apply_action_model(x, assessment.decision)
        return assessment.decision, assessment.sigma, self.rzs.sigma(y)

    def make_goals(self, findings: list[ReflectionFinding]) -> list[LearningGoal]:
        goals: list[LearningGoal] = []
        used: set[str] = set()

        def add_from_finding(finding: ReflectionFinding, goal_kind: str, action: str, criterion: str, bonus: float = 0.0) -> None:
            if goal_kind in used:
                return
            used.add(goal_kind)
            decision, sigma_before, sigma_after = self.rzs_for_goal(finding)
            idx = len(goals) + 1
            goals.append(
                LearningGoal(
                    goal_id=f"goal:{self.reflection_id}:{idx:03d}",
                    module_key=finding.module_key,
                    target_node_id=finding.target_node_id,
                    goal_kind=goal_kind,
                    priority=clamp(finding.score + bonus),
                    action_plan=action,
                    success_criterion=criterion,
                    rzs_decision=decision,
                    sigma_before=sigma_before,
                    sigma_after=sigma_after,
                )
            )

        for finding in findings:
            if finding.finding_kind == "risk" and finding.module_key == "voice":
                add_from_finding(
                    finding,
                    "repair_real_voice_input",
                    "Criar diagnostico guiado para instalar/validar reconhecimento de fala do Windows e retestar primeiras palavras reais.",
                    "Uma sessao v49.10 registra recognizer_ready e pelo menos 5 palavras reais reconhecidas.",
                    0.08,
                )
            elif finding.finding_kind == "gap" and finding.module_key == "first_words":
                add_from_finding(
                    finding,
                    "expand_first_words",
                    "Adicionar novas palavras basicas e repetir associacoes sonoras com significado relacional.",
                    "O vocabulario v49.10 chega a pelo menos 12 palavras com confianca crescente.",
                )
            elif finding.finding_kind == "gap" and finding.module_key == "companion":
                add_from_finding(
                    finding,
                    "expand_companion_intents",
                    "Ensinar novas intencoes de dialogo: pergunta, duvida, correcao, brincadeira, pedido e lembranca.",
                    "O companion registra pelo menos 10 intents e usa memoria para responder.",
                )
            elif finding.finding_kind == "opportunity" and finding.module_key == "semantic":
                add_from_finding(
                    finding,
                    "semantic_memory_to_behavior",
                    "Usar memoria semantica para escolher automaticamente um treino ou resposta.",
                    "Um loop escolhe acao cognitiva a partir de memoria semantica recuperada.",
                )
            elif finding.finding_kind == "strength" and finding.module_key == "memory_cards":
                add_from_finding(
                    finding,
                    "increase_memory_game_difficulty",
                    "Aumentar dificuldade do jogo de memoria e medir desempenho em multiplos embaralhamentos.",
                    "Darwin completa pelo menos 3 jogos embaralhados sem acesso ao baralho.",
                )
            elif finding.finding_kind == "strength" and finding.module_key == "joint_attention":
                add_from_finding(
                    finding,
                    "turn_joint_attention_into_requests",
                    "Transformar palavra-objeto em pedidos simples: apontar, escolher, negar, ajudar.",
                    "Darwin interpreta uma palavra como pedido contextual e escolhe foco correto.",
                )

        if not goals and findings:
            finding = findings[0]
            add_from_finding(
                finding,
                "continue_balanced_training",
                "Escolher o modulo com menor conectividade e criar novo treino curto.",
                "O proximo treino reduz uma lacuna de conectividade no grafo.",
            )
        return sorted(goals, key=lambda g: -g.priority)[:8]

    def rehearsal_steps(self, goal: LearningGoal) -> list[tuple[str, str]]:
        if goal.goal_kind == "repair_real_voice_input":
            return [
                ("Detectar reconhecedores de fala instalados no Windows.", "separa erro de ambiente de erro cognitivo"),
                ("Mostrar instrucoes locais quando pt-BR nao estiver disponivel.", "reduz frustracao e mantem o loop vivo"),
                ("Retestar mamae, papai, Felipe e Darwin por microfone real.", "conecta som real ao bercario v49.10"),
            ]
        if goal.goal_kind == "expand_first_words":
            return [
                ("Adicionar palavras de necessidade: comer, dormir, dor, vem, pega.", "aumenta vocabulário funcional"),
                ("Repetir cada palavra em ciclos com confianca baixa e alta.", "mede aprendizagem por repeticao"),
                ("Criar significados relacionais e episodios.", "liga som a experiencia"),
            ]
        if goal.goal_kind == "increase_memory_game_difficulty":
            return [
                ("Rodar tres embaralhamentos independentes.", "mede generalizacao"),
                ("Registrar curva de erros por jogo.", "separa sorte de memoria"),
                ("Aumentar para 5x4 quando 4x4 estabilizar.", "escala dificuldade"),
            ]
        if goal.goal_kind == "semantic_memory_to_behavior":
            return [
                ("Recuperar memorias por foco atual.", "aproxima memoria de acao"),
                ("Escolher treino pelo menor vinculo do grafo.", "transforma grafo em controle"),
                ("Registrar predicao antes e resultado depois.", "mantem ciencia no loop"),
            ]
        return [
            ("Selecionar exemplos simples.", "reduz carga inicial"),
            ("Executar tentativa com erro permitido.", "gera experiencia"),
            ("Consolidar no grafo e no banco.", "fecha ciclo de aprendizagem"),
        ]

    def complete_summary(self) -> dict[str, Any]:
        by_kind: dict[str, int] = {}
        for finding in self.findings:
            by_kind[finding.finding_kind] = by_kind.get(finding.finding_kind, 0) + 1
        return {
            "reflection_complete": True,
            "graph_nodes": len(self.graph.nodes),
            "graph_edges": len(self.graph.edges),
            "finding_count": len(self.findings),
            "goal_count": len(self.goals),
            "finding_kinds": by_kind,
            "top_goals": [g.goal_kind for g in self.goals[:5]],
            "rzs_decisions": sorted({g.rzs_decision for g in self.goals}),
        }


class SelfReflectionApp:
    BG = "#071018"
    PANEL = "#10202d"
    INK = "#edf7fb"
    MUTED = "#93aabd"
    GREEN = "#75e7a8"
    AMBER = "#f2bf72"
    RED = "#ff707a"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Darwin Self Reflection v49.15")
        self.root.geometry("1160x780")
        self.root.minsize(960, 660)
        self.root.configure(bg=self.BG)
        self.planner = SelfReflectionPlanner(mode="gui")
        self.result: dict[str, Any] = {}

        top = tk.Frame(root, bg=self.PANEL)
        top.pack(fill="x")
        ttk.Button(top, text="Refletir agora", command=self.reflect).pack(side="left", padx=(14, 8), pady=10)
        ttk.Button(top, text="Atualizar", command=self.reflect).pack(side="left", padx=(0, 8), pady=10)
        self.status_var = tk.StringVar(value="pronto para refletir sobre o grafo")
        tk.Label(top, textvariable=self.status_var, bg=self.PANEL, fg=self.MUTED, font=("Segoe UI", 10)).pack(side="left", padx=8)

        body = tk.Frame(root, bg=self.BG)
        body.pack(fill="both", expand=True)
        left = tk.Frame(body, bg=self.BG)
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(body, bg=self.BG)
        right.pack(side="right", fill="both", expand=True)

        tk.Label(left, text="Achados", bg=self.BG, fg=self.INK, font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=12, pady=(12, 4))
        self.findings_box = tk.Listbox(left, bg="#061019", fg=self.INK, selectbackground="#214866", relief="flat", font=("Segoe UI", 10))
        self.findings_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.findings_box.bind("<<ListboxSelect>>", self.show_finding)

        tk.Label(right, text="Metas propostas", bg=self.BG, fg=self.INK, font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=12, pady=(12, 4))
        self.goals_box = tk.Listbox(right, bg="#061019", fg=self.INK, selectbackground="#214866", relief="flat", font=("Segoe UI", 10))
        self.goals_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.goals_box.bind("<<ListboxSelect>>", self.show_goal)

        self.details = tk.Text(root, height=10, bg="#061019", fg=self.INK, insertbackground=self.INK, relief="flat", wrap="word", font=("Segoe UI", 10))
        self.details.pack(fill="x")
        self.details.config(state="disabled")
        self.reflect()

    def reflect(self) -> None:
        self.planner = SelfReflectionPlanner(mode="gui")
        self.result = self.planner.reflect()
        self.findings_box.delete(0, "end")
        self.goals_box.delete(0, "end")
        for finding in self.planner.findings:
            self.findings_box.insert("end", f"[{finding.finding_kind}] {finding.module_key}: {short(finding.summary, 70)}")
        for goal in self.planner.goals:
            self.goals_box.insert("end", f"{goal.priority:.2f}  {goal.goal_kind}  RZS={goal.rzs_decision}")
        self.status_var.set(
            f"reflexao={self.result['reflection_id']}  achados={len(self.planner.findings)}  metas={len(self.planner.goals)}"
        )
        self.write_details(self.summary_text())

    def summary_text(self) -> str:
        lines = [
            "Resumo da reflexao",
            "===================",
            f"grafo: {self.result.get('graph_nodes')} nos, {self.result.get('graph_edges')} arestas",
            f"achados: {self.result.get('finding_count')}",
            f"metas: {self.result.get('goal_count')}",
            f"top goals: {', '.join(self.result.get('top_goals', []))}",
            "",
            "Clique em um achado ou meta para ver detalhes.",
        ]
        return "\n".join(lines)

    def selected_index(self, box: tk.Listbox) -> int | None:
        got = box.curselection()
        return int(got[0]) if got else None

    def show_finding(self, _event: tk.Event) -> None:
        idx = self.selected_index(self.findings_box)
        if idx is None or idx >= len(self.planner.findings):
            return
        finding = self.planner.findings[idx]
        lines = [
            finding.summary,
            "=" * min(48, max(8, len(finding.summary))),
            f"id: {finding.finding_id}",
            f"tipo: {finding.finding_kind}",
            f"modulo: {finding.module_key}",
            f"alvo: {finding.target_node_id}",
            f"score: {finding.score:.3f}",
            "",
            "Evidencia:",
        ]
        for key, value in sorted(finding.evidence.items()):
            lines.append(f"- {key}: {value}")
        self.write_details("\n".join(lines))

    def show_goal(self, _event: tk.Event) -> None:
        idx = self.selected_index(self.goals_box)
        if idx is None or idx >= len(self.planner.goals):
            return
        goal = self.planner.goals[idx]
        steps = self.planner.rehearsal_steps(goal)
        lines = [
            goal.goal_kind,
            "=" * len(goal.goal_kind),
            f"id: {goal.goal_id}",
            f"modulo: {goal.module_key}",
            f"alvo: {goal.target_node_id}",
            f"prioridade: {goal.priority:.3f}",
            f"RZS: {goal.rzs_decision}  sigma {goal.sigma_before:.3f}->{goal.sigma_after:.3f}",
            "",
            "Plano:",
            goal.action_plan,
            "",
            "Criterio de sucesso:",
            goal.success_criterion,
            "",
            "Ensaio:",
        ]
        for idx, (step, effect) in enumerate(steps, 1):
            lines.append(f"{idx}. {step} -> {effect}")
        self.write_details("\n".join(lines))

    def write_details(self, text: str) -> None:
        self.details.config(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.config(state="disabled")


def run_self_test(details: bool = False) -> dict[str, Any]:
    planner = SelfReflectionPlanner(mode="self_test")
    result = planner.reflect()
    report = {
        **result,
        "has_gap": any(f.finding_kind == "gap" for f in planner.findings),
        "has_strength": any(f.finding_kind == "strength" for f in planner.findings),
        "has_goal": bool(planner.goals),
        "has_rzs": all(g.rzs_decision for g in planner.goals),
    }
    report["ok"] = (
        result["graph_nodes"] >= 80
        and result["graph_edges"] >= 80
        and result["finding_count"] >= 5
        and result["goal_count"] >= 3
        and report["has_gap"]
        and report["has_strength"]
        and report["has_rzs"]
    )
    if details:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"DARWIN v49.15 self reflection self-test: "
            f"reflection={result['reflection_id']} goals={result['goal_count']} ok={report['ok']}"
        )
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin Self Reflection Planner v49.15")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        report = run_self_test(details=args.details)
        return 0 if report["ok"] else 2
    root = tk.Tk()
    SelfReflectionApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
