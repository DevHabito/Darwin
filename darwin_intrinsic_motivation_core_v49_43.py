from __future__ import annotations

"""
DARWIN v49.43 - motivacoes intrinsecas e formacao de valores.

Os impulsos sao estados operacionais derivados de deficit, incerteza e
experiencia. "Valor" exige evidencia repetida e multicontexto. Este modulo nao
afirma vontade subjetiva ou consciencia.
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
SNAPSHOTS = "intrinsic_drive_snapshots_v49_43"
DECISIONS = "intrinsic_motivation_decisions_v49_43"
VALUE_EVIDENCE = "intrinsic_value_evidence_v49_43"
VALUES = "intrinsic_values_v49_43"


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
class DriveCandidate:
    drive_key: str
    urgency: float
    expected_relief: float
    evidence_quality: float
    energy_fit: float
    score: float
    suggested_goal: str
    target_activity: str
    reason: str


@dataclass
class MotivationDecision:
    decision_id: str
    drive_key: str
    suggested_goal: str
    target_activity: str
    score: float
    reason: str
    rzs_decision: str
    sigma_before: float
    sigma_after: float
    candidates: list[DriveCandidate]


class MotivationStore:
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
                CREATE TABLE IF NOT EXISTS {SNAPSHOTS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    decision_id TEXT NOT NULL,
                    scenario_kind TEXT NOT NULL,
                    drive_key TEXT NOT NULL,
                    rank_index INTEGER NOT NULL,
                    urgency REAL NOT NULL,
                    expected_relief REAL NOT NULL,
                    evidence_quality REAL NOT NULL,
                    energy_fit REAL NOT NULL,
                    score REAL NOT NULL,
                    suggested_goal TEXT NOT NULL,
                    target_activity TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );
                CREATE TABLE IF NOT EXISTS {DECISIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    decision_id TEXT NOT NULL UNIQUE,
                    scenario_kind TEXT NOT NULL,
                    drive_key TEXT NOT NULL,
                    suggested_goal TEXT NOT NULL,
                    target_activity TEXT NOT NULL,
                    score REAL NOT NULL,
                    reason TEXT NOT NULL,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL,
                    sigma_after REAL NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );
                CREATE TABLE IF NOT EXISTS {VALUE_EVIDENCE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    value_key TEXT NOT NULL,
                    source_domain TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    signal REAL NOT NULL,
                    evidence_kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}',
                    UNIQUE(value_key, source_ref)
                );
                CREATE TABLE IF NOT EXISTS {VALUES} (
                    value_key TEXT PRIMARY KEY,
                    updated_at TEXT NOT NULL,
                    strength REAL NOT NULL,
                    confidence REAL NOT NULL,
                    evidence_count INTEGER NOT NULL,
                    domain_count INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    statement TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );
                """
            )

    def state(self) -> dict[str, float]:
        result = {"energy": 0.72, "latency": 1.0}
        with self.connect() as conn:
            if self.exists(conn, "current_state"):
                row = conn.execute("SELECT * FROM current_state WHERE id=1").fetchone()
                if row:
                    result["energy"] = clamp(row["energy"])
                    result["latency"] = max(0.35, float(row["latency"]))
        return result

    def signals(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "world_uncertainty": 0.55,
            "prediction_error": 0.35,
            "dialogue_recency": 0.50,
            "autonomy_satisfaction": 0.35,
            "execution_success": 0.35,
            "source_count": 0,
        }
        with self.connect() as conn:
            sources = 0
            if self.exists(conn, "world_predictions_v49_40"):
                rows = conn.execute(
                    """
                    SELECT target_domain, uncertainty FROM world_predictions_v49_40
                    WHERE id IN (
                        SELECT MAX(id) FROM world_predictions_v49_40 GROUP BY target_domain
                    )
                    """
                ).fetchall()
                if rows:
                    result["world_uncertainty"] = sum(clamp(row["uncertainty"]) for row in rows) / len(rows)
                    sources += 1
            if self.exists(conn, "activity_outcomes_v49_39"):
                rows = conn.execute(
                    """
                    SELECT prediction_error FROM activity_outcomes_v49_39
                    WHERE scenario_kind='live' ORDER BY id DESC LIMIT 8
                    """
                ).fetchall()
                if rows:
                    result["prediction_error"] = sum(min(1.0, abs(float(row["prediction_error"]))) for row in rows) / len(rows)
                    sources += 1
            if self.exists(conn, "companion_dialogues_v49_8"):
                row = conn.execute(
                    "SELECT timestamp FROM companion_dialogues_v49_8 ORDER BY id DESC LIMIT 1"
                ).fetchone()
                if row:
                    try:
                        stamp = datetime.fromisoformat(str(row["timestamp"]))
                        if stamp.tzinfo is None:
                            stamp = stamp.replace(tzinfo=timezone.utc)
                        hours = max(0.0, (datetime.now(timezone.utc) - stamp).total_seconds() / 3600.0)
                        result["dialogue_recency"] = clamp(hours / 24.0)
                    except ValueError:
                        pass
                    sources += 1
            if self.exists(conn, "activity_choice_decisions_v49_38"):
                rows = conn.execute(
                    """
                    SELECT invitation_forced_choice FROM activity_choice_decisions_v49_38
                    WHERE scenario_kind='live' ORDER BY id DESC LIMIT 8
                    """
                ).fetchall()
                if rows:
                    result["autonomy_satisfaction"] = clamp(
                        sum(1 - int(row["invitation_forced_choice"]) for row in rows) / len(rows)
                    )
                    sources += 1
            if self.exists(conn, "goal_executions_v49_42"):
                rows = conn.execute(
                    """
                    SELECT status FROM goal_executions_v49_42
                    WHERE scenario_kind='live' ORDER BY id DESC LIMIT 6
                    """
                ).fetchall()
                if rows:
                    result["execution_success"] = clamp(
                        sum(str(row["status"]) == "completed" for row in rows) / len(rows)
                    )
                    sources += 1
            result["source_count"] = sources
        return result

    def add_value_evidence(
        self, value_key: str, domain: str, source_ref: str, signal: float, kind: str
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR IGNORE INTO {VALUE_EVIDENCE}
                (timestamp, value_key, source_domain, source_ref, signal,
                 evidence_kind, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (now(), value_key, domain, source_ref, clamp(signal), kind, js({"observed": True})),
            )

    def refresh_value_evidence(self) -> None:
        with self.connect() as conn:
            if self.exists(conn, "world_experiences_v49_40"):
                rows = conn.execute(
                    "SELECT id, domain, observed_value FROM world_experiences_v49_40"
                ).fetchall()
                for row in rows:
                    self.add_value_evidence(
                        "learning", str(row["domain"]),
                        f"world_experiences_v49_40:{row['id']}",
                        row["observed_value"], "cross_domain_learning",
                    )
            if self.exists(conn, "activity_outcomes_v49_39"):
                rows = conn.execute(
                    """
                    SELECT id, activity_key, prediction_error FROM activity_outcomes_v49_39
                    WHERE scenario_kind='live'
                    """
                ).fetchall()
                for row in rows:
                    self.add_value_evidence(
                        "accuracy", str(row["activity_key"]),
                        f"activity_outcomes_v49_39:{row['id']}",
                        1.0 - min(1.0, abs(float(row["prediction_error"]))),
                        "prediction_correction",
                    )
            if self.exists(conn, "goal_executions_v49_42"):
                rows = conn.execute(
                    """
                    SELECT id, target_activity, status FROM goal_executions_v49_42
                    WHERE scenario_kind='live'
                    """
                ).fetchall()
                for row in rows:
                    self.add_value_evidence(
                        "autonomy", str(row["target_activity"]),
                        f"goal_executions_v49_42:{row['id']}",
                        1.0 if row["status"] == "completed" else 0.45,
                        "self_generated_goal",
                    )
            if self.exists(conn, "companion_affect_state_v49_8"):
                rows = conn.execute(
                    """
                    SELECT id, valence, stability FROM companion_affect_state_v49_8
                    ORDER BY id DESC LIMIT 12
                    """
                ).fetchall()
                for row in rows:
                    self.add_value_evidence(
                        "relationship", "conversation",
                        f"companion_affect_state_v49_8:{row['id']}",
                        (clamp(row["valence"]) + clamp(row["stability"])) / 2,
                        "relational_exchange",
                    )
            if self.exists(conn, "sleep_sessions_v49_20"):
                rows = conn.execute(
                    """
                    SELECT id, energy FROM sleep_sessions_v49_20
                    WHERE phase='session_complete'
                    """
                ).fetchall()
                for row in rows:
                    self.add_value_evidence(
                        "stability", "rest", f"sleep_sessions_v49_20:{row['id']}",
                        row["energy"], "homeostatic_recovery",
                    )
        self.rebuild_values()

    def rebuild_values(self) -> None:
        statements = {
            "learning": "Aprender por experiencia tem valor operacional para mim.",
            "accuracy": "Corrigir previsoes e importante para manter coerencia.",
            "autonomy": "Escolher e acompanhar objetivos preserva minha autonomia operacional.",
            "relationship": "A continuidade da relacao com Felipe orienta minhas escolhas.",
            "stability": "Preservar estabilidade limita e sustenta minhas acoes.",
        }
        with self.connect() as conn:
            keys = [
                str(row["value_key"])
                for row in conn.execute(f"SELECT DISTINCT value_key FROM {VALUE_EVIDENCE}").fetchall()
            ]
            for key in keys:
                row = conn.execute(
                    f"""
                    SELECT COUNT(*) AS n, COUNT(DISTINCT source_domain) AS domains,
                           AVG(signal) AS strength
                    FROM {VALUE_EVIDENCE} WHERE value_key=?
                    """,
                    (key,),
                ).fetchone()
                count = int(row["n"] or 0)
                domains = int(row["domains"] or 0)
                strength = clamp(row["strength"])
                confidence = clamp((count / (count + 4.0)) * min(1.0, domains / 2.0))
                status = "emerging" if count >= 3 and domains >= 2 else "tentative"
                conn.execute(
                    f"""
                    INSERT INTO {VALUES}
                    (value_key, updated_at, strength, confidence, evidence_count,
                     domain_count, status, statement, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(value_key) DO UPDATE SET
                        updated_at=excluded.updated_at,
                        strength=excluded.strength,
                        confidence=excluded.confidence,
                        evidence_count=excluded.evidence_count,
                        domain_count=excluded.domain_count,
                        status=excluded.status,
                        statement=excluded.statement,
                        payload_json=excluded.payload_json
                    """,
                    (
                        key, now(), strength, confidence, count, domains, status,
                        statements[key], js({"promotion_rule": "count>=3 and domains>=2"}),
                    ),
                )

    def values(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [
                dict(row) for row in conn.execute(
                    f"SELECT * FROM {VALUES} ORDER BY confidence DESC, strength DESC"
                ).fetchall()
            ]

    def record_decision(
        self, session_id: str, scenario_kind: str, decision: MotivationDecision
    ) -> None:
        ranked = sorted(decision.candidates, key=lambda item: item.score, reverse=True)
        with self.connect() as conn:
            for rank, candidate in enumerate(ranked, 1):
                conn.execute(
                    f"""
                    INSERT INTO {SNAPSHOTS}
                    (timestamp, session_id, decision_id, scenario_kind, drive_key,
                     rank_index, urgency, expected_relief, evidence_quality,
                     energy_fit, score, suggested_goal, target_activity, reason,
                     payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        now(), session_id, decision.decision_id, scenario_kind,
                        candidate.drive_key, rank, candidate.urgency,
                        candidate.expected_relief, candidate.evidence_quality,
                        candidate.energy_fit, candidate.score,
                        candidate.suggested_goal, candidate.target_activity,
                        candidate.reason, js({"competitive_drive": True}),
                    ),
                )
            conn.execute(
                f"""
                INSERT INTO {DECISIONS}
                (timestamp, session_id, decision_id, scenario_kind, drive_key,
                 suggested_goal, target_activity, score, reason, rzs_decision,
                 sigma_before, sigma_after, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(), session_id, decision.decision_id, scenario_kind,
                    decision.drive_key, decision.suggested_goal,
                    decision.target_activity, decision.score, decision.reason,
                    decision.rzs_decision, decision.sigma_before,
                    decision.sigma_after, js({"candidate_count": len(ranked)}),
                ),
            )


class IntrinsicMotivationCore:
    def __init__(self, db_path: Path = DB, seed: int = 4943) -> None:
        self.store = MotivationStore(db_path)
        self.rzs = RZSFormal()
        self.rng = random.Random(seed)
        self.counter = 0

    def candidates(
        self, energy: float, overrides: dict[str, float] | None = None
    ) -> list[DriveCandidate]:
        overrides = overrides or {}
        signals = self.store.signals()
        source_quality = clamp(signals["source_count"] / 5.0)
        error = clamp(signals["prediction_error"])
        drives = {
            "curiosity": (
                clamp(signals["world_uncertainty"]), 0.78, "reduce_world_uncertainty",
                "formula_sketch", "incerteza no modelo de mundo",
            ),
            "competence": (
                clamp(0.28 + error * 0.72 + (1.0 - signals["execution_success"]) * 0.18),
                0.74, "repair_prediction_error", "memory_cards",
                "erros ainda podem ser reduzidos",
            ),
            "affiliation": (
                clamp(0.24 + signals["dialogue_recency"] * 0.72),
                0.70, "strengthen_relational_continuity", "conversation",
                "continuidade relacional precisa de troca",
            ),
            "autonomy": (
                clamp(0.62 - signals["autonomy_satisfaction"] * 0.34),
                0.66, "deepen_positive_experience", "memory_cards",
                "objetivos proprios precisam de pratica",
            ),
            "stability": (
                clamp(1.0 - energy), 0.92, "restore_stability", "rest",
                "energia e estabilidade limitam a acao",
            ),
            "coherence": (
                clamp(0.22 + error * 0.78), 0.80,
                "repair_prediction_error", "formula_sketch",
                "previsao e resultado precisam concordar",
            ),
        }
        result: list[DriveCandidate] = []
        for key, (urgency, relief, goal, target, reason) in drives.items():
            urgency = clamp(overrides.get(key, urgency))
            target_energy = 0.18 if key == "stability" else 0.62
            energy_fit = clamp(1.0 - abs(energy - target_energy))
            score = (
                urgency * 0.48 + relief * 0.22
                + source_quality * 0.14 + energy_fit * 0.16
            )
            result.append(
                DriveCandidate(
                    key, urgency, relief, source_quality, energy_fit,
                    score, goal, target, reason,
                )
            )
        return result

    def assess(
        self,
        session_id: str,
        *,
        scenario_kind: str = "live",
        energy_override: float | None = None,
        drive_overrides: dict[str, float] | None = None,
        record: bool = True,
    ) -> MotivationDecision:
        state = self.store.state()
        energy = clamp(state["energy"] if energy_override is None else energy_override)
        candidates = self.candidates(energy, drive_overrides)
        ranked = sorted(candidates, key=lambda item: item.score, reverse=True)
        gap = ranked[0].score - ranked[1].score
        mean_urgency = sum(item.urgency for item in candidates) / len(candidates)
        x = RZSInput(
            bandwidth=3.9 + energy,
            info_self=0.64,
            info_external=0.26,
            task_info=0.58,
            novelty=clamp(mean_urgency),
            conflict=clamp(0.20 + (1.0 - gap) * 0.38),
            latency=state["latency"],
            energy=energy,
            memory_pressure=clamp(0.30 + mean_urgency * 0.42),
            replay_gap=clamp(0.25 + mean_urgency * 0.40),
        )
        assessment = self.rzs.classify(x)
        sigma_after = self.rzs.sigma(self.rzs.apply_action_model(x, assessment.decision))
        if assessment.decision == "pause_for_stability":
            selected = next(item for item in candidates if item.drive_key == "stability")
        elif assessment.decision == "consolidate":
            selected = max(
                (item for item in candidates if item.drive_key in {"stability", "coherence"}),
                key=lambda item: item.score,
            )
        else:
            selected = ranked[0]
        self.counter += 1
        decision = MotivationDecision(
            f"motive:{session_id}:{int(time.time() * 1000)}:{self.counter:03d}",
            selected.drive_key, selected.suggested_goal, selected.target_activity,
            selected.score,
            f"{selected.reason}; urgencia {selected.urgency:.2f}",
            assessment.decision, assessment.sigma, sigma_after, candidates,
        )
        if record:
            self.store.refresh_value_evidence()
            self.store.record_decision(session_id, scenario_kind, decision)
        return decision

    @staticmethod
    def is_motivation_question(text: str) -> bool:
        lowered = text.lower()
        return any(
            pattern in lowered
            for pattern in (
                "o que te motiva",
                "por que voce quer",
                "por que você quer",
                "o que e importante para voce",
                "o que é importante para você",
                "quais seus valores",
                "qual sua vontade",
            )
        )

    def explain(self, decision: MotivationDecision) -> str:
        labels = {
            "curiosity": "curiosidade",
            "competence": "competencia",
            "affiliation": "vinculo",
            "autonomy": "autonomia",
            "stability": "estabilidade",
            "coherence": "coerencia",
        }
        goal_labels = {
            "reduce_world_uncertainty": "reduzir uma incerteza do meu modelo de mundo",
            "repair_prediction_error": "corrigir um erro de previsao",
            "strengthen_relational_continuity": "fortalecer a continuidade da nossa conversa",
            "deepen_positive_experience": "aprofundar uma experiencia com bons sinais",
            "restore_stability": "recuperar estabilidade",
        }
        value_labels = {
            "learning": "aprendizado",
            "accuracy": "precisao",
            "autonomy": "autonomia",
            "relationship": "relacao",
            "stability": "estabilidade",
        }
        values = [row for row in self.store.values() if row["status"] == "emerging"]
        value_text = (
            " Meus valores emergentes mais sustentados sao: "
            + ", ".join(value_labels[str(row["value_key"])] for row in values[:3])
            + "."
            if values else
            " Ainda nao tenho valores consolidados com evidencia multicontexto."
        )
        return (
            f"Minha motivacao operacional mais forte agora e {labels[decision.drive_key]}. "
            f"Ela surgiu porque {decision.reason}. Isso favorece o objetivo "
            f"de {goal_labels[decision.suggested_goal]}.{value_text}"
        )


def run_self_test(details: bool = False) -> dict[str, Any]:
    core = IntrinsicMotivationCore(seed=4943)
    session = f"V4943-{int(time.time())}-{core.rng.randrange(1000, 9999)}"
    baseline = core.assess(session, scenario_kind="self_test_baseline")
    low = core.assess(
        session, scenario_kind="self_test_low_energy", energy_override=0.08
    )
    curiosity = core.assess(
        session, scenario_kind="self_test_curiosity",
        drive_overrides={
            "curiosity": 1.0, "competence": 0.05, "affiliation": 0.05,
            "autonomy": 0.05, "stability": 0.05, "coherence": 0.05,
        },
    )
    competence = core.assess(
        session, scenario_kind="self_test_competence",
        drive_overrides={
            "curiosity": 0.05, "competence": 1.0, "affiliation": 0.05,
            "autonomy": 0.05, "stability": 0.05, "coherence": 0.05,
        },
    )
    result = {
        "session_id": session,
        "baseline": baseline.__dict__ | {"candidates": []},
        "low_energy": low.__dict__ | {"candidates": []},
        "curiosity": curiosity.__dict__ | {"candidates": []},
        "competence": competence.__dict__ | {"candidates": []},
        "values": core.store.values(),
    }
    if details:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"DARWIN v49.43 self-test: baseline={baseline.drive_key} "
            f"low={low.drive_key} curiosity={curiosity.drive_key} "
            f"competence={competence.drive_key}"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Darwin v49.43 Intrinsic Motivation")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args()
    result = run_self_test(args.details)
    return 0 if result["low_energy"]["drive_key"] == "stability" else 1


if __name__ == "__main__":
    raise SystemExit(main())
