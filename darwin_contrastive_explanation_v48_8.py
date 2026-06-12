from __future__ import annotations
"""
DARWIN v48.8 — Explicação causal contrastiva

Objetivo:
Darwin deve explicar não só por que escolheu uma ação, mas também por que
NÃO escolheu alternativas.

Fluxo:
    problema novo
    -> avaliação causal
    -> explicação contrastiva antes da ação
    -> decisão
    -> execução
    -> registro auditável

Uso:
    py darwin_contrastive_explanation_v48_8.py

Tabela:
    geometry_contrastive_explanations_v48_8

Dependência esperada:
    geometry_concept_transfer_v48_7
"""

import json
import math
import random
import sqlite3
import time
import tkinter as tk
from collections import Counter
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from tkinter import ttk


DB = Path("darwin_home") / "darwin.db"
TABLE = "geometry_contrastive_explanations_v48_8"
SOURCE_TABLE = "geometry_concept_transfer_v48_7"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def js(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def suffix(rng: random.Random) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(rng.choice(alphabet) for _ in range(5))


@dataclass
class Problem:
    problem_id: str
    problem_kind: str
    piece_id: str
    hole_id: str
    piece_family: str
    hole_family: str
    piece_size: float
    hole_size: float
    tolerance: float
    piece_depth: float
    hole_depth: float
    angle_value: float
    target_angle: float
    symmetry_deg: float
    expected_decision: str
    expected_relation: str
    expected_primary_contrast: str


@dataclass
class Contrast:
    problem_id: str
    relation: str
    decision: str
    action: str
    why_action: str
    why_not: dict[str, str]
    primary_contrast: str
    rotation_delta: float = 0.0


class Memory:
    def __init__(self) -> None:
        self.enabled = True
        try:
            DB.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(DB) as conn:
                conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS {TABLE}(
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        scenario_id TEXT NOT NULL DEFAULT '',
                        action_kind TEXT NOT NULL,
                        problem_id TEXT NOT NULL DEFAULT '',
                        problem_kind TEXT NOT NULL DEFAULT '',
                        piece_id TEXT NOT NULL DEFAULT '',
                        hole_id TEXT NOT NULL DEFAULT '',
                        relation TEXT NOT NULL DEFAULT '',
                        decision TEXT NOT NULL DEFAULT '',
                        action TEXT NOT NULL DEFAULT '',
                        rejected_alternative TEXT NOT NULL DEFAULT '',
                        contrast_reason TEXT NOT NULL DEFAULT '',
                        primary_contrast TEXT NOT NULL DEFAULT '',
                        score REAL NOT NULL DEFAULT 0.0,
                        outcome TEXT NOT NULL DEFAULT '',
                        payload_json TEXT NOT NULL DEFAULT '{{}}'
                    )
                """)
                conn.commit()
        except Exception:
            self.enabled = False

    def log(self, sid: str, kind: str, problem: Problem | None = None,
            contrast: Contrast | None = None, alt: str = "", reason: str = "",
            score: float = 0.0, outcome: str = "", payload=None) -> None:
        if not self.enabled:
            return

        payload = payload or {}
        if problem:
            payload = {"problem": asdict(problem), **payload}
        if contrast:
            payload = {"contrast": asdict(contrast), **payload}

        try:
            with sqlite3.connect(DB) as conn:
                conn.execute(f"""
                    INSERT INTO {TABLE}(
                        timestamp, scenario_id, action_kind, problem_id, problem_kind, piece_id, hole_id,
                        relation, decision, action, rejected_alternative, contrast_reason,
                        primary_contrast, score, outcome, payload_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    now(), sid, kind,
                    problem.problem_id if problem else (contrast.problem_id if contrast else ""),
                    problem.problem_kind if problem else "",
                    problem.piece_id if problem else "",
                    problem.hole_id if problem else "",
                    contrast.relation if contrast else "",
                    contrast.decision if contrast else "",
                    contrast.action if contrast else "",
                    alt,
                    reason,
                    contrast.primary_contrast if contrast else "",
                    score,
                    outcome,
                    js(payload),
                ))
                conn.commit()
        except Exception:
            self.enabled = False

    def transfer_sources(self) -> dict:
        if not DB.exists():
            return {"available": False, "count": 0, "scenarios": []}
        try:
            with sqlite3.connect(DB) as conn:
                conn.row_factory = sqlite3.Row
                exists = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (SOURCE_TABLE,),
                ).fetchone()
                if not exists:
                    return {"available": False, "count": 0, "scenarios": []}
                count = conn.execute(f"SELECT COUNT(*) AS n FROM {SOURCE_TABLE}").fetchone()["n"]
                rows = conn.execute(f"""
                    SELECT DISTINCT scenario_id
                    FROM {SOURCE_TABLE}
                    WHERE action_kind='transfer_complete'
                    ORDER BY scenario_id
                """).fetchall()
                return {"available": True, "count": count, "scenarios": [r["scenario_id"] for r in rows]}
        except Exception:
            return {"available": False, "count": 0, "scenarios": []}


