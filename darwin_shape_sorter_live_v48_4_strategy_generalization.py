from __future__ import annotations

"""
DARWIN v48.4 — Strategy Generalization Lab

Objetivo pedagógico:
Darwin deve provar que não aprendeu apenas um caso isolado.
Ele deve generalizar a escolha de estratégia para vários tipos de falha física:

    contour_mismatch  -> try_alternate_hole
    size_mismatch     -> reject_pair_size
    depth_mismatch    -> reject_pair_depth
    rotation_mismatch -> rotate_piece
    uncertain_failure -> cautious_exploration

Uso:
    py darwin_shape_sorter_live_v48_4_strategy_generalization.py

Tabela SQLite:
    geometry_live_actions_v48_4

Observação:
Este é um micromundo/currículo visual. Os cenários de falha são provocados
de propósito, mas a estratégia é escolhida pela classificação do erro.
"""

import json
import math
import sqlite3
import tkinter as tk
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from tkinter import ttk


DB_PATH = Path("darwin_home") / "darwin.db"
TABLE = "geometry_live_actions_v48_4"


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
    angle: float
    color: str
    placed: bool = False
    rejected: bool = False


@dataclass
class Hole:
    hole_id: str
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
class Eval:
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
                        action_kind TEXT NOT NULL,
                        piece_id TEXT NOT NULL DEFAULT '',
                        hole_id TEXT NOT NULL DEFAULT '',
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

    def log(self, kind: str, piece: str = "", hole: str = "", score: float = 0.0,
            outcome: str = "", note: str = "", payload=None) -> None:
        if not self.enabled:
            return
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    f"""
                    INSERT INTO {TABLE}
                    (timestamp, action_kind, piece_id, hole_id, score, outcome, note, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (now_iso(), kind, piece, hole, score, outcome, note, safe_json(payload or {})),
                )
                conn.commit()
        except Exception:
            self.enabled = False


class DarwinPolicy:
    def __init__(self, mem: Memory) -> None:
        self.mem = mem
        self.failed_pairs: set[tuple[str, str]] = set()

    def rotation_match(self, p: Piece, h: Hole) -> bool:
        if p.family in ("circle", "unknown"):
            return True
        symmetry = 90.0 if p.family == "square" else 120.0
        delta = abs((p.angle - h.angle) % 360.0)
        if delta > 180.0:
            delta = 360.0 - delta
        rem = min(delta % symmetry, symmetry - (delta % symmetry))
        return rem <= 3.0

    def evaluate(self, p: Piece, h: Hole) -> Eval:
        if p.family == "unknown":
            # Caso proposital: informação perceptiva insuficiente.
            return Eval(
                p.piece_id, h.hole_id,
                False, True, True, True,
                False, True, 0.50,
                "uncertain_failure",
                "forma parcialmente desconhecida; explorar com cautela antes de concluir",
            )

        contour = p.family == h.family
        size_ok = p.size <= h.size + h.tol
        depth_ok = p.depth <= h.depth
        rot_ok = self.rotation_match(p, h)
        fit = contour and size_ok and depth_ok and rot_ok

        score = 0.0
        score += 0.42 if contour else 0.0
        score += 0.22 if size_ok else 0.0
        score += 0.20 if depth_ok else 0.0
        score += 0.16 if rot_ok else 0.0
        score = round(score, 3)

        if fit:
            reason = ""
            exp = "compatível: inserir"
        elif not contour:
            reason = "contour_mismatch"
            exp = "contorno incompatível; testar outro buraco"
        elif not size_ok:
            reason = "size_mismatch"
            exp = "peça grande demais; rejeitar este par"
        elif not depth_ok:
            reason = "depth_mismatch"
            exp = "peça profunda demais; rejeitar inserção completa"
        elif not rot_ok:
            reason = "rotation_mismatch"
            exp = "orientação incompatível; girar peça"
        else:
            reason = "uncertain_failure"
            exp = "falha incerta; explorar com cautela"

        return Eval(p.piece_id, h.hole_id, contour, size_ok, depth_ok, rot_ok, fit, not fit, score, reason, exp)

    def strategy_for(self, ev: Eval) -> Strategy:
        mapping = {
            "contour_mismatch": ("try_alternate_hole", "contorno errado: buscar outro buraco para a mesma peça"),
            "size_mismatch": ("reject_pair_size", "tamanho errado: não repetir este par sem nova evidência"),
            "depth_mismatch": ("reject_pair_depth", "profundidade errada: não insistir em inserção completa"),
            "rotation_mismatch": ("rotate_piece", "orientação errada: girar e reavaliar"),
            "uncertain_failure": ("cautious_exploration", "incerteza: observar/provar com cautela, sem forçar encaixe"),
        }
        rec, exp = mapping.get(ev.failure_reason, ("cautious_exploration", "falha desconhecida: explorar com cautela"))
        return Strategy(ev.failure_reason, rec, exp)

    def record_failure_and_strategy(self, ev: Eval) -> Strategy:
        self.failed_pairs.add((ev.piece_id, ev.hole_id))
        self.mem.log(
            "error_memory_write",
            ev.piece_id,
            ev.hole_id,
            ev.score,
            "stored",
            ev.failure_reason,
            {"evaluation": asdict(ev), "failed_pairs": sorted([list(x) for x in self.failed_pairs])},
        )
        st = self.strategy_for(ev)
        self.mem.log(
            "strategy_select",
            ev.piece_id,
            ev.hole_id,
            ev.score,
            "selected",
            st.recommendation,
            {"strategy": asdict(st), "source_error": asdict(ev)},
        )
        return st


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

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("DARWIN v48.4 — generalização de estratégia")
        root.geometry("1260x790")
        root.configure(bg=self.BG)

        self.mem = Memory()
        self.policy = DarwinPolicy(self.mem)

        self.canvas = tk.Canvas(root, width=820, height=750, bg=self.BG, highlightthickness=0)
        self.canvas.pack(side="left", padx=12, pady=12)

        side = tk.Frame(root, bg=self.BG)
        side.pack(side="right", fill="both", expand=True, padx=(0, 12), pady=12)

        controls = tk.Frame(side, bg=self.BG)
        controls.pack(fill="x")

        ttk.Button(controls, text="Iniciar Auto", command=self.start).grid(row=0, column=0, padx=4, pady=4, sticky="ew")
        ttk.Button(controls, text="Pausar", command=self.pause).grid(row=0, column=1, padx=4, pady=4, sticky="ew")
        ttk.Button(controls, text="Passo", command=self.step).grid(row=0, column=2, padx=4, pady=4, sticky="ew")
        ttk.Button(controls, text="Resetar", command=self.reset).grid(row=0, column=3, padx=4, pady=4, sticky="ew")
        for i in range(4):
            controls.grid_columnconfigure(i, weight=1)

        self.status_var = tk.StringVar(value="Pronto. Darwin vai testar estratégias para vários tipos de falha.")
        tk.Label(side, textvariable=self.status_var, bg="white", fg=self.TEXT, wraplength=400,
                 justify="left", anchor="w", padx=10, pady=8, relief="solid", bd=1).pack(fill="x", pady=(8, 8))

        self.logic = tk.Text(side, height=17, wrap="word", bg="white", fg=self.TEXT, relief="solid", bd=1)
        self.logic.pack(fill="x", pady=(0, 8))
        self.logic.config(state="disabled")

        self.hist = tk.Text(side, height=20, wrap="word", bg="#0D3B66", fg="#EAF7FF", relief="solid", bd=1)
        self.hist.pack(fill="both", expand=True)
        self.hist.config(state="disabled")

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

        self.setup_world()
        self.write_logic("v48.4: provar que a política de estratégia generaliza para vários tipos de falha.\n")
        self.loop()

    def setup_world(self) -> None:
        self.holes = [
            Hole("hole_square", "square", 500, 365, 82, 1.5),
            Hole("hole_triangle", "triangle", 620, 365, 86, 1.5),
            Hole("hole_circle", "circle", 740, 365, 82, 1.5),
        ]
        self.pieces = [
            Piece("piece_triangle", "triangle", 135, 570, 135, 570, 78, 1.0, 0, self.YELLOW),
            Piece("piece_circle_large", "circle", 255, 570, 255, 570, 104, 1.0, 0, "#F07C7C"),
            Piece("piece_square_deep", "square", 375, 570, 375, 570, 74, 2.4, 0, "#77A7F2"),
            Piece("piece_unknown", "unknown", 135, 675, 135, 675, 72, 1.0, 0, "#9B8DE5"),
            Piece("piece_circle", "circle", 255, 675, 255, 675, 74, 1.0, 0, self.RED),
            Piece("piece_square_rotated", "square", 375, 675, 375, 675, 74, 1.0, 45, self.BLUE),
        ]
        self.stage = 0
        self.policy.failed_pairs.clear()
        self.phase = "idle"
        self.current = None
        self.face = "neutral"

    def reset(self) -> None:
        self.auto = False
        self.setup_world()
        self.log("RESET.")
        self.write_logic("Resetado. Clique em Iniciar Auto.\n")

    def start(self) -> None:
        self.auto = True
        self.log("AUTO: iniciado.")

    def pause(self) -> None:
        self.auto = False
        self.log("AUTO: pausado.")

    def step(self) -> None:
        if self.phase == "idle":
            self.plan()

    def piece(self, pid: str) -> Piece:
        return next(p for p in self.pieces if p.piece_id == pid)

    def hole(self, hid: str) -> Hole:
        return next(h for h in self.holes if h.hole_id == hid)

    def next_probe(self):
        curriculum = [
            ("contour_mismatch", "piece_triangle", "hole_square"),
            ("size_mismatch", "piece_circle_large", "hole_circle"),
            ("depth_mismatch", "piece_square_deep", "hole_square"),
            ("uncertain_failure", "piece_unknown", "hole_circle"),
            ("rotation_mismatch", "piece_square_rotated", "hole_square"),
            ("solve_circle", "piece_circle", "hole_circle"),
        ]
        while self.stage < len(curriculum):
            label, pid, hid = curriculum[self.stage]
            self.stage += 1
            p = self.piece(pid)
            h = self.hole(hid)
            if p.placed or p.rejected or h.filled:
                continue
            return label, p, h
        return None

    def plan(self) -> None:
        nxt = self.next_probe()
        if not nxt:
            self.auto = False
            self.face = "happy"
            self.status_var.set("Concluído. Darwin aplicou estratégias para vários tipos de falha.")
            self.write_logic(
                "Final v48.4:\n"
                "- contour_mismatch → try_alternate_hole ✔\n"
                "- size_mismatch → reject_pair_size ✔\n"
                "- depth_mismatch → reject_pair_depth ✔\n"
                "- uncertain_failure → cautious_exploration ✔\n"
                "- rotation_mismatch → rotate_piece ✔\n"
                "- brinquedo resolvido com peças válidas ✔"
            )
            self.log("SUCESSO: ciclo v48.4 concluído.")
            return

        label, p, h = nxt
        ev = self.policy.evaluate(p, h)
        self.current = {"label": label, "piece": p.piece_id, "hole": h.hole_id, "eval": ev}
        self.phase = "thinking"
        self.counter = 24
        self.face = "thinking"
        self.status_var.set(f"Darwin avaliando {p.family} → {h.family}.")
        self.log(f"PROBE[{label}]: {p.piece_id} -> {h.hole_id} | score={ev.score:.2f} | {ev.failure_reason or 'success'}")
        self.mem.log("probe_choose", p.piece_id, h.hole_id, ev.score, "chosen", label, asdict(ev))
        self.write_logic(self.eval_text("AVALIAR", p, h, ev, label))

    def eval_text(self, title: str, p: Piece, h: Hole, ev: Eval, label: str) -> str:
        return (
            f"Ação: {title}\n"
            f"Caso: {label}\n\n"
            f"Peça: {p.piece_id}\n"
            f"Buraco: {h.hole_id}\n\n"
            f"contorno={ev.contour_match}\n"
            f"tamanho={ev.size_match}\n"
            f"profundidade={ev.depth_match}\n"
            f"orientação={ev.rotation_match}\n"
            f"score={ev.score:.2f}\n\n"
            f"resultado={'encaixa' if ev.observed_fit else 'não encaixa'}\n"
            f"falha={ev.failure_reason or 'compatível'}\n"
            f"{ev.explanation}\n"
        )

    def after_think(self) -> None:
        p = self.piece(self.current["piece"])
        h = self.hole(self.current["hole"])
        ev = self.policy.evaluate(p, h)

        if ev.observed_fit:
            self.start_move("insert")
            self.mem.log("insert_start", p.piece_id, h.hole_id, ev.score, "started", "inserção direta", asdict(ev))
            return

        if ev.failure_reason == "rotation_mismatch":
            st = self.policy.strategy_for(ev)
            self.mem.log("strategy_select", p.piece_id, h.hole_id, ev.score, "selected", st.recommendation, {"strategy": asdict(st), "source_error": asdict(ev)})
            self.mem.log("strategy_execute", p.piece_id, h.hole_id, ev.score, "executed", st.recommendation, {"strategy": asdict(st)})
            self.mem.log("rotate_start", p.piece_id, h.hole_id, ev.score, "started", "rotate_piece", asdict(ev))
            self.log(f"ESTRATÉGIA: {ev.failure_reason} -> {st.recommendation}")
            self.phase = "rotate"
            self.face = "thinking"
            self.write_logic(self.eval_text("ESTRATÉGIA: GIRAR", p, h, ev, "rotation_mismatch") + f"\nEstratégia: {st.recommendation}\n{st.explanation}\n")
            return

        self.start_move("collision")

    def start_move(self, kind: str) -> None:
        p = self.piece(self.current["piece"])
        h = self.hole(self.current["hole"])
        self.phase = "move_" + kind
        self.t = 0.0
        self.start_xy = (p.x, p.y)
        self.back_xy = (p.home_x, p.home_y)
        self.face = "focus"
        if kind == "collision":
            ev = self.policy.evaluate(p, h)
            self.mem.log("controlled_collision_start", p.piece_id, h.hole_id, ev.score, "started", ev.failure_reason, asdict(ev))

    def handle_failure(self, p: Piece, h: Hole, ev: Eval) -> None:
        self.mem.log("controlled_collision", p.piece_id, h.hole_id, ev.score, "collision", ev.failure_reason, asdict(ev))
        self.log(f"COLISÃO: {p.piece_id} -> {h.hole_id} | {ev.failure_reason}")

        st = self.policy.record_failure_and_strategy(ev)
        self.log(f"ESTRATÉGIA: {ev.failure_reason} -> {st.recommendation}")

        self.mem.log("strategy_execute", p.piece_id, h.hole_id, ev.score, "executed", st.recommendation, {"strategy": asdict(st), "source_error": asdict(ev)})

        if st.recommendation == "try_alternate_hole":
            alt = self.hole("hole_triangle")
            ev2 = self.policy.evaluate(p, alt)
            self.mem.log("strategy_execute_alternate_target", p.piece_id, alt.hole_id, ev2.score, "chosen", "try_alternate_hole", {"strategy": asdict(st), "chosen": asdict(ev2)})
            self.current = {"label": "alternate_after_contour", "piece": p.piece_id, "hole": alt.hole_id, "eval": ev2}
            self.phase = "move_insert"
            self.t = 0.0
            self.start_xy = (p.x, p.y)
            self.back_xy = (p.home_x, p.home_y)
            self.mem.log("insert_start", p.piece_id, alt.hole_id, ev2.score, "started", "após try_alternate_hole", asdict(ev2))
            self.write_logic(self.eval_text("EXECUTAR ESTRATÉGIA", p, alt, ev2, "try_alternate_hole"))
            return

        if st.recommendation in ("reject_pair_size", "reject_pair_depth", "cautious_exploration"):
            p.rejected = True
            outcome = "rejected" if st.recommendation != "cautious_exploration" else "cautious_skip"
            self.mem.log("strategy_outcome", p.piece_id, h.hole_id, ev.score, outcome, st.recommendation, {"strategy": asdict(st), "source_error": asdict(ev)})
            self.flash = st.recommendation
            self.flash_n = 42
            self.phase = "return"
            self.t = 0.0
            self.write_logic(self.eval_text("REJEITAR / EXPLORAR COM CAUTELA", p, h, ev, st.recommendation) + f"\nEstratégia: {st.recommendation}\n{st.explanation}\n")
            return

        self.phase = "return"
        self.t = 0.0

    def animate(self) -> None:
        if self.flash_n > 0:
            self.flash_n -= 1

        if self.phase == "idle" or not self.current:
            return

        p = self.piece(self.current["piece"])
        h = self.hole(self.current["hole"])

        if self.phase == "thinking":
            self.counter -= 1
            if self.counter <= 0:
                self.after_think()

        elif self.phase == "rotate":
            delta = (h.angle - p.angle) % 360.0
            if delta > 180.0:
                delta -= 360.0
            step = 5.5 if delta > 0 else -5.5
            if abs(delta) <= 5.5:
                p.angle = h.angle
                ev = self.policy.evaluate(p, h)
                self.mem.log("rotate_success", p.piece_id, h.hole_id, ev.score, "success", "rotate_piece", asdict(ev))
                self.log(f"ROTAÇÃO RESOLVEU: {p.piece_id} -> {h.hole_id}")
                self.start_move("insert")
                self.mem.log("insert_start", p.piece_id, h.hole_id, ev.score, "started", "após rotação", asdict(ev))
            else:
                p.angle = (p.angle + step) % 360.0

        elif self.phase in ("move_insert", "move_collision"):
            sx, sy = self.start_xy
            self.t = min(1.0, self.t + 0.04)
            t = 1.0 - (1.0 - self.t) * (1.0 - self.t)
            p.x = sx + (h.x - sx) * t
            p.y = sy + (h.y - 105 - sy) * t - 20 * math.sin(math.pi * t)

            if self.t >= 1.0:
                ev = self.policy.evaluate(p, h)
                if self.phase == "move_insert" and ev.observed_fit:
                    p.x, p.y = h.x, h.y
                    p.placed = True
                    h.filled = True
                    h.filled_by = p.piece_id
                    self.mem.log("insert_success", p.piece_id, h.hole_id, ev.score, "success", "encaixe correto", asdict(ev))
                    self.log(f"SUCESSO: {p.piece_id} -> {h.hole_id}")
                    self.flash = "encaixe correto"
                    self.flash_n = 35
                    self.phase = "idle"
                    self.current = None
                    self.face = "happy"
                else:
                    self.handle_failure(p, h, ev)

        elif self.phase == "return":
            sx, sy = self.start_xy
            tx, ty = self.back_xy
            self.t = min(1.0, self.t + 0.06)
            t = 1.0 - (1.0 - self.t) * (1.0 - self.t)
            p.x = sx + (tx - sx) * t
            p.y = sy + (ty - sy) * t
            if self.t >= 1.0:
                self.log(f"RECUO: {p.piece_id} voltou ao ponto seguro.")
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
        self.hist.config(state="normal")
        self.hist.insert("end", text + "\n")
        self.hist.see("end")
        self.hist.config(state="disabled")

    def rr(self, x1, y1, x2, y2, r=18, **kw):
        pts = [
            x1+r, y1, x2-r, y1, x2, y1, x2, y1+r,
            x2, y2-r, x2, y2, x2-r, y2, x1+r, y2,
            x1, y2, x1, y2-r, x1, y1+r, x1, y1,
        ]
        return self.canvas.create_polygon(pts, smooth=True, splinesteps=24, **kw)

    def draw(self) -> None:
        c = self.canvas
        c.delete("all")
        self.rr(15, 15, 805, 735, 26, fill="#F8FBFF", outline="#CBD8E8", width=2)
        c.create_text(35, 38, anchor="w", text="DARWIN v48.4 — generalização de estratégia", font=("Segoe UI", 17, "bold"), fill=self.TEXT)
        c.create_text(35, 65, anchor="w", text="Vários tipos de falha → estratégias diferentes", font=("Segoe UI", 10), fill=self.MUTED)

        self.draw_robot(135, 225)
        self.draw_policy(35, 105)
        self.draw_board()

        for p in self.pieces:
            if not p.placed:
                self.draw_piece(p)

        if self.current:
            self.draw_link()

        if self.flash_n > 0 and self.flash:
            col = self.GREEN if "correto" in self.flash else self.BAD
            self.rr(455, 120, 790, 165, 14, fill="white", outline=col, width=3)
            c.create_text(622, 142, text=self.flash, font=("Segoe UI", 13, "bold"), fill=col)

        c.create_text(
            35, 715,
            anchor="w",
            text=f"Stage: {self.stage}/6 | SQLite: {'ON' if self.mem.enabled else 'OFF'}",
            font=("Segoe UI", 10, "bold"),
            fill=self.TEXT,
        )

    def draw_policy(self, x, y) -> None:
        self.rr(x, y, x+430, y+120, 14, fill="white", outline="#D6E2F1", width=2)
        pairs = [
            ("contorno", "outro buraco"),
            ("tamanho", "rejeitar par"),
            ("profund.", "não inserir"),
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
        self.rr(445, 300, 790, 540, 20, fill=self.WOOD, outline="#BE9569", width=2)
        for h in self.holes:
            self.draw_hole(h)

    def draw_hole(self, h: Hole) -> None:
        c = self.canvas
        if h.family == "square":
            c.create_rectangle(h.x-40, h.y-40, h.x+40, h.y+40, fill=self.DARK, outline="#62482F", width=3)
            if h.filled:
                c.create_rectangle(h.x-35, h.y-35, h.x+35, h.y+35, fill=self.piece(h.filled_by).color, outline="")
        elif h.family == "triangle":
            c.create_polygon([h.x, h.y-45, h.x-45, h.y+36, h.x+45, h.y+36], fill=self.DARK, outline="#62482F", width=3)
            if h.filled:
                c.create_polygon([h.x, h.y-38, h.x-37, h.y+30, h.x+37, h.y+30], fill=self.piece(h.filled_by).color, outline="")
        else:
            c.create_oval(h.x-40, h.y-40, h.x+40, h.y+40, fill=self.DARK, outline="#62482F", width=3)
            if h.filled:
                c.create_oval(h.x-35, h.y-35, h.x+35, h.y+35, fill=self.piece(h.filled_by).color, outline="")

    def rotated(self, pts, angle, cx, cy):
        r = math.radians(angle)
        return [
            (cx + (x-cx)*math.cos(r) - (y-cy)*math.sin(r),
             cy + (x-cx)*math.sin(r) + (y-cy)*math.cos(r))
            for x, y in pts
        ]

    def draw_piece(self, p: Piece) -> None:
        c = self.canvas
        if p.rejected:
            c.create_text(p.x, p.y-48, text="rejeitada", font=("Segoe UI", 8, "bold"), fill=self.BAD)

        if self.current and self.current["piece"] == p.piece_id:
            c.create_oval(p.x-52, p.y-52, p.x+52, p.y+52, outline="#AEE8FF", width=3)

        if p.family == "square":
            s = p.size/2
            pts = self.rotated([(p.x-s,p.y-s), (p.x+s,p.y-s), (p.x+s,p.y+s), (p.x-s,p.y+s)], p.angle, p.x, p.y)
            c.create_polygon([v for pt in pts for v in pt], fill=p.color, outline="#2458B8", width=2)
            c.create_text(p.x, p.y+s+16, text=f"{p.angle:.0f}°", font=("Segoe UI", 8, "bold"), fill=self.MUTED)
        elif p.family == "triangle":
            s = p.size/2
            pts = self.rotated([(p.x,p.y-s), (p.x-s,p.y+s*.84), (p.x+s,p.y+s*.84)], p.angle, p.x, p.y)
            c.create_polygon([v for pt in pts for v in pt], fill=p.color, outline="#A98013", width=2)
        elif p.family == "unknown":
            s = p.size/2
            c.create_polygon([p.x-s,p.y, p.x,p.y-s, p.x+s,p.y, p.x,p.y+s], fill=p.color, outline="#6B5DC6", width=2)
            c.create_text(p.x, p.y, text="?", font=("Segoe UI", 18, "bold"), fill="white")
        else:
            r = p.size/2
            c.create_oval(p.x-r, p.y-r, p.x+r, p.y+r, fill=p.color, outline="#B43B3B", width=2)

        if "large" in p.piece_id:
            c.create_text(p.x, p.y+p.size/2+16, text="grande", font=("Segoe UI", 8), fill=self.MUTED)
        if "deep" in p.piece_id:
            c.create_text(p.x, p.y+p.size/2+16, text="profundo", font=("Segoe UI", 8), fill=self.MUTED)

    def draw_link(self) -> None:
        p = self.piece(self.current["piece"])
        h = self.hole(self.current["hole"])
        self.canvas.create_line(p.x, p.y-55, h.x, h.y-68, fill="#6EC6FF", width=3, dash=(7, 5), arrow="last")


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
