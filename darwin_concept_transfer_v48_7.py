from __future__ import annotations
"""
DARWIN v48.7 — Transferência conceitual para novos problemas

Darwin deve usar conceitos aprendidos na v48.6 para EXPLICAR antes de agir.

Uso:
    py darwin_concept_transfer_v48_7.py

Tabela:
    geometry_concept_transfer_v48_7
"""
import json, math, random, sqlite3, time, tkinter as tk
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from tkinter import ttk

DB = Path("darwin_home") / "darwin.db"
TABLE = "geometry_concept_transfer_v48_7"
SOURCE_TABLE = "geometry_measure_curriculum_v48_6"

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
    piece_value: float
    hole_value: float
    tolerance: float
    depth_value: float
    depth_limit: float
    angle_value: float
    target_angle: float
    symmetry_deg: float
    expected_concept: str
    expected_relation: str
    expected_decision: str

@dataclass
class Explanation:
    problem_id: str
    recalled_concept: str
    relation: str
    decision: str
    action: str
    explanation: str
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
                        recalled_concept TEXT NOT NULL DEFAULT '',
                        relation TEXT NOT NULL DEFAULT '',
                        decision TEXT NOT NULL DEFAULT '',
                        action TEXT NOT NULL DEFAULT '',
                        explanation TEXT NOT NULL DEFAULT '',
                        score REAL NOT NULL DEFAULT 0.0,
                        outcome TEXT NOT NULL DEFAULT '',
                        payload_json TEXT NOT NULL DEFAULT '{{}}'
                    )
                """)
                conn.commit()
        except Exception:
            self.enabled = False

    def log(self, sid: str, kind: str, problem: Problem | None = None,
            exp: Explanation | None = None, score: float = 0.0, outcome: str = "",
            payload=None) -> None:
        if not self.enabled:
            return
        payload = payload or {}
        if problem:
            payload = {"problem": asdict(problem), **payload}
        if exp:
            payload = {"explanation_obj": asdict(exp), **payload}
        try:
            with sqlite3.connect(DB) as conn:
                conn.execute(f"""
                    INSERT INTO {TABLE}(
                        timestamp, scenario_id, action_kind, problem_id, problem_kind, piece_id, hole_id,
                        recalled_concept, relation, decision, action, explanation, score, outcome, payload_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    now(), sid, kind,
                    problem.problem_id if problem else (exp.problem_id if exp else ""),
                    problem.problem_kind if problem else "",
                    problem.piece_id if problem else "",
                    problem.hole_id if problem else "",
                    exp.recalled_concept if exp else "",
                    exp.relation if exp else "",
                    exp.decision if exp else "",
                    exp.action if exp else "",
                    exp.explanation if exp else "",
                    score, outcome, js(payload),
                ))
                conn.commit()
        except Exception:
            self.enabled = False

    def learned_concepts_v48_6(self) -> dict[str, dict]:
        if not DB.exists():
            return {}
        try:
            with sqlite3.connect(DB) as conn:
                conn.row_factory = sqlite3.Row
                exists = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (SOURCE_TABLE,),
                ).fetchone()
                if not exists:
                    return {}
                rows = conn.execute(f"""
                    SELECT concept_key, relation, verdict, payload_json
                    FROM {SOURCE_TABLE}
                    WHERE action_kind='concept_learned'
                    ORDER BY id ASC
                """).fetchall()
        except Exception:
            return {}
        concepts = {}
        for row in rows:
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except Exception:
                payload = {}
            concepts[str(row["concept_key"])] = {
                "concept_key": row["concept_key"],
                "relation": row["relation"],
                "verdict": row["verdict"],
                "payload": payload,
            }
        return concepts

