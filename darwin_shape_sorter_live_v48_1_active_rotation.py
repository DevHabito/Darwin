from __future__ import annotations

"""
DARWIN v48.1 — Shape Sorter ao vivo com rotação ativa

Este visualizador é um micromundo pedagógico:
Darwin observa peças e buracos, avalia propriedades físicas e escolhe ações
em runtime. A sequência NÃO é uma lista fixa de "quadrado, triângulo, círculo".

Diferença da demo anterior:
- O quadrado correto começa rotacionado.
- Darwin precisa detectar rotation_mismatch.
- Darwin precisa girar a peça antes de encaixar.
- Há peças distratoras: círculo grande demais e quadrado profundo demais.
- As ações são registradas no SQLite em geometry_live_actions_v48_1.

Uso:
    py darwin_shape_sorter_live_v48_1_active_rotation.py

Controles:
- Iniciar Auto
- Pausar
- Passo
- Resetar
- Novo cenário
- Curiosidade ON/OFF: permite tentativas exploratórias fracas às vezes

Observação honesta:
Isto ainda é um micromundo simulado. A autonomia é local: Darwin decide dentro
das regras físicas simplificadas do ambiente. Não é consciência, nem autonomia
geral, mas já permite ver ação, erro, correção e encaixe ao vivo.
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


# ============================================================
# util
# ============================================================

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ============================================================
# dados do micromundo
# ============================================================

@dataclass
class Piece:
    piece_id: str
    family: str
    x: float
    y: float
    home_x: float
    home_y: float
    size: float
    depth: float
    orientation_deg: float
    color: str
    placed: bool = False
    rejected: bool = False
    attempts: int = 0

    def reset_to_home(self) -> None:
        self.x = self.home_x
        self.y = self.home_y
        self.placed = False
        self.rejected = False
        self.attempts = 0


@dataclass
class Hole:
    hole_id: str
    family: str
    x: float
    y: float
    size: float
    depth: float
    orientation_deg: float = 0.0
    tolerance: float = 5.0
    filled: bool = False
    filled_by: str = ""


@dataclass
class Evaluation:
    piece_id: str
    hole_id: str
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
class Action:
    kind: str
    piece_id: str = ""
    hole_id: str = ""
    evaluation: Evaluation | None = None
    target_angle: float = 0.0
    note: str = ""


# ============================================================
# memória SQLite simples
# ============================================================

class LiveMemory:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self.enabled = True
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS geometry_live_actions_v48_1 (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        action_kind TEXT NOT NULL,
                        piece_id TEXT NOT NULL DEFAULT '',
                        hole_id TEXT NOT NULL DEFAULT '',
                        score REAL NOT NULL DEFAULT 0.0,
                        outcome TEXT NOT NULL DEFAULT '',
                        note TEXT NOT NULL DEFAULT '',
                        payload_json TEXT NOT NULL DEFAULT '{}'
                    )
                    """
                )
                conn.commit()
        except Exception:
            self.enabled = False

    def log(self, action_kind: str, piece_id: str = "", hole_id: str = "",
            score: float = 0.0, outcome: str = "", note: str = "", payload=None) -> None:
        if not self.enabled:
            return
        payload = payload or {}
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO geometry_live_actions_v48_1 (
                        timestamp, action_kind, piece_id, hole_id, score, outcome, note, payload_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (now_iso(), action_kind, piece_id, hole_id, score, outcome, note, safe_json(payload)),
                )
                conn.commit()
        except Exception:
            self.enabled = False


# ============================================================
# agente Darwin local
# ============================================================

