from __future__ import annotations

"""
DARWIN v48.2 — Shape Sorter ao vivo: erro exploratório controlado

Objetivo pedagógico:
- Darwin deve testar UMA hipótese fraca em ambiente seguro.
- Se houver colisão, ele recua.
- Ele registra o motivo da falha.
- Ele evita repetir o mesmo erro sem nova evidência.
- Depois continua resolvendo o brinquedo com encaixe e rotação ativa.

Isto não é uma sequência fixa de "errar aqui e depois acertar ali".
A política é:
1. Se ainda não houve exploração controlada, procurar uma hipótese fraca
   com score intermediário.
2. Testar a hipótese fraca de forma segura.
3. Se falhar, memorizar o par como bloqueado.
4. Nas próximas escolhas, penalizar pares bloqueados.
5. Resolver o restante pela melhor compatibilidade física.

Uso:
    py darwin_shape_sorter_live_v48_2_controlled_error.py

Tabela SQLite:
    geometry_live_actions_v48_2
"""

import json
import math
import random
import sqlite3
import tkinter as tk
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from tkinter import ttk


DB_PATH = Path("darwin_home") / "darwin.db"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


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
    attempts: int = 0


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


class LiveMemoryV482:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self.enabled = True
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS geometry_live_actions_v48_2 (
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
                    INSERT INTO geometry_live_actions_v48_2 (
                        timestamp, action_kind, piece_id, hole_id, score, outcome, note, payload_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (now_iso(), action_kind, piece_id, hole_id, score, outcome, note, safe_json(payload)),
                )
                conn.commit()
        except Exception:
            self.enabled = False


class DarwinShapeAgentV482:
    def __init__(self, memory: LiveMemoryV482) -> None:
        self.memory = memory
        self.failed_pairs: set[tuple[str, str]] = set()
        self.controlled_error_done = False
        self.step_counter = 0

    def rotation_match(self, piece: Piece, hole: Hole) -> bool:
        if piece.family == "circle":
            return True
        symmetry = 90.0 if piece.family == "square" else 120.0
        delta = abs((piece.orientation_deg - hole.orientation_deg) % 360.0)
        if delta > 180.0:
            delta = 360.0 - delta
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
        score = round(score, 3)

        if observed:
            reason = ""
            explanation = "compatível: contorno, tamanho, profundidade e orientação permitem encaixe"
        elif not contour:
            reason = "contour_mismatch"
            explanation = "colisão de contorno: a forma da peça não corresponde à abertura"
        elif not size:
            reason = "size_mismatch"
            explanation = "colisão de tamanho: a peça é grande demais"
        elif not depth:
            reason = "depth_mismatch"
            explanation = "colisão de profundidade: a peça é profunda demais"
        elif not rotation:
            reason = "rotation_mismatch"
            explanation = "orientação incompatível: rotação pode resolver"
        else:
            reason = "unknown_collision"
            explanation = "colisão não classificada"

        return Evaluation(
            piece.piece_id, hole.hole_id,
            contour, size, depth, rotation, observed,
            not observed, score, reason, explanation
        )

    def choose(self, pieces: list[Piece], holes: list[Hole]) -> Action | None:
        available_pieces = [p for p in pieces if not p.placed]
        available_holes = [h for h in holes if not h.filled]
        if not available_pieces or not available_holes:
            return None

        ranked: list[tuple[float, Piece, Hole, Evaluation]] = []
        weak: list[tuple[float, Piece, Hole, Evaluation]] = []

        for p in available_pieces:
            for h in available_holes:
                ev = self.evaluate(p, h)
                score = ev.score
                if (p.piece_id, h.hole_id) in self.failed_pairs:
                    score -= 0.40
                score -= min(0.05 * p.attempts, 0.15)

                ranked.append((score, p, h, ev))

                # hipótese fraca segura: nem aleatória demais, nem já impossível por tamanho/profundidade.
                if (
                    not self.controlled_error_done
                    and not ev.observed_fit
                    and 0.45 <= ev.score <= 0.70
                    and ev.size_match
                    and ev.depth_match
                    and (p.piece_id, h.hole_id) not in self.failed_pairs
                ):
                    weak.append((score, p, h, ev))

        self.step_counter += 1

        if weak:
            # Escolhe a hipótese fraca mais plausível, não um erro arbitrário.
            weak.sort(key=lambda item: item[0], reverse=True)
            score, p, h, ev = weak[0]
            self.controlled_error_done = True
            self.memory.log(
                "controlled_explore_choose",
                p.piece_id, h.hole_id, ev.score,
                "chosen",
                "hipótese fraca escolhida para aprendizagem segura",
                asdict(ev),
            )
            return Action("think", p.piece_id, h.hole_id, ev, note="exploração controlada")

        ranked.sort(key=lambda item: item[0], reverse=True)
        score, p, h, ev = ranked[0]

        if self.failed_pairs and (p.piece_id, h.hole_id) not in self.failed_pairs:
            self.memory.log(
                "avoid_repeat",
                p.piece_id, h.hole_id, ev.score,
                "selected_non_failed_pair",
                f"par(es) bloqueado(s) ignorado(s): {sorted(self.failed_pairs)}",
                {
                    "selected": asdict(ev),
                    "failed_pairs": sorted([list(pair) for pair in self.failed_pairs]),
                },
            )

        self.memory.log(
            "choose",
            p.piece_id, h.hole_id, ev.score,
            "chosen",
            "melhor hipótese atual",
            asdict(ev),
        )
        return Action("think", p.piece_id, h.hole_id, ev, note="melhor hipótese atual")

    def action_after_think(self, piece: Piece, hole: Hole, ev: Evaluation) -> Action:
        if ev.observed_fit:
            return Action("insert", piece.piece_id, hole.hole_id, ev, note="encaixe previsto")

        if ev.failure_reason == "rotation_mismatch" and ev.contour_match and ev.size_match and ev.depth_match:
            return Action(
                "rotate",
                piece.piece_id,
                hole.hole_id,
                ev,
                target_angle=hole.orientation_deg,
                note="rotação ativa antes de desistir",
            )

        return Action(
            "controlled_collision",
            piece.piece_id,
            hole.hole_id,
            ev,
            note="testar hipótese fraca, detectar colisão e recuar",
        )


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
        root.title("DARWIN v48.2 — erro exploratório controlado")
        root.geometry("1380x860")
        root.configure(bg=self.BG)

        self.memory = LiveMemoryV482()
        self.agent = DarwinShapeAgentV482(self.memory)

        self.canvas = tk.Canvas(root, width=940, height=820, bg=self.BG, highlightthickness=0)
        self.canvas.pack(side="left", padx=14, pady=14)

        side = tk.Frame(root, bg=self.BG)
        side.pack(side="right", fill="both", expand=True, padx=(0, 14), pady=14)

        controls = tk.Frame(side, bg=self.BG)
        controls.pack(fill="x", pady=(0, 8))

        ttk.Button(controls, text="Iniciar Auto", command=self.start).grid(row=0, column=0, padx=4, pady=4, sticky="ew")
        ttk.Button(controls, text="Pausar", command=self.pause).grid(row=0, column=1, padx=4, pady=4, sticky="ew")
        ttk.Button(controls, text="Passo", command=self.step).grid(row=0, column=2, padx=4, pady=4, sticky="ew")
        ttk.Button(controls, text="Resetar", command=self.reset).grid(row=0, column=3, padx=4, pady=4, sticky="ew")
        ttk.Button(controls, text="Novo cenário", command=self.new_scenario).grid(row=1, column=0, columnspan=4, padx=4, pady=4, sticky="ew")

        for i in range(4):
            controls.grid_columnconfigure(i, weight=1)

        self.status_var = tk.StringVar(value="Pronto. Darwin fará uma exploração fraca segura antes de resolver.")
        self.status = tk.Label(side, textvariable=self.status_var, bg=self.PANEL, fg=self.TEXT,
                               wraplength=390, justify="left", anchor="w", padx=12, pady=10,
                               relief="solid", bd=1)
        self.status.pack(fill="x", pady=(0, 8))

        self.logic = tk.Text(side, height=18, wrap="word", bg=self.PANEL, fg=self.TEXT, relief="solid", bd=1)
        self.logic.pack(fill="x", pady=(0, 8))
        self.logic.configure(state="disabled")

        self.history = tk.Text(side, height=22, wrap="word", bg="#0D3B66", fg="#EAF7FF", relief="solid", bd=1)
        self.history.pack(fill="both", expand=True)
        self.history.configure(state="disabled")

        self.auto = False
        self.phase = "idle"
        self.current_action: Action | None = None
        self.counter = 0
        self.drag_t = 0.0
        self.start_pos: tuple[float, float] | None = None
        self.return_pos: tuple[float, float] | None = None
        self.robot_face = "neutral"
        self.flash_text = ""
        self.flash_counter = 0

        random.seed(482)
        self.setup_world()
        self.write_logic("Darwin aguardando.\n\nMeta v48.2: testar uma hipótese fraca, colidir com segurança, recuar e não repetir.")
        self.draw()
        root.after(25, self.loop)

    def setup_world(self) -> None:
        self.holes = [
            Hole("hole_square", "square", 555, 395, 82, 1.5),
            Hole("hole_triangle", "triangle", 690, 395, 86, 1.5),
            Hole("hole_circle", "circle", 825, 395, 82, 1.5),
        ]
        self.pieces = [
            Piece("piece_square_rotated", "square", 145, 650, 145, 650, 74, 1.0, 45.0, self.BLUE),
            Piece("piece_triangle", "triangle", 270, 650, 270, 650, 78, 1.0, 0.0, self.YELLOW),
            Piece("piece_circle", "circle", 395, 650, 395, 650, 74, 1.0, 0.0, self.RED),
            Piece("piece_circle_large", "circle", 145, 742, 145, 742, 104, 1.0, 0.0, "#F07C7C"),
            Piece("piece_square_deep", "square", 285, 742, 285, 742, 74, 2.4, 0.0, "#77A7F2"),
        ]
        self.agent.failed_pairs.clear()
        self.agent.controlled_error_done = False
        self.agent.step_counter = 0
        self.phase = "idle"
        self.current_action = None
        self.robot_face = "neutral"
        self.flash_text = ""
        self.flash_counter = 0

    def reset(self) -> None:
        self.auto = False
        self.setup_world()
        self.log("RESET: mundo reiniciado.")
        self.status_var.set("Mundo reiniciado. Darwin fará uma exploração controlada.")
        self.write_logic("Reset.\n\nA primeira hipótese fraca será escolhida por score intermediário, não por roteiro fixo.")

    def new_scenario(self) -> None:
        self.reset()
        for p in self.pieces:
            dx = random.randint(-18, 18)
            dy = random.randint(-8, 8)
            p.x += dx
            p.y += dy
            p.home_x = p.x
            p.home_y = p.y
        self.log("NOVO CENÁRIO: posições alteradas levemente.")

    def start(self) -> None:
        self.auto = True
        self.log("AUTO: iniciado.")

    def pause(self) -> None:
        self.auto = False
        self.log("AUTO: pausado.")

    def step(self) -> None:
        if self.phase == "idle":
            self.plan()
        else:
            self.status_var.set("Aguarde a ação atual terminar.")

    def loop(self) -> None:
        if self.auto and self.phase == "idle":
            self.plan()
        self.animate()
        self.draw()
        self.root.after(25, self.loop)

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
            self.status_var.set("Concluído. Darwin errou com segurança, recuou, evitou repetir e resolveu.")
            self.write_logic(
                "Estado final v48.2:\n"
                "- houve exploração fraca ✔\n"
                "- houve colisão controlada ✔\n"
                "- houve recuo ✔\n"
                "- erro foi memorizado ✔\n"
                "- Darwin evitou repetir o par falho ✔\n"
                "- brinquedo resolvido ✔"
            )
            self.log("SUCESSO: ciclo v48.2 concluído.")
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
        tag = "EXPLORAÇÃO" if action.note == "exploração controlada" else "PENSAR"
        self.log(f"{tag}: {p.piece_id} -> {h.hole_id} | score={ev.score:.2f} | {ev.failure_reason or 'success'}")
        self.write_logic(self.evaluation_text("OBSERVAR / AVALIAR", p, h, ev, action.note))

    def evaluation_text(self, title: str, p: Piece, h: Hole, ev: Evaluation, note: str = "") -> str:
        return (
            f"Ação: {title}\n\n"
            f"Política: {note or 'melhor hipótese atual'}\n\n"
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
            self.robot_face = "thinking"
            self.status_var.set("Rotation mismatch: Darwin vai girar antes de desistir.")
            self.write_logic(self.evaluation_text("CORRIGIR ORIENTAÇÃO", p, h, ev, next_action.note))
            self.log(f"GIRAR: {p.piece_id} de {p.orientation_deg:.0f}° para {h.orientation_deg:.0f}°")
            self.agent.memory.log("rotate_start", p.piece_id, h.hole_id, ev.score, "started", "rotação ativa", asdict(ev))

        elif next_action.kind == "insert":
            self.phase = "moving_insert"
            self.drag_t = 0.0
            self.start_pos = (p.x, p.y)
            self.return_pos = (p.home_x, p.home_y)
            self.robot_face = "focus"
            self.status_var.set("Compatível. Darwin vai inserir.")
            self.write_logic(self.evaluation_text("INSERIR", p, h, ev, next_action.note))
            self.log(f"INSERIR: {p.piece_id} -> {h.hole_id}")
            self.agent.memory.log("insert_start", p.piece_id, h.hole_id, ev.score, "started", "inserção", asdict(ev))

        elif next_action.kind == "controlled_collision":
            self.phase = "moving_collision"
            self.drag_t = 0.0
            self.start_pos = (p.x, p.y)
            self.return_pos = (p.home_x, p.home_y)
            self.robot_face = "focus"
            self.status_var.set("Hipótese fraca: Darwin vai testar e recuar se houver colisão.")
            self.write_logic(self.evaluation_text("TESTE CONTROLADO", p, h, ev, next_action.note))
            self.log(f"TESTE CONTROLADO: {p.piece_id} -> {h.hole_id}")
            self.agent.memory.log("controlled_collision_start", p.piece_id, h.hole_id, ev.score, "started", "teste seguro", asdict(ev))

    def animate(self) -> None:
        if self.flash_counter > 0:
            self.flash_counter -= 1

        if self.phase == "idle" or self.current_action is None:
            return

        if self.phase == "thinking":
            self.counter -= 1
            if self.counter <= 0:
                self.after_think()

        elif self.phase == "rotating":
            p = self.piece(self.current_action.piece_id)
            h = self.hole(self.current_action.hole_id)
            target = h.orientation_deg
            delta = (target - p.orientation_deg) % 360.0
            if delta > 180.0:
                delta -= 360.0
            step = 5.5 if delta > 0 else -5.5
            if abs(delta) <= 5.5:
                p.orientation_deg = target
                ev = self.agent.evaluate(p, h)
                self.agent.memory.log("rotate_success", p.piece_id, h.hole_id, ev.score, "success", "rotação resolveu", asdict(ev))
                self.log(f"ROTAÇÃO RESOLVEU: {p.piece_id} -> {h.hole_id}")
                self.current_action = Action("insert", p.piece_id, h.hole_id, ev, note="após rotação")
                self.phase = "moving_insert"
                self.drag_t = 0.0
                self.start_pos = (p.x, p.y)
                self.return_pos = (p.home_x, p.home_y)
                self.write_logic(self.evaluation_text("REAVALIAR APÓS ROTAÇÃO", p, h, ev, "rotação resolveu"))
            else:
                p.orientation_deg = (p.orientation_deg + step) % 360.0

        elif self.phase in {"moving_insert", "moving_collision"}:
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
                    self.write_logic(self.evaluation_text("ENCAIXE CONFIRMADO", p, h, ev, "sucesso"))
                    self.log(f"SUCESSO: {p.piece_id} -> {h.hole_id}")
                    self.agent.memory.log("insert_success", p.piece_id, h.hole_id, ev.score, "success", "encaixe correto", asdict(ev))
                    self.phase = "idle"
                    self.current_action = None
                else:
                    self.agent.failed_pairs.add((p.piece_id, h.hole_id))
                    self.robot_face = "sad"
                    self.flash_text = ev.failure_reason
                    self.flash_counter = 50
                    self.status_var.set(f"Colisão controlada: {ev.failure_reason}. Darwin recua e memoriza.")
                    self.write_logic(
                        self.evaluation_text("COLISÃO CONTROLADA / RECUO", p, h, ev, "aprendizagem por erro")
                        + "\nMemória: este par será evitado sem nova evidência."
                    )
                    self.log(f"COLISÃO CONTROLADA: {p.piece_id} -> {h.hole_id} | {ev.failure_reason}")
                    self.agent.memory.log("controlled_collision", p.piece_id, h.hole_id, ev.score, "collision", ev.failure_reason, asdict(ev))
                    self.agent.memory.log(
                        "error_memory_write",
                        p.piece_id,
                        h.hole_id,
                        ev.score,
                        "stored",
                        "par falho memorizado para evitar repetição",
                        {"failed_pairs": sorted([list(pair) for pair in self.agent.failed_pairs]), "evaluation": asdict(ev)},
                    )
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
                self.log(f"RECUO: {p.piece_id} voltou ao ponto seguro.")
                self.phase = "idle"
                self.current_action = None
                self.robot_face = "neutral"

    def ease(self, t: float) -> float:
        return 1.0 - (1.0 - t) * (1.0 - t)

    def write_logic(self, text: str) -> None:
        self.logic.configure(state="normal")
        self.logic.delete("1.0", "end")
        self.logic.insert("1.0", text)
        self.logic.configure(state="disabled")

    def log(self, text: str) -> None:
        self.history.configure(state="normal")
        self.history.insert("end", text + "\n")
        self.history.see("end")
        self.history.configure(state="disabled")

    def draw(self) -> None:
        c = self.canvas
        c.delete("all")
        c.create_rectangle(0, 0, 940, 820, fill=self.BG, outline="")
        self.round_rect(18, 18, 922, 802, 28, fill="#F8FBFF", outline="#CBD8E8", width=2)

        c.create_text(42, 42, anchor="w", text="DARWIN v48.2 — erro exploratório controlado",
                      font=("Segoe UI", 18, "bold"), fill=self.TEXT)
        c.create_text(42, 70, anchor="w",
                      text="Darwin testa uma hipótese fraca, colide com segurança, recua e evita repetir.",
                      font=("Segoe UI", 11), fill=self.MUTED)

        self.draw_robot(165, 245)
        self.draw_criteria(54, 118)
        self.draw_board()
        for p in self.pieces:
            if not p.placed:
                self.draw_piece(p)

        if self.current_action:
            self.draw_action_link()

        if self.flash_counter > 0 and self.flash_text:
            color = self.GREEN if "correto" in self.flash_text else self.BAD
            self.round_rect(560, 145, 890, 198, 18, fill="#FFFFFF", outline=color, width=3)
            c.create_text(725, 172, text=self.flash_text, font=("Segoe UI", 16, "bold"), fill=color)

        filled = sum(1 for h in self.holes if h.filled)
        c.create_text(42, 778, anchor="w",
                      text=f"Progresso: {filled}/3 | Pares falhos memorizados: {len(self.agent.failed_pairs)} | SQLite: {'ON' if self.memory.enabled else 'OFF'}",
                      font=("Segoe UI", 11, "bold"), fill=self.TEXT)

    def round_rect(self, x1, y1, x2, y2, r=18, **kwargs):
        pts = [
            x1+r, y1, x2-r, y1, x2, y1, x2, y1+r,
            x2, y2-r, x2, y2, x2-r, y2, x1+r, y2,
            x1, y2, x1, y2-r, x1, y1+r, x1, y1,
        ]
        return self.canvas.create_polygon(pts, smooth=True, splinesteps=36, **kwargs)

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
        c.create_line(cx+65, cy+50, cx+118, cy+96, fill="#A8B7C9", width=9)
        c.create_line(cx+118, cy+96, cx+153, cy+125, fill="#A8B7C9", width=7)
        c.create_oval(cx+146, cy+118, cx+164, cy+136, fill="#FFFFFF", outline="#8FA2B8", width=2)
        c.create_line(cx-65, cy+50, cx-112, cy+96, fill="#A8B7C9", width=9)
        c.create_line(cx-112, cy+96, cx-140, cy+126, fill="#A8B7C9", width=7)
        c.create_oval(cx-148, cy+118, cx-130, cy+136, fill="#FFFFFF", outline="#8FA2B8", width=2)

    def draw_criteria(self, x, y):
        c = self.canvas
        self.round_rect(x, y, x+430, y+138, 16, fill="#FFFFFF", outline="#D6E2F1", width=2)
        items = [("hipótese", "?"), ("colisão", "×"), ("recuo", "↩"), ("memória", "M"), ("evitar repetir", "≠")]
        for i, (label, icon) in enumerate(items):
            px = x + 20 + i * 82
            c.create_text(px, y+22, text=label, anchor="w", font=("Segoe UI", 9, "bold"), fill="#22507C")
            c.create_text(px+22, y+76, text=icon, font=("Segoe UI", 28, "bold"), fill=self.BLUE)

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
            c.create_polygon([v for point in pts for v in point], fill=p.color, outline="#2458B8", width=2)
            c.create_text(p.x, p.y+p.size/2+18, text=f"{p.orientation_deg:.0f}°", font=("Segoe UI", 9, "bold"), fill=self.MUTED)
        elif p.family == "triangle":
            half = p.size / 2
            pts = [(p.x, p.y-half), (p.x-half, p.y+half*0.84), (p.x+half, p.y+half*0.84)]
            pts = self.rotated(pts, p.orientation_deg, p.x, p.y)
            c.create_polygon([v for point in pts for v in point], fill=p.color, outline="#A98013", width=2)
        else:
            r = p.size / 2
            c.create_oval(p.x-r, p.y-r, p.x+r, p.y+r, fill=p.color, outline="#B43B3B", width=2)

        if "large" in p.piece_id:
            c.create_text(p.x, p.y+p.size/2+18, text="grande", font=("Segoe UI", 9, "bold"), fill=self.MUTED)
        if "deep" in p.piece_id:
            c.create_text(p.x, p.y+p.size/2+18, text="profundo", font=("Segoe UI", 9, "bold"), fill=self.MUTED)

    def draw_action_link(self):
        try:
            p = self.piece(self.current_action.piece_id)
            h = self.hole(self.current_action.hole_id)
        except Exception:
            return
        self.canvas.create_line(p.x, p.y-60, h.x, h.y-76, fill="#6EC6FF", width=3, dash=(7, 5), arrow="last")
        self.canvas.create_text((p.x+h.x)/2, (p.y+h.y)/2-60, text=self.current_action.kind,
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