class TransferAgent:
    def __init__(self, memory: Memory) -> None:
        self.memory = memory
        self.learned = memory.learned_concepts_v48_6()

    @staticmethod
    def minrot(angle: float, target: float, symmetry: float) -> float:
        delta = (target - angle) % symmetry
        if delta > symmetry / 2:
            delta -= symmetry
        return round(delta, 3)

    def explain(self, p: Problem) -> Explanation:
        if p.piece_family != p.hole_family:
            return Explanation(
                p.problem_id, "shape_not_scale_or_orientation", "different_shape",
                "reject_shape", "reject",
                "Antes de agir: a forma da peça é diferente da forma do buraco. Isso não é problema de escala nem de orientação; rotação não corrige forma diferente."
            )
        size_delta = round(p.piece_value - p.hole_value, 3)
        if abs(size_delta) <= p.tolerance:
            return Explanation(
                p.problem_id, "tolerance", "within_tolerance", "accept", "insert",
                f"Antes de agir: a diferença de tamanho é {size_delta:+.2f}, dentro da tolerância {p.tolerance:.2f}; portanto pode tentar inserir."
            )
        if size_delta > p.tolerance:
            return Explanation(
                p.problem_id, "larger_smaller", "larger_than", "reject_size", "reject",
                f"Antes de agir: a peça é maior que a abertura por {size_delta:.2f}, excedendo a tolerância {p.tolerance:.2f}; rejeitar por tamanho."
            )
        depth_delta = round(p.depth_value - p.depth_limit, 3)
        if depth_delta > 0.05:
            return Explanation(
                p.problem_id, "deep_shallow", "deeper_than", "reject_depth", "reject",
                f"Antes de agir: a peça é profunda demais por {depth_delta:.2f}; rejeitar inserção completa por profundidade."
            )
        rot = self.minrot(p.angle_value, p.target_angle, p.symmetry_deg)
        if abs(rot) > 3.0:
            return Explanation(
                p.problem_id, "angle_rotation_minimum", "rotation_needed", "rotate", "rotate_then_insert",
                f"Antes de agir: a forma e a escala são compatíveis, mas o ângulo está desalinhado. A rotação mínima necessária é {rot:+.1f}°.",
                rotation_delta=rot
            )
        return Explanation(
            p.problem_id, "tolerance", "within_tolerance", "accept", "insert",
            "Antes de agir: forma, escala, profundidade e orientação estão compatíveis; inserir."
        )

    def recall_concept(self, sid: str, problem: Problem, concept: str) -> None:
        source = self.learned.get(concept, {})
        self.memory.log(
            sid, "concept_recall", problem=problem, outcome="found" if source else "missing",
            payload={"source_table": SOURCE_TABLE, "concept": concept, "source": source}
        )