class DarwinShapeAgent:
    def __init__(self, memory: LiveMemory) -> None:
        self.failed_pairs: set[tuple[str, str]] = set()
        self.curiosity: bool = False
        self.memory = memory
        self.step_counter = 0

    def rotation_match(self, piece: Piece, hole: Hole) -> bool:
        if piece.family == "circle":
            return True
        symmetry = 90.0 if piece.family == "square" else 120.0
        delta = abs((piece.orientation_deg - hole.orientation_deg) % 360.0)
        if delta > 180:
            delta = 360 - delta
        rem = min(delta % symmetry, symmetry - (delta % symmetry))
        return rem <= 3.0

    def evaluate(self, piece: Piece, hole: Hole) -> Evaluation:
        contour = piece.family == hole.family
        size = piece.size <= hole.size + hole.tolerance
        depth = piece.depth <= hole.depth
        rotation = self.rotation_match(piece, hole)
        observed = contour and size and depth and rotation

        score = 0.0
        score += 0.42 if contour else 0.0
        score += 0.22 if size else 0.0
        score += 0.20 if depth else 0.0
        score += 0.16 if rotation else 0.0

        if observed:
            reason = ""
            explanation = "contorno, tamanho, profundidade e orientação compatíveis"
        elif not contour:
            reason = "contour_mismatch"
            explanation = "contorno diferente: colisão de forma"
        elif not size:
            reason = "size_mismatch"
            explanation = "peça grande demais para a abertura"
        elif not depth:
            reason = "depth_mismatch"
            explanation = "peça profunda demais para a abertura"
        elif not rotation:
            reason = "rotation_mismatch"
            explanation = "orientação incompatível; talvez girar resolva"
        else:
            reason = "unknown_collision"
            explanation = "colisão não classificada"

        return Evaluation(
            piece_id=piece.piece_id,
            hole_id=hole.hole_id,
            contour_match=contour,
            size_match=size,
            depth_match=depth,
            rotation_match=rotation,
            observed_fit=observed,
            collision_detected=not observed,
            score=round(score, 3),
            failure_reason=reason,
            explanation=explanation,
        )

    def choose(self, pieces: list[Piece], holes: list[Hole]) -> Action | None:
        available_pieces = [p for p in pieces if not p.placed and not p.rejected]
        available_holes = [h for h in holes if not h.filled]
        if not available_pieces or not available_holes:
            return None

        ranked: list[tuple[float, Piece, Hole, Evaluation]] = []
        for p in available_pieces:
            for h in available_holes:
                ev = self.evaluate(p, h)
                score = ev.score
                if (p.piece_id, h.hole_id) in self.failed_pairs:
                    score -= 0.30
                score -= min(0.06 * p.attempts, 0.18)
                ranked.append((score, p, h, ev))

        ranked.sort(key=lambda item: item[0], reverse=True)
        self.step_counter += 1

        # curiosidade: às vezes testa uma hipótese imperfeita, mas não uma impossível demais
        if self.curiosity and self.step_counter % 4 == 0:
            weak = [item for item in ranked if 0.45 <= item[0] < 0.82]
            if weak:
                score, p, h, ev = random.choice(weak)
                self.memory.log("curiosity_choose", p.piece_id, h.hole_id, ev.score, "chosen", "hipótese exploratória", asdict(ev))
                return Action("think", p.piece_id, h.hole_id, ev, note="hipótese exploratória")

        score, p, h, ev = ranked[0]
        self.memory.log("choose", p.piece_id, h.hole_id, ev.score, "chosen", "melhor hipótese atual", asdict(ev))
        return Action("think", p.piece_id, h.hole_id, ev, note="melhor hipótese atual")

    def action_after_think(self, piece: Piece, hole: Hole, ev: Evaluation) -> Action:
        if ev.observed_fit:
            return Action("insert", piece.piece_id, hole.hole_id, ev, note="encaixe previsto")

        # aqui está o salto v48.1: não desistir diante de rotação.
        if ev.failure_reason == "rotation_mismatch" and ev.contour_match and ev.size_match and ev.depth_match:
            return Action(
                "rotate",
                piece.piece_id,
                hole.hole_id,
                ev,
                target_angle=hole.orientation_deg,
                note="rotação ativa antes de desistir",
            )

        return Action("test_reject", piece.piece_id, hole.hole_id, ev, note="testar colisão e rejeitar par")


# ============================================================
# GUI
# ============================================================

