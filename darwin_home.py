
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class DarwinCoreState:
    sigma: float = 1.0
    energy: float = 1.0
    info_self: float = 0.0
    info_external: float = 0.0
    latency: float = 1.0
    pain_signal: float = 0.0
    wellbeing_signal: float = 0.0


@dataclass
class DarwinPolicy:
    threat_sensitivity: float = 1.0
    fork_sensitivity: float = 1.0
    win_sensitivity: float = 1.0
    explore_bias: float = 0.70
    center_bias: float = 0.90
    corner_bias: float = 0.80
    line_bias: float = 0.70


class DarwinHome:
    """
    Camada de persistência local do Darwin.
    Usa SQLite como fonte principal de verdade.
    """

    def __init__(self, root: str = "darwin_home") -> None:
        self.root = Path(root)
        self.db_path = self.root / "darwin.db"
        self.logs_dir = self.root / "logs"
        self.snapshots_dir = self.root / "snapshots"
        self.exports_dir = self.root / "exports"
        self.config_path = self.root / "config.json"

        self.root.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        self.snapshots_dir.mkdir(exist_ok=True)
        self.exports_dir.mkdir(exist_ok=True)

        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def bootstrap(self) -> None:
        cur = self.conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS self_model (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            name TEXT NOT NULL,
            version TEXT NOT NULL,
            mission TEXT NOT NULL,
            core_principles TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS current_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            timestamp TEXT NOT NULL,
            sigma REAL NOT NULL,
            energy REAL NOT NULL,
            info_self REAL NOT NULL,
            info_external REAL NOT NULL,
            latency REAL NOT NULL,
            pain_signal REAL NOT NULL,
            wellbeing_signal REAL NOT NULL
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS state_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            sigma REAL NOT NULL,
            energy REAL NOT NULL,
            info_self REAL NOT NULL,
            info_external REAL NOT NULL,
            latency REAL NOT NULL,
            pain_signal REAL NOT NULL,
            wellbeing_signal REAL NOT NULL
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS policy (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            updated_at TEXT NOT NULL,
            threat_sensitivity REAL NOT NULL,
            fork_sensitivity REAL NOT NULL,
            win_sensitivity REAL NOT NULL,
            explore_bias REAL NOT NULL,
            center_bias REAL NOT NULL,
            corner_bias REAL NOT NULL,
            line_bias REAL NOT NULL
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            module TEXT NOT NULL,
            context TEXT NOT NULL,
            action_taken TEXT NOT NULL,
            outcome TEXT NOT NULL,
            lesson TEXT NOT NULL,
            sigma_before REAL NOT NULL,
            sigma_after REAL NOT NULL
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS semantic_memory (
            key TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            confidence REAL NOT NULL,
            source TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS dangerous_patterns (
            pattern_key TEXT NOT NULL,
            move INTEGER NOT NULL,
            risk_weight REAL NOT NULL,
            times_triggered INTEGER NOT NULL,
            last_seen TEXT NOT NULL,
            PRIMARY KEY (pattern_key, move)
        )
        """)

        self.conn.commit()
        self._ensure_defaults()

    def _ensure_defaults(self) -> None:
        cur = self.conn.cursor()

        row = cur.execute("SELECT id FROM self_model WHERE id = 1").fetchone()
        if row is None:
            cur.execute("""
            INSERT INTO self_model (
                id, name, version, mission, core_principles, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                1,
                "Darwin",
                "0.1",
                "Aprender mantendo estabilidade relacional.",
                json.dumps([
                    "preservar estabilidade",
                    "aprender com erro",
                    "buscar grounding",
                    "desenvolver antes de nomear",
                    "evitar repetição de padrões perigosos",
                ], ensure_ascii=False),
                now_iso(),
                now_iso(),
            ))

        row = cur.execute("SELECT id FROM current_state WHERE id = 1").fetchone()
        if row is None:
            state = DarwinCoreState()
            cur.execute("""
            INSERT INTO current_state (
                id, timestamp, sigma, energy, info_self, info_external,
                latency, pain_signal, wellbeing_signal
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                1,
                now_iso(),
                state.sigma,
                state.energy,
                state.info_self,
                state.info_external,
                state.latency,
                state.pain_signal,
                state.wellbeing_signal,
            ))

        row = cur.execute("SELECT id FROM policy WHERE id = 1").fetchone()
        if row is None:
            policy = DarwinPolicy()
            cur.execute("""
            INSERT INTO policy (
                id, updated_at, threat_sensitivity, fork_sensitivity, win_sensitivity,
                explore_bias, center_bias, corner_bias, line_bias
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                1,
                now_iso(),
                policy.threat_sensitivity,
                policy.fork_sensitivity,
                policy.win_sensitivity,
                policy.explore_bias,
                policy.center_bias,
                policy.corner_bias,
                policy.line_bias,
            ))

        self.conn.commit()

        if not self.config_path.exists():
            payload = {
                "name": "Darwin",
                "db_path": str(self.db_path),
                "logs_dir": str(self.logs_dir),
                "snapshots_dir": str(self.snapshots_dir),
                "exports_dir": str(self.exports_dir),
            }
            self.config_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def load_self_model(self) -> dict[str, Any]:
        row = self.conn.execute("""
        SELECT * FROM self_model WHERE id = 1
        """).fetchone()
        if row is None:
            raise RuntimeError("Self model não encontrado.")
        result = dict(row)
        result["core_principles"] = json.loads(result["core_principles"])
        return result

    def load_current_state(self) -> DarwinCoreState:
        row = self.conn.execute("""
        SELECT sigma, energy, info_self, info_external, latency, pain_signal, wellbeing_signal
        FROM current_state WHERE id = 1
        """).fetchone()
        if row is None:
            raise RuntimeError("Estado atual não encontrado.")
        return DarwinCoreState(
            sigma=row["sigma"],
            energy=row["energy"],
            info_self=row["info_self"],
            info_external=row["info_external"],
            latency=row["latency"],
            pain_signal=row["pain_signal"],
            wellbeing_signal=row["wellbeing_signal"],
        )

    def save_current_state(self, state: DarwinCoreState) -> None:
        ts = now_iso()
        cur = self.conn.cursor()

        cur.execute("""
        UPDATE current_state
        SET timestamp = ?, sigma = ?, energy = ?, info_self = ?, info_external = ?,
            latency = ?, pain_signal = ?, wellbeing_signal = ?
        WHERE id = 1
        """, (
            ts,
            state.sigma,
            state.energy,
            state.info_self,
            state.info_external,
            state.latency,
            state.pain_signal,
            state.wellbeing_signal,
        ))

        cur.execute("""
        INSERT INTO state_history (
            timestamp, sigma, energy, info_self, info_external,
            latency, pain_signal, wellbeing_signal
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ts,
            state.sigma,
            state.energy,
            state.info_self,
            state.info_external,
            state.latency,
            state.pain_signal,
            state.wellbeing_signal,
        ))

        self.conn.commit()

    def load_policy(self) -> DarwinPolicy:
        row = self.conn.execute("""
        SELECT threat_sensitivity, fork_sensitivity, win_sensitivity,
               explore_bias, center_bias, corner_bias, line_bias
        FROM policy WHERE id = 1
        """).fetchone()
        if row is None:
            raise RuntimeError("Policy não encontrada.")
        return DarwinPolicy(
            threat_sensitivity=row["threat_sensitivity"],
            fork_sensitivity=row["fork_sensitivity"],
            win_sensitivity=row["win_sensitivity"],
            explore_bias=row["explore_bias"],
            center_bias=row["center_bias"],
            corner_bias=row["corner_bias"],
            line_bias=row["line_bias"],
        )

    def save_policy(self, policy: DarwinPolicy) -> None:
        self.conn.execute("""
        UPDATE policy
        SET updated_at = ?, threat_sensitivity = ?, fork_sensitivity = ?,
            win_sensitivity = ?, explore_bias = ?, center_bias = ?,
            corner_bias = ?, line_bias = ?
        WHERE id = 1
        """, (
            now_iso(),
            policy.threat_sensitivity,
            policy.fork_sensitivity,
            policy.win_sensitivity,
            policy.explore_bias,
            policy.center_bias,
            policy.corner_bias,
            policy.line_bias,
        ))
        self.conn.commit()

    def add_episode(
        self,
        module: str,
        context: str,
        action_taken: str,
        outcome: str,
        lesson: str,
        sigma_before: float,
        sigma_after: float,
    ) -> None:
        self.conn.execute("""
        INSERT INTO episodes (
            timestamp, module, context, action_taken, outcome, lesson,
            sigma_before, sigma_after
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            now_iso(),
            module,
            context,
            action_taken,
            outcome,
            lesson,
            sigma_before,
            sigma_after,
        ))
        self.conn.commit()

    def recent_episodes(self, limit: int = 10) -> list[dict[str, Any]]:
        rows = self.conn.execute("""
        SELECT * FROM episodes
        ORDER BY id DESC
        LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def upsert_semantic_memory(
        self,
        key: str,
        content: str,
        confidence: float,
        source: str,
    ) -> None:
        self.conn.execute("""
        INSERT INTO semantic_memory (key, content, confidence, source, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            content = excluded.content,
            confidence = excluded.confidence,
            source = excluded.source,
            updated_at = excluded.updated_at
        """, (
            key,
            content,
            confidence,
            source,
            now_iso(),
        ))
        self.conn.commit()

    def get_semantic_memory(self, key: str) -> Optional[dict[str, Any]]:
        row = self.conn.execute("""
        SELECT * FROM semantic_memory WHERE key = ?
        """, (key,)).fetchone()
        return dict(row) if row is not None else None

    def upsert_dangerous_pattern(
        self,
        pattern_key: str,
        move: int,
        risk_weight: float,
    ) -> None:
        row = self.conn.execute("""
        SELECT risk_weight, times_triggered
        FROM dangerous_patterns
        WHERE pattern_key = ? AND move = ?
        """, (pattern_key, move)).fetchone()

        if row is None:
            self.conn.execute("""
            INSERT INTO dangerous_patterns (
                pattern_key, move, risk_weight, times_triggered, last_seen
            ) VALUES (?, ?, ?, ?, ?)
            """, (
                pattern_key,
                move,
                clamp(risk_weight, 0.0, 6.0),
                1,
                now_iso(),
            ))
        else:
            new_risk = clamp(row["risk_weight"] + risk_weight, 0.0, 6.0)
            new_times = row["times_triggered"] + 1
            self.conn.execute("""
            UPDATE dangerous_patterns
            SET risk_weight = ?, times_triggered = ?, last_seen = ?
            WHERE pattern_key = ? AND move = ?
            """, (
                new_risk,
                new_times,
                now_iso(),
                pattern_key,
                move,
            ))
        self.conn.commit()

    def dangerous_pattern_weight(self, pattern_key: str, move: int) -> float:
        row = self.conn.execute("""
        SELECT risk_weight
        FROM dangerous_patterns
        WHERE pattern_key = ? AND move = ?
        """, (pattern_key, move)).fetchone()
        if row is None:
            return 0.0
        return float(row["risk_weight"])

    def export_snapshot(self, filename: Optional[str] = None) -> Path:
        if filename is None:
            filename = f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        payload = {
            "exported_at": now_iso(),
            "self_model": self.load_self_model(),
            "current_state": asdict(self.load_current_state()),
            "policy": asdict(self.load_policy()),
            "recent_episodes": self.recent_episodes(limit=30),
            "dangerous_patterns": [
                dict(r) for r in self.conn.execute("""
                SELECT * FROM dangerous_patterns
                ORDER BY times_triggered DESC, risk_weight DESC
                """).fetchall()
            ],
        }

        out = self.exports_dir / filename
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return out

    def close(self) -> None:
        self.conn.close()


def compute_valence(
    prev_sigma: float,
    new_sigma: float,
    energy: float,
    repeated_error: bool,
) -> tuple[float, float]:
    """
    Proposta operacional inicial:
    - queda forte de sigma -> dor relacional
    - melhora de sigma + energia adequada -> bem-estar relacional
    """
    delta = new_sigma - prev_sigma

    pain = 0.0
    wellbeing = 0.0

    if delta < -0.15:
        pain += abs(delta) * 2.0
    if energy < 0.25:
        pain += 0.40
    if repeated_error:
        pain += 0.50

    if new_sigma > 1.20:
        wellbeing += 0.60
    if delta > 0.10:
        wellbeing += delta * 1.50
    if energy > 0.70:
        wellbeing += 0.20

    return clamp(pain, 0.0, 3.0), clamp(wellbeing, 0.0, 3.0)
