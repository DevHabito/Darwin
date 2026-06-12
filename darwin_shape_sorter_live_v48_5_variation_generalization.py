from __future__ import annotations

"""
DARWIN v48.5 — Generalização por Variação

Objetivo:
Darwin deve aplicar as estratégias aprendidas sem depender de nomes fixos
como piece_triangle ou hole_square.

Nesta versão:
- nomes de peças e buracos são gerados com sufixos variáveis;
- medidas, tolerâncias e ângulos variam dentro de faixas seguras;
- o diagnóstico valida por papéis, razões de falha e estratégias, não por IDs fixos.

Uso:
    py darwin_shape_sorter_live_v48_5_variation_generalization.py

Tabela:
    geometry_live_actions_v48_5

Critério pedagógico:
    contour_mismatch  -> try_alternate_hole
    size_mismatch     -> reject_pair_size
    depth_mismatch    -> reject_pair_depth
    uncertain_failure -> cautious_exploration
    rotation_mismatch -> rotate_piece
"""

import json
import math
import random
import sqlite3
import time
import tkinter as tk
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from tkinter import ttk


DB_PATH = Path("darwin_home") / "darwin.db"
TABLE = "geometry_live_actions_v48_5"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def rand_suffix(rng: random.Random) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(rng.choice(alphabet) for _ in range(5))


@dataclass
class Piece:
    piece_id: str
    role: str
    family: str
    x: float
    y: float
    home_x: float
    home_y: float
    size: float
    depth: float
    angle: float
    color: str
    placed: bool = False
    rejected: bool = False


@dataclass
class Hole:
    hole_id: str
    role: str
    family: str
    x: float
    y: float
    size: float
    depth: float
    angle: float = 0.0
    tol: float = 5.0
    filled: bool = False
    filled_by: str = ""


@dataclass
class Evaluation:
    scenario_id: str
    piece_id: str
    hole_id: str
    piece_role: str
    hole_role: str
    contour_match: bool
    size_match: bool
    depth_match: bool
    rotation_match: bool
    observed_fit: bool
    collision_detected: bool
    score: float
    failure_reason: str
    explanation: str


@dataclass
class Strategy:
    failure_reason: str
    recommendation: str
    explanation: str


class Memory:
    def __init__(self) -> None:
        self.enabled = True
        try:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {TABLE} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        scenario_id TEXT NOT NULL DEFAULT '',
                        action_kind TEXT NOT NULL,
                        piece_id TEXT NOT NULL DEFAULT '',
                        hole_id TEXT NOT NULL DEFAULT '',
                        piece_role TEXT NOT NULL DEFAULT '',
                        hole_role TEXT NOT NULL DEFAULT '',
                        failure_reason TEXT NOT NULL DEFAULT '',
                        recommendation TEXT NOT NULL DEFAULT '',
                        score REAL NOT NULL DEFAULT 0.0,
                        outcome TEXT NOT NULL DEFAULT '',
                        note TEXT NOT NULL DEFAULT '',
                        payload_json TEXT NOT NULL DEFAULT '{{}}'
                    )
                    """
                )
                conn.commit()
        except Exception:
            self.enabled = False

    def log(
        self,
        scenario_id: str,
        kind: str,
        piece: Piece | None = None,
        hole: Hole | None = None,
        score: float = 0.0,
        outcome: str = "",
        note: str = "",
        failure_reason: str = "",
        recommendation: str = "",
        payload=None,
    ) -> None:
        if not self.enabled:
            return
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    f"""
                    INSERT INTO {TABLE} (
                        timestamp, scenario_id, action_kind, piece_id, hole_id, piece_role, hole_role,
                        failure_reason, recommendation, score, outcome, note, payload_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        now_iso(),
                        scenario_id,
                        kind,
                        piece.piece_id if piece else "",
                        hole.hole_id if hole else "",
                        piece.role if piece else "",
                        hole.role if hole else "",
                        failure_reason,
                        recommendation,
                        score,
                        outcome,
                        note,
                        safe_json(payload or {}),
                    ),
                )
                conn.commit()
        except Exception:
            self.enabled = False


