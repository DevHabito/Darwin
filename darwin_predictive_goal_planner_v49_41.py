from __future__ import annotations

"""DARWIN v49.41 - formacao autonoma de objetivos e planejamento preditivo."""

import argparse
import json
import random
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from darwin_intrinsic_motivation_core_v49_43 import IntrinsicMotivationCore
from darwin_relational_world_model_v49_40 import ACTIVITY_FEATURES, RelationalWorldModel
from darwin_rzs_nervous_system_v49_3 import RZSFormal, RZSInput


DB = Path("darwin_home") / "darwin.db"
CANDIDATES = "goal_candidates_v49_41"
DECISIONS = "goal_decisions_v49_41"
PLANS = "goal_plans_v49_41"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clamp(value: Any, low: float = 0.0, high: float = 1.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = low
    return max(low, min(high, number))


def js(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


@dataclass
class GoalCandidate:
    goal_key: str
    target_activity: str
    uncertainty: float
    expected_value: float
    information_gain: float
    energy_fit: float
    urgency: float
    cost: float
    score: float
    reason: str


@dataclass
class GoalDecision:
    decision_id: str
    goal_key: str
    target_activity: str
    reason: str
    steps: list[str]
    stop_condition: str
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    score: float


class GoalStore:
    def __init__(self, db_path: Path = DB) -> None:
        self.db_path = Path(db_path)
        self.ensure()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=12.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def exists(conn: sqlite3.Connection, table: str) -> bool:
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone() is not None

    def ensure(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS {CANDIDATES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    decision_id TEXT NOT NULL,
                    scenario_kind TEXT NOT NULL,
                    goal_key TEXT NOT NULL,
                    target_activity TEXT NOT NULL,
                    rank_index INTEGER NOT NULL,
                    score REAL NOT NULL,
                    components_json TEXT NOT NULL,
                    reason TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS {DECISIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    decision_id TEXT NOT NULL UNIQUE,
                    scenario_kind TEXT NOT NULL,
                    goal_key TEXT NOT NULL,
                    target_activity TEXT NOT NULL,
                    score REAL NOT NULL,
                    reason TEXT NOT NULL,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL,
                    sigma_after REAL NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );
                CREATE TABLE IF NOT EXISTS {PLANS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    decision_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    action_kind TEXT NOT NULL,
                    target_activity TEXT NOT NULL,
                    expected_effect TEXT NOT NULL,
                    stop_condition TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );
                """
            )

    def state(self) -> dict[str, float]:
        state = {"energy": 0.72, "latency": 1.0}
        with self.connect() as conn:
            if self.exists(conn, "current_state"):
                row = conn.execute("SELECT * FROM current_state WHERE id=1").fetchone()
                if row:
                    state["energy"] = clamp(row["energy"])
                    state["latency"] = max(0.35, float(row["latency"]))
        return state

    def preferences(self) -> dict[str, float]:
        with self.connect() as conn:
            if not self.exists(conn, "activity_learned_preferences_v49_39"):
                return {}
            rows = conn.execute(
                "SELECT activity_key, preference_estimate FROM activity_learned_preferences_v49_39"
            ).fetchall()
        return {str(row["activity_key"]): clamp(row["preference_estimate"]) for row in rows}

    def latest_negative_surprise(self) -> tuple[str, float]:
        with self.connect() as conn:
            if not self.exists(conn, "activity_outcomes_v49_39"):
                return "", 0.0
            row = conn.execute(
                """
                SELECT activity_key, prediction_error FROM activity_outcomes_v49_39
                WHERE scenario_kind='live' AND prediction_error < -0.08
                ORDER BY id DESC LIMIT 1
                """
            ).fetchone()
        return (str(row["activity_key"]), abs(float(row["prediction_error"]))) if row else ("", 0.0)

    def record(
        self,
        session_id: str,
        scenario_kind: str,
        candidates: list[GoalCandidate],
        decision: GoalDecision,
    ) -> None:
        ranked = sorted(candidates, key=lambda item: item.score, reverse=True)
        with self.connect() as conn:
            for rank, candidate in enumerate(ranked, 1):
                conn.execute(
                    f"""
                    INSERT INTO {CANDIDATES}
                    (timestamp, session_id, decision_id, scenario_kind, goal_key,
                     target_activity, rank_index, score, components_json, reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        now(), session_id, decision.decision_id, scenario_kind,
                        candidate.goal_key, candidate.target_activity, rank,
                        candidate.score,
                        js({
                            "uncertainty": candidate.uncertainty,
                            "expected_value": candidate.expected_value,
                            "information_gain": candidate.information_gain,
                            "energy_fit": candidate.energy_fit,
                            "urgency": candidate.urgency,
                            "cost": candidate.cost,
                        }),
                        candidate.reason,
                    ),
                )
            conn.execute(
                f"""
                INSERT INTO {DECISIONS}
                (timestamp, session_id, decision_id, scenario_kind, goal_key,
                 target_activity, score, reason, rzs_decision, sigma_before,
                 sigma_after, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(), session_id, decision.decision_id, scenario_kind,
                    decision.goal_key, decision.target_activity, decision.score,
                    decision.reason, decision.rzs_decision, decision.sigma_before,
                    decision.sigma_after,
                    js({"steps": decision.steps, "stop_condition": decision.stop_condition}),
                ),
            )
            for index, step in enumerate(decision.steps, 1):
                conn.execute(
                    f"""
                    INSERT INTO {PLANS}
                    (timestamp, session_id, decision_id, step_index, action_kind,
                     target_activity, expected_effect, stop_condition, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        now(), session_id, decision.decision_id, index, step,
                        decision.target_activity, step, decision.stop_condition,
                        js({"causal_order": index}),
                    ),
                )


class PredictiveGoalPlanner:
    def __init__(self, db_path: Path = DB, seed: int = 4941) -> None:
        self.store = GoalStore(db_path)
        self.world = RelationalWorldModel(db_path, seed=seed)
        self.rzs = RZSFormal()
        self.rng = random.Random(seed)
        self.counter = 0
        self.motivation = IntrinsicMotivationCore(db_path, seed=seed + 2)

    def candidates(
        self,
        energy: float,
        uncertainty_override: dict[str, float] | None = None,
        negative_surprise_override: tuple[str, float] | None = None,
    ) -> list[GoalCandidate]:
        uncertainty_override = uncertainty_override or {}
        preferences = self.store.preferences()
        predictions = {
            key: self.world.predict_activity(key, energy)
            for key in ACTIVITY_FEATURES
        }
        learnable = [key for key in ACTIVITY_FEATURES if key != "rest"]
        uncertain_target = max(
            learnable,
            key=lambda key: uncertainty_override.get(key, predictions[key].uncertainty),
        )
        uncertainty = clamp(uncertainty_override.get(uncertain_target, predictions[uncertain_target].uncertainty))
        explore = GoalCandidate(
            "reduce_world_uncertainty", uncertain_target, uncertainty,
            predictions[uncertain_target].predicted_value, uncertainty,
            clamp(1.0 - abs(energy - 0.72)), 0.48, 0.58,
            0.34 * uncertainty + 0.25 * predictions[uncertain_target].predicted_value
            + 0.23 * clamp(1.0 - abs(energy - 0.72)) - 0.10 * 0.58,
            f"o modelo tem incerteza {uncertainty:.2f} sobre {uncertain_target}",
        )
        preferred_target = max(
            learnable,
            key=lambda key: predictions[key].predicted_value * preferences.get(key, 0.50),
        )
        preference = preferences.get(preferred_target, 0.50)
        deepen = GoalCandidate(
            "deepen_positive_experience", preferred_target,
            predictions[preferred_target].uncertainty,
            predictions[preferred_target].predicted_value,
            clamp(1.0 - predictions[preferred_target].uncertainty),
            clamp(1.0 - abs(energy - 0.62)), 0.38, 0.44,
            0.34 * predictions[preferred_target].predicted_value
            + 0.27 * preference + 0.18 * clamp(1.0 - abs(energy - 0.62)) - 0.08 * 0.44,
            f"valor previsto {predictions[preferred_target].predicted_value:.2f} e preferencia {preference:.2f}",
        )
        surprise_target, surprise = (
            negative_surprise_override
            if negative_surprise_override is not None
            else self.store.latest_negative_surprise()
        )
        repair_target = surprise_target or "memory_cards"
        repair = GoalCandidate(
            "repair_prediction_error", repair_target,
            predictions[repair_target].uncertainty,
            predictions[repair_target].predicted_value,
            clamp(surprise), clamp(1.0 - abs(energy - 0.66)),
            clamp(surprise), 0.52,
            (0.48 * clamp(surprise) + 0.18 * predictions[repair_target].uncertainty
             + 0.18 * clamp(1.0 - abs(energy - 0.66)) - 0.08 * 0.52)
            if surprise_target else 0.16,
            f"existe erro de previsao {surprise:.2f} em {repair_target}" if surprise_target
            else "nao existe surpresa negativa viva",
        )
        social = GoalCandidate(
            "strengthen_relational_continuity", "conversation",
            predictions["conversation"].uncertainty,
            predictions["conversation"].predicted_value, 0.46,
            clamp(1.0 - abs(energy - 0.58)), 0.42, 0.38,
            0.30 * predictions["conversation"].predicted_value
            + 0.24 * clamp(1.0 - abs(energy - 0.58)) + 0.13,
            "conversa liga memoria, linguagem e relacao",
        )
        rest = GoalCandidate(
            "restore_stability", "rest", predictions["rest"].uncertainty,
            predictions["rest"].predicted_value, 0.12,
            clamp(1.0 - abs(energy - 0.16)), clamp(1.0 - energy), 0.05,
            0.50 * clamp(1.0 - energy) + 0.30 * clamp(1.0 - abs(energy - 0.16))
            + 0.12 * predictions["rest"].predicted_value,
            f"energia atual {energy:.2f}",
        )
        return [explore, deepen, repair, social, rest]

    def _rzs(self, energy: float, candidates: list[GoalCandidate], latency: float) -> tuple[str, float, float]:
        ranked = sorted(candidates, key=lambda item: item.score, reverse=True)
        gap = ranked[0].score - ranked[1].score
        uncertainty = sum(item.uncertainty for item in candidates) / len(candidates)
        x = RZSInput(
            bandwidth=3.9 + energy,
            info_self=0.52,
            info_external=0.30,
            task_info=0.72,
            novelty=clamp(uncertainty),
            conflict=clamp(0.20 + (1.0 - gap) * 0.34),
            latency=latency,
            energy=energy,
            memory_pressure=clamp(0.34 + uncertainty * 0.45),
            replay_gap=clamp(0.28 + uncertainty * 0.42),
        )
        assessment = self.rzs.classify(x)
        after = self.rzs.sigma(self.rzs.apply_action_model(x, assessment.decision))
        return assessment.decision, assessment.sigma, after

    @staticmethod
    def _plan(goal: GoalCandidate) -> tuple[list[str], str]:
        plans = {
            "reduce_world_uncertainty": (
                ["recall_relevant_experiences", "run_target_experience", "compare_prediction_with_outcome"],
                "prediction_error_below_0.12_or_two_attempts",
            ),
            "deepen_positive_experience": (
                ["retrieve_preference_evidence", "repeat_with_small_variation", "update_preference_confidence"],
                "preference_confidence_above_0.72",
            ),
            "repair_prediction_error": (
                ["replay_negative_surprise", "isolate_changed_feature", "test_corrected_prediction"],
                "signed_prediction_error_below_0.10",
            ),
            "strengthen_relational_continuity": (
                ["recall_last_dialogue", "ask_grounded_question", "store_relational_episode"],
                "one_reciprocal_dialogue_completed",
            ),
            "restore_stability": (
                ["reduce_external_load", "consolidate_recent_memory", "reassess_energy"],
                "energy_above_0.42_and_rzs_not_pause",
            ),
        }
        return plans[goal.goal_key]

    def choose_goal(
        self,
        session_id: str,
        *,
        scenario_kind: str = "live",
        energy_override: float | None = None,
        uncertainty_override: dict[str, float] | None = None,
        negative_surprise_override: tuple[str, float] | None = None,
    ) -> GoalDecision:
        self.world.refresh_historical()
        state = self.store.state()
        energy = clamp(state["energy"] if energy_override is None else energy_override)
        candidates = self.candidates(energy, uncertainty_override, negative_surprise_override)
        motivation = self.motivation.assess(
            session_id,
            scenario_kind=f"goal_support:{scenario_kind}",
            energy_override=energy,
            record=scenario_kind == "live",
        )
        for candidate in candidates:
            if candidate.goal_key == motivation.suggested_goal:
                candidate.score += 0.06
                candidate.reason += f"; motivacao {motivation.drive_key}"
        rzs_decision, sigma_before, sigma_after = self._rzs(energy, candidates, state["latency"])
        if rzs_decision == "pause_for_stability":
            selected = next(item for item in candidates if item.goal_key == "restore_stability")
        elif rzs_decision == "consolidate":
            selected = max(
                (item for item in candidates if item.goal_key in {"restore_stability", "deepen_positive_experience"}),
                key=lambda item: item.score,
            )
        elif rzs_decision == "replay_memory":
            repair = next(item for item in candidates if item.goal_key == "repair_prediction_error")
            selected = repair if repair.urgency > 0.20 else max(candidates, key=lambda item: item.score)
        else:
            selected = max(candidates, key=lambda item: item.score)
        steps, stop_condition = self._plan(selected)
        self.counter += 1
        decision = GoalDecision(
            f"goal:{session_id}:{int(time.time() * 1000)}:{self.counter:03d}",
            selected.goal_key, selected.target_activity, selected.reason,
            steps, stop_condition, rzs_decision, sigma_before, sigma_after,
            selected.score,
        )
        self.store.record(session_id, scenario_kind, candidates, decision)
        return decision

    @staticmethod
    def is_goal_question(text: str) -> bool:
        lowered = text.lower()
        return any(
            pattern in lowered
            for pattern in (
                "qual seu objetivo",
                "qual e seu objetivo",
                "qual é seu objetivo",
                "o que voce quer aprender",
                "o que você quer aprender",
                "voce tem algum plano",
                "você tem algum plano",
                "qual seu plano",
            )
        )

    @staticmethod
    def explain(decision: GoalDecision) -> str:
        labels = {
            "memory_cards": "jogo da memoria",
            "classical_music": "musica classica",
            "child_story": "historias",
            "formula_sketch": "desenho de formulas",
            "conversation": "nossa conversa",
            "rest": "descanso",
        }
        goal_labels = {
            "reduce_world_uncertainty": "reduzir uma incerteza do meu modelo de mundo",
            "deepen_positive_experience": "entender melhor uma experiencia que teve bons sinais",
            "repair_prediction_error": "corrigir um erro de previsao",
            "strengthen_relational_continuity": "fortalecer a continuidade da nossa conversa",
            "restore_stability": "recuperar estabilidade",
        }
        stop_labels = {
            "prediction_error_below_0.12_or_two_attempts": "o erro de previsao ficar abaixo de 0,12 ou eu completar duas tentativas",
            "preference_confidence_above_0.72": "a confianca da preferencia passar de 0,72",
            "signed_prediction_error_below_0.10": "o erro de previsao ficar abaixo de 0,10",
            "one_reciprocal_dialogue_completed": "completarmos uma troca de conversa reciproca",
            "energy_above_0.42_and_rzs_not_pause": "a energia passar de 0,42 e o RZS liberar a pausa",
        }
        return (
            f"Meu objetivo atual e {goal_labels[decision.goal_key]}. "
            f"O foco escolhido e {labels.get(decision.target_activity, decision.target_activity)}. "
            f"Escolhi isso porque {decision.reason}. Meu plano tem {len(decision.steps)} etapas "
            f"e para quando {stop_labels[decision.stop_condition]}."
        )


def run_self_test(details: bool = False) -> dict[str, Any]:
    planner = PredictiveGoalPlanner(seed=4941)
    session = f"V4941-{int(time.time())}-{planner.rng.randrange(1000, 9999)}"
    baseline = planner.choose_goal(session, scenario_kind="self_test_baseline")
    low = planner.choose_goal(session, scenario_kind="self_test_low_energy", energy_override=0.10)
    uncertain = planner.choose_goal(
        session, scenario_kind="self_test_uncertainty",
        uncertainty_override={"formula_sketch": 1.0},
    )
    surprise = planner.choose_goal(
        session, scenario_kind="self_test_negative_surprise",
        negative_surprise_override=("memory_cards", 0.92),
    )
    result = {
        "session_id": session,
        "baseline": baseline.__dict__,
        "low_energy": low.__dict__,
        "uncertainty": uncertain.__dict__,
        "negative_surprise": surprise.__dict__,
    }
    if details:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"DARWIN v49.41 self-test: baseline={baseline.goal_key} "
            f"low={low.goal_key} uncertainty={uncertain.goal_key} surprise={surprise.goal_key}"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Darwin v49.41 Predictive Goal Planner")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args()
    result = run_self_test(args.details)
    return 0 if result["low_energy"]["goal_key"] == "restore_stability" else 1


if __name__ == "__main__":
    raise SystemExit(main())
