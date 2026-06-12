
from __future__ import annotations

"""
DARWIN v48.1-demo — Shape Sorter ao vivo (Tkinter)

Objetivo:
- Visualizar o Darwin resolvendo o brinquedo de encaixe AO VIVO.
- A decisão não é uma sequência fixa hardcoded; ela é escolhida em tempo real
  por uma rotina de avaliação física simples:
    contorno, tamanho, profundidade, orientação e colisão.

Requisitos:
- Python 3.10+ (ideal)
- Tkinter (normalmente já vem com Python no Windows)

Uso:
    py darwin_shape_sorter_live_v48_1.py

Controles:
- Iniciar Auto
- Pausar
- Passo
- Resetar
- Exploração ON/OFF

Observação honesta:
Isto ainda é uma simulação pedagógica. O Darwin "decide" dentro deste mundo
geométrico simplificado, avaliando opções em runtime; não é uma sequência
pré-programada de "quadrado, depois triângulo, depois círculo".
"""

import math
import random
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import ttk


# ============================================================
# MODELOS
# ============================================================

@dataclass
class Piece:
    piece_id: str
    family: str
    x: float
    y: float
    size: float
    depth: float = 1.0
    orientation_deg: float = 0.0
    color: str = "#4A90E2"
    placed: bool = False
    locked_hole_id: str | None = None
    attempt_count: int = 0
    success: bool = False

    def center(self) -> tuple[float, float]:
        return self.x, self.y


@dataclass
class Hole:
    hole_id: str
    family: str
    x: float
    y: float
    size: float
    depth: float = 1.5
    tolerance: float = 4.0
    orientation_deg: float = 0.0
    filled: bool = False
    filled_by: str | None = None


@dataclass
class FitEvaluation:
    piece_id: str
    hole_id: str
    contour_match: bool
    size_match: bool
    depth_match: bool
    rotation_match: bool
    collision_detected: bool
    fit_score: float
    observed_fit: bool
    failure_reason: str
    explanation: str


@dataclass
class Action:
    kind: str  # think, rotate, move_insert, move_bounce
    piece_id: str | None = None
    hole_id: str | None = None
    target_orientation: float | None = None
    evaluation: FitEvaluation | None = None
    text: str = ""


# ============================================================
# DARWIN AGENTE
# ============================================================