class DarwinPolicy:
    def __init__(self, memory: Memory) -> None:
        self.memory = memory
        self.failed_pairs: set[tuple[str, str]] = set()

    def rotation_match(self, piece: Piece, hole: Hole) -> bool:
        if piece.family in ("circle", "unknown"):
            return True

        symmetry = 90.0 if piece.family == "square" else 120.0
        delta = abs((piece.angle - hole.angle) % 360.0)
        if delta > 180.0:
            delta = 360.0 - delta
        remainder = min(delta % symmetry, symmetry - (delta % symmetry))
        return remainder <= 3.0

    def evaluate(self, scenario_id: str, piece: Piece, hole: Hole) -> Evaluation:
        if piece.family == "unknown":
            return Evaluation(
                scenario_id,
                piece.piece_id,
                hole.hole_id,
                piece.role,
                hole.role,
                contour_match=False,
                size_match=True,
                depth_match=True,
                rotation_match=True,
                observed_fit=False,
                collision_detected=True,
                score=0.50,
                failure_reason="uncertain_failure",
                explanation="forma parcialmente desconhecida; explorar com cautela antes de concluir",
            )

        contour = piece.family == hole.family
        size_ok = piece.size <= hole.size + hole.tol
        depth_ok = piece.depth <= hole.depth
        rot_ok = self.rotation_match(piece, hole)
        fit = contour and size_ok and depth_ok and rot_ok

        score = 0.0
        score += 0.42 if contour else 0.0
        score += 0.22 if size_ok else 0.0
        score += 0.20 if depth_ok else 0.0
        score += 0.16 if rot_ok else 0.0
        score = round(score, 3)

        if fit:
            reason = ""
            explanation = "compatível: inserir"
        elif not contour:
            reason = "contour_mismatch"
            explanation = "contorno incompatível; procurar buraco alternativo"
        elif not size_ok:
            reason = "size_mismatch"
            explanation = "peça maior do que a abertura tolerada; rejeitar par"
        elif not depth_ok:
            reason = "depth_mismatch"
            explanation = "profundidade incompatível; rejeitar inserção completa"
        elif not rot_ok:
            reason = "rotation_mismatch"
            explanation = "orientação incompatível; girar e reavaliar"
        else:
            reason = "uncertain_failure"
            explanation = "falha incerta; exploração cautelosa"

        return Evaluation(
            scenario_id,
            piece.piece_id,
            hole.hole_id,
            piece.role,
            hole.role,
            contour,
            size_ok,
            depth_ok,
            rot_ok,
            fit,
            not fit,
            score,
            reason,
            explanation,
        )

    def strategy_for(self, ev: Evaluation) -> Strategy:
        mapping = {
            "contour_mismatch": ("try_alternate_hole", "tentar outro buraco para a mesma peça"),
            "size_mismatch": ("reject_pair_size", "rejeitar o par por tamanho"),
            "depth_mismatch": ("reject_pair_depth", "rejeitar a inserção por profundidade"),
            "rotation_mismatch": ("rotate_piece", "girar a peça e reavaliar"),
            "uncertain_failure": ("cautious_exploration", "explorar com cautela, sem forçar"),
        }
        rec, exp = mapping.get(ev.failure_reason, ("cautious_exploration", "falha desconhecida; cautela"))
        return Strategy(ev.failure_reason, rec, exp)

    def record_failure_and_strategy(self, scenario_id: str, piece: Piece, hole: Hole, ev: Evaluation) -> Strategy:
        self.failed_pairs.add((piece.piece_id, hole.hole_id))
        self.memory.log(
            scenario_id,
            "error_memory_write",
            piece,
            hole,
            ev.score,
            "stored",
            ev.failure_reason,
            ev.failure_reason,
            "",
            {"evaluation": asdict(ev), "failed_pairs": sorted([list(x) for x in self.failed_pairs])},
        )
        strategy = self.strategy_for(ev)
        self.memory.log(
            scenario_id,
            "strategy_select",
            piece,
            hole,
            ev.score,
            "selected",
            strategy.recommendation,
            ev.failure_reason,
            strategy.recommendation,
            {"strategy": asdict(strategy), "source_error": asdict(ev)},
        )
        return strategy