class App:
    BG = "#EEF4FB"
    PANEL = "#FFFFFF"
    TEXT = "#172B44"
    MUTED = "#60758E"
    BLUE = "#3977E3"
    YELLOW = "#F2C94C"
    RED = "#EB5757"
    WOOD = "#DBB789"
    WOOD_DARK = "#7D593A"
    GREEN = "#2DBE78"
    BAD = "#D9534F"
    CYAN = "#6EC6FF"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("DARWIN v48.1 — rotação ativa ao vivo")
        self.root.geometry("1380x860")
        self.root.configure(bg=self.BG)

        self.memory = LiveMemory()
        self.agent = DarwinShapeAgent(self.memory)

        self.canvas = tk.Canvas(root, width=940, height=820, bg=self.BG, highlightthickness=0)
        self.canvas.pack(side="left", padx=14, pady=14)

        side = tk.Frame(root, bg=self.BG)
        side.pack(side="right", fill="both", expand=True, padx=(0, 14), pady=14)

        self.status_var = tk.StringVar(value="Pronto. Clique em Iniciar Auto ou Passo.")
        self.mode_var = tk.StringVar(value="Cenário: quadrado rotacionado + distratores.")

        buttons = tk.Frame(side, bg=self.BG)
        buttons.pack(fill="x", pady=(0, 8))

        ttk.Button(buttons, text="Iniciar Auto", command=self.start).grid(row=0, column=0, padx=4, pady=4, sticky="ew")
        ttk.Button(buttons, text="Pausar", command=self.pause).grid(row=0, column=1, padx=4, pady=4, sticky="ew")
        ttk.Button(buttons, text="Passo", command=self.step).grid(row=0, column=2, padx=4, pady=4, sticky="ew")
        ttk.Button(buttons, text="Resetar", command=self.reset).grid(row=0, column=3, padx=4, pady=4, sticky="ew")
        ttk.Button(buttons, text="Novo cenário", command=self.new_scenario).grid(row=1, column=0, columnspan=2, padx=4, pady=4, sticky="ew")

        self.curiosity_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(buttons, text="Curiosidade ON/OFF", variable=self.curiosity_var, command=self.toggle_curiosity).grid(
            row=1, column=2, columnspan=2, padx=4, pady=4, sticky="w"
        )
        for i in range(4):
            buttons.grid_columnconfigure(i, weight=1)

        self.status_label = tk.Label(side, textvariable=self.status_var, bg=self.PANEL, fg=self.TEXT,
                                     justify="left", anchor="w", wraplength=380, padx=12, pady=10,
                                     relief="solid", bd=1)
        self.status_label.pack(fill="x", pady=(0, 8))

        self.mode_label = tk.Label(side, textvariable=self.mode_var, bg=self.PANEL, fg=self.MUTED,
                                   justify="left", anchor="w", wraplength=380, padx=12, pady=8,
                                   relief="solid", bd=1)
        self.mode_label.pack(fill="x", pady=(0, 8))

        self.logic = tk.Text(side, height=18, wrap="word", bg=self.PANEL, fg=self.TEXT, relief="solid", bd=1)
        self.logic.pack(fill="x", pady=(0, 8))
        self.logic.configure(state="disabled")

        self.history = tk.Text(side, height=20, wrap="word", bg="#0D3B66", fg="#EAF7FF", relief="solid", bd=1)
        self.history.pack(fill="both", expand=True)
        self.history.configure(state="disabled")

        self.auto = False
        self.current_action: Action | None = None
        self.phase = "idle"
        self.counter = 0
        self.drag_t = 0.0
        self.start_pos: tuple[float, float] | None = None
        self.return_pos: tuple[float, float] | None = None
        self.robot_face = "neutral"
        self.flash_text = ""
        self.flash_counter = 0

        self.scenario_seed = 481
        random.seed(self.scenario_seed)
        self.setup_world()
        self.write_logic("Darwin aguardando.\n\nA sequência será escolhida por avaliação de compatibilidade, não por lista fixa.")
        self.draw()
        self.root.after(25, self.loop)

    # --------------------------------------------------------
    # mundo
    # --------------------------------------------------------

    def setup_world(self) -> None:
        self.holes = [
            Hole("hole_square", "square", 555, 395, 82, 1.5),
            Hole("hole_triangle", "triangle", 690, 395, 86, 1.5),
            Hole("hole_circle", "circle", 825, 395, 82, 1.5),
        ]

        # Intencional: não há quadrado perfeitamente orientado.
        # Darwin precisa girar piece_square_rotated para resolver.
        self.pieces = [
            Piece("piece_square_rotated", "square", 145, 655, 145, 655, 74, 1.0, 45.0, self.BLUE),
            Piece("piece_triangle", "triangle", 270, 655, 270, 655, 78, 1.0, 0.0, self.YELLOW),
            Piece("piece_circle", "circle", 395, 655, 395, 655, 74, 1.0, 0.0, self.RED),
            Piece("piece_circle_large", "circle", 145, 745, 145, 745, 104, 1.0, 0.0, "#F07C7C"),
            Piece("piece_square_deep", "square", 285, 745, 285, 745, 74, 2.4, 0.0, "#77A7F2"),
        ]
        self.agent.failed_pairs.clear()
        self.robot_face = "neutral"
        self.current_action = None
        self.phase = "idle"
        self.counter = 0
        self.drag_t = 0.0
        self.start_pos = None
        self.return_pos = None
        self.flash_text = ""
        self.flash_counter = 0

    def reset(self) -> None:
        self.auto = False
        self.setup_world()
        self.log("RESET: mundo reiniciado.")
        self.status_var.set("Mundo reiniciado. Darwin pronto.")
        self.write_logic("Mundo reiniciado.\n\nO quadrado azul começa rotacionado: Darwin precisa descobrir que deve girar.")
        self.draw()

    def new_scenario(self) -> None:
        self.reset()
        # pequenas variações de posição para evitar "filme" sempre igual
        for p in self.pieces:
            p.x += random.randint(-18, 18)
            p.home_x = p.x
            p.y += random.randint(-10, 10)
            p.home_y = p.y
        self.log("NOVO CENÁRIO: posições levemente alteradas.")
        self.status_var.set("Novo cenário gerado. A decisão continua por avaliação física.")

    def toggle_curiosity(self) -> None:
        self.agent.curiosity = bool(self.curiosity_var.get())
        self.log(f"CURIOSIDADE: {'ON' if self.agent.curiosity else 'OFF'}")

    # --------------------------------------------------------
    # controle
    # --------------------------------------------------------

    def start(self) -> None:
        self.auto = True
        self.log("AUTO: iniciado.")
        self.status_var.set("Auto ligado. Darwin está avaliando o micromundo.")

    def pause(self) -> None:
        self.auto = False
        self.log("AUTO: pausado.")
        self.status_var.set("Auto pausado.")

    def step(self) -> None:
        if self.phase == "idle":
            self.plan()
        else:
            self.status_var.set("Aguarde a ação atual terminar.")

    # --------------------------------------------------------
    # loop
    # --------------------------------------------------------

    def loop(self) -> None:
        if self.auto and self.phase == "idle":
            self.plan()

        self.animate()
        self.draw()
        self.root.after(25, self.loop)

    # --------------------------------------------------------
    # lógica
    # --------------------------------------------------------

    def piece(self, piece_id: str) -> Piece:
        for p in self.pieces:
            if p.piece_id == piece_id:
                return p
        raise KeyError(piece_id)

    def hole(self, hole_id: str) -> Hole:
        for h in self.holes:
            if h.hole_id == hole_id:
                return h
        raise KeyError(hole_id)

    def solved(self) -> bool:
        return all(h.filled for h in self.holes)

    def plan(self) -> None:
        if self.solved():
            self.auto = False
            self.robot_face = "happy"
            self.status_var.set("Concluído. Darwin resolveu o brinquedo.")
            self.write_logic(
                "Estado final:\n"
                "- buraco quadrado preenchido ✔\n"
                "- buraco triangular preenchido ✔\n"
                "- buraco circular preenchido ✔\n\n"
                "Darwin usou avaliação física e rotação ativa."
            )
            self.log("SUCESSO: todos os buracos foram preenchidos.")
            return

        action = self.agent.choose(self.pieces, self.holes)
        if action is None:
            self.auto = False
            self.status_var.set("Sem ação disponível.")
            return

        self.current_action = action
        self.phase = "thinking"
        self.counter = 28
        self.robot_face = "thinking"

        p = self.piece(action.piece_id)
        h = self.hole(action.hole_id)
        ev = action.evaluation
        self.status_var.set(f"Darwin avaliando {p.family} → {h.family}.")
        self.log(f"PENSAR: {p.piece_id} -> {h.hole_id} | score={ev.score:.2f} | {ev.failure_reason or 'success'}")
        self.write_logic(self.evaluation_text("OBSERVAR / AVALIAR", p, h, ev))

    def evaluation_text(self, title: str, p: Piece, h: Hole, ev: Evaluation) -> str:
        return (
            f"Ação: {title}\n\n"
            f"Peça: {p.piece_id}\n"
            f"Buraco: {h.hole_id}\n\n"
            f"contorno = {'sim' if ev.contour_match else 'não'}\n"
            f"tamanho = {'sim' if ev.size_match else 'não'}\n"
            f"profundidade = {'sim' if ev.depth_match else 'não'}\n"
            f"orientação = {'sim' if ev.rotation_match else 'não'}\n"
            f"score = {ev.score:.2f}\n\n"
            f"resultado previsto: {'encaixa' if ev.observed_fit else 'não encaixa'}\n"
            f"motivo: {ev.failure_reason or 'compatível'}\n"
            f"explicação: {ev.explanation}\n"
        )

    def after_think(self) -> None:
        assert self.current_action is not None
        p = self.piece(self.current_action.piece_id)
        h = self.hole(self.current_action.hole_id)
        ev = self.agent.evaluate(p, h)
        next_action = self.agent.action_after_think(p, h, ev)
        self.current_action = next_action

        if next_action.kind == "rotate":
            self.phase = "rotating"
            self.counter = 0
            self.robot_face = "thinking"
            self.status_var.set("Rotation mismatch detectado. Darwin vai girar a peça.")
            self.write_logic(
                self.evaluation_text("CORRIGIR ORIENTAÇÃO", p, h, ev)
                + "\nDecisão: não desistir. Girar a peça e reavaliar."
            )
            self.log(f"GIRAR: {p.piece_id} de {p.orientation_deg:.0f}° para {h.orientation_deg:.0f}°")
            self.memory.log("rotate_start", p.piece_id, h.hole_id, ev.score, "started", "rotação ativa", asdict(ev))

        elif next_action.kind == "insert":
            self.phase = "moving_insert"
            self.drag_t = 0.0
            self.start_pos = (p.x, p.y)
            self.return_pos = (p.home_x, p.home_y)
            self.robot_face = "focus"
            self.status_var.set("Compatibilidade suficiente. Darwin vai inserir.")
            self.write_logic(self.evaluation_text("INSERIR", p, h, ev))
            self.log(f"INSERIR: {p.piece_id} -> {h.hole_id}")
            self.memory.log("insert_start", p.piece_id, h.hole_id, ev.score, "started", "inserção", asdict(ev))

        elif next_action.kind == "test_reject":
            self.phase = "moving_reject"
            self.drag_t = 0.0
            self.start_pos = (p.x, p.y)
            self.return_pos = (p.home_x, p.home_y)
            self.robot_face = "focus"
            self.status_var.set("Hipótese fraca. Darwin testa e recua ao detectar colisão.")
            self.write_logic(self.evaluation_text("TESTAR E RECUAR", p, h, ev))
            self.log(f"TESTAR: {p.piece_id} -> {h.hole_id}")
            self.memory.log("reject_test_start", p.piece_id, h.hole_id, ev.score, "started", "teste de colisão", asdict(ev))

    # --------------------------------------------------------
    # animação
    # --------------------------------------------------------

    def animate(self) -> None:
        if self.phase == "idle" or self.current_action is None:
            return

        if self.flash_counter > 0:
            self.flash_counter -= 1

        if self.phase == "thinking":
            self.counter -= 1
            if self.counter <= 0:
                self.after_think()

        elif self.phase == "rotating":
            p = self.piece(self.current_action.piece_id)
            h = self.hole(self.current_action.hole_id)
            target = h.orientation_deg
            delta = (target - p.orientation_deg) % 360
            if delta > 180:
                delta -= 360
            step = 5.5 if delta > 0 else -5.5
            if abs(delta) <= 5.5:
                p.orientation_deg = target
                ev = self.agent.evaluate(p, h)
                p.attempts += 1
                self.status_var.set("Rotação concluída. Darwin reavaliou: agora encaixa.")
                self.write_logic(
                    self.evaluation_text("REAVALIAR APÓS ROTAÇÃO", p, h, ev)
                    + "\nDecisão: inserir agora."
                )
                self.log(f"ROTAÇÃO RESOLVEU: {p.piece_id} -> {h.hole_id}")
                self.memory.log("rotate_success", p.piece_id, h.hole_id, ev.score, "success", "rotação resolveu", asdict(ev))
                self.current_action = Action("insert", p.piece_id, h.hole_id, ev, note="após rotação")
                self.phase = "moving_insert"
                self.drag_t = 0.0
                self.start_pos = (p.x, p.y)
                self.return_pos = (p.home_x, p.home_y)
            else:
                p.orientation_deg = (p.orientation_deg + step) % 360

        elif self.phase in {"moving_insert", "moving_reject"}:
            p = self.piece(self.current_action.piece_id)
            h = self.hole(self.current_action.hole_id)
            sx, sy = self.start_pos or (p.x, p.y)
            self.drag_t = min(1.0, self.drag_t + 0.035)
            t = self.ease(self.drag_t)
            p.x = sx + (h.x - sx) * t
            p.y = sy + (h.y - 118 - sy) * t - 26 * math.sin(math.pi * t)

            if self.drag_t >= 1.0:
                ev = self.agent.evaluate(p, h)
                p.attempts += 1

                if self.phase == "moving_insert" and ev.observed_fit:
                    p.x, p.y = h.x, h.y
                    p.placed = True
                    h.filled = True
                    h.filled_by = p.piece_id
                    self.robot_face = "happy"
                    self.flash_text = "encaixe correto"
                    self.flash_counter = 45
                    self.status_var.set(f"Sucesso: {p.piece_id} encaixou em {h.hole_id}.")
                    self.write_logic(self.evaluation_text("ENCAIXE CONFIRMADO", p, h, ev))
                    self.log(f"SUCESSO: {p.piece_id} -> {h.hole_id}")
                    self.memory.log("insert_success", p.piece_id, h.hole_id, ev.score, "success", "encaixe correto", asdict(ev))
                    self.phase = "idle"
                    self.current_action = None

                else:
                    self.agent.failed_pairs.add((p.piece_id, h.hole_id))
                    self.robot_face = "sad"
                    self.flash_text = ev.failure_reason
                    self.flash_counter = 45
                    self.status_var.set(f"Colisão: {ev.failure_reason}. Darwin recua.")
                    self.write_logic(
                        self.evaluation_text("COLISÃO / RECUO", p, h, ev)
                        + "\nDecisão: memorizar par como falho e tentar outra hipótese."
                    )
                    self.log(f"COLISÃO: {p.piece_id} -> {h.hole_id} | {ev.failure_reason}")
                    self.memory.log("collision", p.piece_id, h.hole_id, ev.score, "collision", ev.failure_reason, asdict(ev))
                    self.phase = "returning"
                    self.drag_t = 0.0
                    self.start_pos = (p.x, p.y)

        elif self.phase == "returning":
            p = self.piece(self.current_action.piece_id)
            sx, sy = self.start_pos or (p.x, p.y)
            tx, ty = self.return_pos or (p.home_x, p.home_y)
            self.drag_t = min(1.0, self.drag_t + 0.055)
            t = self.ease(self.drag_t)
            p.x = sx + (tx - sx) * t
            p.y = sy + (ty - sy) * t
            if self.drag_t >= 1.0:
                self.phase = "idle"
                self.current_action = None
                self.robot_face = "neutral"

    def ease(self, t: float) -> float:
        return 1 - (1 - t) * (1 - t)

    # --------------------------------------------------------
    # texto
    # --------------------------------------------------------

    def write_logic(self, txt: str) -> None:
        self.logic.configure(state="normal")
        self.logic.delete("1.0", "end")
        self.logic.insert("1.0", txt)
        self.logic.configure(state="disabled")

    def log(self, txt: str) -> None:
        self.history.configure(state="normal")
        self.history.insert("end", txt + "\n")
        self.history.see("end")
        self.history.configure(state="disabled")

    # --------------------------------------------------------
    # desenho
    # --------------------------------------------------------

    def draw(self) -> None:
        c = self.canvas
        c.delete("all")
        self.round_rect(18, 18, 922, 802, 28, fill="#F8FBFF", outline="#CBD8E8", width=2)
        c.create_text(42, 42, anchor="w", text="DARWIN v48.1 — rotação ativa",
                      font=("Segoe UI", 19, "bold"), fill=self.TEXT)
        c.create_text(42, 70, anchor="w",
                      text="O quadrado começa torto. Darwin precisa girar antes de encaixar.",
                      font=("Segoe UI", 11), fill=self.MUTED)

        self.draw_robot(165, 245)
        self.draw_criteria(54, 118)
        self.draw_board()
        self.draw_pieces()

        if self.current_action:
            self.draw_action_link()

        if self.flash_counter > 0 and self.flash_text:
            color = self.GREEN if "correto" in self.flash_text else self.BAD
            self.round_rect(560, 145, 890, 198, 18, fill="#FFFFFF", outline=color, width=3)
            c.create_text(725, 172, text=self.flash_text, font=("Segoe UI", 16, "bold"), fill=color)

        filled = sum(1 for h in self.holes if h.filled)
        c.create_text(42, 778, anchor="w",
                      text=f"Progresso: {filled}/3 buracos preenchidos | Memória SQLite: {'ON' if self.memory.enabled else 'OFF'}",
                      font=("Segoe UI", 11, "bold"), fill=self.TEXT)

    def round_rect(self, x1, y1, x2, y2, r=18, **kwargs):
        c = self.canvas
        pts = [
            x1+r, y1, x2-r, y1, x2, y1, x2, y1+r,
            x2, y2-r, x2, y2, x2-r, y2, x1+r, y2,
            x1, y2, x1, y2-r, x1, y1+r, x1, y1,
        ]
        return c.create_polygon(pts, smooth=True, splinesteps=36, **kwargs)

    def draw_robot(self, cx, cy):
        c = self.canvas
        c.create_oval(cx-76, cy-98, cx+76, cy+54, fill="#F8FBFF", outline="#B9C8DA", width=3)
        c.create_oval(cx-60, cy-70, cx+60, cy+18, fill="#192638", outline="#30465F", width=2)

        if self.robot_face == "happy":
            c.create_arc(cx-35, cy-38, cx-5, cy-8, start=180, extent=180, outline="#8BDBFF", width=4, style="arc")
            c.create_arc(cx+5, cy-38, cx+35, cy-8, start=180, extent=180, outline="#8BDBFF", width=4, style="arc")
            c.create_arc(cx-22, cy+0, cx+22, cy+24, start=180, extent=180, outline="#8BDBFF", width=3, style="arc")
        elif self.robot_face == "sad":
            c.create_oval(cx-35, cy-38, cx-12, cy-15, fill="#8BDBFF", outline="")
            c.create_oval(cx+12, cy-38, cx+35, cy-15, fill="#8BDBFF", outline="")
            c.create_arc(cx-22, cy+12, cx+22, cy+34, start=0, extent=180, outline="#8BDBFF", width=3, style="arc")
        elif self.robot_face == "thinking":
            c.create_oval(cx-35, cy-38, cx-12, cy-15, fill="#8BDBFF", outline="")
            c.create_oval(cx+12, cy-38, cx+35, cy-15, fill="#8BDBFF", outline="")
            c.create_text(cx, cy+4, text="...", font=("Segoe UI", 15, "bold"), fill="#8BDBFF")
        else:
            c.create_oval(cx-35, cy-38, cx-12, cy-15, fill="#8BDBFF", outline="")
            c.create_oval(cx+12, cy-38, cx+35, cy-15, fill="#8BDBFF", outline="")
            c.create_arc(cx-18, cy+2, cx+18, cy+20, start=180, extent=180, outline="#8BDBFF", width=3, style="arc")

        c.create_oval(cx-22, cy+33, cx+22, cy+77, fill="#DDF5FF", outline="#6EC6FF", width=3)
        c.create_oval(cx-10, cy+45, cx+10, cy+65, fill="#6EC6FF", outline="")
        c.create_text(cx, cy+98, text="DARWIN", font=("Segoe UI", 10, "bold"), fill="#355574")

        # braços
        c.create_line(cx+65, cy+50, cx+118, cy+96, fill="#A8B7C9", width=9)
        c.create_line(cx+118, cy+96, cx+153, cy+125, fill="#A8B7C9", width=7)
        c.create_oval(cx+146, cy+118, cx+164, cy+136, fill="#FFFFFF", outline="#8FA2B8", width=2)
        c.create_line(cx-65, cy+50, cx-112, cy+96, fill="#A8B7C9", width=9)
        c.create_line(cx-112, cy+96, cx-140, cy+126, fill="#A8B7C9", width=7)
        c.create_oval(cx-148, cy+118, cx-130, cy+136, fill="#FFFFFF", outline="#8FA2B8", width=2)

    def draw_criteria(self, x, y):
        c = self.canvas
        self.round_rect(x, y, x+390, y+138, 16, fill="#FFFFFF", outline="#D6E2F1", width=2)
        items = [("contorno", "□"), ("tamanho", "□ □"), ("profundidade", "▱"), ("orientação", "↻")]
        for i, (label, icon) in enumerate(items):
            px = x + 22 + i * 92
            c.create_text(px, y+22, text=label, anchor="w", font=("Segoe UI", 10, "bold"), fill="#22507C")
            c.create_text(px+26, y+75, text=icon, font=("Segoe UI", 30, "bold"), fill=self.BLUE)

    def draw_board(self):
        c = self.canvas
        self.round_rect(500, 310, 895, 600, 22, fill=self.WOOD, outline="#BE9569", width=2)
        c.create_rectangle(525, 340, 870, 570, fill="#E8C69A", outline="")
        for h in self.holes:
            self.draw_hole(h)

    def draw_hole(self, h: Hole):
        c = self.canvas
        fill = self.WOOD_DARK
        outline = "#62482F"
        if h.family == "square":
            c.create_rectangle(h.x-42, h.y-42, h.x+42, h.y+42, fill=fill, outline=outline, width=3)
            if h.filled:
                p = self.piece(h.filled_by)
                c.create_rectangle(h.x-37, h.y-37, h.x+37, h.y+37, fill=p.color, outline="")
        elif h.family == "triangle":
            pts = [h.x, h.y-48, h.x-48, h.y+39, h.x+48, h.y+39]
            c.create_polygon(pts, fill=fill, outline=outline, width=3)
            if h.filled:
                p = self.piece(h.filled_by)
                pts2 = [h.x, h.y-41, h.x-40, h.y+32, h.x+40, h.y+32]
                c.create_polygon(pts2, fill=p.color, outline="")
        else:
            c.create_oval(h.x-42, h.y-42, h.x+42, h.y+42, fill=fill, outline=outline, width=3)
            if h.filled:
                p = self.piece(h.filled_by)
                c.create_oval(h.x-37, h.y-37, h.x+37, h.y+37, fill=p.color, outline="")

    def draw_pieces(self):
        for p in self.pieces:
            if not p.placed:
                self.draw_piece(p)

    def rotated(self, pts, angle, cx, cy):
        a = math.radians(angle)
        out = []
        for x, y in pts:
            dx, dy = x-cx, y-cy
            out.append((cx + dx*math.cos(a) - dy*math.sin(a), cy + dx*math.sin(a) + dy*math.cos(a)))
        return out

    def draw_piece(self, p: Piece):
        c = self.canvas
        if self.current_action and self.current_action.piece_id == p.piece_id:
            c.create_oval(p.x-55, p.y-55, p.x+55, p.y+55, outline="#AEE8FF", width=3)

        if p.family == "square":
            half = p.size / 2
            pts = [(p.x-half, p.y-half), (p.x+half, p.y-half), (p.x+half, p.y+half), (p.x-half, p.y+half)]
            pts = self.rotated(pts, p.orientation_deg, p.x, p.y)
            c.create_polygon([v for pt in pts for v in pt], fill=p.color, outline="#2458B8", width=2)
            c.create_text(p.x, p.y+p.size/2+18, text=f"{p.orientation_deg:.0f}°", font=("Segoe UI", 9, "bold"), fill=self.MUTED)
        elif p.family == "triangle":
            half = p.size / 2
            pts = [(p.x, p.y-half), (p.x-half, p.y+half*0.84), (p.x+half, p.y+half*0.84)]
            pts = self.rotated(pts, p.orientation_deg, p.x, p.y)
            c.create_polygon([v for pt in pts for v in pt], fill=p.color, outline="#A98013", width=2)
        else:
            r = p.size / 2
            c.create_oval(p.x-r, p.y-r, p.x+r, p.y+r, fill=p.color, outline="#B43B3B", width=2)

        if "large" in p.piece_id:
            c.create_text(p.x, p.y+p.size/2+18, text="grande", font=("Segoe UI", 9, "bold"), fill=self.MUTED)
        if "deep" in p.piece_id:
            c.create_text(p.x, p.y+p.size/2+18, text="profundo", font=("Segoe UI", 9, "bold"), fill=self.MUTED)

    def draw_action_link(self):
        c = self.canvas
        try:
            p = self.piece(self.current_action.piece_id)
            h = self.hole(self.current_action.hole_id)
        except Exception:
            return
        c.create_line(p.x, p.y-60, h.x, h.y-76, fill="#6EC6FF", width=3, dash=(7, 5), arrow="last")
        c.create_text((p.x+h.x)/2, (p.y+h.y)/2-60, text=self.current_action.kind,
                      font=("Segoe UI", 10, "bold"), fill="#2870B8")


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