class DarwinShapeAgent:
    def __init__(self) -> None:
        self.history: list[str] = []
        self.failed_pairs: set[tuple[str, str]] = set()
        self.exploration_enabled: bool = False

    def log(self, msg: str) -> None:
        self.history.append(msg)
        if len(self.history) > 200:
            self.history = self.history[-200:]

    def _rotation_match(self, piece: Piece, hole: Hole) -> bool:
        if piece.family == "circle":
            return True
        symmetry = 90.0 if piece.family == "square" else 120.0
        delta = abs((piece.orientation_deg - hole.orientation_deg) % 360.0)
        if delta > 180.0:
            delta = 360.0 - delta
        remainder = min(delta % symmetry, symmetry - (delta % symmetry))
        return remainder <= 3.0

    def evaluate_fit(self, piece: Piece, hole: Hole) -> FitEvaluation:
        contour_match = piece.family == hole.family
        size_match = piece.size <= hole.size + hole.tolerance
        depth_match = piece.depth <= hole.depth
        rotation_match = self._rotation_match(piece, hole)

        observed_fit = contour_match and size_match and depth_match and rotation_match
        collision_detected = not observed_fit

        fit_score = 0.0
        fit_score += 0.45 if contour_match else 0.0
        fit_score += 0.20 if size_match else 0.0
        fit_score += 0.20 if depth_match else 0.0
        fit_score += 0.15 if rotation_match else 0.0
        fit_score = round(fit_score, 3)

        if observed_fit:
            failure_reason = ""
            explanation = "encaixe bem-sucedido: contorno, tamanho, profundidade e orientação são compatíveis"
        elif not contour_match:
            failure_reason = "contour_mismatch"
            explanation = "falha: o contorno da peça não corresponde ao contorno do buraco"
        elif not size_match:
            failure_reason = "size_mismatch"
            explanation = "falha: a peça é grande demais para esse buraco"
        elif not depth_match:
            failure_reason = "depth_mismatch"
            explanation = "falha: a profundidade da peça excede a profundidade do buraco"
        elif not rotation_match:
            failure_reason = "rotation_mismatch"
            explanation = "falha: a orientação da peça não coincide com a abertura"
        else:
            failure_reason = "unknown_collision"
            explanation = "falha: colisão detectada"

        return FitEvaluation(
            piece_id=piece.piece_id,
            hole_id=hole.hole_id,
            contour_match=contour_match,
            size_match=size_match,
            depth_match=depth_match,
            rotation_match=rotation_match,
            collision_detected=collision_detected,
            fit_score=fit_score,
            observed_fit=observed_fit,
            failure_reason=failure_reason,
            explanation=explanation,
        )

    def choose_next_action(self, pieces: list[Piece], holes: list[Hole]) -> Action | None:
        remaining_pieces = [p for p in pieces if not p.placed]
        remaining_holes = [h for h in holes if not h.filled]

        if not remaining_pieces or not remaining_holes:
            return None

        candidates: list[tuple[float, Piece, Hole, FitEvaluation]] = []
        for piece in remaining_pieces:
            for hole in remaining_holes:
                ev = self.evaluate_fit(piece, hole)
                penalty = 0.0
                if (piece.piece_id, hole.hole_id) in self.failed_pairs:
                    penalty -= 0.20
                if piece.attempt_count > 0:
                    penalty -= min(0.05 * piece.attempt_count, 0.15)
                score = ev.fit_score + penalty
                candidates.append((score, piece, hole, ev))

        candidates.sort(key=lambda row: (row[0], -row[1].attempt_count), reverse=True)

        # exploração opcional: às vezes tenta uma hipótese fraca e aprende com ela
        if self.exploration_enabled:
            weak = [row for row in candidates if 0.35 <= row[0] < 0.65]
            if weak and random.random() < 0.20:
                score, piece, hole, ev = random.choice(weak)
                self.log(f"Exploração: testar hipótese fraca {piece.piece_id} -> {hole.hole_id} (score={score:.2f})")
                return Action(
                    kind="think",
                    piece_id=piece.piece_id,
                    hole_id=hole.hole_id,
                    evaluation=ev,
                    text=f"Explorando hipótese: {piece.family} → {hole.family}",
                )

        best_score, piece, hole, ev = candidates[0]
        self.log(
            f"Avaliação principal: {piece.piece_id} -> {hole.hole_id} | "
            f"score={best_score:.2f} | reason={ev.failure_reason or 'success'}"
        )
        return Action(
            kind="think",
            piece_id=piece.piece_id,
            hole_id=hole.hole_id,
            evaluation=ev,
            text=f"Avaliar {piece.family} → {hole.family} | score={best_score:.2f}",
        )

    def next_after_think(self, piece: Piece, hole: Hole, ev: FitEvaluation) -> Action:
        if ev.failure_reason == "rotation_mismatch":
            target = hole.orientation_deg
            self.log(f"Tentando corrigir por rotação: {piece.piece_id} para {target:.0f}°")
            return Action(
                kind="rotate",
                piece_id=piece.piece_id,
                hole_id=hole.hole_id,
                target_orientation=target,
                evaluation=ev,
                text=f"Rotation mismatch detectado. Girar peça para {target:.0f}°",
            )

        if ev.observed_fit:
            self.log(f"Hipótese forte confirmada para inserção: {piece.piece_id} -> {hole.hole_id}")
            return Action(
                kind="move_insert",
                piece_id=piece.piece_id,
                hole_id=hole.hole_id,
                evaluation=ev,
                text="Compatibilidade alta. Inserir a peça.",
            )

        self.log(f"Hipótese fraca/falha prevista: {piece.piece_id} -> {hole.hole_id}")
        return Action(
            kind="move_bounce",
            piece_id=piece.piece_id,
            hole_id=hole.hole_id,
            evaluation=ev,
            text="Hipótese fraca. Testar e recuar se houver colisão.",
        )


# ============================================================
# APP VISUAL
# ============================================================