class App:
    BG = "#EEF4FB"
    TEXT = "#172B44"
    MUTED = "#60758E"
    BLUE = "#3977E3"
    YELLOW = "#F2C94C"
    RED = "#EB5757"
    WOOD = "#DBB789"
    DARK = "#7D593A"
    GREEN = "#2DBE78"
    BAD = "#D9534F"
    PURPLE = "#9B8DE5"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("DARWIN v48.5 — generalização por variação")
        root.geometry("1280x800")
        root.configure(bg=self.BG)

        self.memory = Memory()
        self.policy = DarwinPolicy(self.memory)

        self.canvas = tk.Canvas(root, width=835, height=760, bg=self.BG, highlightthickness=0)
        self.canvas.pack(side="left", padx=12, pady=12)

        side = tk.Frame(root, bg=self.BG)
        side.pack(side="right", fill="both", expand=True, padx=(0, 12), pady=12)

        controls = tk.Frame(side, bg=self.BG)
        controls.pack(fill="x")
        ttk.Button(controls, text="Iniciar Auto", command=self.start).grid(row=0, column=0, padx=4, pady=4, sticky="ew")
        ttk.Button(controls, text="Pausar", command=self.pause).grid(row=0, column=1, padx=4, pady=4, sticky="ew")
        ttk.Button(controls, text="Passo", command=self.step).grid(row=0, column=2, padx=4, pady=4, sticky="ew")
        ttk.Button(controls, text="Novo cenário", command=self.new_scenario).grid(row=0, column=3, padx=4, pady=4, sticky="ew")
        for i in range(4):
            controls.grid_columnconfigure(i, weight=1)

        self.status_var = tk.StringVar(value="Pronto. Nomes, medidas e ângulos variam por cenário.")
        tk.Label(
            side,
            textvariable=self.status_var,
            bg="white",
            fg=self.TEXT,
            wraplength=405,
            justify="left",
            anchor="w",
            padx=10,
            pady=8,
            relief="solid",
            bd=1,
        ).pack(fill="x", pady=(8, 8))

        self.logic = tk.Text(side, height=17, wrap="word", bg="white", fg=self.TEXT, relief="solid", bd=1)
        self.logic.pack(fill="x", pady=(0, 8))
        self.logic.config(state="disabled")

        self.history = tk.Text(side, height=20, wrap="word", bg="#0D3B66", fg="#EAF7FF", relief="solid", bd=1)
        self.history.pack(fill="both", expand=True)
        self.history.config(state="disabled")

        self.auto = False
        self.phase = "idle"
        self.current = None
        self.counter = 0
        self.t = 0.0
        self.start_xy = (0.0, 0.0)
        self.back_xy = (0.0, 0.0)
        self.flash = ""
        self.flash_n = 0
        self.face = "neutral"
        self.stage = 0

        self.scenario_seed = int(time.time()) % 10_000_000
        self.setup_world(self.scenario_seed)
        self.write_logic("v48.5: aplicar a política a um cenário com nomes e medidas variáveis.\n")
        self.loop()

    def setup_world(self, seed: int) -> None:
        self.scenario_seed = seed
        self.scenario_id = f"V485-{seed}-{rand_suffix(random.Random(seed + 999))}"
        rng = random.Random(seed)

        self.policy.failed_pairs.clear()
        self.stage = 0
        self.phase = "idle"
        self.current = None
        self.face = "neutral"

        square_size = rng.randint(78, 88)
        triangle_size = rng.randint(80, 92)
        circle_size = rng.randint(78, 88)
        base_depth = round(rng.uniform(1.35, 1.65), 2)
        tolerance = round(rng.uniform(3.0, 6.0), 1)
        bad_angle = rng.choice([17, 29, 37, 44, 53, 61])

        suffixes = {key: rand_suffix(rng) for key in [
            "tri", "circ_big", "sq_deep", "unk", "circ", "sq_rot", "hsq", "htri", "hcirc"
        ]}

        self.holes = [
            Hole(f"aperture_{suffixes['hsq']}", "target_square", "square", 510, 370, square_size, base_depth, 0.0, tolerance),
            Hole(f"aperture_{suffixes['htri']}", "target_triangle", "triangle", 635, 370, triangle_size, base_depth, 0.0, tolerance),
            Hole(f"aperture_{suffixes['hcirc']}", "target_circle", "circle", 760, 370, circle_size, base_depth, 0.0, tolerance),
        ]

        self.pieces = [
            Piece(f"object_{suffixes['tri']}", "valid_triangle", "triangle", 135, 575, 135, 575, triangle_size - rng.randint(4, 8), base_depth - 0.2, 0.0, self.YELLOW),
            Piece(f"object_{suffixes['circ_big']}", "oversize_circle", "circle", 265, 575, 265, 575, circle_size + rng.randint(18, 30), base_depth - 0.15, 0.0, "#F07C7C"),
            Piece(f"object_{suffixes['sq_deep']}", "deep_square", "square", 395, 575, 395, 575, square_size - rng.randint(6, 10), base_depth + rng.uniform(0.45, 0.85), 0.0, "#77A7F2"),
            Piece(f"object_{suffixes['unk']}", "unknown_piece", "unknown", 135, 685, 135, 685, circle_size - 8, base_depth - 0.2, 0.0, self.PURPLE),
            Piece(f"object_{suffixes['circ']}", "valid_circle", "circle", 265, 685, 265, 685, circle_size - rng.randint(5, 9), base_depth - 0.2, 0.0, self.RED),
            Piece(f"object_{suffixes['sq_rot']}", "rotated_square", "square", 395, 685, 395, 685, square_size - rng.randint(5, 9), base_depth - 0.2, float(bad_angle), self.BLUE),
        ]

        self.memory.log(
            self.scenario_id,
            "scenario_init",
            score=0.0,
            outcome="created",
            note="randomized_variation",
            payload={
                "scenario_id": self.scenario_id,
                "seed": seed,
                "square_size": square_size,
                "triangle_size": triangle_size,
                "circle_size": circle_size,
                "base_depth": base_depth,
                "tolerance": tolerance,
                "bad_angle": bad_angle,
                "piece_ids": [p.piece_id for p in self.pieces],
                "hole_ids": [h.hole_id for h in self.holes],
            },
        )

    def new_scenario(self) -> None:
        self.auto = False
        self.setup_world(int(time.time()) % 10_000_000)
        self.log(f"NOVO CENÁRIO: {self.scenario_id}")
        self.write_logic(f"Novo cenário: {self.scenario_id}\nIDs e medidas foram alterados.\n")

    def start(self) -> None:
        self.auto = True
        self.log("AUTO: iniciado.")

    def pause(self) -> None:
        self.auto = False
        self.log("AUTO: pausado.")

    def step(self) -> None:
        if self.phase == "idle":
            self.plan()

    def piece_by_role(self, role: str) -> Piece:
        return next(p for p in self.pieces if p.role == role)

    def hole_by_role(self, role: str) -> Hole:
        return next(h for h in self.holes if h.role == role)

    def piece(self, piece_id: str) -> Piece:
        return next(p for p in self.pieces if p.piece_id == piece_id)

    def hole(self, hole_id: str) -> Hole:
        return next(h for h in self.holes if h.hole_id == hole_id)

    def next_probe(self):
        curriculum = [
            ("contour_mismatch", "valid_triangle", "target_square"),
            ("size_mismatch", "oversize_circle", "target_circle"),
            ("depth_mismatch", "deep_square", "target_square"),
            ("uncertain_failure", "unknown_piece", "target_circle"),
            ("rotation_mismatch", "rotated_square", "target_square"),
            ("solve_circle", "valid_circle", "target_circle"),
        ]
        while self.stage < len(curriculum):
            label, piece_role, hole_role = curriculum[self.stage]
            self.stage += 1
            piece = self.piece_by_role(piece_role)
            hole = self.hole_by_role(hole_role)
            if piece.placed or piece.rejected or hole.filled:
                continue
            return label, piece, hole
        return None

    def plan(self) -> None:
        nxt = self.next_probe()
        if not nxt:
            self.auto = False
            self.face = "happy"
            self.status_var.set("Concluído. Darwin generalizou sob nomes e medidas variáveis.")
            self.write_logic(
                "Final v48.5:\n"
                "- IDs variáveis ✔\n"
                "- medidas variáveis ✔\n"
                "- tolerância variável ✔\n"
                "- ângulo variável ✔\n"
                "- estratégias aplicadas por propriedades, não por nomes ✔"
            )
            self.log("SUCESSO: ciclo v48.5 concluído.")
            self.memory.log(self.scenario_id, "scenario_complete", outcome="success", note="variation_generalization_complete")
            return

        label, piece, hole = nxt
        ev = self.policy.evaluate(self.scenario_id, piece, hole)
        self.current = {"label": label, "piece_id": piece.piece_id, "hole_id": hole.hole_id, "eval": ev}
        self.phase = "thinking"
        self.counter = 24
        self.face = "thinking"
        self.status_var.set(f"Darwin avaliando {piece.role} → {hole.role}.")
        self.log(f"PROBE[{label}]: {piece.piece_id} -> {hole.hole_id} | score={ev.score:.2f} | {ev.failure_reason or 'success'}")
        self.memory.log(self.scenario_id, "probe_choose", piece, hole, ev.score, "chosen", label, ev.failure_reason, "", asdict(ev))
        self.write_logic(self.eval_text("AVALIAR", piece, hole, ev, label))

    def eval_text(self, title: str, piece: Piece, hole: Hole, ev: Evaluation, label: str) -> str:
        return (
            f"Ação: {title}\n"
            f"Cenário: {self.scenario_id}\n"
            f"Caso: {label}\n\n"
            f"Peça: {piece.piece_id}\n"
            f"Role: {piece.role}\n"
            f"Forma: {piece.family} | size={piece.size:.2f} | depth={piece.depth:.2f} | angle={piece.angle:.1f}\n\n"
            f"Buraco: {hole.hole_id}\n"
            f"Role: {hole.role}\n"
            f"Forma: {hole.family} | size={hole.size:.2f} | depth={hole.depth:.2f} | tol={hole.tol:.1f}\n\n"
            f"contorno={ev.contour_match}\n"
            f"tamanho={ev.size_match}\n"
            f"profundidade={ev.depth_match}\n"
            f"orientação={ev.rotation_match}\n"
            f"score={ev.score:.2f}\n\n"
            f"falha={ev.failure_reason or 'compatível'}\n"
            f"{ev.explanation}\n"
        )

    def after_think(self) -> None:
        piece = self.piece(self.current["piece_id"])
        hole = self.hole(self.current["hole_id"])
        ev = self.policy.evaluate(self.scenario_id, piece, hole)

        if ev.observed_fit:
            self.start_move("insert")
            self.memory.log(self.scenario_id, "insert_start", piece, hole, ev.score, "started", "direct_insert", "", "", asdict(ev))
            return

        if ev.failure_reason == "rotation_mismatch":
            strategy = self.policy.strategy_for(ev)
            self.memory.log(self.scenario_id, "strategy_select", piece, hole, ev.score, "selected", strategy.recommendation, ev.failure_reason, strategy.recommendation, {"strategy": asdict(strategy), "source_error": asdict(ev)})
            self.memory.log(self.scenario_id, "strategy_execute", piece, hole, ev.score, "executed", strategy.recommendation, ev.failure_reason, strategy.recommendation, {"strategy": asdict(strategy)})
            self.memory.log(self.scenario_id, "rotate_start", piece, hole, ev.score, "started", "rotate_piece", ev.failure_reason, "rotate_piece", asdict(ev))
            self.log(f"ESTRATÉGIA: {ev.failure_reason} -> {strategy.recommendation}")
            self.phase = "rotate"
            self.face = "thinking"
            self.write_logic(self.eval_text("ESTRATÉGIA: GIRAR", piece, hole, ev, "rotation_mismatch") + f"\nEstratégia: {strategy.recommendation}\n{strategy.explanation}\n")
            return

        self.start_move("collision")

    def start_move(self, kind: str) -> None:
        piece = self.piece(self.current["piece_id"])
        hole = self.hole(self.current["hole_id"])
        self.phase = "move_" + kind
        self.t = 0.0
        self.start_xy = (piece.x, piece.y)
        self.back_xy = (piece.home_x, piece.home_y)
        self.face = "focus"

        if kind == "collision":
            ev = self.policy.evaluate(self.scenario_id, piece, hole)
            self.memory.log(self.scenario_id, "controlled_collision_start", piece, hole, ev.score, "started", ev.failure_reason, ev.failure_reason, "", asdict(ev))

    def handle_failure(self, piece: Piece, hole: Hole, ev: Evaluation) -> None:
        self.memory.log(self.scenario_id, "controlled_collision", piece, hole, ev.score, "collision", ev.failure_reason, ev.failure_reason, "", asdict(ev))
        self.log(f"COLISÃO: {piece.piece_id} -> {hole.hole_id} | {ev.failure_reason}")

        strategy = self.policy.record_failure_and_strategy(self.scenario_id, piece, hole, ev)
        self.log(f"ESTRATÉGIA: {ev.failure_reason} -> {strategy.recommendation}")
        self.memory.log(self.scenario_id, "strategy_execute", piece, hole, ev.score, "executed", strategy.recommendation, ev.failure_reason, strategy.recommendation, {"strategy": asdict(strategy), "source_error": asdict(ev)})

        if strategy.recommendation == "try_alternate_hole":
            alt = self.hole_by_role("target_triangle")
            ev2 = self.policy.evaluate(self.scenario_id, piece, alt)
            self.memory.log(self.scenario_id, "strategy_execute_alternate_target", piece, alt, ev2.score, "chosen", "try_alternate_hole", ev.failure_reason, "try_alternate_hole", {"strategy": asdict(strategy), "chosen": asdict(ev2)})
            self.current = {"label": "alternate_after_contour", "piece_id": piece.piece_id, "hole_id": alt.hole_id, "eval": ev2}
            self.phase = "move_insert"
            self.t = 0.0
            self.start_xy = (piece.x, piece.y)
            self.back_xy = (piece.home_x, piece.home_y)
            self.memory.log(self.scenario_id, "insert_start", piece, alt, ev2.score, "started", "after_try_alternate_hole", "", "", asdict(ev2))
            self.write_logic(self.eval_text("EXECUTAR ESTRATÉGIA", piece, alt, ev2, "try_alternate_hole"))
            return

        if strategy.recommendation in ("reject_pair_size", "reject_pair_depth", "cautious_exploration"):
            piece.rejected = True
            outcome = "rejected" if strategy.recommendation != "cautious_exploration" else "cautious_skip"
            self.memory.log(self.scenario_id, "strategy_outcome", piece, hole, ev.score, outcome, strategy.recommendation, ev.failure_reason, strategy.recommendation, {"strategy": asdict(strategy), "source_error": asdict(ev)})
            self.flash = strategy.recommendation
            self.flash_n = 42
            self.phase = "return"
            self.t = 0.0
            self.write_logic(self.eval_text("REJEITAR / CAUTELA", piece, hole, ev, strategy.recommendation) + f"\nEstratégia: {strategy.recommendation}\n{strategy.explanation}\n")
            return

        self.phase = "return"
        self.t = 0.0

    def animate(self) -> None:
        if self.flash_n > 0:
            self.flash_n -= 1

        if self.phase == "idle" or not self.current:
            return

        piece = self.piece(self.current["piece_id"])
        hole = self.hole(self.current["hole_id"])

        if self.phase == "thinking":
            self.counter -= 1
            if self.counter <= 0:
                self.after_think()

        elif self.phase == "rotate":
            delta = (hole.angle - piece.angle) % 360.0
            if delta > 180.0:
                delta -= 360.0
            step = 5.5 if delta > 0 else -5.5
            if abs(delta) <= 5.5:
                piece.angle = hole.angle
                ev = self.policy.evaluate(self.scenario_id, piece, hole)
                self.memory.log(self.scenario_id, "rotate_success", piece, hole, ev.score, "success", "rotate_piece", "", "rotate_piece", asdict(ev))
                self.log(f"ROTAÇÃO RESOLVEU: {piece.piece_id} -> {hole.hole_id}")
                self.start_move("insert")
                self.memory.log(self.scenario_id, "insert_start", piece, hole, ev.score, "started", "after_rotation", "", "", asdict(ev))
            else:
                piece.angle = (piece.angle + step) % 360.0

        elif self.phase in ("move_insert", "move_collision"):
            sx, sy = self.start_xy
            self.t = min(1.0, self.t + 0.04)
            eased = 1.0 - (1.0 - self.t) * (1.0 - self.t)
            piece.x = sx + (hole.x - sx) * eased
            piece.y = sy + (hole.y - 105 - sy) * eased - 20 * math.sin(math.pi * eased)

            if self.t >= 1.0:
                ev = self.policy.evaluate(self.scenario_id, piece, hole)
                if self.phase == "move_insert" and ev.observed_fit:
                    piece.x, piece.y = hole.x, hole.y
                    piece.placed = True
                    hole.filled = True
                    hole.filled_by = piece.piece_id
                    self.memory.log(self.scenario_id, "insert_success", piece, hole, ev.score, "success", "fit", "", "", asdict(ev))
                    self.log(f"SUCESSO: {piece.piece_id} -> {hole.hole_id}")
                    self.flash = "encaixe correto"
                    self.flash_n = 35
                    self.phase = "idle"
                    self.current = None
                    self.face = "happy"
                else:
                    self.handle_failure(piece, hole, ev)

        elif self.phase == "return":
            sx, sy = self.start_xy
            tx, ty = self.back_xy
            self.t = min(1.0, self.t + 0.06)
            eased = 1.0 - (1.0 - self.t) * (1.0 - self.t)
            piece.x = sx + (tx - sx) * eased
            piece.y = sy + (ty - sy) * eased
            if self.t >= 1.0:
                self.log(f"RECUO: {piece.piece_id} voltou ao ponto seguro.")
                self.phase = "idle"
                self.current = None
                self.face = "neutral"

    def loop(self) -> None:
        if self.auto and self.phase == "idle":
            self.plan()
        self.animate()
        self.draw()
        self.root.after(25, self.loop)

    def write_logic(self, text: str) -> None:
        self.logic.config(state="normal")
        self.logic.delete("1.0", "end")
        self.logic.insert("1.0", text)
        self.logic.config(state="disabled")

    def log(self, text: str) -> None:
        self.history.config(state="normal")
        self.history.insert("end", text + "\n")
        self.history.see("end")
        self.history.config(state="disabled")

    def round_rect(self, x1, y1, x2, y2, r=18, **kwargs):
        pts = [
            x1+r, y1, x2-r, y1, x2, y1, x2, y1+r,
            x2, y2-r, x2, y2, x2-r, y2, x1+r, y2,
            x1, y2, x1, y2-r, x1, y1+r, x1, y1,
        ]
        return self.canvas.create_polygon(pts, smooth=True, splinesteps=24, **kwargs)

    def draw(self) -> None:
        c = self.canvas
        c.delete("all")
        self.round_rect(15, 15, 820, 745, 26, fill="#F8FBFF", outline="#CBD8E8", width=2)
        c.create_text(35, 38, anchor="w", text="DARWIN v48.5 — generalização por variação", font=("Segoe UI", 17, "bold"), fill=self.TEXT)
        c.create_text(35, 65, anchor="w", text=f"Cenário: {self.scenario_id}", font=("Segoe UI", 10), fill=self.MUTED)

        self.draw_robot(135, 225)
        self.draw_policy(35, 105)
        self.draw_board()

        for piece in self.pieces:
            if not piece.placed:
                self.draw_piece(piece)

        if self.current:
            self.draw_link()

        if self.flash_n > 0 and self.flash:
            color = self.GREEN if "correto" in self.flash else self.BAD
            self.round_rect(465, 120, 805, 165, 14, fill="white", outline=color, width=3)
            c.create_text(635, 142, text=self.flash, font=("Segoe UI", 13, "bold"), fill=color)

        c.create_text(
            35,
            725,
            anchor="w",
            text=f"Stage: {self.stage}/6 | nomes variáveis | SQLite: {'ON' if self.memory.enabled else 'OFF'}",
            font=("Segoe UI", 10, "bold"),
            fill=self.TEXT,
        )

    def draw_policy(self, x, y) -> None:
        self.round_rect(x, y, x+430, y+120, 14, fill="white", outline="#D6E2F1", width=2)
        pairs = [
            ("contorno", "outro buraco"),
            ("tamanho", "rejeitar"),
            ("profund.", "rejeitar"),
            ("orient.", "girar"),
            ("incerto", "cautela"),
        ]
        for i, (a, b) in enumerate(pairs):
            px = x + 16 + i * 82
            self.canvas.create_text(px, y+22, anchor="w", text=a, font=("Segoe UI", 9, "bold"), fill="#22507C")
            self.canvas.create_text(px, y+52, anchor="w", text="↓", font=("Segoe UI", 16, "bold"), fill=self.BLUE)
            self.canvas.create_text(px, y+82, anchor="w", text=b, font=("Segoe UI", 8), fill=self.MUTED)

    def draw_robot(self, cx, cy) -> None:
        c = self.canvas
        c.create_oval(cx-65, cy-85, cx+65, cy+45, fill="#F8FBFF", outline="#B9C8DA", width=3)
        c.create_oval(cx-50, cy-58, cx+50, cy+15, fill="#192638", outline="#30465F", width=2)
        c.create_oval(cx-30, cy-35, cx-10, cy-15, fill="#8BDBFF", outline="")
        c.create_oval(cx+10, cy-35, cx+30, cy-15, fill="#8BDBFF", outline="")
        if self.face == "thinking":
            c.create_text(cx, cy, text="...", font=("Segoe UI", 14, "bold"), fill="#8BDBFF")
        elif self.face == "focus":
            c.create_text(cx, cy, text="!", font=("Segoe UI", 14, "bold"), fill="#8BDBFF")
        else:
            c.create_arc(cx-18, cy+0, cx+18, cy+18, start=180, extent=180, outline="#8BDBFF", width=3, style="arc")
        c.create_oval(cx-18, cy+28, cx+18, cy+64, fill="#DDF5FF", outline="#6EC6FF", width=3)
        c.create_text(cx, cy+83, text="DARWIN", font=("Segoe UI", 9, "bold"), fill="#355574")
        c.create_line(cx+55, cy+40, cx+110, cy+85, fill="#A8B7C9", width=8)
        c.create_oval(cx+104, cy+78, cx+120, cy+94, fill="white", outline="#8FA2B8", width=2)

    def draw_board(self) -> None:
        self.round_rect(455, 300, 805, 545, 20, fill=self.WOOD, outline="#BE9569", width=2)
        for hole in self.holes:
            self.draw_hole(hole)

    def draw_hole(self, hole: Hole) -> None:
        c = self.canvas
        if hole.family == "square":
            c.create_rectangle(hole.x-40, hole.y-40, hole.x+40, hole.y+40, fill=self.DARK, outline="#62482F", width=3)
            if hole.filled:
                c.create_rectangle(hole.x-35, hole.y-35, hole.x+35, hole.y+35, fill=self.piece(hole.filled_by).color, outline="")
        elif hole.family == "triangle":
            c.create_polygon([hole.x, hole.y-45, hole.x-45, hole.y+36, hole.x+45, hole.y+36], fill=self.DARK, outline="#62482F", width=3)
            if hole.filled:
                c.create_polygon([hole.x, hole.y-38, hole.x-37, hole.y+30, hole.x+37, hole.y+30], fill=self.piece(hole.filled_by).color, outline="")
        else:
            c.create_oval(hole.x-40, hole.y-40, hole.x+40, hole.y+40, fill=self.DARK, outline="#62482F", width=3)
            if hole.filled:
                c.create_oval(hole.x-35, hole.y-35, hole.x+35, hole.y+35, fill=self.piece(hole.filled_by).color, outline="")

    def rotated(self, points, angle, cx, cy):
        radians = math.radians(angle)
        return [
            (
                cx + (x-cx)*math.cos(radians) - (y-cy)*math.sin(radians),
                cy + (x-cx)*math.sin(radians) + (y-cy)*math.cos(radians),
            )
            for x, y in points
        ]

    def draw_piece(self, piece: Piece) -> None:
        c = self.canvas
        if piece.rejected:
            c.create_text(piece.x, piece.y-48, text="rejeitada", font=("Segoe UI", 8, "bold"), fill=self.BAD)

        if self.current and self.current["piece_id"] == piece.piece_id:
            c.create_oval(piece.x-52, piece.y-52, piece.x+52, piece.y+52, outline="#AEE8FF", width=3)

        if piece.family == "square":
            half = piece.size / 2
            pts = self.rotated(
                [(piece.x-half, piece.y-half), (piece.x+half, piece.y-half), (piece.x+half, piece.y+half), (piece.x-half, piece.y+half)],
                piece.angle,
                piece.x,
                piece.y,
            )
            c.create_polygon([v for pt in pts for v in pt], fill=piece.color, outline="#2458B8", width=2)
            c.create_text(piece.x, piece.y+half+16, text=f"{piece.angle:.0f}°", font=("Segoe UI", 8, "bold"), fill=self.MUTED)
        elif piece.family == "triangle":
            half = piece.size / 2
            pts = self.rotated([(piece.x, piece.y-half), (piece.x-half, piece.y+half*.84), (piece.x+half, piece.y+half*.84)], piece.angle, piece.x, piece.y)
            c.create_polygon([v for pt in pts for v in pt], fill=piece.color, outline="#A98013", width=2)
        elif piece.family == "unknown":
            half = piece.size / 2
            c.create_polygon([piece.x-half, piece.y, piece.x, piece.y-half, piece.x+half, piece.y, piece.x, piece.y+half], fill=piece.color, outline="#6B5DC6", width=2)
            c.create_text(piece.x, piece.y, text="?", font=("Segoe UI", 18, "bold"), fill="white")
        else:
            radius = piece.size / 2
            c.create_oval(piece.x-radius, piece.y-radius, piece.x+radius, piece.y+radius, fill=piece.color, outline="#B43B3B", width=2)

        label = piece.role.replace("_", " ")
        c.create_text(piece.x, piece.y+piece.size/2+28, text=label, font=("Segoe UI", 7), fill=self.MUTED)

    def draw_link(self) -> None:
        piece = self.piece(self.current["piece_id"])
        hole = self.hole(self.current["hole_id"])
        self.canvas.create_line(piece.x, piece.y-55, hole.x, hole.y-68, fill="#6EC6FF", width=3, dash=(7, 5), arrow="last")


def main() -> None:
    root = tk.Tk()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    try:
        ttk.Style().theme_use("vista")
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