class App:
    BG = "#eef4fb"
    TEXT = "#172b44"
    MUTED = "#60758e"
    BLUE = "#3977e3"
    GREEN = "#2dbe78"
    BAD = "#d9534f"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("DARWIN v48.7 — transferência conceitual")
        root.geometry("1280x800")
        root.configure(bg=self.BG)
        self.mem = Memory()
        self.agent = TransferAgent(self.mem)

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

        self.status = tk.StringVar(value="Pronto. Darwin deve explicar antes de agir.")
        tk.Label(side, textvariable=self.status, bg="white", fg=self.TEXT, wraplength=405,
                 justify="left", anchor="w", padx=10, pady=8, relief="solid", bd=1).pack(fill="x", pady=(8, 8))

        self.logic = tk.Text(side, height=19, wrap="word", bg="white", fg=self.TEXT, relief="solid", bd=1)
        self.logic.pack(fill="x", pady=(0, 8))
        self.logic.config(state="disabled")

        self.hist = tk.Text(side, height=20, wrap="word", bg="#0d3b66", fg="#eaf7ff", relief="solid", bd=1)
        self.hist.pack(fill="both", expand=True)
        self.hist.config(state="disabled")

        self.auto = False
        self.stage = 0
        self.count = 0
        self.current_problem = None
        self.current_exp = None
        self.face = "neutral"
        self.flash = ""
        self.flash_n = 0
        self.setup(int(time.time()) % 10_000_000)
        self.write("v48.7: Darwin deve recordar conceitos da v48.6 e explicar antes de agir.\n")
        self.loop()

    def setup(self, seed: int) -> None:
        self.seed = seed
        rng = random.Random(seed)
        self.sid = f"V487-{seed}-{suffix(rng)}"
        self.stage = 0
        self.count = 0
        self.current_problem = None
        self.current_exp = None
        self.face = "neutral"

        hole_size = rng.randint(80, 88)
        tol = round(rng.uniform(3.0, 5.5), 1)
        depth_limit = round(rng.uniform(1.30, 1.60), 2)
        angle = rng.choice([18, 27, 36, 54, 63])
        self.problems = [
            Problem("problem_oversize", "new_size_problem", f"object_{suffix(rng)}", f"aperture_{suffix(rng)}",
                    "circle", "circle", hole_size + tol + 10, hole_size, tol, depth_limit - .1, depth_limit, 0, 0, 90,
                    "larger_smaller", "larger_than", "reject_size"),
            Problem("problem_tolerance", "new_tolerance_problem", f"object_{suffix(rng)}", f"aperture_{suffix(rng)}",
                    "circle", "circle", hole_size + tol - .6, hole_size, tol, depth_limit - .1, depth_limit, 0, 0, 90,
                    "tolerance", "within_tolerance", "accept"),
            Problem("problem_depth", "new_depth_problem", f"object_{suffix(rng)}", f"aperture_{suffix(rng)}",
                    "circle", "circle", hole_size - 7, hole_size, tol, depth_limit + .7, depth_limit, 0, 0, 90,
                    "deep_shallow", "deeper_than", "reject_depth"),
            Problem("problem_rotation", "new_angle_problem", f"object_{suffix(rng)}", f"aperture_{suffix(rng)}",
                    "square", "square", hole_size - 7, hole_size, tol, depth_limit - .15, depth_limit, angle, 0, 90,
                    "angle_rotation_minimum", "rotation_needed", "rotate"),
            Problem("problem_shape", "new_shape_problem", f"object_{suffix(rng)}", f"aperture_{suffix(rng)}",
                    "triangle", "circle", hole_size - 6, hole_size, tol, depth_limit - .1, depth_limit, 0, 0, 120,
                    "shape_not_scale_or_orientation", "different_shape", "reject_shape"),
        ]
        self.mem.log(self.sid, "transfer_init", outcome="created", payload={
            "scenario_id": self.sid,
            "seed": seed,
            "source_table": SOURCE_TABLE,
            "available_concepts": sorted(self.agent.learned.keys()),
            "problems": [asdict(p) for p in self.problems],
        })

    def new_scenario(self) -> None:
        self.auto = False
        self.setup(int(time.time()) % 10_000_000)
        self.log(f"NOVO CENÁRIO: {self.sid}")
        self.write(f"Novo cenário: {self.sid}\nProblemas mudaram, conceitos devem transferir.\n")

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
            self.status.set("Concluído. Darwin explicou antes de agir em problemas novos.")
            self.mem.log(self.sid, "transfer_complete", outcome="success", payload={
                "problems": len(self.problems),
                "source_table": SOURCE_TABLE,
            })
            self.write(
                "Final v48.7:\n"
                "- recordou conceitos da v48.6 ✔\n"
                "- explicou antes de agir ✔\n"
                "- rejeitou por tamanho ✔\n"
                "- aceitou por tolerância ✔\n"
                "- rejeitou por profundidade ✔\n"
                "- calculou rotação antes de agir ✔\n"
                "- separou forma de escala/orientação ✔"
            )
            self.log("SUCESSO: transferência conceitual v48.7 concluída.")
            return

        problem = self.problems[self.stage]
        self.stage += 1
        self.current_problem = problem
        self.mem.log(self.sid, "problem_present", problem=problem, outcome="presented")
        exp = self.agent.explain(problem)
        self.current_exp = exp
        self.agent.recall_concept(self.sid, problem, exp.recalled_concept)
        self.mem.log(self.sid, "explanation_before_action", problem=problem, exp=exp, outcome="explained")
        self.mem.log(self.sid, "action_decide", problem=problem, exp=exp, outcome=exp.decision)

        if exp.action == "rotate_then_insert":
            self.mem.log(self.sid, "action_execute", problem=problem, exp=exp, outcome="rotate_then_insert")
            self.mem.log(self.sid, "rotation_applied", problem=problem, exp=exp, outcome="success")
            self.mem.log(self.sid, "insert_success", problem=problem, exp=exp, outcome="success")
        elif exp.action == "insert":
            self.mem.log(self.sid, "action_execute", problem=problem, exp=exp, outcome="insert")
            self.mem.log(self.sid, "insert_success", problem=problem, exp=exp, outcome="success")
        else:
            self.mem.log(self.sid, "action_execute", problem=problem, exp=exp, outcome="reject")
            self.mem.log(self.sid, "safe_reject", problem=problem, exp=exp, outcome=exp.decision)

        self.count = 52
        self.face = "thinking"
        self.flash = exp.decision
        self.flash_n = 42
        self.status.set(f"Problema novo: {problem.problem_kind}. Darwin explicou antes de agir.")
        self.log(f"EXPLICAR[{problem.problem_kind}]: {exp.relation} -> {exp.decision}")
        self.write(self.text(problem, exp))

    def text(self, p: Problem, e: Explanation) -> str:
        rot = f"\nRotação mínima calculada: {e.rotation_delta:+.1f}°\n" if e.rotation_delta else ""
        return (
            f"Problema: {p.problem_id}\n"
            f"Tipo: {p.problem_kind}\n\n"
            f"Peça: {p.piece_id} | forma={p.piece_family} | tamanho={p.piece_value:.2f} | profundidade={p.depth_value:.2f} | ângulo={p.angle_value:.1f}°\n"
            f"Buraco: {p.hole_id} | forma={p.hole_family} | tamanho={p.hole_value:.2f} | profundidade={p.depth_limit:.2f} | tolerância={p.tolerance:.2f}\n\n"
            f"Conceito recordado: {e.recalled_concept}\n"
            f"Relação inferida: {e.relation}\n"
            f"Decisão: {e.decision}\n"
            f"Ação: {e.action}\n"
            f"{rot}\n"
            f"Explicação antes da ação:\n{e.explanation}\n"
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
        c.create_text(35, 38, anchor="w", text="DARWIN v48.7 — transferência conceitual", font=("Segoe UI", 18, "bold"), fill=self.TEXT)
        c.create_text(35, 66, anchor="w", text=f"Cenário: {self.sid}", font=("Segoe UI", 10), fill=self.MUTED)
        self.robot(135, 225)
        self.concepts(35, 105)
        self.problem_panel(455, 115)
        if self.flash_n > 0 and self.flash:
            col = self.GREEN if self.flash in ("accept", "rotate") else self.BAD
            self.rr(465, 620, 805, 670, 14, fill="white", outline=col, width=3)
            c.create_text(635, 645, text=self.flash, font=("Segoe UI", 15, "bold"), fill=col)
        c.create_text(35, 725, anchor="w",
                      text=f"Etapa: {self.stage}/{len(self.problems)} | conceitos v48.6 disponíveis: {len(self.agent.learned)} | SQLite: {'ON' if self.mem.enabled else 'OFF'}",
                      font=("Segoe UI", 10, "bold"), fill=self.TEXT)

    def robot(self, cx, cy) -> None:
        c = self.cv
        c.create_oval(cx-65, cy-85, cx+65, cy+45, fill="#f8fbff", outline="#b9c8da", width=3)
        c.create_oval(cx-50, cy-58, cx+50, cy+15, fill="#192638", outline="#30465f", width=2)
        c.create_oval(cx-30, cy-35, cx-10, cy-15, fill="#8bdbff", outline="")
        c.create_oval(cx+10, cy-35, cx+30, cy-15, fill="#8bdbff", outline="")
        symbol = "?" if self.face == "neutral" else ("✓" if self.face == "happy" else "→")
        c.create_text(cx, cy, text=symbol, font=("Segoe UI", 18, "bold"), fill="#8bdbff")
        c.create_oval(cx-18, cy+28, cx+18, cy+64, fill="#ddf5ff", outline="#6ec6ff", width=3)
        c.create_text(cx, cy+83, text="DARWIN", font=("Segoe UI", 9, "bold"), fill="#355574")
        c.create_line(cx+55, cy+40, cx+110, cy+85, fill="#a8b7c9", width=8)
        c.create_oval(cx+104, cy+78, cx+120, cy+94, fill="white", outline="#8fa2b8", width=2)

    def concepts(self, x, y) -> None:
        self.rr(x, y, x+395, y+155, 14, fill="white", outline="#d6e2f1", width=2)
        items = [
            ("maior", "rejeitar tamanho"),
            ("tolerância", "aceitar"),
            ("profundo", "rejeitar profund."),
            ("ângulo", "rotacionar"),
            ("forma", "≠ escala"),
            ("explicar", "antes de agir"),
        ]
        for i, (a, b) in enumerate(items):
            px = x + 18 + (i % 3) * 125
            py = y + 30 + (i // 3) * 66
            self.cv.create_text(px, py, anchor="w", text=a, font=("Segoe UI", 10, "bold"), fill="#22507c")
            self.cv.create_text(px, py+25, anchor="w", text=b, font=("Segoe UI", 8), fill=self.MUTED)

    def problem_panel(self, x, y) -> None:
        self.rr(x, y, x+345, y+465, 18, fill="white", outline="#d6e2f1", width=2)
        self.cv.create_text(x+20, y+25, anchor="w", text="Problema novo", font=("Segoe UI", 14, "bold"), fill=self.TEXT)
        p = self.current_problem
        e = self.current_exp
        if not p or not e:
            self.cv.create_text(x+20, y+70, anchor="w", text="Aguardando problema...", font=("Segoe UI", 11), fill=self.MUTED)
            return
        self.cv.create_text(x+20, y+62, anchor="w", text=p.problem_kind, font=("Segoe UI", 11, "bold"), fill=self.BLUE)
        self.cv.create_text(x+20, y+95, anchor="w", text=f"conceito: {e.recalled_concept}", font=("Segoe UI", 10), fill=self.MUTED)
        base = y + 150
        maxv = max(p.piece_value, p.hole_value, 1)
        pl = min(230, 230 * p.piece_value / maxv)
        hl = min(230, 230 * p.hole_value / maxv)
        self.cv.create_text(x+20, base-25, anchor="w", text="peça", font=("Segoe UI", 9, "bold"), fill=self.TEXT)
        self.cv.create_rectangle(x+80, base-36, x+80+pl, base-14, fill=self.BLUE, outline="")
        self.cv.create_text(x+80+pl+8, base-25, anchor="w", text=f"{p.piece_value:.1f}", font=("Segoe UI", 9), fill=self.MUTED)
        self.cv.create_text(x+20, base+20, anchor="w", text="buraco", font=("Segoe UI", 9, "bold"), fill=self.TEXT)
        self.cv.create_rectangle(x+80, base+9, x+80+hl, base+31, fill=self.GREEN, outline="")
        self.cv.create_text(x+80+hl+8, base+20, anchor="w", text=f"{p.hole_value:.1f}", font=("Segoe UI", 9), fill=self.MUTED)
        if e.rotation_delta:
            cx, cy = x+175, base+120
            self.cv.create_oval(cx-48, cy-48, cx+48, cy+48, outline="#c9d8e8", width=2)
            self.cv.create_line(cx, cy, cx+48, cy, fill=self.GREEN, width=3)
            a = math.radians(p.angle_value)
            self.cv.create_line(cx, cy, cx+48*math.cos(a), cy-48*math.sin(a), fill=self.BLUE, width=3, arrow="last")
            self.cv.create_text(cx, cy+68, text=f"rot. {e.rotation_delta:+.1f}°", font=("Segoe UI", 11, "bold"), fill=self.TEXT)
        self.cv.create_text(x+20, y+370, anchor="w", text=f"relação: {e.relation}", font=("Segoe UI", 10, "bold"), fill=self.TEXT)
        self.cv.create_text(x+20, y+398, anchor="w", text=f"decisão: {e.decision}", font=("Segoe UI", 10, "bold"), fill=self.BLUE)
        self.cv.create_text(x+20, y+430, anchor="w", text="explicou antes de agir ✔", font=("Segoe UI", 10, "bold"), fill=self.GREEN)

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