class DarwinLiveApp:
    BG = "#F2F6FB"
    PANEL = "#FFFFFF"
    LINE = "#B9C7DA"
    TEXT = "#20324A"
    MUTED = "#5E738D"
    OK = "#2EB872"
    BAD = "#D94C4C"
    ACCENT = "#4A90E2"
    YELLOW = "#F2C94C"
    RED = "#EB5757"
    BLUE = "#3A7BEB"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("DARWIN v48.1-demo — Shape Sorter ao vivo")
        self.root.geometry("1320x840")
        self.root.configure(bg=self.BG)

        self.agent = DarwinShapeAgent()

        self.canvas = tk.Canvas(root, width=900, height=780, bg=self.BG, highlightthickness=0)
        self.canvas.pack(side="left", padx=12, pady=12)

        right = tk.Frame(root, bg=self.BG)
        right.pack(side="right", fill="both", expand=True, padx=(0, 12), pady=12)

        controls = tk.Frame(right, bg=self.BG)
        controls.pack(fill="x", pady=(0, 8))

        self.btn_start = ttk.Button(controls, text="Iniciar Auto", command=self.start_auto)
        self.btn_start.grid(row=0, column=0, padx=4, pady=4, sticky="ew")

        self.btn_pause = ttk.Button(controls, text="Pausar", command=self.pause_auto)
        self.btn_pause.grid(row=0, column=1, padx=4, pady=4, sticky="ew")

        self.btn_step = ttk.Button(controls, text="Passo", command=self.step_once)
        self.btn_step.grid(row=0, column=2, padx=4, pady=4, sticky="ew")

        self.btn_reset = ttk.Button(controls, text="Resetar", command=self.reset_world)
        self.btn_reset.grid(row=0, column=3, padx=4, pady=4, sticky="ew")

        self.explore_var = tk.BooleanVar(value=False)
        self.chk_explore = ttk.Checkbutton(
            controls,
            text="Exploração ON/OFF",
            variable=self.explore_var,
            command=self.toggle_exploration,
        )
        self.chk_explore.grid(row=1, column=0, columnspan=4, sticky="w", padx=4, pady=4)

        for i in range(4):
            controls.grid_columnconfigure(i, weight=1)

        self.status_var = tk.StringVar(value="Pronto. Clique em 'Iniciar Auto' ou 'Passo'.")
        status = tk.Label(
            right, textvariable=self.status_var, bg=self.PANEL, fg=self.TEXT,
            anchor="w", justify="left", wraplength=360, padx=12, pady=10,
            relief="solid", bd=1
        )
        status.pack(fill="x", pady=(0, 8))

        self.logic_text = tk.Text(right, height=16, wrap="word", bg=self.PANEL, fg=self.TEXT, relief="solid", bd=1)
        self.logic_text.pack(fill="x", pady=(0, 8))
        self.logic_text.insert("1.0", "Painel cognitivo do Darwin.\n")
        self.logic_text.configure(state="disabled")

        self.history_text = tk.Text(right, height=20, wrap="word", bg=self.PANEL, fg=self.TEXT, relief="solid", bd=1)
        self.history_text.pack(fill="both", expand=True)
        self.history_text.insert("1.0", "Histórico de ações.\n")
        self.history_text.configure(state="disabled")

        self.auto_running = False
        self.current_action: Action | None = None
        self.animation_phase = "idle"
        self.animation_counter = 0
        self.anim_piece_id: str | None = None
        self.target_hole_id: str | None = None
        self.drag_progress = 0.0
        self.rotation_progress = 0.0
        self.bounce_back = False
        self.saved_position: tuple[float, float] | None = None

        self.world_seed = 48
        random.seed(self.world_seed)
        self.setup_world()
        self.draw_everything()
        self.root.after(30, self.tick)

    # --------------------------------------------------------
    # Mundo
    # --------------------------------------------------------

    def setup_world(self) -> None:
        self.pieces: list[Piece] = [
            Piece("piece_square", "square", 170, 620, 70, 1.0, 0.0, self.BLUE),
            Piece("piece_triangle", "triangle", 300, 625, 74, 1.0, 0.0, self.YELLOW),
            Piece("piece_circle", "circle", 430, 620, 70, 1.0, 0.0, self.RED),
        ]

        self.holes: list[Hole] = [
            Hole("hole_square", "square", 540, 380, 78, 1.5, 4.0, 0.0, False, None),
            Hole("hole_triangle", "triangle", 660, 380, 82, 1.5, 4.0, 0.0, False, None),
            Hole("hole_circle", "circle", 780, 380, 78, 1.5, 4.0, 0.0, False, None),
        ]

        self.robot_face = "neutral"
        self.agent.history.clear()
        self.agent.failed_pairs.clear()
        self.current_action = None
        self.animation_phase = "idle"
        self.animation_counter = 0
        self.anim_piece_id = None
        self.target_hole_id = None
        self.drag_progress = 0.0
        self.rotation_progress = 0.0
        self.bounce_back = False
        self.saved_position = None
        self.status_var.set("Mundo resetado. Darwin pronto para observar e agir.")
        self.set_logic_panel("Darwin aguardando.\nSem ação em andamento.")

    def reset_world(self) -> None:
        self.auto_running = False
        self.setup_world()
        self.draw_everything()
        self.push_history("RESET: mundo reiniciado.")

    def toggle_exploration(self) -> None:
        self.agent.exploration_enabled = bool(self.explore_var.get())
        self.push_history(f"Exploração {'ativada' if self.agent.exploration_enabled else 'desativada'}.")

    # --------------------------------------------------------
    # Controles
    # --------------------------------------------------------

    def start_auto(self) -> None:
        self.auto_running = True
        self.status_var.set("Auto ligado. Darwin está resolvendo o brinquedo.")
        self.push_history("AUTO: iniciado.")

    def pause_auto(self) -> None:
        self.auto_running = False
        self.status_var.set("Auto pausado.")
        self.push_history("AUTO: pausado.")

    def step_once(self) -> None:
        if self.animation_phase == "idle":
            self.plan_next_action()
        else:
            self.status_var.set("Há uma animação em andamento. Aguarde concluir.")

    # --------------------------------------------------------
    # Loop
    # --------------------------------------------------------

    def tick(self) -> None:
        if self.auto_running and self.animation_phase == "idle":
            self.plan_next_action()

        self.update_animation()
        self.draw_everything()
        self.root.after(30, self.tick)

    # --------------------------------------------------------
    # Planejamento
    # --------------------------------------------------------

    def get_piece(self, piece_id: str) -> Piece:
        for p in self.pieces:
            if p.piece_id == piece_id:
                return p
        raise KeyError(piece_id)

    def get_hole(self, hole_id: str) -> Hole:
        for h in self.holes:
            if h.hole_id == hole_id:
                return h
        raise KeyError(hole_id)

    def world_solved(self) -> bool:
        return all(h.filled for h in self.holes)

    def plan_next_action(self) -> None:
        if self.world_solved():
            self.robot_face = "happy"
            self.status_var.set("Concluído. Darwin encaixou todas as peças corretamente.")
            self.set_logic_panel(
                "Estado final:\n"
                "- contorno ✔\n- tamanho ✔\n- profundidade ✔\n- orientação ✔\n\n"
                "Encaixe correto."
            )
            self.auto_running = False
            self.push_history("SUCESSO: todas as peças foram encaixadas.")
            return

        action = self.agent.choose_next_action(self.pieces, self.holes)
        if action is None:
            self.status_var.set("Sem ação disponível.")
            self.auto_running = False
            return

        self.current_action = action
        self.animation_phase = "thinking"
        self.animation_counter = 26  # ~780 ms
        self.anim_piece_id = action.piece_id
        self.target_hole_id = action.hole_id
        self.robot_face = "thinking"

        piece = self.get_piece(action.piece_id) if action.piece_id else None
        hole = self.get_hole(action.hole_id) if action.hole_id else None
        ev = action.evaluation

        if piece and hole and ev:
            self.status_var.set(f"Darwin avaliando {piece.family} → {hole.family} ...")
            self.set_logic_panel(
                f"Ação atual: OBSERVAR / PENSAR\n\n"
                f"Peça: {piece.piece_id} ({piece.family})\n"
                f"Buraco: {hole.hole_id} ({hole.family})\n\n"
                f"contorno_match = {'sim' if ev.contour_match else 'não'}\n"
                f"size_match = {'sim' if ev.size_match else 'não'}\n"
                f"depth_match = {'sim' if ev.depth_match else 'não'}\n"
                f"rotation_match = {'sim' if ev.rotation_match else 'não'}\n"
                f"fit_score = {ev.fit_score:.2f}\n"
                f"previsão = {'encaixa' if ev.observed_fit else 'não encaixa'}\n"
                f"falha prevista = {ev.failure_reason or 'nenhuma'}\n\n"
                f"explicação: {ev.explanation}"
            )
            self.push_history(
                f"PENSAR: {piece.piece_id} -> {hole.hole_id} | "
                f"score={ev.fit_score:.2f} | {ev.failure_reason or 'success'}"
            )

    # --------------------------------------------------------
    # Animação
    # --------------------------------------------------------

    def update_animation(self) -> None:
        if self.animation_phase == "idle" or self.current_action is None:
            return

        if self.animation_phase == "thinking":
            self.animation_counter -= 1
            if self.animation_counter <= 0:
                piece = self.get_piece(self.current_action.piece_id)
                hole = self.get_hole(self.current_action.hole_id)
                ev = self.agent.evaluate_fit(piece, hole)
                next_action = self.agent.next_after_think(piece, hole, ev)
                self.current_action = next_action

                if next_action.kind == "rotate":
                    self.animation_phase = "rotating"
                    self.rotation_progress = 0.0
                    self.saved_position = (piece.x, piece.y)
                    self.status_var.set(next_action.text)
                    self.set_logic_panel(
                        f"Ação atual: GIRAR PEÇA\n\n"
                        f"Peça: {piece.piece_id}\n"
                        f"Ângulo atual: {piece.orientation_deg:.0f}°\n"
                        f"Ângulo alvo: {next_action.target_orientation:.0f}°\n\n"
                        f"Motivo: corrigir mismatch de orientação antes da inserção."
                    )
                    self.push_history(f"GIRAR: {piece.piece_id} -> {next_action.target_orientation:.0f}°")

                elif next_action.kind == "move_insert":
                    self.animation_phase = "moving_insert"
                    self.drag_progress = 0.0
                    self.saved_position = (piece.x, piece.y)
                    self.status_var.set(next_action.text)
                    self.set_logic_panel(
                        f"Ação atual: INSERIR\n\n"
                        f"Peça: {piece.piece_id}\n"
                        f"Destino: {hole.hole_id}\n\n"
                        f"Darwin decidiu que a compatibilidade é suficiente para encaixe."
                    )
                    self.push_history(f"INSERIR: {piece.piece_id} -> {hole.hole_id}")

                elif next_action.kind == "move_bounce":
                    self.animation_phase = "moving_bounce"
                    self.drag_progress = 0.0
                    self.saved_position = (piece.x, piece.y)
                    self.status_var.set(next_action.text)
                    self.set_logic_panel(
                        f"Ação atual: TESTAR HIPÓTESE FRACA\n\n"
                        f"Peça: {piece.piece_id}\n"
                        f"Destino: {hole.hole_id}\n\n"
                        f"Darwin vai testar a hipótese e recuar se detectar colisão."
                    )
                    self.push_history(f"TESTAR: {piece.piece_id} -> {hole.hole_id}")

        elif self.animation_phase == "rotating":
            piece = self.get_piece(self.current_action.piece_id)
            target = float(self.current_action.target_orientation or 0.0)
            step = 6.0
            delta = (target - piece.orientation_deg) % 360.0
            if delta > 180:
                delta -= 360

            if abs(delta) <= step:
                piece.orientation_deg = target
                piece.attempt_count += 1
                hole = self.get_hole(self.current_action.hole_id)
                ev = self.agent.evaluate_fit(piece, hole)
                if ev.observed_fit:
                    self.current_action = Action(
                        kind="move_insert",
                        piece_id=piece.piece_id,
                        hole_id=hole.hole_id,
                        evaluation=ev,
                        text="Rotação resolveu o problema. Inserir a peça.",
                    )
                    self.animation_phase = "moving_insert"
                    self.drag_progress = 0.0
                    self.status_var.set("Rotação concluída. Nova avaliação: encaixe possível.")
                    self.set_logic_panel(
                        f"Ação atual: REAVALIAR APÓS ROTAÇÃO\n\n"
                        f"Novo rotation_match = sim\n"
                        f"Novo fit_score = {ev.fit_score:.2f}\n\n"
                        f"Conclusão: agora a peça pode ser inserida."
                    )
                    self.push_history(f"ROTAÇÃO RESOLVEU: {piece.piece_id} agora encaixa em {hole.hole_id}")
                else:
                    self.current_action = Action(
                        kind="move_bounce",
                        piece_id=piece.piece_id,
                        hole_id=hole.hole_id,
                        evaluation=ev,
                        text="Mesmo após rotação, a hipótese continua fraca. Testar e recuar.",
                    )
                    self.animation_phase = "moving_bounce"
                    self.drag_progress = 0.0
                    self.status_var.set("Rotação não bastou. Darwin vai testar e recuar.")
                    self.push_history(f"ROTAÇÃO NÃO BASTOU: {piece.piece_id} -> {hole.hole_id}")
            else:
                piece.orientation_deg += step if delta > 0 else -step

        elif self.animation_phase in ("moving_insert", "moving_bounce"):
            piece = self.get_piece(self.current_action.piece_id)
            hole = self.get_hole(self.current_action.hole_id)
            sx, sy = self.saved_position or (piece.x, piece.y)
            self.drag_progress += 0.05
            t = min(self.drag_progress, 1.0)

            # curva simples
            mx = sx + (hole.x - sx) * t
            my = sy + (hole.y - 120 - sy) * t + 50 * math.sin(t * math.pi)

            piece.x = mx
            piece.y = my

            if t >= 1.0:
                ev = self.agent.evaluate_fit(piece, hole)
                piece.attempt_count += 1

                if self.animation_phase == "moving_insert" and ev.observed_fit:
                    piece.x, piece.y = hole.x, hole.y
                    piece.placed = True
                    piece.success = True
                    piece.locked_hole_id = hole.hole_id
                    hole.filled = True
                    hole.filled_by = piece.piece_id
                    self.status_var.set(f"Sucesso: {piece.family} encaixou em {hole.family}.")
                    self.robot_face = "happy"
                    self.push_history(f"SUCESSO: {piece.piece_id} encaixada em {hole.hole_id}")
                    self.set_logic_panel(
                        f"Ação atual: ENCAIXE BEM-SUCEDIDO\n\n"
                        f"Peça: {piece.piece_id}\n"
                        f"Buraco: {hole.hole_id}\n\n"
                        f"Resultado: encaixe correto.\n"
                        f"Motivo: compatibilidade de contorno, tamanho, profundidade e orientação."
                    )
                    self.animation_phase = "idle"
                    self.current_action = None
                    self.anim_piece_id = None
                    self.target_hole_id = None

                else:
                    # colisão / recuo
                    self.agent.failed_pairs.add((piece.piece_id, hole.hole_id))
                    self.push_history(
                        f"COLISÃO: {piece.piece_id} -> {hole.hole_id} | "
                        f"{ev.failure_reason or 'falha'}"
                    )
                    self.set_logic_panel(
                        f"Ação atual: COLISÃO / RECUO\n\n"
                        f"Peça: {piece.piece_id}\n"
                        f"Buraco: {hole.hole_id}\n\n"
                        f"Razão: {ev.failure_reason}\n"
                        f"Explicação: {ev.explanation}\n\n"
                        f"Darwin vai recuar e tentar outra hipótese."
                    )
                    self.status_var.set(f"Colisão detectada: {ev.failure_reason}. Darwin vai tentar outra hipótese.")
                    self.animation_phase = "bouncing_back"
                    self.drag_progress = 0.0
                    self.robot_face = "sad"

        elif self.animation_phase == "bouncing_back":
            piece = self.get_piece(self.current_action.piece_id)
            sx, sy = piece.x, piece.y
            tx, ty = self.saved_position or (piece.x, piece.y)
            self.drag_progress += 0.08
            t = min(self.drag_progress, 1.0)
            piece.x = sx + (tx - sx) * t
            piece.y = sy + (ty - sy) * t

            if t >= 1.0:
                self.animation_phase = "idle"
                self.current_action = None
                self.anim_piece_id = None
                self.target_hole_id = None
                self.robot_face = "neutral"

    # --------------------------------------------------------
    # UI texto
    # --------------------------------------------------------

    def set_logic_panel(self, text: str) -> None:
        self.logic_text.configure(state="normal")
        self.logic_text.delete("1.0", "end")
        self.logic_text.insert("1.0", text)
        self.logic_text.configure(state="disabled")

    def push_history(self, line: str) -> None:
        self.history_text.configure(state="normal")
        self.history_text.insert("end", line + "\n")
        self.history_text.see("end")
        self.history_text.configure(state="disabled")

    # --------------------------------------------------------
    # Desenho
    # --------------------------------------------------------

    def draw_everything(self) -> None:
        c = self.canvas
        c.delete("all")

        # fundo geral
        c.create_rectangle(0, 0, 900, 780, fill=self.BG, outline="")

        # cabeçalho
        c.create_text(28, 24, anchor="w", text="DARWIN v48.1-demo — Shape Sorter ao vivo",
                      font=("Segoe UI", 18, "bold"), fill=self.TEXT)
        c.create_text(28, 50, anchor="w",
                      text="Darwin observa, avalia compatibilidade física e escolhe a próxima ação em runtime.",
                      font=("Segoe UI", 10), fill=self.MUTED)

        # painel laboratório
        c.create_round_rect = lambda x1, y1, x2, y2, r=18, **kwargs: self.round_rect(c, x1, y1, x2, y2, r, **kwargs)
        c.create_round_rect(20, 70, 880, 750, r=28, fill="#F7FAFE", outline="#D4DFEE", width=2)

        # robô
        self.draw_robot(155, 240)

        # painel de critérios
        self.draw_criteria_panel(60, 110)

        # base/mesa
        c.create_round_rect(475, 280, 865, 560, r=24, fill="#DDBB93", outline="#C9A275", width=2)
        c.create_rectangle(495, 310, 845, 520, fill="#E6C49B", outline="")

        # buracos
        for hole in self.holes:
            self.draw_hole(hole)

        # peças
        for piece in self.pieces:
            self.draw_piece(piece)

        # seta/realce de ação
        if self.anim_piece_id and self.target_hole_id:
            piece = self.get_piece(self.anim_piece_id)
            hole = self.get_hole(self.target_hole_id)
            self.draw_highlight(piece, hole)

        # status inferior
        solved = sum(1 for h in self.holes if h.filled)
        total = len(self.holes)
        c.create_text(30, 728, anchor="w",
                      text=f"Progresso: {solved}/{total} peças encaixadas | Exploração: {'ON' if self.agent.exploration_enabled else 'OFF'}",
                      font=("Segoe UI", 11, "bold"), fill=self.TEXT)

    def round_rect(self, canvas: tk.Canvas, x1, y1, x2, y2, r=18, **kwargs):
        points = [
            x1+r, y1, x2-r, y1, x2, y1, x2, y1+r,
            x2, y2-r, x2, y2, x2-r, y2, x1+r, y2,
            x1, y2, x1, y2-r, x1, y1+r, x1, y1
        ]
        return canvas.create_polygon(points, smooth=True, splinesteps=36, **kwargs)

    def draw_robot(self, cx: float, cy: float) -> None:
        c = self.canvas

        # corpo
        c.create_oval(cx-70, cy-95, cx+70, cy+45, fill="#F8FBFF", outline="#BFCBDD", width=3)
        c.create_oval(cx-55, cy-70, cx+55, cy+15, fill="#1B2638", outline="#364861", width=2)

        # olhos/expressão
        if self.robot_face == "thinking":
            c.create_oval(cx-28, cy-35, cx-8, cy-15, fill="#8CD3FF", outline="")
            c.create_oval(cx+8, cy-35, cx+28, cy-15, fill="#8CD3FF", outline="")
            c.create_text(cx, cy-2, text="...", fill="#8CD3FF", font=("Segoe UI", 16, "bold"))
        elif self.robot_face == "happy":
            c.create_arc(cx-34, cy-34, cx-6, cy-6, start=180, extent=180, style="arc", outline="#8CD3FF", width=4)
            c.create_arc(cx+6, cy-34, cx+34, cy-6, start=180, extent=180, style="arc", outline="#8CD3FF", width=4)
            c.create_arc(cx-18, cy-3, cx+18, cy+18, start=180, extent=180, style="arc", outline="#8CD3FF", width=3)
        elif self.robot_face == "sad":
            c.create_oval(cx-28, cy-35, cx-8, cy-15, fill="#8CD3FF", outline="")
            c.create_oval(cx+8, cy-35, cx+28, cy-15, fill="#8CD3FF", outline="")
            c.create_arc(cx-18, cy+6, cx+18, cy+26, start=0, extent=180, style="arc", outline="#8CD3FF", width=3)
        else:
            c.create_oval(cx-28, cy-35, cx-8, cy-15, fill="#8CD3FF", outline="")
            c.create_oval(cx+8, cy-35, cx+28, cy-15, fill="#8CD3FF", outline="")
            c.create_arc(cx-16, cy+2, cx+16, cy+18, start=180, extent=180, style="arc", outline="#8CD3FF", width=3)

        # antena
        c.create_line(cx, cy-110, cx+10, cy-132, fill="#7F8FA6", width=4)
        c.create_oval(cx+5, cy-138, cx+15, cy-128, fill="#4A90E2", outline="")

        # lados
        c.create_oval(cx-82, cy-52, cx-52, cy-22, fill="#EAF2FB", outline="#BFCBDD", width=2)
        c.create_oval(cx+52, cy-52, cx+82, cy-22, fill="#EAF2FB", outline="#BFCBDD", width=2)

        # peito
        c.create_oval(cx-18, cy+25, cx+18, cy+61, fill="#DDF4FF", outline="#6CC6F1", width=3)
        c.create_oval(cx-9, cy+34, cx+9, cy+52, fill="#74D0FF", outline="")
        c.create_text(cx, cy+82, text="DARWIN", fill="#44617C", font=("Segoe UI", 10, "bold"))

        # braço direito em posição variável
        c.create_line(cx+58, cy+40, cx+110, cy+78, fill="#A9B6C8", width=8, smooth=True)
        c.create_line(cx+110, cy+78, cx+150, cy+105, fill="#A9B6C8", width=7, smooth=True)
        c.create_oval(cx+145, cy+100, cx+160, cy+115, fill="#F8FBFF", outline="#A9B6C8", width=2)

        # braço esquerdo
        c.create_line(cx-58, cy+40, cx-95, cy+85, fill="#A9B6C8", width=8, smooth=True)
        c.create_line(cx-95, cy+85, cx-115, cy+110, fill="#A9B6C8", width=7, smooth=True)
        c.create_oval(cx-120, cy+105, cx-105, cy+120, fill="#F8FBFF", outline="#A9B6C8", width=2)

    def draw_criteria_panel(self, x: float, y: float) -> None:
        c = self.canvas
        c.create_round_rect(x, y, x+360, y+130, r=18, fill="#FFFFFF", outline="#D9E4F2", width=2)
        labels = ["contorno", "tamanho", "profundidade", "orientação"]
        for i, lab in enumerate(labels):
            colx = x + 20 + i * 85
            c.create_text(colx+18, y+18, text=lab, anchor="w", font=("Segoe UI", 10, "bold"), fill="#2E5481")
        # ícones simples
        c.create_rectangle(x+28, y+48, x+58, y+78, outline="#3A7BEB", width=3)
        c.create_rectangle(x+64, y+55, x+80, y+71, outline="#A9C3F3", width=2, dash=(2, 2))

        c.create_rectangle(x+114, y+56, x+124, y+66, outline="#3A7BEB", width=2)
        c.create_rectangle(x+132, y+50, x+152, y+70, outline="#3A7BEB", width=2)
        c.create_rectangle(x+160, y+54, x+178, y+72, outline="#A9C3F3", width=2, dash=(2, 2))

        c.create_polygon(x+214, y+75, x+250, y+75, x+250, y+45, x+230, y+35, x+214, y+45,
                         fill="", outline="#3A7BEB", width=2)
        c.create_line(x+214, y+45, x+230, y+55, fill="#3A7BEB", width=2)
        c.create_line(x+250, y+45, x+230, y+55, fill="#3A7BEB", width=2)

        c.create_polygon(x+302, y+75, x+332, y+75, x+317, y+45, fill="", outline="#3A7BEB", width=2)
        c.create_polygon(x+340, y+75, x+370, y+75, x+355, y+45, fill="", outline="#A9C3F3", width=2)
        c.create_line(x+317, y+32, x+317, y+42, fill="#3A7BEB", width=2)
        c.create_line(x+355, y+32, x+355, y+42, fill="#A9C3F3", width=2)

    def draw_hole(self, hole: Hole) -> None:
        c = self.canvas
        outline = "#8F6E4D"
        fill = "#7E5B38"
        glow = "#AEE0FF" if self.target_hole_id == hole.hole_id else ""
        if hole.family == "square":
            c.create_rectangle(hole.x-39, hole.y-39, hole.x+39, hole.y+39, fill=fill, outline=outline, width=3)
            if hole.filled and hole.filled_by:
                p = self.get_piece(hole.filled_by)
                c.create_rectangle(hole.x-35, hole.y-35, hole.x+35, hole.y+35, fill=p.color, outline="")
        elif hole.family == "triangle":
            pts = [hole.x, hole.y-42, hole.x-42, hole.y+34, hole.x+42, hole.y+34]
            c.create_polygon(pts, fill=fill, outline=outline, width=3)
            if hole.filled and hole.filled_by:
                p = self.get_piece(hole.filled_by)
                pts2 = [hole.x, hole.y-36, hole.x-36, hole.y+28, hole.x+36, hole.y+28]
                c.create_polygon(pts2, fill=p.color, outline="")
        elif hole.family == "circle":
            c.create_oval(hole.x-39, hole.y-39, hole.x+39, hole.y+39, fill=fill, outline=outline, width=3)
            if hole.filled and hole.filled_by:
                p = self.get_piece(hole.filled_by)
                c.create_oval(hole.x-35, hole.y-35, hole.x+35, hole.y+35, fill=p.color, outline="")
        if glow:
            if hole.family == "square":
                c.create_rectangle(hole.x-44, hole.y-44, hole.x+44, hole.y+44, outline=glow, width=3)
            elif hole.family == "triangle":
                pts = [hole.x, hole.y-46, hole.x-46, hole.y+36, hole.x+46, hole.y+36]
                c.create_polygon(pts, fill="", outline=glow, width=3)
            else:
                c.create_oval(hole.x-44, hole.y-44, hole.x+44, hole.y+44, outline=glow, width=3)

    def rotated_points(self, points: list[tuple[float, float]], angle_deg: float, cx: float, cy: float):
        angle = math.radians(angle_deg)
        out = []
        for px, py in points:
            dx, dy = px-cx, py-cy
            rx = dx * math.cos(angle) - dy * math.sin(angle)
            ry = dx * math.sin(angle) + dy * math.cos(angle)
            out.append((cx+rx, cy+ry))
        return out

    def draw_piece(self, piece: Piece) -> None:
        c = self.canvas
        if piece.placed:
            return

        if self.anim_piece_id == piece.piece_id:
            c.create_oval(piece.x-48, piece.y-48, piece.x+48, piece.y+48, outline="#C7EEFF", width=3)

        if piece.family == "square":
            half = piece.size / 2
            pts = [
                (piece.x-half, piece.y-half),
                (piece.x+half, piece.y-half),
                (piece.x+half, piece.y+half),
                (piece.x-half, piece.y+half),
            ]
            pts = self.rotated_points(pts, piece.orientation_deg, piece.x, piece.y)
            c.create_polygon([v for pt in pts for v in pt], fill=piece.color, outline="#285DBD", width=2)

        elif piece.family == "triangle":
            half = piece.size / 2
            pts = [
                (piece.x, piece.y-half),
                (piece.x-half, piece.y+half*0.82),
                (piece.x+half, piece.y+half*0.82),
            ]
            pts = self.rotated_points(pts, piece.orientation_deg, piece.x, piece.y)
            c.create_polygon([v for pt in pts for v in pt], fill=piece.color, outline="#C09B1F", width=2)

        elif piece.family == "circle":
            r = piece.size / 2
            c.create_oval(piece.x-r, piece.y-r, piece.x+r, piece.y+r, fill=piece.color, outline="#BE3838", width=2)

    def draw_highlight(self, piece: Piece, hole: Hole) -> None:
        c = self.canvas
        c.create_line(piece.x, piece.y-55, hole.x, hole.y-70, fill="#80C8FF", width=3, dash=(8, 5), arrow="last")
        c.create_text((piece.x+hole.x)/2, (piece.y+hole.y)/2 - 62, text="ação em curso",
                      font=("Segoe UI", 10, "bold"), fill="#3A7BEB")

    # --------------------------------------------------------
    # init
    # --------------------------------------------------------

if __name__ == "__main__":
    root = tk.Tk()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    style = ttk.Style()
    try:
        style.theme_use("vista")
    except Exception:
        pass

    app = DarwinLiveApp(root)
    root.mainloop()
