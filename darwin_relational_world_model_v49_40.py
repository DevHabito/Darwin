from __future__ import annotations

"""DARWIN v49.40 - modelo de mundo relacional e transferencia entre dominios."""

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
EXPERIENCES = "world_experiences_v49_40"
RELATIONS = "world_relations_v49_40"
PREDICTIONS = "world_predictions_v49_40"
TRANSFERS = "world_transfer_tests_v49_40"

FEATURE_NAMES = (
    "memory",
    "symbolic",
    "auditory",
    "narrative",
    "creative",
    "social",
    "calm",
    "cognitive_load",
)

ACTIVITY_FEATURES = {
    "memory_cards": {
        "memory": 1.00, "symbolic": 0.62, "auditory": 0.05, "narrative": 0.08,
        "creative": 0.22, "social": 0.18, "calm": 0.46, "cognitive_load": 0.72,
    },
    "classical_music": {
        "memory": 0.34, "symbolic": 0.18, "auditory": 1.00, "narrative": 0.22,
        "creative": 0.48, "social": 0.14, "calm": 0.92, "cognitive_load": 0.24,
    },
    "child_story": {
        "memory": 0.48, "symbolic": 0.38, "auditory": 0.42, "narrative": 1.00,
        "creative": 0.58, "social": 0.54, "calm": 0.82, "cognitive_load": 0.36,
    },
    "formula_sketch": {
        "memory": 0.58, "symbolic": 1.00, "auditory": 0.04, "narrative": 0.16,
        "creative": 0.96, "social": 0.12, "calm": 0.38, "cognitive_load": 0.82,
    },
    "conversation": {
        "memory": 0.58, "symbolic": 0.54, "auditory": 0.76, "narrative": 0.62,
        "creative": 0.52, "social": 1.00, "calm": 0.72, "cognitive_load": 0.46,
    },
    "rest": {
        "memory": 0.18, "symbolic": 0.05, "auditory": 0.06, "narrative": 0.05,
        "creative": 0.08, "social": 0.04, "calm": 1.00, "cognitive_load": 0.04,
    },
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clamp(value: Any, low: float = 0.0, high: float = 1.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = low
    return max(low, min(high, number))


def pj(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def js(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


@dataclass
class WorldExperience:
    experience_id: str
    domain: str
    features: dict[str, float]
    observed_value: float
    source_table: str
    source_row_id: int


@dataclass
class WorldPrediction:
    prediction_id: str
    target_domain: str
    predicted_value: float
    confidence: float
    uncertainty: float
    contributors: list[str]
    rzs_decision: str
    sigma_before: float
    sigma_after: float


class WorldModelStore:
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
                CREATE TABLE IF NOT EXISTS {EXPERIENCES} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    experience_id TEXT NOT NULL UNIQUE,
                    domain TEXT NOT NULL,
                    features_json TEXT NOT NULL,
                    observed_value REAL NOT NULL,
                    source_table TEXT NOT NULL,
                    source_row_id INTEGER NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );
                CREATE TABLE IF NOT EXISTS {RELATIONS} (
                    feature_key TEXT PRIMARY KEY,
                    updated_at TEXT NOT NULL,
                    target_key TEXT NOT NULL,
                    relation_weight REAL NOT NULL,
                    evidence_count INTEGER NOT NULL,
                    confidence REAL NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );
                CREATE TABLE IF NOT EXISTS {PREDICTIONS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    prediction_id TEXT NOT NULL UNIQUE,
                    scenario_kind TEXT NOT NULL,
                    target_domain TEXT NOT NULL,
                    features_json TEXT NOT NULL,
                    predicted_value REAL NOT NULL,
                    confidence REAL NOT NULL,
                    uncertainty REAL NOT NULL,
                    contributors_json TEXT NOT NULL,
                    rzs_decision TEXT NOT NULL,
                    sigma_before REAL NOT NULL,
                    sigma_after REAL NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );
                CREATE TABLE IF NOT EXISTS {TRANSFERS} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    transfer_id TEXT NOT NULL UNIQUE,
                    target_domain TEXT NOT NULL,
                    training_domains_json TEXT NOT NULL,
                    predicted_value REAL NOT NULL,
                    observed_value REAL NOT NULL,
                    model_error REAL NOT NULL,
                    baseline_error REAL NOT NULL,
                    transfer_gain REAL NOT NULL,
                    counterfactual_value REAL NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{{}}'
                );
                """
            )

    def upsert_experience(self, experience: WorldExperience) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {EXPERIENCES}
                (timestamp, experience_id, domain, features_json, observed_value,
                 source_table, source_row_id, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(experience_id) DO UPDATE SET
                    timestamp=excluded.timestamp,
                    features_json=excluded.features_json,
                    observed_value=excluded.observed_value,
                    payload_json=excluded.payload_json
                """,
                (
                    now(), experience.experience_id, experience.domain,
                    js(experience.features), experience.observed_value,
                    experience.source_table, experience.source_row_id,
                    js({"normalized_world_experience": True}),
                ),
            )

    def experiences(self) -> list[WorldExperience]:
        with self.connect() as conn:
            rows = conn.execute(f"SELECT * FROM {EXPERIENCES} ORDER BY id").fetchall()
        return [
            WorldExperience(
                str(row["experience_id"]),
                str(row["domain"]),
                {key: clamp(value) for key, value in pj(row["features_json"]).items()},
                clamp(row["observed_value"]),
                str(row["source_table"]),
                int(row["source_row_id"]),
            )
            for row in rows
        ]

    def replace_relations(self, relations: dict[str, tuple[float, int, float]]) -> None:
        with self.connect() as conn:
            for key, (weight, count, confidence) in relations.items():
                conn.execute(
                    f"""
                    INSERT INTO {RELATIONS}
                    (feature_key, updated_at, target_key, relation_weight,
                     evidence_count, confidence, payload_json)
                    VALUES (?, ?, 'operational_value', ?, ?, ?, ?)
                    ON CONFLICT(feature_key) DO UPDATE SET
                        updated_at=excluded.updated_at,
                        relation_weight=excluded.relation_weight,
                        evidence_count=excluded.evidence_count,
                        confidence=excluded.confidence,
                        payload_json=excluded.payload_json
                    """,
                    (key, now(), weight, count, confidence, js({"method": "centered_slope"})),
                )

    def record_prediction(
        self, prediction: WorldPrediction, features: dict[str, float], scenario_kind: str
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {PREDICTIONS}
                (timestamp, prediction_id, scenario_kind, target_domain, features_json,
                 predicted_value, confidence, uncertainty, contributors_json,
                 rzs_decision, sigma_before, sigma_after, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(), prediction.prediction_id, scenario_kind, prediction.target_domain,
                    js(features), prediction.predicted_value, prediction.confidence,
                    prediction.uncertainty, js(prediction.contributors),
                    prediction.rzs_decision, prediction.sigma_before, prediction.sigma_after,
                    js({"cross_domain": True}),
                ),
            )

    def record_transfer(
        self,
        transfer_id: str,
        target: str,
        training_domains: list[str],
        predicted: float,
        observed: float,
        baseline_error: float,
        counterfactual: float,
    ) -> None:
        model_error = abs(predicted - observed)
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {TRANSFERS}
                (timestamp, transfer_id, target_domain, training_domains_json,
                 predicted_value, observed_value, model_error, baseline_error,
                 transfer_gain, counterfactual_value, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now(), transfer_id, target, js(training_domains), predicted, observed,
                    model_error, baseline_error, baseline_error - model_error,
                    counterfactual, js({"held_out_target": True}),
                ),
            )