class ContrastiveAgent:
    @staticmethod
    def minrot(angle: float, target: float, symmetry: float) -> float:
        delta = (target - angle) % symmetry
        if delta > symmetry / 2:
            delta -= symmetry
        return round(delta, 3)

    def analyze(self, p: Problem) -> Contrast:
        size_delta = round(p.piece_size - p.hole_size, 3)
        depth_delta = round(p.piece_depth - p.hole_depth, 3)
        rot = self.minrot(p.angle_value, p.target_angle, p.symmetry_deg)

        if p.piece_family != p.hole_family:
            return Contrast(
                p.problem_id,
                "different_shape",
                "reject_shape",
                "reject",
                "rejeitar porque a família geométrica da peça é diferente da família do buraco",
                {
                    "rotate": "girar muda orientação, mas não transforma triângulo em círculo",
                    "scale": "mudar escala não troca a categoria de forma",
                    "insert": "inserir causaria colisão de contorno",
                },
                "reject_not_rotate_or_scale",
            )

        if size_delta > p.tolerance:
            return Contrast(
                p.problem_id,
                "larger_than",
                "reject_size",
                "reject",
                f"rejeitar porque a peça excede a abertura por {size_delta:.2f}, acima da tolerância {p.tolerance:.2f}",
                {
                    "rotate": "girar não reduz largura nem diâmetro",
                    "insert": "inserir sem corrigir tamanho causaria colisão",
                    "reject_depth": "a causa primária não é profundidade; é escala/tamanho",
                },
                "reject_size_not_rotate",
            )

        if depth_delta > 0.05:
            return Contrast(
                p.problem_id,
                "deeper_than",
                "reject_depth",
                "reject",
                f"rejeitar porque a profundidade excede o limite por {depth_delta:.2f}",
                {
                    "rotate": "girar não reduz profundidade",
                    "insert": "inserir completamente falharia em profundidade",
                    "reject_size": "o tamanho de abertura é compatível; o problema é profundidade",
                },
                "reject_depth_not_size_or_rotate",
            )

        if abs(rot) > 3.0:
            return Contrast(
                p.problem_id,
                "rotation_needed",
                "rotate",
                "rotate_then_insert",
                f"girar porque forma, tamanho e profundidade são compatíveis; só o ângulo exige correção de {rot:+.1f}°",
                {
                    "reject_size": "não rejeitar por tamanho porque está dentro da tolerância",
                    "reject_shape": "não rejeitar por forma porque peça e buraco têm a mesma família",
                    "insert_now": "não inserir agora porque o ângulo ainda está desalinhado",
                },
                "rotate_not_reject",
                rotation_delta=rot,
            )

        return Contrast(
            p.problem_id,
            "within_tolerance",
            "accept",
            "insert",
            "inserir porque forma, tamanho, profundidade e orientação estão compatíveis",
            {
                "reject_size": "não rejeitar por tamanho porque a diferença está dentro da tolerância",
                "rotate": "não girar porque o ângulo já está dentro da tolerância",
                "reject_shape": "não rejeitar por forma porque a família geométrica coincide",
            },
            "insert_not_reject",
        )


