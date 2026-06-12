from __future__ import annotations
"""
DARWIN v48.9 — Planejamento de ação em múltiplos passos

Objetivo:
Darwin deve escolher uma sequência curta de ações, justificar cada etapa
e revisar o plano quando uma etapa falhar.

Fluxo pedagógico:
    tarefa nova
    -> avaliar estado
    -> criar plano curto
    -> justificar cada etapa
    -> executar etapa por etapa
    -> se falhar, revisar plano
    -> registrar resultado auditável

Uso:
    py darwin_multistep_planning_v48_9.py

Tabela:
    geometry_multistep_plans_v48_9

Dependência esperada:
    geometry_contrastive_explanations_v48_8
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
TABLE = "geometry_multistep_plans_v48_9"
SOURCE_TABLE = "geometry_contrastive_explanations_v48_8"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def js(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def suffix(rng: random.Random) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(rng.choice(alphabet) for _ in range(5))


@dataclass
class Task:
    task_id: str
    task_kind: str
    piece_id: str
    primary_hole_id: str
    alternate_hole_id: str
    piece_family: str
    primary_hole_family: str
    alternate_hole_family: str
    piece_size: float
    primary_hole_size: float
    alternate_hole_size: float
    tolerance: float
    piece_depth: float
    hole_depth: float
    angle_value: float
    target_angle: float
    symmetry_deg: float
    hidden_failure: str
    expected_final: str
    expected_revision: bool


@dataclass
class PlanStep:
    step_index: int
    step_kind: str
    target: str
    justification: str
    expected_outcome: str


@dataclass
class Plan:
    plan_id: str
    task_id: str
    revision_id: int
    steps: list[PlanStep]
    reason: str


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
                        task_id TEXT NOT NULL DEFAULT '',
                        task_kind TEXT NOT NULL DEFAULT '',
                        plan_id TEXT NOT NULL DEFAULT '',
                        revision_id INTEGER NOT NULL DEFAULT 0,
                        step_index INTEGER NOT NULL DEFAULT -1,
                        step_kind TEXT NOT NULL DEFAULT '',
                        decision TEXT NOT NULL DEFAULT '',
                        justification TEXT NOT NULL DEFAULT '',
                        expected_outcome TEXT NOT NULL DEFAULT '',
                        observed_outcome TEXT NOT NULL DEFAULT '',
                        final_status TEXT NOT NULL DEFAULT '',
                        payload_json TEXT NOT NULL DEFAULT '{{}}'
                    )
                """)
                conn.commit()
        except Exception:
            self.enabled = False

    def log(
        self,
        sid: str,
        action_kind: str,
        task: Task | None = None,
        plan: Plan | None = None,
        step: PlanStep | None = None,
        decision: str = "",
        outcome: str = "",
        observed_outcome: str = "",
        final_status: str = "",
        payload=None,
    ) -> None:
        if not self.enabled:
            return

        if outcome and not observed_outcome:
            observed_outcome = outcome

        payload = payload or {}
        if task:
            payload = {"task": asdict(task), **payload}
        if plan:
            payload = {"plan": {
                "plan_id": plan.plan_id,
                "task_id": plan.task_id,
                "revision_id": plan.revision_id,
                "reason": plan.reason,
                "steps": [asdict(s) for s in plan.steps],
            }, **payload}
        if step:
            payload = {"step": asdict(step), **payload}

        try:
            with sqlite3.connect(DB) as conn:
                conn.execute(f"""
                    INSERT INTO {TABLE}(
                        timestamp, scenario_id, action_kind, task_id, task_kind, plan_id,
                        revision_id, step_index, step_kind, decision, justification,
                        expected_outcome, observed_outcome, final_status, payload_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    now(),
                    sid,
                    action_kind,
                    task.task_id if task else (plan.task_id if plan else ""),
                    task.task_kind if task else "",
                    plan.plan_id if plan else "",
                    plan.revision_id if plan else 0,
                    step.step_index if step else -1,
                    step.step_kind if step else "",
                    decision,
                    step.justification if step else "",
                    step.expected_outcome if step else "",
                    observed_outcome,
                    final_status,
                    js(payload),
                ))
                conn.commit()
        except Exception:
            self.enabled = False

    def source_status(self) -> dict:
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
                scenarios = [
                    r["scenario_id"]
                    for r in conn.execute(f"""
                        SELECT DISTINCT scenario_id
                        FROM {SOURCE_TABLE}
                        WHERE action_kind='contrastive_complete'
                        ORDER BY scenario_id
                    """).fetchall()
                ]
                return {"available": True, "count": count, "scenarios": scenarios}
        except Exception:
            return {"available": False, "count": 0, "scenarios": []}


class Planner:
    @staticmethod
    def minrot(angle: float, target: float, symmetry: float) -> float:
        delta = (target - angle) % symmetry
        if delta > symmetry / 2:
            delta -= symmetry
        return round(delta, 3)

    def make_plan(self, sid: str, task: Task, revision_id: int = 0, failure: str = "") -> Plan:
        plan_id = f"{task.task_id}_plan_r{revision_id}"
        steps: list[PlanStep] = []

        if revision_id > 0:
            if failure == "hidden_depth_failure":
                steps = [
                    PlanStep(0, "stop_current_action", task.primary_hole_id, "a etapa de inserção falhou; parar antes de forçar", "stopped"),
                    PlanStep(1, "classify_failure", task.primary_hole_id, "a falha observada é profundidade oculta, não tamanho nem rotação", "depth_failure_classified"),
                    PlanStep(2, "safe_reject", task.primary_hole_id, "rejeitar inserção completa porque a profundidade excede o limite", "rejected_depth"),
                ]
                return Plan(plan_id, task.task_id, revision_id, steps, "revision_after_hidden_depth_failure")

            steps = [
                PlanStep(0, "safe_abort", task.primary_hole_id, "falha desconhecida; abortar com segurança", "aborted"),
            ]
            return Plan(plan_id, task.task_id, revision_id, steps, "revision_after_unknown_failure")

        # Plano inicial.
        if task.piece_family != task.primary_hole_family and task.piece_family == task.alternate_hole_family:
            steps = [
                PlanStep(0, "assess_primary_shape", task.primary_hole_id, "comparar forma antes de tentar encaixar", "shape_mismatch_found"),
                PlanStep(1, "reject_primary_hole", task.primary_hole_id, "forma diferente não se corrige por rotação ou escala", "primary_rejected"),
                PlanStep(2, "select_alternate_hole", task.alternate_hole_id, "procurar buraco com mesma família geométrica", "alternate_selected"),
                PlanStep(3, "insert_alternate", task.alternate_hole_id, "forma e escala do alternativo são compatíveis", "inserted"),
            ]
            return Plan(plan_id, task.task_id, revision_id, steps, "shape_mismatch_requires_alternate")

        size_delta = task.piece_size - task.primary_hole_size
        depth_delta = task.piece_depth - task.hole_depth
        rot = self.minrot(task.angle_value, task.target_angle, task.symmetry_deg)

        if size_delta > task.tolerance:
            steps = [
                PlanStep(0, "assess_size", task.primary_hole_id, "medir tamanho antes de agir", "larger_than"),
                PlanStep(1, "safe_reject_size", task.primary_hole_id, "rejeitar porque girar não reduz tamanho", "rejected_size"),
            ]
            return Plan(plan_id, task.task_id, revision_id, steps, "oversize_reject_plan")

        if depth_delta > 0.05:
            steps = [
                PlanStep(0, "assess_depth", task.primary_hole_id, "medir profundidade antes de inserir", "deeper_than"),
                PlanStep(1, "safe_reject_depth", task.primary_hole_id, "rejeitar porque profundidade excede o limite", "rejected_depth"),
            ]
            return Plan(plan_id, task.task_id, revision_id, steps, "depth_reject_plan")

        if abs(rot) > 3.0:
            steps = [
                PlanStep(0, "assess_angle", task.primary_hole_id, "forma e tamanho são compatíveis; verificar orientação", "rotation_needed"),
                PlanStep(1, "rotate_piece", task.primary_hole_id, f"girar rotação mínima de {rot:+.1f}° antes de inserir", "rotated"),
                PlanStep(2, "insert_primary", task.primary_hole_id, "após rotação, inserir no buraco compatível", "inserted"),
            ]
            return Plan(plan_id, task.task_id, revision_id, steps, "rotation_then_insert_plan")

        steps = [
            PlanStep(0, "assess_fit", task.primary_hole_id, "forma, tamanho, profundidade e ângulo parecem compatíveis", "fit_predicted"),
            PlanStep(1, "insert_primary", task.primary_hole_id, "inserir porque nenhuma incompatibilidade foi prevista", "inserted"),
        ]
        return Plan(plan_id, task.task_id, revision_id, steps, "direct_insert_plan")

    def execute_step(self, task: Task, step: PlanStep) -> tuple[str, bool]:
        """Retorna (observed_outcome, should_continue)."""
        if step.step_kind in ("assess_primary_shape", "assess_size", "assess_depth", "assess_angle", "assess_fit", "classify_failure"):
            return step.expected_outcome, True

        if step.step_kind in ("reject_primary_hole", "safe_reject_size", "safe_reject_depth", "safe_reject", "safe_abort", "stop_current_action"):
            return step.expected_outcome, True

        if step.step_kind == "select_alternate_hole":
            return "alternate_selected", True

        if step.step_kind == "rotate_piece":
            return "rotated", True

        if step.step_kind == "insert_alternate":
            return "inserted", True

        if step.step_kind == "insert_primary":
            if task.hidden_failure == "hidden_depth_failure":
                return "hidden_depth_failure", False
            return "inserted", True

        return "unknown_step", False


class App:
    BG = "#eef4fb"
    TEXT = "#172b44"
    MUTED = "#60758e"
    BLUE = "#3977e3"
    GREEN = "#2dbe78"
    BAD = "#d9534f"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("DARWIN v48.9 — planejamento em múltiplos passos")
        root.geometry("1280x800")
        root.configure(bg=self.BG)

        self.mem = Memory()
        self.planner = Planner()
        self.source = self.mem.source_status()

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

        self.status = tk.StringVar(value="Pronto. Darwin deve planejar, executar e revisar se falhar.")
        tk.Label(side, textvariable=self.status, bg="white", fg=self.TEXT, wraplength=405,
                 justify="left", anchor="w", padx=10, pady=8, relief="solid", bd=1).pack(fill="x", pady=(8, 8))

        self.logic = tk.Text(side, height=21, wrap="word", bg="white", fg=self.TEXT, relief="solid", bd=1)
        self.logic.pack(fill="x", pady=(0, 8))
        self.logic.config(state="disabled")

        self.hist = tk.Text(side, height=18, wrap="word", bg="#0d3b66", fg="#eaf7ff", relief="solid", bd=1)
        self.hist.pack(fill="both", expand=True)
        self.hist.config(state="disabled")

        self.auto = False
        self.task_index = 0
        self.step_index = -1
        self.current_task: Task | None = None
        self.current_plan: Plan | None = None
        self.current_step: PlanStep | None = None
        self.count = 0
        self.face = "neutral"
        self.flash = ""
        self.flash_n = 0
        self.revision_used = False

        self.setup(int(time.time()) % 10_000_000)
        self.write("v48.9: Darwin deve planejar múltiplas etapas e revisar o plano se uma etapa falhar.\n")
        self.loop()

    def setup(self, seed: int) -> None:
        self.seed = seed
        rng = random.Random(seed)
        self.sid = f"V489-{seed}-{suffix(rng)}"
        self.task_index = 0
        self.step_index = -1
        self.current_task = None
        self.current_plan = None
        self.current_step = None
        self.revision_used = False
        self.face = "neutral"

        hole = rng.randint(80, 88)
        tol = round(rng.uniform(3.0, 5.5), 1)
        depth = round(rng.uniform(1.30, 1.60), 2)
        angle = rng.choice([18, 27, 36, 54, 63])

        self.tasks = [
            Task("task_rotate_insert", "plan_rotate_then_insert", f"object_{suffix(rng)}", f"aperture_{suffix(rng)}", "",
                 "square", "square", "", hole - 7, hole, 0, tol, depth - .1, depth, angle, 0, 90, "", "inserted", False),
            Task("task_alternate_shape", "plan_select_alternate_hole", f"object_{suffix(rng)}", f"aperture_{suffix(rng)}", f"aperture_{suffix(rng)}",
                 "triangle", "circle", "triangle", hole - 6, hole, hole + 2, tol, depth - .1, depth, 0, 0, 120, "", "inserted", False),
            Task("task_reject_oversize", "plan_reject_oversize", f"object_{suffix(rng)}", f"aperture_{suffix(rng)}", "",
                 "circle", "circle", "", hole + tol + 10, hole, 0, tol, depth - .1, depth, 0, 0, 90, "", "rejected_size", False),
            Task("task_direct_insert", "plan_direct_insert", f"object_{suffix(rng)}", f"aperture_{suffix(rng)}", "",
                 "circle", "circle", "", hole + tol - .8, hole, 0, tol, depth - .1, depth, 0, 0, 90, "", "inserted", False),
            Task("task_revision_hidden_depth", "plan_then_revise_hidden_depth", f"object_{suffix(rng)}", f"aperture_{suffix(rng)}", "",
                 "square", "square", "", hole - 6, hole, 0, tol, depth - .1, depth, 0, 0, 90, "hidden_depth_failure", "rejected_depth_after_revision", True),
        ]

        self.mem.log(self.sid, "planning_init", outcome="created", payload={
            "scenario_id": self.sid,
            "seed": seed,
            "source_table": SOURCE_TABLE,
            "source_status": self.source,
            "tasks": [asdict(t) for t in self.tasks],
        })

    def new_scenario(self) -> None:
        self.auto = False
        self.setup(int(time.time()) % 10_000_000)
        self.log(f"NOVO CENÁRIO: {self.sid}")
        self.write(f"Novo cenário: {self.sid}\nAgora Darwin deve planejar e revisar se necessário.\n")

    def start(self) -> None:
        self.auto = True
        self.log("AUTO: iniciado.")

    def pause(self) -> None:
        self.auto = False
        self.log("AUTO: pausado.")

    def step(self) -> None:
        if self.count <= 0:
            self.advance()

    def start_next_task(self) -> bool:
        if self.task_index >= len(self.tasks):
            self.auto = False
            self.face = "happy"
            self.status.set("Concluído. Darwin planejou múltiplos passos e revisou plano quando falhou.")
            self.mem.log(self.sid, "planning_complete", outcome="success", payload={
                "tasks": len(self.tasks),
                "source_table": SOURCE_TABLE,
            })
            self.write(
                "Final v48.9:\n"
                "- plano rotação → inserção ✔\n"
                "- plano escolher buraco alternativo ✔\n"
                "- plano rejeitar por tamanho ✔\n"
                "- plano inserir direto ✔\n"
                "- plano revisado após falha oculta ✔"
            )
            self.log("SUCESSO: planejamento multi-etapas v48.9 concluído.")
            return False

        self.current_task = self.tasks[self.task_index]
        self.task_index += 1
        self.current_plan = self.planner.make_plan(self.sid, self.current_task)
        self.step_index = 0
        self.revision_used = False

        self.mem.log(self.sid, "task_present", task=self.current_task, outcome="presented")
        self.mem.log(self.sid, "plan_create", task=self.current_task, plan=self.current_plan, outcome="created")
        for step in self.current_plan.steps:
            self.mem.log(self.sid, "step_justify", task=self.current_task, plan=self.current_plan, step=step, outcome="justified")

        self.log(f"PLANO[{self.current_task.task_kind}]: {len(self.current_plan.steps)} etapas | {self.current_plan.reason}")
        return True

    def advance(self) -> None:
        if self.current_plan is None or self.current_task is None or self.step_index >= len(self.current_plan.steps):
            if self.current_task and self.current_plan:
                final = self.current_task.expected_final
                self.mem.log(self.sid, "task_complete", task=self.current_task, plan=self.current_plan, final_status=final, outcome="success")
                self.log(f"TAREFA CONCLUÍDA: {self.current_task.task_id} -> {final}")
            if not self.start_next_task():
                return

        assert self.current_task is not None
        assert self.current_plan is not None

        step = self.current_plan.steps[self.step_index]
        self.current_step = step
        self.step_index += 1

        self.mem.log(self.sid, "step_execute", task=self.current_task, plan=self.current_plan, step=step, outcome="started")
        observed, should_continue = self.planner.execute_step(self.current_task, step)
        self.mem.log(self.sid, "step_observe", task=self.current_task, plan=self.current_plan, step=step, observed_outcome=observed, outcome=observed)

        self.flash = observed
        self.flash_n = 42
        self.face = "thinking"

        if should_continue:
            self.status.set(f"Executando etapa: {step.step_kind}.")
            self.log(f"ETAPA: {step.step_kind} -> {observed}")
            self.write(self.text(self.current_task, self.current_plan, step, observed))
        else:
            self.status.set(f"Falha detectada: {observed}. Darwin vai revisar plano.")
            self.log(f"FALHA: {step.step_kind} -> {observed}")
            self.mem.log(self.sid, "plan_failure_detected", task=self.current_task, plan=self.current_plan, step=step, observed_outcome=observed, outcome="failure")
            revised = self.planner.make_plan(self.sid, self.current_task, revision_id=1, failure=observed)
            self.mem.log(self.sid, "plan_revise", task=self.current_task, plan=revised, observed_outcome=observed, outcome="revised")
            for rstep in revised.steps:
                self.mem.log(self.sid, "revision_step_justify", task=self.current_task, plan=revised, step=rstep, outcome="justified")
            self.current_plan = revised
            self.step_index = 0
            self.revision_used = True
            self.write(self.text(self.current_task, revised, revised.steps[0], observed, revision=True))

        self.count = 46

    def text(self, task: Task, plan: Plan, step: PlanStep, observed: str, revision: bool = False) -> str:
        plan_lines = "\n".join(
            f"{s.step_index + 1}. {s.step_kind} → {s.expected_outcome}\n   justificativa: {s.justification}"
            for s in plan.steps
        )
        rev = "\n[REVISÃO ATIVA]\n" if revision or plan.revision_id > 0 else ""
        return (
            f"Tarefa: {task.task_id}\n"
            f"Tipo: {task.task_kind}\n"
            f"Plano: {plan.plan_id} | revisão={plan.revision_id}\n"
            f"Razão do plano: {plan.reason}\n"
            f"{rev}\n"
            f"Peça: {task.piece_id} | forma={task.piece_family} | tamanho={task.piece_size:.2f} | profundidade={task.piece_depth:.2f} | ângulo={task.angle_value:.1f}°\n"
            f"Buraco primário: {task.primary_hole_id} | forma={task.primary_hole_family} | tamanho={task.primary_hole_size:.2f} | profundidade={task.hole_depth:.2f}\n"
            f"Buraco alternativo: {task.alternate_hole_id or '-'} | forma={task.alternate_hole_family or '-'}\n\n"
            f"Plano completo:\n{plan_lines}\n\n"
            f"Etapa atual: {step.step_kind}\n"
            f"Justificativa: {step.justification}\n"
            f"Esperado: {step.expected_outcome}\n"
            f"Observado: {observed}\n"
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
        c.create_text(35, 38, anchor="w", text="DARWIN v48.9 — planejamento multi-etapas", font=("Segoe UI", 17, "bold"), fill=self.TEXT)
        c.create_text(35, 66, anchor="w", text=f"Cenário: {self.sid}", font=("Segoe UI", 10), fill=self.MUTED)

        self.robot(135, 225)
        self.plan_map(35, 105)
        self.panel(455, 115)

        if self.flash_n > 0 and self.flash:
            col = self.GREEN if "inserted" in self.flash or "rotated" in self.flash or "selected" in self.flash else self.BAD if "failure" in self.flash else self.BLUE
            self.rr(465, 620, 805, 670, 14, fill="white", outline=col, width=3)
            c.create_text(635, 645, text=self.flash, font=("Segoe UI", 13, "bold"), fill=col)

        c.create_text(35, 725, anchor="w",
                      text=f"Tarefa: {self.task_index}/{len(self.tasks)} | fonte v48.8: {'OK' if self.source.get('available') else 'AUSENTE'} | SQLite: {'ON' if self.mem.enabled else 'OFF'}",
                      font=("Segoe UI", 10, "bold"), fill=self.TEXT)

    def robot(self, cx, cy) -> None:
        c = self.cv
        c.create_oval(cx-65, cy-85, cx+65, cy+45, fill="#f8fbff", outline="#b9c8da", width=3)
        c.create_oval(cx-50, cy-58, cx+50, cy+15, fill="#192638", outline="#30465f", width=2)
        c.create_oval(cx-30, cy-35, cx-10, cy-15, fill="#8bdbff", outline="")
        c.create_oval(cx+10, cy-35, cx+30, cy-15, fill="#8bdbff", outline="")
        symbol = "↻" if self.revision_used else ("✓" if self.face == "happy" else "1→2")
        c.create_text(cx, cy, text=symbol, font=("Segoe UI", 15, "bold"), fill="#8bdbff")
        c.create_oval(cx-18, cy+28, cx+18, cy+64, fill="#ddf5ff", outline="#6ec6ff", width=3)
        c.create_text(cx, cy+83, text="DARWIN", font=("Segoe UI", 9, "bold"), fill="#355574")
        c.create_line(cx+55, cy+40, cx+110, cy+85, fill="#a8b7c9", width=8)
        c.create_oval(cx+104, cy+78, cx+120, cy+94, fill="white", outline="#8fa2b8", width=2)

    def plan_map(self, x, y) -> None:
        self.rr(x, y, x+395, y+165, 14, fill="white", outline="#d6e2f1", width=2)
        items = [
            ("avaliar", "estado"),
            ("planejar", "etapas"),
            ("justificar", "cada passo"),
            ("executar", "sequência"),
            ("observar", "falha"),
            ("revisar", "plano"),
        ]
        for i, (a, b) in enumerate(items):
            px = x + 18 + (i % 3) * 125
            py = y + 32 + (i // 3) * 70
            self.cv.create_text(px, py, anchor="w", text=a, font=("Segoe UI", 10, "bold"), fill="#22507c")
            self.cv.create_text(px, py+25, anchor="w", text=b, font=("Segoe UI", 8), fill=self.MUTED)

    def panel(self, x, y) -> None:
        self.rr(x, y, x+345, y+465, 18, fill="white", outline="#d6e2f1", width=2)
        self.cv.create_text(x+20, y+25, anchor="w", text="Plano atual", font=("Segoe UI", 14, "bold"), fill=self.TEXT)

        task = self.current_task
        plan = self.current_plan
        step = self.current_step
        if not task or not plan:
            self.cv.create_text(x+20, y+70, anchor="w", text="Aguardando tarefa...", font=("Segoe UI", 11), fill=self.MUTED)
            return

        self.cv.create_text(x+20, y+62, anchor="w", text=task.task_kind, font=("Segoe UI", 10, "bold"), fill=self.BLUE)
        self.cv.create_text(x+20, y+90, anchor="w", text=f"plano: {plan.plan_id}", font=("Segoe UI", 9), fill=self.MUTED)

        start_y = y + 130
        for s in plan.steps:
            yy = start_y + s.step_index * 58
            active = step and s.step_index == step.step_index
            fill = "#eaf4ff" if active else "#ffffff"
            outline = self.BLUE if active else "#d6e2f1"
            self.rr(x+20, yy, x+320, yy+42, 10, fill=fill, outline=outline, width=2)
            self.cv.create_text(x+35, yy+12, anchor="w", text=f"{s.step_index+1}. {s.step_kind}", font=("Segoe UI", 9, "bold"), fill=self.TEXT)
            self.cv.create_text(x+35, yy+30, anchor="w", text=s.expected_outcome, font=("Segoe UI", 8), fill=self.MUTED)

        self.cv.create_text(x+20, y+395, anchor="w", text=f"razão: {plan.reason}", font=("Segoe UI", 9, "bold"), fill=self.TEXT)
        self.cv.create_text(x+20, y+425, anchor="w", text=f"revisão: {plan.revision_id}", font=("Segoe UI", 10, "bold"), fill=self.BAD if plan.revision_id else self.GREEN)


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
