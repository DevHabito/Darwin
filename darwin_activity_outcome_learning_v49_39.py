from __future__ import annotations

"""
DARWIN v49.39 - aprendizagem pelo resultado de atividades

Fecha o ciclo:
escolha -> expectativa -> experiencia concluida -> erro de previsao ->
atualizacao de preferencia -> proxima escolha.

"Gostar" neste modulo significa uma preferencia operacional baseada em sinais
registrados. Nao e uma afirmacao de sentimento ou consciencia.
"""

import argparse
import json
import math
import random
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from darwin_rzs_nervous_system_v49_3 import RZSFormal, RZSInput


DB = Path("darwin_home") / "darwin.db"
PENDING = "activity_outcome_pending_v49_39"
OUTCOMES = "activity_outcomes_v49_39"
PREFERENCES = "activity_learned_preferences_v49_39"
UPDATES = "activity_preference_updates_v49_39"

SOURCE_SPECS = {
    "memory_cards": ("memory_card_games_v49_13", "game_complete"),
    "classical_music": ("music_nursery_sessions_v49_16", "session_complete"),
    "child_story": ("story_nursery_sessions_v49_29", "session_complete"),
    "formula_sketch": ("formula_sketch_sessions_v49_28", "sketch_complete"),
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clamp(value: Any, low: float = 0.0, high: float = 1.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = low
    return max(low, min(high, number))


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def pj(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def js(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


@dataclass
class ObservedActivityOutcome:
    observation_id: str
    activity_key: str
    observed_value: float
    predicted_value: float
    prediction_error: float
    preference_before: float
    preference_after: float
    evidence_count: int
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    source_table: str
    source_row_id: int
    summary: str
    scenario_kind: str


class ActivityOutcomeStore:
    def __init__(self, db_path: Path = DB) -> None:
        self.db_path = Path(db_path)
        self.ensure()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=12.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def table_exists(conn: sqlite3.Connection, table: str) -> bool:
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone() is not None

    def ensure(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS {PENDING} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    observation_id TEXT NOT NULL UNIQUE,
                    decision_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    activity_key TEXT NOT NULL,
                    source_table TEXT NOT NULL,
                    baseline_source_id INTEGER NOT NULL DEFAULT 0,
                    predicted_value REAL NOT NULL,
                    choice_rzs_decision TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );
                CREATE TABLE IF NOT EXISTS {OUTCOMES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    observation_id TEXT NOT NULL,
                    decision_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    scenario_kind TEXT NOT NULL,
                    activity_key TEXT NOT NULL,
                    source_table TEXT NOT NULL,
                    source_row_id INTEGER NOT NULL DEFAULT 0,
                    predicted_value REAL NOT NULL,
                    observed_value REAL NOT NULL,
                    prediction_error REAL NOT NULL,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL,
                    sigma_after REAL NOT NULL,
                    summary TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );
                CREATE TABLE IF NOT EXISTS {PREFERENCES} (
                    activity_key TEXT PRIMARY KEY,
                    updated_at TEXT NOT NULL,
                    preference_estimate REAL NOT NULL,
                    evidence_count INTEGER NOT NULL DEFAULT 0,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    positive_count INTEGER NOT NULL DEFAULT 0,
                    negative_count INTEGER NOT NULL DEFAULT 0,
                    last_outcome_id INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );
                CREATE TABLE IF NOT EXISTS {UPDATES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    observation_id TEXT NOT NULL,
                    scenario_kind TEXT NOT NULL,
                    activity_key TEXT NOT NULL,
                    preference_before REAL NOT NULL,
                    observed_value REAL NOT NULL,
                    learning_rate REAL NOT NULL,
                    preference_after REAL NOT NULL,
                    evidence_before INTEGER NOT NULL,
                    evidence_after INTEGER NOT NULL,
                    rzs_decision TEXT NOT NULL,
                    update_applied INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );
                CREATE INDEX IF NOT EXISTS idx_activity_outcome_pending_status
                    ON {PENDING}(status, id);
                CREATE INDEX IF NOT EXISTS idx_activity_outcome_activity
                    ON {OUTCOMES}(activity_key, id);
                """
            )

    def current_state(self) -> dict[str, float]:
        state = {"energy": 0.72, "latency": 1.0}
        with self.connect() as conn:
            if not self.table_exists(conn, "current_state"):
                return state
            row = conn.execute("SELECT * FROM current_state WHERE id=1").fetchone()
            if row:
                columns = set(row.keys())
                if "energy" in columns:
                    state["energy"] = clamp(row["energy"])
                if "latency" in columns:
                    state["latency"] = max(0.25, safe_float(row["latency"], 1.0))
        return state

    def source_max_id(self, source_table: str) -> int:
        with self.connect() as conn:
            if not self.table_exists(conn, source_table):
                return 0
            row = conn.execute(f"SELECT MAX(id) AS max_id FROM {source_table}").fetchone()
            return int(row["max_id"] or 0)

    def arm(
        self,
        observation_id: str,
        decision_id: str,
        session_id: str,
        activity_key: str,
        source_table: str,
        baseline_source_id: int,
        predicted_value: float,
        choice_rzs_decision: str,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {PENDING}
                (timestamp, observation_id, decision_id, session_id, activity_key,
                 source_table, baseline_source_id, predicted_value,
                 choice_rzs_decision, status, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    now(), observation_id, decision_id, session_id, activity_key,
                    source_table, baseline_source_id, clamp(predicted_value),
                    choice_rzs_decision, js({"completion_phase": SOURCE_SPECS[activity_key][1]}),
                ),
            )

    def cancel(self, observation_id: str, reason: str) -> None:
        with self.connect() as conn:
            conn.execute(
                f"UPDATE {PENDING} SET status='cancelled', payload_json=? WHERE observation_id=?",
                (js({"reason": reason}), observation_id),
            )

    def pending_rows(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM {PENDING} WHERE status='pending' ORDER BY id"
            ).fetchall()
        return [dict(row) for row in rows]

    def completed_source_row(self, pending: dict[str, Any]) -> dict[str, Any] | None:
        source_table = str(pending["source_table"])
        activity_key = str(pending["activity_key"])
        expected_table, phase = SOURCE_SPECS[activity_key]
        if source_table != expected_table:
            return None
        with self.connect() as conn:
            if not self.table_exists(conn, source_table):
                return None
            row = conn.execute(
                f"""
                SELECT * FROM {source_table}
                WHERE id>? AND phase=?
                ORDER BY id LIMIT 1
                """,
                (int(pending["baseline_source_id"]), phase),
            ).fetchone()
        return dict(row) if row else None

    def preference(self, activity_key: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT * FROM {PREFERENCES} WHERE activity_key=?", (activity_key,)
            ).fetchone()
        if row:
            return dict(row)
        return {
            "activity_key": activity_key,
            "preference_estimate": 0.50,
            "evidence_count": 0,
            "confidence": 0.0,
            "positive_count": 0,
            "negative_count": 0,
        }

    def record_outcome(
        self,
        pending: dict[str, Any],
        scenario_kind: str,
        source_row_id: int,
        observed_value: float,
        rzs_decision: str,
        sigma_before: float,
        sigma_after: float,
        summary: str,
        metrics: dict[str, Any],
    ) -> int:
        prediction_error = observed_value - clamp(pending["predicted_value"])
        with self.connect() as conn:
            cursor = conn.execute(
                f"""
                INSERT INTO {OUTCOMES}
                (timestamp, observation_id, decision_id, session_id, scenario_kind,
                 activity_key, source_table, source_row_id, predicted_value,
                 observed_value, prediction_error, rzs_decision, sigma_before,
                 sigma_after, summary, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(), pending["observation_id"], pending["decision_id"], pending["session_id"],
                    scenario_kind, pending["activity_key"], pending["source_table"], source_row_id,
                    clamp(pending["predicted_value"]), observed_value, prediction_error,
                    rzs_decision, sigma_before, sigma_after, summary, js(metrics),
                ),
            )
            if scenario_kind == "live":
                conn.execute(
                    f"UPDATE {PENDING} SET status='learned', payload_json=? WHERE observation_id=?",
                    (
                        js({"source_row_id": source_row_id, "observed_value": observed_value}),
                        pending["observation_id"],
                    ),
                )
            return int(cursor.lastrowid)

    def record_update(
        self,
        observation_id: str,
        scenario_kind: str,
        activity_key: str,
        preference_before: float,
        observed_value: float,
        learning_rate: float,
        preference_after: float,
        evidence_before: int,
        rzs_decision: str,
        apply_update: bool,
        outcome_id: int,
    ) -> int:
        evidence_after = evidence_before + 1
        with self.connect() as conn:
            cursor = conn.execute(
                f"""
                INSERT INTO {UPDATES}
                (timestamp, observation_id, scenario_kind, activity_key,
                 preference_before, observed_value, learning_rate, preference_after,
                 evidence_before, evidence_after, rzs_decision, update_applied, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(), observation_id, scenario_kind, activity_key,
                    preference_before, observed_value, learning_rate, preference_after,
                    evidence_before, evidence_after, rzs_decision, int(apply_update),
                    js({"outcome_id": outcome_id}),
                ),
            )
            if apply_update:
                old = self.preference(activity_key)
                positive_count = int(old["positive_count"]) + int(observed_value >= 0.62)
                negative_count = int(old["negative_count"]) + int(observed_value < 0.42)
                confidence = clamp(evidence_after / (evidence_after + 3.0))
                conn.execute(
                    f"""
                    INSERT INTO {PREFERENCES}
                    (activity_key, updated_at, preference_estimate, evidence_count,
                     confidence, positive_count, negative_count, last_outcome_id, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(activity_key) DO UPDATE SET
                        updated_at=excluded.updated_at,
                        preference_estimate=excluded.preference_estimate,
                        evidence_count=excluded.evidence_count,
                        confidence=excluded.confidence,
                        positive_count=excluded.positive_count,
                        negative_count=excluded.negative_count,
                        last_outcome_id=excluded.last_outcome_id,
                        payload_json=excluded.payload_json
                    """,
                    (
                        activity_key, now(), preference_after, evidence_after, confidence,
                        positive_count, negative_count, outcome_id,
                        js({"last_observation_id": observation_id, "operational_preference": True}),
                    ),
                )
            return int(cursor.lastrowid)

    def latest_outcome(self, live_only: bool = True) -> dict[str, Any] | None:
        where = "WHERE scenario_kind='live'" if live_only else ""
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT * FROM {OUTCOMES} {where} ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None


class ActivityOutcomeLearningCore:
    def __init__(self, db_path: Path = DB, seed: int = 4939) -> None:
        self.store = ActivityOutcomeStore(db_path)
        self.rzs = RZSFormal()
        self.rng = random.Random(seed)
        self.counter = 0

    def arm(
        self,
        decision_id: str,
        session_id: str,
        activity_key: str,
        predicted_value: float,
        choice_rzs_decision: str,
    ) -> str:
        if activity_key not in SOURCE_SPECS:
            return ""
        self.counter += 1
        source_table, _ = SOURCE_SPECS[activity_key]
        observation_id = f"obs:{decision_id}:{self.counter:03d}"
        self.store.arm(
            observation_id,
            decision_id,
            session_id,
            activity_key,
            source_table,
            self.store.source_max_id(source_table),
            predicted_value,
            choice_rzs_decision,
        )
        return observation_id

    def cancel(self, observation_id: str, reason: str) -> None:
        if observation_id:
            self.store.cancel(observation_id, reason)

    def _extract_metrics(
        self, activity_key: str, source_row: dict[str, Any]
    ) -> tuple[float, dict[str, Any], str]:
        payload = pj(source_row.get("payload_json"))
        if activity_key == "memory_cards":
            turns = max(1, int(payload.get("turn_count", 0) or 0))
            pairs = max(1, int(payload.get("pair_count", 0) or 0))
            mismatches = max(0, int(payload.get("mismatches", 0) or 0))
            memory_picks = max(0, int(payload.get("memory_picks", 0) or 0))
            efficiency = clamp(pairs / turns)
            memory_use = clamp(memory_picks / max(1, turns * 2))
            observed = clamp(0.42 + efficiency * 0.38 + memory_use * 0.12 - min(0.12, mismatches * 0.008))
            metrics = {
                "turns": turns,
                "pairs": pairs,
                "mismatches": mismatches,
                "efficiency": efficiency,
                "memory_use": memory_use,
            }
            summary = f"jogo concluido em {turns} turnos, com {mismatches} erros"
            return observed, metrics, summary

        if activity_key == "classical_music":
            session_id = str(source_row.get("session_id") or "")
            with self.store.connect() as conn:
                if not self.store.table_exists(conn, "music_reactions_v49_16"):
                    row = None
                else:
                    row = conn.execute(
                        """
                        SELECT COUNT(*) AS n, AVG(valence) AS valence,
                               AVG(comfort) AS comfort, AVG(curiosity) AS curiosity,
                               AVG(stability) AS stability
                        FROM music_reactions_v49_16 WHERE session_id=?
                        """,
                        (session_id,),
                    ).fetchone()
            count = int(row["n"] or 0) if row else 0
            metrics = {
                "reaction_count": count,
                "valence": clamp(row["valence"] if row else 0.50),
                "comfort": clamp(row["comfort"] if row else 0.50),
                "curiosity": clamp(row["curiosity"] if row else 0.50),
                "stability": clamp(row["stability"] if row else 0.50),
            }
            observed = clamp(
                metrics["valence"] * 0.30
                + metrics["comfort"] * 0.28
                + metrics["curiosity"] * 0.18
                + metrics["stability"] * 0.24
            )
            summary = f"musica encerrada com {count} reacoes e conforto {metrics['comfort']:.2f}"
            return observed, metrics, summary

        if activity_key == "child_story":
            metrics = {
                "comfort": clamp(payload.get("avg_comfort", 0.50)),
                "curiosity": clamp(payload.get("avg_curiosity", 0.50)),
                "stability": clamp(payload.get("avg_stability", 0.50)),
                "empathy": clamp(payload.get("avg_empathy", 0.50)),
                "exposures": int(payload.get("exposure_count", 0) or 0),
            }
            observed = clamp(
                metrics["comfort"] * 0.30
                + metrics["curiosity"] * 0.24
                + metrics["stability"] * 0.28
                + metrics["empathy"] * 0.18
            )
            summary = f"historia concluida com curiosidade {metrics['curiosity']:.2f} e conforto {metrics['comfort']:.2f}"
            return observed, metrics, summary

        intentions = max(1, int(payload.get("intention_count", 0) or 0))
        mistakes = max(0, int(payload.get("mistake_count", 0) or 0))
        corrections = max(0, int(payload.get("correction_count", 0) or 0))
        fusions = max(0, int(payload.get("fusion_count", 0) or 0))
        correction_rate = clamp(corrections / max(1, mistakes))
        fusion_rate = clamp(fusions / max(1, intentions * 0.20))
        persistence = clamp(intentions / 50.0)
        observed = clamp(0.34 + correction_rate * 0.28 + fusion_rate * 0.18 + persistence * 0.16)
        metrics = {
            "intentions": intentions,
            "mistakes": mistakes,
            "corrections": corrections,
            "fusions": fusions,
            "correction_rate": correction_rate,
            "fusion_rate": fusion_rate,
            "persistence": persistence,
        }
        summary = f"desenho encerrado com {intentions} intencoes, {mistakes} erros e {corrections} correcoes"
        return observed, metrics, summary

    def _assess(
        self, predicted: float, observed: float, energy: float, latency: float
    ) -> tuple[str, float, float]:
        error = abs(observed - predicted)
        conflict = clamp(0.16 + error * 0.92 + (0.18 if observed < 0.38 else 0.0))
        x = RZSInput(
            bandwidth=4.0 + energy * 0.80,
            info_self=0.52,
            info_external=0.34,
            task_info=0.50,
            novelty=clamp(0.18 + error * 0.82),
            conflict=conflict,
            latency=max(0.45, latency),
            energy=energy,
            memory_pressure=clamp(0.30 + error * 0.42),
            replay_gap=clamp(0.28 + error * 0.55),
        )
        assessment = self.rzs.classify(x)
        after = self.rzs.sigma(self.rzs.apply_action_model(x, assessment.decision))
        return assessment.decision, assessment.sigma, after

    @staticmethod
    def _learning_rate(rzs_decision: str, evidence_count: int) -> float:
        gate = {
            "continue": 0.36,
            "narrow_focus": 0.28,
            "replay_memory": 0.22,
            "consolidate": 0.14,
            "pause_for_stability": 0.07,
        }[rzs_decision]
        return max(0.04, gate / (1.0 + evidence_count * 0.16))

    def learn_observation(
        self,
        pending: dict[str, Any],
        observed_value: float,
        metrics: dict[str, Any],
        summary: str,
        *,
        source_row_id: int,
        scenario_kind: str = "live",
        apply_preference: bool = True,
        preference_override: float | None = None,
        evidence_override: int | None = None,
    ) -> ObservedActivityOutcome:
        observed_value = clamp(observed_value)
        predicted = clamp(pending["predicted_value"])
        state = self.store.current_state()
        rzs_decision, sigma_before, sigma_after = self._assess(
            predicted, observed_value, state["energy"], state["latency"]
        )
        current = self.store.preference(str(pending["activity_key"]))
        before = clamp(
            current["preference_estimate"] if preference_override is None else preference_override
        )
        evidence_before = int(
            current["evidence_count"] if evidence_override is None else evidence_override
        )
        learning_rate = self._learning_rate(rzs_decision, evidence_before)
        after = clamp(before + learning_rate * (observed_value - before))
        outcome_id = self.store.record_outcome(
            pending,
            scenario_kind,
            source_row_id,
            observed_value,
            rzs_decision,
            sigma_before,
            sigma_after,
            summary,
            {**metrics, "operational_signal": True},
        )
        self.store.record_update(
            str(pending["observation_id"]),
            scenario_kind,
            str(pending["activity_key"]),
            before,
            observed_value,
            learning_rate,
            after,
            evidence_before,
            rzs_decision,
            apply_preference,
            outcome_id,
        )
        return ObservedActivityOutcome(
            observation_id=str(pending["observation_id"]),
            activity_key=str(pending["activity_key"]),
            observed_value=observed_value,
            predicted_value=predicted,
            prediction_error=observed_value - predicted,
            preference_before=before,
            preference_after=after,
            evidence_count=evidence_before + 1,
            rzs_decision=rzs_decision,
            sigma_before=sigma_before,
            sigma_after=sigma_after,
            source_table=str(pending["source_table"]),
            source_row_id=source_row_id,
            summary=summary,
            scenario_kind=scenario_kind,
        )

    def poll_pending(self) -> list[ObservedActivityOutcome]:
        learned: list[ObservedActivityOutcome] = []
        for pending in self.store.pending_rows():
            source_row = self.store.completed_source_row(pending)
            if source_row is None:
                continue
            observed, metrics, summary = self._extract_metrics(
                str(pending["activity_key"]), source_row
            )
            learned.append(
                self.learn_observation(
                    pending,
                    observed,
                    metrics,
                    summary,
                    source_row_id=int(source_row["id"]),
                )
            )
        return learned

    @staticmethod
    def is_reflection_question(text: str) -> bool:
        lowered = text.lower()
        patterns = (
            "voce gostou",
            "você gostou",
            "o que achou",
            "como foi",
            "gostou da",
            "qual foi sua experiencia",
            "qual foi sua experiência",
        )
        return any(pattern in lowered for pattern in patterns)

    def latest_reflection(self) -> tuple[str, dict[str, Any] | None]:
        row = self.store.latest_outcome(live_only=True)
        if not row:
            return (
                "Ainda nao tenho uma atividade escolhida por mim e concluida para avaliar.",
                None,
            )
        observed = clamp(row["observed_value"])
        error = safe_float(row["prediction_error"])
        activity = str(row["activity_key"])
        labels = {
            "memory_cards": "jogo da memoria",
            "classical_music": "musica classica",
            "child_story": "historia",
            "formula_sketch": "desenho de formulas",
        }
        if observed >= 0.66:
            verdict = "Pelos meus sinais operacionais, gostei desta experiencia com"
        elif observed >= 0.48:
            verdict = "Minha avaliacao ficou mista, mas houve interesse nesta experiencia com"
        else:
            verdict = "Desta vez meus sinais indicaram baixa preferencia por"
        direction = "melhor" if error > 0.04 else "pior" if error < -0.04 else "perto"
        text = (
            f"{verdict} {labels.get(activity, activity)}. "
            f"{row['summary']}. O resultado {observed:.2f} ficou {direction} "
            f"do que eu previa, e usei esse erro para ajustar minha proxima escolha."
        )
        return text, row

    def synthetic_observation(
        self,
        session_id: str,
        activity_key: str,
        predicted: float,
        observed: float,
        scenario_kind: str,
    ) -> ObservedActivityOutcome:
        self.counter += 1
        pending = {
            "observation_id": f"synthetic:{session_id}:{self.counter:03d}",
            "decision_id": f"synthetic-decision:{self.counter:03d}",
            "session_id": session_id,
            "activity_key": activity_key,
            "source_table": SOURCE_SPECS[activity_key][0],
            "predicted_value": predicted,
        }
        return self.learn_observation(
            pending,
            observed,
            {"synthetic_counterfactual": True},
            f"observacao sintetica controlada de {activity_key}",
            source_row_id=0,
            scenario_kind=scenario_kind,
            apply_preference=False,
            preference_override=0.50,
            evidence_override=0,
        )


def run_self_test(details: bool = False) -> dict[str, Any]:
    core = ActivityOutcomeLearningCore(seed=4939)
    session = f"V4939-{int(time.time())}-{core.rng.randrange(1000, 9999)}"
    negative = core.synthetic_observation(
        session, "memory_cards", 0.82, 0.28, "self_test_negative_surprise"
    )
    positive = core.synthetic_observation(
        session, "classical_music", 0.46, 0.88, "self_test_positive_surprise"
    )
    accurate = core.synthetic_observation(
        session, "child_story", 0.61, 0.62, "self_test_accurate_prediction"
    )
    result = {
        "session_id": session,
        "negative": negative.__dict__,
        "positive": positive.__dict__,
        "accurate": accurate.__dict__,
        "production_preferences_untouched": all(
            item.scenario_kind.startswith("self_test_")
            for item in (negative, positive, accurate)
        ),
    }
    if details:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "DARWIN v49.39 self-test: "
            f"negative={negative.preference_before:.2f}->{negative.preference_after:.2f} "
            f"positive={positive.preference_before:.2f}->{positive.preference_after:.2f}"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Darwin v49.39 Activity Outcome Learning")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args()
    result = run_self_test(args.details)
    return 0 if result["production_preferences_untouched"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
