from __future__ import annotations

"""DARWIN v49.42 - execucao persistente de objetivos em circuito fechado."""

import argparse
import json
import random
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from darwin_activity_outcome_learning_v49_39 import ObservedActivityOutcome
from darwin_predictive_goal_planner_v49_41 import GoalDecision, PredictiveGoalPlanner


DB = Path("darwin_home") / "darwin.db"
EXECUTIONS = "goal_executions_v49_42"
STEPS = "goal_execution_steps_v49_42"
EVIDENCE = "goal_execution_evidence_v49_42"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def js(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


@dataclass
class GoalExecution:
    execution_id: str
    goal_decision_id: str
    goal_key: str
    target_activity: str
    status: str
    current_step: int
    total_steps: int
    selected_activity: str
    outcome_value: float
    message: str


class ExecutionStore:
    def __init__(self, db_path: Path = DB) -> None:
        self.db_path = Path(db_path)
        self.ensure()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=12.0)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS {EXECUTIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    execution_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL,
                    scenario_kind TEXT NOT NULL,
                    goal_decision_id TEXT NOT NULL,
                    goal_key TEXT NOT NULL,
                    target_activity TEXT NOT NULL,
                    selected_activity TEXT NOT NULL DEFAULT '',
                    activity_decision_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    current_step INTEGER NOT NULL DEFAULT 0,
                    total_steps INTEGER NOT NULL,
                    stop_condition TEXT NOT NULL,
                    outcome_value REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );
                CREATE TABLE IF NOT EXISTS {STEPS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    action_kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL DEFAULT '',
                    completed_at TEXT NOT NULL DEFAULT '',
                    evidence_ref TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}',
                    UNIQUE(execution_id, step_index)
                );
                CREATE TABLE IF NOT EXISTS {EVIDENCE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    evidence_kind TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    accepted INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );
                """
            )

    def create(self, session_id: str, scenario_kind: str, execution_id: str, goal: GoalDecision) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {EXECUTIONS}
                (timestamp, updated_at, execution_id, session_id, scenario_kind,
                 goal_decision_id, goal_key, target_activity, status, current_step,
                 total_steps, stop_condition, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'started', 1, ?, ?, ?)
                """,
                (
                    now(), now(), execution_id, session_id, scenario_kind,
                    goal.decision_id, goal.goal_key, goal.target_activity,
                    len(goal.steps), goal.stop_condition,
                    js({"rzs_decision": goal.rzs_decision, "goal_score": goal.score}),
                ),
            )
            for index, action in enumerate(goal.steps, 1):
                conn.execute(
                    f"""
                    INSERT INTO {STEPS}
                    (timestamp, execution_id, step_index, action_kind, status,
                     started_at, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        now(), execution_id, index, action,
                        "active" if index == 1 else "pending",
                        now() if index == 1 else "",
                        js({"causal_order": index}),
                    ),
                )

    def row(self, execution_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT * FROM {EXECUTIONS} WHERE execution_id=?", (execution_id,)
            ).fetchone()
        return dict(row) if row else {}

    def latest_open(self) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                f"""
                SELECT * FROM {EXECUTIONS}
                WHERE status IN ('started', 'waiting_outcome', 'replanning')
                ORDER BY id DESC LIMIT 1
                """
            ).fetchone()
        return dict(row) if row else {}

    def transition(
        self,
        execution_id: str,
        *,
        status: str,
        current_step: int | None = None,
        selected_activity: str | None = None,
        activity_decision_id: str | None = None,
        outcome_value: float | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        row = self.row(execution_id)
        with self.connect() as conn:
            conn.execute(
                f"""
                UPDATE {EXECUTIONS}
                SET updated_at=?, status=?, current_step=?, selected_activity=?,
                    activity_decision_id=?, outcome_value=?, payload_json=?
                WHERE execution_id=?
                """,
                (
                    now(), status,
                    int(row["current_step"] if current_step is None else current_step),
                    str(row["selected_activity"] if selected_activity is None else selected_activity),
                    str(row["activity_decision_id"] if activity_decision_id is None else activity_decision_id),
                    float(row["outcome_value"] if outcome_value is None else outcome_value),
                    js(payload or {}),
                    execution_id,
                ),
            )

    def complete_step(self, execution_id: str, step_index: int, evidence_ref: str) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                UPDATE {STEPS}
                SET status='completed', completed_at=?, evidence_ref=?
                WHERE execution_id=? AND step_index=?
                """,
                (now(), evidence_ref, execution_id, step_index),
            )
            conn.execute(
                f"""
                UPDATE {STEPS}
                SET status='active', started_at=?
                WHERE execution_id=? AND step_index=? AND status='pending'
                """,
                (now(), execution_id, step_index + 1),
            )

    def add_evidence(
        self, execution_id: str, kind: str, source_ref: str, accepted: bool, payload: dict[str, Any]
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {EVIDENCE}
                (timestamp, execution_id, evidence_kind, source_ref, accepted, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (now(), execution_id, kind, source_ref, int(accepted), js(payload)),
            )


class GoalExecutionLoop:
    def __init__(self, db_path: Path = DB, seed: int = 4942) -> None:
        self.store = ExecutionStore(db_path)
        self.planner = PredictiveGoalPlanner(db_path, seed=seed)
        self.rng = random.Random(seed)
        self.counter = 0

    def start(
        self,
        session_id: str,
        *,
        scenario_kind: str = "live",
        goal: GoalDecision | None = None,
    ) -> GoalExecution:
        goal = goal or self.planner.choose_goal(session_id, scenario_kind=f"execution:{scenario_kind}")
        self.counter += 1
        execution_id = f"exec:{session_id}:{int(time.time() * 1000)}:{self.counter:03d}"
        self.store.create(session_id, scenario_kind, execution_id, goal)
        if goal.target_activity in {"conversation", "rest"}:
            labels = {"conversation": "da nossa conversa", "rest": "do descanso"}
            for index in range(1, len(goal.steps) + 1):
                self.store.complete_step(execution_id, index, f"internal:{goal.target_activity}")
            self.store.add_evidence(
                execution_id, "internal_action", f"internal:{goal.target_activity}", True,
                {"target_activity": goal.target_activity},
            )
            self.store.transition(
                execution_id, status="completed", current_step=len(goal.steps),
                selected_activity=goal.target_activity, outcome_value=0.70,
                payload={"completion_kind": "internal"},
            )
            message = f"Comecei e conclui o objetivo interno por meio {labels[goal.target_activity]}."
        else:
            self.store.complete_step(execution_id, 1, "goal_plan:recalled")
            self.store.transition(
                execution_id, status="started", current_step=2,
                payload={"waiting_for_activity_choice": True},
            )
            message = f"Comecei o objetivo. Agora preciso escolher e realizar {goal.target_activity}."
        return self.describe(execution_id, message)

    def bind_activity(
        self,
        execution_id: str,
        selected_activity: str,
        activity_decision_id: str,
        launched: bool,
    ) -> GoalExecution:
        row = self.store.row(execution_id)
        aligned = selected_activity == row.get("target_activity") and launched
        self.store.add_evidence(
            execution_id, "activity_choice", f"activity:{activity_decision_id}", aligned,
            {
                "target": row.get("target_activity"),
                "selected": selected_activity,
                "launched": launched,
            },
        )
        if aligned:
            self.store.complete_step(execution_id, 2, f"activity:{activity_decision_id}")
            self.store.transition(
                execution_id, status="waiting_outcome", current_step=3,
                selected_activity=selected_activity,
                activity_decision_id=activity_decision_id,
                payload={"causal_requirement": "real_activity_outcome"},
            )
            message = "A atividade escolhida corresponde ao objetivo. Agora aguardarei o resultado real."
        else:
            self.store.transition(
                execution_id, status="replanning", current_step=2,
                selected_activity=selected_activity,
                activity_decision_id=activity_decision_id,
                payload={"mismatch": True, "launched": launched},
            )
            message = "A escolha não correspondeu ao objetivo ou não abriu; não marquei sucesso e preciso replanejar."
        return self.describe(execution_id, message)

    def observe_outcomes(self, outcomes: list[ObservedActivityOutcome]) -> list[GoalExecution]:
        completed: list[GoalExecution] = []
        for outcome in outcomes:
            row = self.store.latest_open()
            if not row or row.get("status") != "waiting_outcome":
                continue
            accepted = outcome.activity_key == row.get("target_activity")
            self.store.add_evidence(
                str(row["execution_id"]), "activity_outcome",
                f"{outcome.source_table}:{outcome.source_row_id}", accepted,
                {"observed_value": outcome.observed_value, "prediction_error": outcome.prediction_error},
            )
            if not accepted:
                continue
            self.store.complete_step(
                str(row["execution_id"]), 3,
                f"{outcome.source_table}:{outcome.source_row_id}",
            )
            self.store.transition(
                str(row["execution_id"]), status="completed", current_step=3,
                outcome_value=outcome.observed_value,
                payload={"stop_condition_checked": True, "outcome_observed": True},
            )
            completed.append(self.describe(str(row["execution_id"]), "Objetivo concluído com resultado observado."))
        return completed

    def describe(self, execution_id: str, message: str = "") -> GoalExecution:
        row = self.store.row(execution_id)
        return GoalExecution(
            execution_id=execution_id,
            goal_decision_id=str(row.get("goal_decision_id", "")),
            goal_key=str(row.get("goal_key", "")),
            target_activity=str(row.get("target_activity", "")),
            status=str(row.get("status", "")),
            current_step=int(row.get("current_step", 0) or 0),
            total_steps=int(row.get("total_steps", 0) or 0),
            selected_activity=str(row.get("selected_activity", "")),
            outcome_value=float(row.get("outcome_value", 0.0) or 0.0),
            message=message,
        )

    @staticmethod
    def is_start_request(text: str) -> bool:
        lowered = text.lower()
        return any(
            pattern in lowered
            for pattern in (
                "comece seu objetivo",
                "começa seu objetivo",
                "inicie seu objetivo",
                "execute seu plano",
                "pode comecar seu objetivo",
                "pode começar seu objetivo",
            )
        )


def fake_goal(key: str, target: str) -> GoalDecision:
    return GoalDecision(
        f"test-goal:{key}:{target}", key, target, "teste controlado",
        ["recall_relevant_experiences", "run_target_experience", "compare_prediction_with_outcome"],
        "controlled_stop", "continue", 1.8, 2.0, 0.7,
    )


def run_self_test(details: bool = False) -> dict[str, Any]:
    core = GoalExecutionLoop(seed=4942)
    session = f"V4942-{int(time.time())}-{core.rng.randrange(1000, 9999)}"
    aligned = core.start(session, scenario_kind="self_test_aligned", goal=fake_goal("learn", "memory_cards"))
    aligned = core.bind_activity(aligned.execution_id, "memory_cards", "choice-aligned", True)
    outcome = ObservedActivityOutcome(
        "outcome-test", "memory_cards", 0.74, 0.68, 0.06,
        0.50, 0.58, 1, "continue", 1.8, 1.9,
        "controlled_source", 1, "resultado controlado", "self_test",
    )
    completed = core.observe_outcomes([outcome])[0]
    mismatch = core.start(session, scenario_kind="self_test_mismatch", goal=fake_goal("learn", "formula_sketch"))
    mismatch = core.bind_activity(mismatch.execution_id, "classical_music", "choice-mismatch", True)
    internal = core.start(
        session, scenario_kind="self_test_internal",
        goal=fake_goal("restore_stability", "rest"),
    )
    result = {
        "session_id": session,
        "aligned_waited": aligned.__dict__,
        "completed": completed.__dict__,
        "mismatch": mismatch.__dict__,
        "internal": internal.__dict__,
    }
    if details:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"DARWIN v49.42 self-test: completed={completed.status} "
            f"mismatch={mismatch.status} internal={internal.status}"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Darwin v49.42 Goal Execution Loop")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args()
    result = run_self_test(args.details)
    return 0 if result["completed"]["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