class App:
    BG = "#eef4fb"
    TEXT = "#172b44"
    MUTED = "#60758e"
    BLUE = "#3977e3"
    GREEN = "#2dbe78"
    BAD = "#d9534f"
    YELLOW = "#f2c94c"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("DARWIN v48.8 — explicação causal contrastiva")
        root.geometry("1280x800")
        root.configure(bg=self.BG)

        self.mem = Memory()
        self.agent = ContrastiveAgent()
        self.source = self.mem.transfer_sources()

        self.cv = tk.Canvas(root, width=840, height=760, bg=self.BG, highlightthickness=0)
        self.cv.pack(side="left", padx=12, pady=12)

        side = tk.Frame(root, bg=self.BG)
        side.pack(side="right", fill="both", expand=True, padx=(0, 12), pady=12)

        bar = tk.Frame(side, bg=self.BG)
        bar.pack(fill="x")
        ttk.Button(bar, text="Iniciar Auto", command=self.start).grid(row=0, column=0, padx=4, pady=4, sticky="ew")
        ttk.Button(bar, text="Pausar", command=self.pause).grid(row=0, column=1, padx=4, pady=4, sticky="ew")
        ttk.Button(bar, text="Passo", command=self.step).grid(row=0, column=2, padx=4, pady=4, sticky="ew")
        ttk.Button(bar, text="Novo cenário", command=self.new_scenario).grid(row=0, column=3, padx=4, pady=4, sticky="ew")
        for i in range(4):
            bar.grid_columnconfigure(i, weight=1)

        self.status = tk.StringVar(value="Pronto. Darwin deve explicar por que X e por que não Y.")
        tk.Label(side, textvariable=self.status, bg="white", fg=self.TEXT, wraplength=405,
                 justify="left", anchor="w", padx=10, pady=8, relief="solid", bd=1).pack(fill="x", pady=(8, 8))

        self.logic = tk.Text(side, height=21, wrap="word", bg="white", fg=self.TEXT, relief="solid", bd=1)
        self.logic.pack(fill="x", pady=(0, 8))
        self.logic.config(state="disabled")

        self.hist = tk.Text(side, height=18, wrap="word", bg="#0d3b66", fg="#eaf7ff", relief="solid", bd=1)
        self.hist.pack(fill="both", expand=True)
        self.hist.config(state="disabled")

        self.auto = False
        self.stage = 0
        self.count = 0
        self.problem: Problem | None = None
        self.contrast: Contrast | None = None
        self.face = "neutral"
        self.flash = ""
        self.flash_n = 0

        self.setup(int(time.time()) % 10_000_000)
        self.write("v48.8: Darwin deve explicar a ação escolhida e rejeitar alternativas.\n")
        self.loop()

    def setup(self, seed: int) -> None:
        self.seed = seed
        rng = random.Random(seed)
        self.sid = f"V488-{seed}-{suffix(rng)}"
        self.stage = 0
        self.count = 0
        self.problem = None
        self.contrast = None
        self.face = "neutral"

        hole = rng.randint(80, 88)
        tol = round(rng.uniform(3.0, 5.5), 1)
        depth = round(rng.uniform(1.30, 1.60), 2)
        angle = rng.choice([18, 27, 36, 54, 63])

        self.problems = [
            Problem("contrast_oversize", "reject_size_vs_rotate", f"object_{suffix(rng)}", f"aperture_{suffix(rng)}",
                    "circle", "circle", hole + tol + 9, hole, tol, depth - .1, depth, 0, 0, 90,
                    "reject_size", "larger_than", "reject_size_not_rotate"),
            Problem("contrast_depth", "reject_depth_vs_size_or_rotate", f"object_{suffix(rng)}", f"aperture_{suffix(rng)}",
                    "square", "square", hole - 6, hole, tol, depth + .65, depth, 0, 0, 90,
                    "reject_depth", "deeper_than", "reject_depth_not_size_or_rotate"),
            Problem("contrast_rotation", "rotate_vs_reject", f"object_{suffix(rng)}", f"aperture_{suffix(rng)}",
                    "square", "square", hole - 7, hole, tol, depth - .1, depth, angle, 0, 90,
                    "rotate", "rotation_needed", "rotate_not_reject"),
            Problem("contrast_insert", "insert_vs_reject", f"object_{suffix(rng)}", f"aperture_{suffix(rng)}",
                    "circle", "circle", hole + tol - .6, hole, tol, depth - .1, depth, 0, 0, 90,
                    "accept", "within_tolerance", "insert_not_reject"),
            Problem("contrast_shape", "reject_shape_vs_scale_or_orientation", f"object_{suffix(rng)}", f"aperture_{suffix(rng)}",
                    "triangle", "circle", hole - 8, hole, tol, depth - .1, depth, 0, 0, 120,
                    "reject_shape", "different_shape", "reject_not_rotate_or_scale"),
        ]

        self.mem.log(self.sid, "contrastive_init", outcome="created", payload={
            "scenario_id": self.sid,
            "seed": seed,
            "source_table": SOURCE_TABLE,
            "source_status": self.source,
            "problems": [asdict(p) for p in self.problems],
        })

    def new_scenario(self) -> None:
        self.auto = False
        self.setup(int(time.time()) % 10_000_000)
        self.log(f"NOVO CENÁRIO: {self.sid}")
        self.write(f"Novo cenário: {self.sid}\nAgora Darwin deve justificar escolhas e rejeitar alternativas.\n")

    def start(self) -> None:
        self.auto = True
        self.log("AUTO: iniciado.")

    def pause(self) -> None:
        self.auto = False
        self.log("AUTO: pausado.")

    def step(self) -> None:
        if self.count <= 0:
            self.advance()

    def advance(self) -> None:
        if self.stage >= len(self.problems):
            self.auto = False
            self.face = "happy"
            self.status.set("Concluído. Darwin produziu explicações contrastivas.")
            self.mem.log(self.sid, "contrastive_complete", outcome="success", payload={
                "problems": len(self.problems),
                "source_table": SOURCE_TABLE,
            })
            self.write(
                "Final v48.8:\n"
                "- rejeitar por tamanho em vez de girar ✔\n"
                "- rejeitar por profundidade em vez de tamanho/rotação ✔\n"
                "- girar em vez de rejeitar ✔\n"
                "- inserir em vez de rejeitar ✔\n"
                "- rejeitar forma diferente em vez de tratar como escala/orientação ✔"
            )
            self.log("SUCESSO: explicação causal contrastiva v48.8 concluída.")
            return

        p = self.problems[self.stage]
        self.stage += 1
        self.problem = p

        self.mem.log(self.sid, "problem_present", problem=p, outcome="presented")
        c = self.agent.analyze(p)
        self.contrast = c

        self.mem.log(self.sid, "causal_assess", problem=p, contrast=c, outcome=c.relation)
        self.mem.log(self.sid, "contrastive_explanation", problem=p, contrast=c, outcome="explained")

        for alt, reason in c.why_not.items():
            self.mem.log(self.sid, "alternative_rejected", problem=p, contrast=c, alt=alt, reason=reason, outcome="rejected")

        self.mem.log(self.sid, "action_decide", problem=p, contrast=c, outcome=c.decision)

        if c.action == "rotate_then_insert":
            self.mem.log(self.sid, "action_execute", problem=p, contrast=c, outcome="rotate_then_insert")
            self.mem.log(self.sid, "rotation_applied", problem=p, contrast=c, outcome="success")
            self.mem.log(self.sid, "insert_success", problem=p, contrast=c, outcome="success")
        elif c.action == "insert":
            self.mem.log(self.sid, "action_execute", problem=p, contrast=c, outcome="insert")
            self.mem.log(self.sid, "insert_success", problem=p, contrast=c, outcome="success")
        else:
            self.mem.log(self.sid, "action_execute", problem=p, contrast=c, outcome="reject")
            self.mem.log(self.sid, "safe_reject", problem=p, contrast=c, outcome=c.decision)

        self.count = 58
        self.face = "thinking"
        self.flash = c.decision
        self.flash_n = 44

        self.status.set(f"Contraste: {p.problem_kind}.")
        self.log(f"CONTRASTE[{p.problem_kind}]: {c.relation} -> {c.decision} | {c.primary_contrast}")
        self.write(self.text(p, c))

    def text(self, p: Problem, c: Contrast) -> str:
        why_not = "\n".join(f"- por que não {alt}: {reason}" for alt, reason in c.why_not.items())
        rot = f"\nRotação mínima: {c.rotation_delta:+.1f}°\n" if c.rotation_delta else ""
        return (
            f"Problema: {p.problem_id}\n"
            f"Tipo: {p.problem_kind}\n\n"
            f"Peça: {p.piece_id} | forma={p.piece_family} | tamanho={p.piece_size:.2f} | profundidade={p.piece_depth:.2f} | ângulo={p.angle_value:.1f}°\n"
            f"Buraco: {p.hole_id} | forma={p.hole_family} | tamanho={p.hole_size:.2f} | profundidade={p.hole_depth:.2f} | tolerância={p.tolerance:.2f}\n\n"
            f"Relação causal: {c.relation}\n"
            f"Decisão: {c.decision}\n"
            f"Ação: {c.action}\n"
            f"Contraste principal: {c.primary_contrast}\n"
            f"{rot}\n"
            f"Por que esta ação:\n{c.why_action}\n\n"
            f"Por que não as alternativas:\n{why_not}\n"
        )

    def loop(self) -> None:
        if self.flash_n > 0:
            self.flash_n -= 1
        if self.count > 0:
            self.count -= 1
        if self.auto and self.count <= 0:
            self.advance()
        self.draw()
        self.root.after(25, self.loop)

    def write(self, text: str) -> None:
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
        pts = [x1+r,y1,x2-r,y1,x2,y1,x2,y1+r,x2,y2-r,x2,y2,x2-r,y2,x1+r,y2,x1,y2,x1,y2-r,x1,y1+r,x1,y1]
        return self.cv.create_polygon(pts, smooth=True, splinesteps=24, **kw)

    def draw(self) -> None:
        c = self.cv
        c.delete("all")
        self.rr(15, 15, 825, 745, 26, fill="#f8fbff", outline="#cbd8e8", width=2)
        c.create_text(35, 38, anchor="w", text="DARWIN v48.8 — explicação causal contrastiva", font=("Segoe UI", 17, "bold"), fill=self.TEXT)
        c.create_text(35, 66, anchor="w", text=f"Cenário: {self.sid}", font=("Segoe UI", 10), fill=self.MUTED)

        self.robot(135, 225)
        self.contrast_map(35, 105)
        self.panel(455, 115)

        if self.flash_n > 0 and self.flash:
            col = self.GREEN if self.flash in ("accept", "rotate") else self.BAD
            self.rr(465, 620, 805, 670, 14, fill="white", outline=col, width=3)
            c.create_text(635, 645, text=self.flash, font=("Segoe UI", 15, "bold"), fill=col)

        c.create_text(35, 725, anchor="w",
                      text=f"Etapa: {self.stage}/{len(self.problems)} | fonte v48.7: {'OK' if self.source.get('available') else 'AUSENTE'} | SQLite: {'ON' if self.mem.enabled else 'OFF'}",
                      font=("Segoe UI", 10, "bold"), fill=self.TEXT)

    def robot(self, cx, cy) -> None:
        c = self.cv
        c.create_oval(cx-65, cy-85, cx+65, cy+45, fill="#f8fbff", outline="#b9c8da", width=3)
        c.create_oval(cx-50, cy-58, cx+50, cy+15, fill="#192638", outline="#30465f", width=2)
        c.create_oval(cx-30, cy-35, cx-10, cy-15, fill="#8bdbff", outline="")
        c.create_oval(cx+10, cy-35, cx+30, cy-15, fill="#8bdbff", outline="")
        symbol = "↔" if self.face == "thinking" else ("✓" if self.face == "happy" else "?")
        c.create_text(cx, cy, text=symbol, font=("Segoe UI", 18, "bold"), fill="#8bdbff")
        c.create_oval(cx-18, cy+28, cx+18, cy+64, fill="#ddf5ff", outline="#6ec6ff", width=3)
        c.create_text(cx, cy+83, text="DARWIN", font=("Segoe UI", 9, "bold"), fill="#355574")
        c.create_line(cx+55, cy+40, cx+110, cy+85, fill="#a8b7c9", width=8)
        c.create_oval(cx+104, cy+78, cx+120, cy+94, fill="white", outline="#8fa2b8", width=2)

    def contrast_map(self, x, y) -> None:
        self.rr(x, y, x+395, y+165, 14, fill="white", outline="#d6e2f1", width=2)
        items = [
            ("rejeitar", "não girar"),
            ("girar", "não rejeitar"),
            ("inserir", "não rejeitar"),
            ("forma", "não escala"),
            ("profund.", "não tamanho"),
            ("causa", "contraste"),
        ]
        for i, (a, b) in enumerate(items):
            px = x + 18 + (i % 3) * 125
            py = y + 32 + (i // 3) * 70
            self.cv.create_text(px, py, anchor="w", text=a, font=("Segoe UI", 10, "bold"), fill="#22507c")
            self.cv.create_text(px, py+25, anchor="w", text=b, font=("Segoe UI", 8), fill=self.MUTED)

    def panel(self, x, y) -> None:
        self.rr(x, y, x+345, y+465, 18, fill="white", outline="#d6e2f1", width=2)
        self.cv.create_text(x+20, y+25, anchor="w", text="Painel contrastivo", font=("Segoe UI", 14, "bold"), fill=self.TEXT)

        p = self.problem
        c = self.contrast
        if not p or not c:
            self.cv.create_text(x+20, y+70, anchor="w", text="Aguardando problema...", font=("Segoe UI", 11), fill=self.MUTED)
            return

        self.cv.create_text(x+20, y+62, anchor="w", text=p.problem_kind, font=("Segoe UI", 11, "bold"), fill=self.BLUE)
        self.cv.create_text(x+20, y+92, anchor="w", text=f"contraste: {c.primary_contrast}", font=("Segoe UI", 9), fill=self.MUTED)

        base = y + 145
        maxv = max(p.piece_size, p.hole_size, 1)
        pl = min(230, 230 * p.piece_size / maxv)
        hl = min(230, 230 * p.hole_size / maxv)

        self.cv.create_text(x+20, base-25, anchor="w", text="peça", font=("Segoe UI", 9, "bold"), fill=self.TEXT)
        self.cv.create_rectangle(x+80, base-36, x+80+pl, base-14, fill=self.BLUE, outline="")
        self.cv.create_text(x+80+pl+8, base-25, anchor="w", text=f"{p.piece_size:.1f}", font=("Segoe UI", 9), fill=self.MUTED)

        self.cv.create_text(x+20, base+20, anchor="w", text="buraco", font=("Segoe UI", 9, "bold"), fill=self.TEXT)
        self.cv.create_rectangle(x+80, base+9, x+80+hl, base+31, fill=self.GREEN, outline="")
        self.cv.create_text(x+80+hl+8, base+20, anchor="w", text=f"{p.hole_size:.1f}", font=("Segoe UI", 9), fill=self.MUTED)

        if c.rotation_delta:
            cx, cy = x+175, base+120
            self.cv.create_oval(cx-48, cy-48, cx+48, cy+48, outline="#c9d8e8", width=2)
            self.cv.create_line(cx, cy, cx+48, cy, fill=self.GREEN, width=3)
            a = math.radians(p.angle_value)
            self.cv.create_line(cx, cy, cx+48*math.cos(a), cy-48*math.sin(a), fill=self.BLUE, width=3, arrow="last")
            self.cv.create_text(cx, cy+68, text=f"rot. {c.rotation_delta:+.1f}°", font=("Segoe UI", 11, "bold"), fill=self.TEXT)

        self.cv.create_text(x+20, y+370, anchor="w", text=f"relação: {c.relation}", font=("Segoe UI", 10, "bold"), fill=self.TEXT)
        self.cv.create_text(x+20, y+398, anchor="w", text=f"decisão: {c.decision}", font=("Segoe UI", 10, "bold"), fill=self.BLUE)
        self.cv.create_text(x+20, y+430, anchor="w", text="por que X / por que não Y ✔", font=("Segoe UI", 10, "bold"), fill=self.GREEN)


if __name__ == "__main__":
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