class RelationalWorldModel:
    def __init__(self, db_path: Path = DB, seed: int = 4940) -> None:
        self.store = WorldModelStore(db_path)
        self.rzs = RZSFormal()
        self.rng = random.Random(seed)
        self.counter = 0

    @staticmethod
    def features_for(activity_key: str, energy: float = 0.72) -> dict[str, float]:
        features = dict(ACTIVITY_FEATURES[activity_key])
        features["cognitive_load"] = clamp(
            features["cognitive_load"] + max(0.0, 0.50 - energy) * 0.25
        )
        return features

    def _historical_rows(self) -> list[WorldExperience]:
        found: list[WorldExperience] = []
        with self.store.connect() as conn:
            if self.store.exists(conn, "memory_card_games_v49_13"):
                row = conn.execute(
                    """
                    SELECT id, payload_json FROM memory_card_games_v49_13
                    WHERE phase='game_complete' ORDER BY id DESC LIMIT 1
                    """
                ).fetchone()
                if row:
                    p = pj(row["payload_json"])
                    turns = max(1, int(p.get("turn_count", 1) or 1))
                    pairs = max(1, int(p.get("pair_count", 1) or 1))
                    mistakes = max(0, int(p.get("mismatches", 0) or 0))
                    value = clamp(0.45 + pairs / turns * 0.40 - min(0.15, mistakes * 0.008))
                    found.append(WorldExperience(
                        f"memory_card_games_v49_13:{row['id']}", "memory_cards",
                        self.features_for("memory_cards"), value,
                        "memory_card_games_v49_13", int(row["id"]),
                    ))
            if self.store.exists(conn, "music_reactions_v49_16"):
                row = conn.execute(
                    """
                    SELECT MAX(id) AS id, AVG(valence) AS valence, AVG(comfort) AS comfort,
                           AVG(curiosity) AS curiosity, AVG(stability) AS stability
                    FROM music_reactions_v49_16
                    """
                ).fetchone()
                if row and row["id"]:
                    value = clamp(
                        clamp(row["valence"]) * 0.30 + clamp(row["comfort"]) * 0.28
                        + clamp(row["curiosity"]) * 0.18 + clamp(row["stability"]) * 0.24
                    )
                    found.append(WorldExperience(
                        f"music_reactions_v49_16:{row['id']}", "classical_music",
                        self.features_for("classical_music"), value,
                        "music_reactions_v49_16", int(row["id"]),
                    ))
            if self.store.exists(conn, "story_nursery_sessions_v49_29"):
                row = conn.execute(
                    """
                    SELECT id, payload_json FROM story_nursery_sessions_v49_29
                    WHERE phase='session_complete' ORDER BY id DESC LIMIT 1
                    """
                ).fetchone()
                if row:
                    p = pj(row["payload_json"])
                    value = clamp(
                        clamp(p.get("avg_comfort", 0.5)) * 0.34
                        + clamp(p.get("avg_curiosity", 0.5)) * 0.26
                        + clamp(p.get("avg_stability", 0.5)) * 0.40
                    )
                    found.append(WorldExperience(
                        f"story_nursery_sessions_v49_29:{row['id']}", "child_story",
                        self.features_for("child_story"), value,
                        "story_nursery_sessions_v49_29", int(row["id"]),
                    ))
            if self.store.exists(conn, "formula_sketch_sessions_v49_28"):
                row = conn.execute(
                    """
                    SELECT id, payload_json FROM formula_sketch_sessions_v49_28
                    WHERE phase='sketch_complete' ORDER BY id DESC LIMIT 1
                    """
                ).fetchone()
                if row:
                    p = pj(row["payload_json"])
                    mistakes = max(1, int(p.get("mistake_count", 1) or 1))
                    corrections = int(p.get("correction_count", 0) or 0)
                    fusions = int(p.get("fusion_count", 0) or 0)
                    value = clamp(0.40 + corrections / mistakes * 0.28 + min(0.18, fusions * 0.012))
                    found.append(WorldExperience(
                        f"formula_sketch_sessions_v49_28:{row['id']}", "formula_sketch",
                        self.features_for("formula_sketch"), value,
                        "formula_sketch_sessions_v49_28", int(row["id"]),
                    ))
            if self.store.exists(conn, "companion_affect_state_v49_8"):
                row = conn.execute(
                    """
                    SELECT MAX(id) AS id, AVG(valence) AS valence, AVG(stability) AS stability
                    FROM (SELECT id, valence, stability FROM companion_affect_state_v49_8
                          ORDER BY id DESC LIMIT 30)
                    """
                ).fetchone()
                if row and row["id"]:
                    value = clamp(clamp(row["valence"]) * 0.48 + clamp(row["stability"]) * 0.52)
                    found.append(WorldExperience(
                        f"companion_affect_state_v49_8:{row['id']}", "conversation",
                        self.features_for("conversation"), value,
                        "companion_affect_state_v49_8", int(row["id"]),
                    ))
            if self.store.exists(conn, "sleep_sessions_v49_20"):
                row = conn.execute(
                    """
                    SELECT MAX(id) AS id, AVG(energy) AS energy FROM sleep_sessions_v49_20
                    WHERE phase='session_complete'
                    """
                ).fetchone()
                if row and row["id"]:
                    value = clamp(0.62 + clamp(row["energy"]) * 0.28)
                    found.append(WorldExperience(
                        f"sleep_sessions_v49_20:{row['id']}", "rest",
                        self.features_for("rest"), value,
                        "sleep_sessions_v49_20", int(row["id"]),
                    ))
        return found

    def refresh_historical(self) -> int:
        for experience in self._historical_rows():
            self.store.upsert_experience(experience)
        self.fit_relations()
        return len(self.store.experiences())

    def fit_relations(self) -> dict[str, tuple[float, int, float]]:
        experiences = self.store.experiences()
        if len(experiences) < 2:
            return {}
        mean_y = sum(item.observed_value for item in experiences) / len(experiences)
        relations: dict[str, tuple[float, int, float]] = {}
        for feature in FEATURE_NAMES:
            mean_x = sum(item.features.get(feature, 0.0) for item in experiences) / len(experiences)
            numerator = sum(
                (item.features.get(feature, 0.0) - mean_x) * (item.observed_value - mean_y)
                for item in experiences
            )
            denominator = sum(
                (item.features.get(feature, 0.0) - mean_x) ** 2 for item in experiences
            )
            slope = max(-1.0, min(1.0, numerator / max(denominator, 1e-9)))
            confidence = clamp(len(experiences) / 12.0)
            relations[feature] = (slope, len(experiences), confidence)
        self.store.replace_relations(relations)
        return relations

    @staticmethod
    def similarity(a: dict[str, float], b: dict[str, float]) -> float:
        distance = sum(abs(a.get(key, 0.0) - b.get(key, 0.0)) for key in FEATURE_NAMES)
        return clamp(1.0 - distance / len(FEATURE_NAMES))

    def predict_from(
        self,
        target_domain: str,
        features: dict[str, float],
        experiences: list[WorldExperience],
        *,
        exclude_domain: str = "",
        scenario_kind: str = "live",
        record: bool = True,
    ) -> WorldPrediction:
        pool = [item for item in experiences if item.domain != exclude_domain]
        ranked = sorted(
            ((self.similarity(features, item.features), item) for item in pool),
            key=lambda pair: pair[0],
            reverse=True,
        )[:4]
        if ranked:
            total = sum(max(0.05, similarity) for similarity, _ in ranked)
            predicted = sum(
                max(0.05, similarity) * item.observed_value for similarity, item in ranked
            ) / total
            confidence = clamp(
                (sum(similarity for similarity, _ in ranked) / len(ranked))
                * min(1.0, len(pool) / 5.0)
            )
            contributors = [item.domain for _, item in ranked]
        else:
            predicted, confidence, contributors = 0.50, 0.0, []
        uncertainty = 1.0 - confidence
        state_energy = 0.72
        x = RZSInput(
            bandwidth=4.1 + state_energy * 0.6,
            info_self=0.40,
            info_external=0.36,
            task_info=0.56,
            novelty=clamp(0.28 + uncertainty * 0.55),
            conflict=clamp(0.16 + uncertainty * 0.38),
            latency=1.0,
            energy=state_energy,
            memory_pressure=clamp(0.30 + uncertainty * 0.50),
            replay_gap=clamp(0.25 + uncertainty * 0.52),
        )
        assessment = self.rzs.classify(x)
        sigma_after = self.rzs.sigma(self.rzs.apply_action_model(x, assessment.decision))
        self.counter += 1
        prediction = WorldPrediction(
            f"world:{int(time.time() * 1000)}:{self.counter:04d}",
            target_domain, clamp(predicted), confidence, uncertainty,
            contributors, assessment.decision, assessment.sigma, sigma_after,
        )
        if record:
            self.store.record_prediction(prediction, features, scenario_kind)
        return prediction

    def predict_activity(self, activity_key: str, energy: float = 0.72) -> WorldPrediction:
        experiences = self.store.experiences()
        return self.predict_from(
            activity_key,
            self.features_for(activity_key, energy),
            experiences,
            scenario_kind="activity_choice",
        )

    def run_transfer_test(self) -> dict[str, Any]:
        training = [
            WorldExperience("control:music", "classical_music", self.features_for("classical_music"), 0.86, "controlled", 0),
            WorldExperience("control:story", "child_story", self.features_for("child_story"), 0.78, "controlled", 0),
            WorldExperience("control:memory", "memory_cards", self.features_for("memory_cards"), 0.62, "controlled", 0),
            WorldExperience("control:formula", "formula_sketch", self.features_for("formula_sketch"), 0.54, "controlled", 0),
        ]
        target_features = self.features_for("conversation")
        observed = 0.79
        prediction = self.predict_from(
            "conversation", target_features, training,
            exclude_domain="conversation", scenario_kind="self_test_transfer",
        )
        baseline = sum(item.observed_value for item in training) / len(training)
        baseline_error = abs(baseline - observed)
        counterfactual_features = dict(target_features)
        counterfactual_features.update(
            {
                "calm": 0.02,
                "cognitive_load": 1.00,
                "social": 0.05,
                "auditory": 0.05,
                "narrative": 0.05,
                "creative": 0.10,
            }
        )
        counterfactual = self.predict_from(
            "conversation_high_load", counterfactual_features, training,
            scenario_kind="self_test_counterfactual",
        )
        transfer_id = f"transfer:{int(time.time())}:{self.rng.randrange(1000, 9999)}"
        self.store.record_transfer(
            transfer_id,
            "conversation",
            [item.domain for item in training],
            prediction.predicted_value,
            observed,
            baseline_error,
            counterfactual.predicted_value,
        )
        return {
            "transfer_id": transfer_id,
            "predicted": prediction.predicted_value,
            "observed": observed,
            "model_error": abs(prediction.predicted_value - observed),
            "baseline_error": baseline_error,
            "counterfactual": counterfactual.predicted_value,
            "contributors": prediction.contributors,
        }


def run_self_test(details: bool = False) -> dict[str, Any]:
    core = RelationalWorldModel(seed=4940)
    experience_count = core.refresh_historical()
    transfer = core.run_transfer_test()
    result = {"experience_count": experience_count, "transfer": transfer}
    if details:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"DARWIN v49.40 self-test: experiences={experience_count} "
            f"error={transfer['model_error']:.3f} baseline={transfer['baseline_error']:.3f}"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Darwin v49.40 Relational World Model")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args()
    result = run_self_test(args.details)
    return 0 if result["experience_count"] >= 4 else 1


if __name__ == "__main__":
    raise SystemExit(main())
