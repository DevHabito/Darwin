from __future__ import annotations

"""
DARWIN v47 — Persistência de Tensões Vivas

Este módulo é a primeira peça da memória executiva persistente do Darwin.

Ele NÃO substitui a economia de tensões da v46.
Ele apenas cria uma ponte segura entre os casos vivos do runtime e o banco SQLite.

Uso futuro dentro do agente:

    from darwin_tension_persistence_v47 import DarwinTensionStoreV47

    self.tension_store = DarwinTensionStoreV47()
    self.tension_store.initialize_schema()
    self.tension_store.upsert_case(case)
    self.tension_store.record_event(...)

A ideia da v47:
- tensão deixa de ser só estado transitório do runtime;
- tensão vira caso cognitivo persistente;
- cada abertura, reabertura, sonda, preempção, atraso e fechamento ganha registro.
"""

import json
import sqlite3
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


DEFAULT_DB_PATH = Path("darwin_home") / "darwin.db"
SOURCE = "darwin_tension_persistence_v47"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def safe_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=False)


def enum_value(value: Any) -> Any:
    """Extrai .value de Enum quando existir, sem exigir import do Enum original."""
    return getattr(value, "value", value)


def case_get(case: Any, name: str, default: Any = None) -> Any:
    if isinstance(case, dict):
        return case.get(name, default)
    return getattr(case, name, default)


def pair_key(lower: str, upper: str) -> str:
    return f"{lower}>{upper}"


class DarwinTensionStoreV47:
    """
    Camada de persistência de tensões vivas.

    A classe foi desenhada para aceitar tanto LiveTensionCase do runtime quanto dicts.
    Assim ela não acopla fortemente o banco ao arquivo principal do Darwin.
    """

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        if not self.db_path.exists():
            raise FileNotFoundError(f"Banco Darwin não encontrado: {self.db_path}")
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize_schema(self) -> None:
        with self.connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            self._create_schema(conn)
            self._record_migration(conn, "v47_tension_persistence_schema")
            conn.commit()

    def _create_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS darwin_schema_migrations (
                name TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL,
                details_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS tension_cases (
                tension_id TEXT PRIMARY KEY,
                source_lower TEXT NOT NULL,
                source_upper TEXT NOT NULL,
                source_pair TEXT NOT NULL,
                source_predicted TEXT,
                source_observed TEXT,
                source_labels_json TEXT NOT NULL DEFAULT '[]',
                semantic_summary TEXT NOT NULL DEFAULT '',
                opened_step INTEGER NOT NULL DEFAULT 0,
                last_event_step INTEGER NOT NULL DEFAULT 0,

                status TEXT NOT NULL DEFAULT 'open',
                outcome TEXT NOT NULL DEFAULT 'unknown',

                contradiction_magnitude REAL NOT NULL DEFAULT 1.0,
                live_pressure REAL NOT NULL DEFAULT 0.0,
                recency_score REAL NOT NULL DEFAULT 0.0,
                continuity_score REAL NOT NULL DEFAULT 0.0,
                ambiguity_score REAL NOT NULL DEFAULT 0.0,
                closure_deficit REAL NOT NULL DEFAULT 1.0,
                saturation_cost REAL NOT NULL DEFAULT 0.0,
                economic_priority REAL NOT NULL DEFAULT 0.0,

                last_probe_lower TEXT,
                last_probe_upper TEXT,
                last_probe_pair TEXT,
                last_probe_step INTEGER,
                last_probe_score REAL NOT NULL DEFAULT 0.0,
                last_probe_judgment TEXT NOT NULL DEFAULT '',
                last_probe_labels_json TEXT NOT NULL DEFAULT '[]',

                inherited_pairs_json TEXT NOT NULL DEFAULT '[]',
                continuity_lines_json TEXT NOT NULL DEFAULT '[]',
                outcome_lines_json TEXT NOT NULL DEFAULT '[]',
                trail_json TEXT NOT NULL DEFAULT '[]',

                probe_count INTEGER NOT NULL DEFAULT 0,
                closure_hits INTEGER NOT NULL DEFAULT 0,
                reopening_hits INTEGER NOT NULL DEFAULT 0,
                weakening_hits INTEGER NOT NULL DEFAULT 0,

                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'darwin_v47'
            );

            CREATE TABLE IF NOT EXISTS tension_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tension_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                step INTEGER,
                event_type TEXT NOT NULL,
                status_after TEXT,
                pressure_after REAL,
                note TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL DEFAULT '{}',
                source TEXT NOT NULL DEFAULT 'darwin_v47',
                FOREIGN KEY(tension_id) REFERENCES tension_cases(tension_id)
            );

            CREATE TABLE IF NOT EXISTS tension_probes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tension_id TEXT NOT NULL,
                selected_at TEXT NOT NULL,
                selected_step INTEGER,
                lower_id TEXT NOT NULL,
                upper_id TEXT NOT NULL,
                pair_key TEXT NOT NULL,
                labels_json TEXT NOT NULL DEFAULT '[]',
                score REAL NOT NULL DEFAULT 0.0,
                judgment TEXT NOT NULL DEFAULT '',
                validated_at TEXT,
                observed TEXT,
                outcome TEXT,
                payload_json TEXT NOT NULL DEFAULT '{}',
                source TEXT NOT NULL DEFAULT 'darwin_v47',
                FOREIGN KEY(tension_id) REFERENCES tension_cases(tension_id)
            );

            CREATE TABLE IF NOT EXISTS tension_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tension_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                step INTEGER,
                outcome TEXT NOT NULL,
                observed TEXT,
                closure_deficit_after REAL NOT NULL DEFAULT 0.0,
                outcome_lines_json TEXT NOT NULL DEFAULT '[]',
                payload_json TEXT NOT NULL DEFAULT '{}',
                source TEXT NOT NULL DEFAULT 'darwin_v47',
                FOREIGN KEY(tension_id) REFERENCES tension_cases(tension_id)
            );

            CREATE INDEX IF NOT EXISTS idx_tension_cases_status
                ON tension_cases(status);

            CREATE INDEX IF NOT EXISTS idx_tension_cases_priority
                ON tension_cases(economic_priority DESC, live_pressure DESC);

            CREATE INDEX IF NOT EXISTS idx_tension_events_tension_time
                ON tension_events(tension_id, timestamp);

            CREATE INDEX IF NOT EXISTS idx_tension_probes_tension_step
                ON tension_probes(tension_id, selected_step);

            CREATE INDEX IF NOT EXISTS idx_tension_outcomes_tension_time
                ON tension_outcomes(tension_id, timestamp);
            """
        )

    def _record_migration(self, conn: sqlite3.Connection, name: str) -> None:
        conn.execute(
            """
            INSERT INTO darwin_schema_migrations (name, applied_at, details_json)
            VALUES (?, ?, ?)
            ON CONFLICT(name) DO NOTHING
            """,
            (
                name,
                now_iso(),
                safe_json(
                    {
                        "module": SOURCE,
                        "purpose": "persistência executiva de tensões vivas para Darwin v47",
                        "tables": [
                            "tension_cases",
                            "tension_events",
                            "tension_probes",
                            "tension_outcomes",
                        ],
                    }
                ),
            ),
        )

    def upsert_case(self, case: Any, emit_event: bool = True) -> None:
        """
        Insere/atualiza um caso de tensão.

        Aceita:
        - LiveTensionCase do runtime;
        - dict com campos equivalentes.
        """
        now = now_iso()

        tension_id = str(case_get(case, "tension_id"))
        lower = str(case_get(case, "source_lower"))
        upper = str(case_get(case, "source_upper"))

        last_probe_lower = case_get(case, "last_probe_lower")
        last_probe_upper = case_get(case, "last_probe_upper")
        last_probe_pair = (
            pair_key(str(last_probe_lower), str(last_probe_upper))
            if last_probe_lower and last_probe_upper
            else None
        )

        payload = self.case_to_payload(case)

        with self.connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                """
                INSERT INTO tension_cases (
                    tension_id,
                    source_lower,
                    source_upper,
                    source_pair,
                    source_predicted,
                    source_observed,
                    source_labels_json,
                    semantic_summary,
                    opened_step,
                    last_event_step,
                    status,
                    outcome,
                    contradiction_magnitude,
                    live_pressure,
                    recency_score,
                    continuity_score,
                    ambiguity_score,
                    closure_deficit,
                    saturation_cost,
                    economic_priority,
                    last_probe_lower,
                    last_probe_upper,
                    last_probe_pair,
                    last_probe_step,
                    last_probe_score,
                    last_probe_judgment,
                    last_probe_labels_json,
                    inherited_pairs_json,
                    continuity_lines_json,
                    outcome_lines_json,
                    trail_json,
                    probe_count,
                    closure_hits,
                    reopening_hits,
                    weakening_hits,
                    created_at,
                    updated_at,
                    source
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(tension_id) DO UPDATE SET
                    source_lower=excluded.source_lower,
                    source_upper=excluded.source_upper,
                    source_pair=excluded.source_pair,
                    source_predicted=excluded.source_predicted,
                    source_observed=excluded.source_observed,
                    source_labels_json=excluded.source_labels_json,
                    semantic_summary=excluded.semantic_summary,
                    last_event_step=excluded.last_event_step,
                    status=excluded.status,
                    outcome=excluded.outcome,
                    contradiction_magnitude=excluded.contradiction_magnitude,
                    live_pressure=excluded.live_pressure,
                    recency_score=excluded.recency_score,
                    continuity_score=excluded.continuity_score,
                    ambiguity_score=excluded.ambiguity_score,
                    closure_deficit=excluded.closure_deficit,
                    saturation_cost=excluded.saturation_cost,
                    economic_priority=excluded.economic_priority,
                    last_probe_lower=excluded.last_probe_lower,
                    last_probe_upper=excluded.last_probe_upper,
                    last_probe_pair=excluded.last_probe_pair,
                    last_probe_step=excluded.last_probe_step,
                    last_probe_score=excluded.last_probe_score,
                    last_probe_judgment=excluded.last_probe_judgment,
                    last_probe_labels_json=excluded.last_probe_labels_json,
                    inherited_pairs_json=excluded.inherited_pairs_json,
                    continuity_lines_json=excluded.continuity_lines_json,
                    outcome_lines_json=excluded.outcome_lines_json,
                    trail_json=excluded.trail_json,
                    probe_count=excluded.probe_count,
                    closure_hits=excluded.closure_hits,
                    reopening_hits=excluded.reopening_hits,
                    weakening_hits=excluded.weakening_hits,
                    updated_at=excluded.updated_at,
                    source=excluded.source
                """,
                (
                    tension_id,
                    lower,
                    upper,
                    pair_key(lower, upper),
                    case_get(case, "source_predicted", ""),
                    case_get(case, "source_observed", ""),
                    safe_json(list(case_get(case, "source_labels", []))),
                    case_get(case, "semantic_summary", ""),
                    int(case_get(case, "opened_step", 0) or 0),
                    int(case_get(case, "last_event_step", 0) or 0),
                    str(enum_value(case_get(case, "status", "open"))),
                    str(enum_value(case_get(case, "outcome", "unknown"))),
                    float(1.0 if case_get(case, "contradiction_magnitude", None) is None else case_get(case, "contradiction_magnitude")),
                    float(case_get(case, "live_pressure", 0.0) or 0.0),
                    float(case_get(case, "recency_score", 0.0) or 0.0),
                    float(case_get(case, "continuity_score", 0.0) or 0.0),
                    float(case_get(case, "ambiguity_score", 0.0) or 0.0),
                    float(1.0 if case_get(case, "closure_deficit", None) is None else case_get(case, "closure_deficit")),
                    float(case_get(case, "saturation_cost", 0.0) or 0.0),
                    float(case_get(case, "economic_priority", 0.0) or 0.0),
                    last_probe_lower,
                    last_probe_upper,
                    last_probe_pair,
                    case_get(case, "last_probe_step"),
                    float(case_get(case, "last_probe_score", 0.0) or 0.0),
                    case_get(case, "last_probe_judgment", ""),
                    safe_json(list(case_get(case, "last_probe_labels", []))),
                    safe_json(list(case_get(case, "inherited_pairs", []))),
                    safe_json(list(case_get(case, "continuity_lines", []))),
                    safe_json(list(case_get(case, "outcome_lines", []))),
                    safe_json(list(case_get(case, "trail", []))),
                    int(case_get(case, "probe_count", 0) or 0),
                    int(case_get(case, "closure_hits", 0) or 0),
                    int(case_get(case, "reopening_hits", 0) or 0),
                    int(case_get(case, "weakening_hits", 0) or 0),
                    now,
                    now,
                    SOURCE,
                ),
            )
            conn.commit()

        if emit_event:
            self.record_event(
                tension_id=tension_id,
                event_type="case_upserted",
                step=case_get(case, "last_event_step"),
                status_after=str(enum_value(case_get(case, "status", "open"))),
                pressure_after=float(case_get(case, "live_pressure", 0.0) or 0.0),
                note="caso sincronizado com persistência v47",
                payload=payload,
            )

    def record_event(
        self,
        *,
        tension_id: str,
        event_type: str,
        step: Optional[int] = None,
        status_after: Optional[str] = None,
        pressure_after: Optional[float] = None,
        note: str = "",
        payload: Optional[dict[str, Any]] = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO tension_events (
                    tension_id, timestamp, step, event_type, status_after,
                    pressure_after, note, payload_json, source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tension_id,
                    now_iso(),
                    step,
                    event_type,
                    status_after,
                    pressure_after,
                    note,
                    safe_json(payload or {}),
                    SOURCE,
                ),
            )
            conn.commit()

    def record_probe(
        self,
        *,
        tension_id: str,
        lower_id: str,
        upper_id: str,
        selected_step: Optional[int],
        labels: Iterable[str],
        score: float,
        judgment: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO tension_probes (
                    tension_id, selected_at, selected_step, lower_id, upper_id,
                    pair_key, labels_json, score, judgment, payload_json, source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tension_id,
                    now_iso(),
                    selected_step,
                    lower_id,
                    upper_id,
                    pair_key(lower_id, upper_id),
                    safe_json(list(labels)),
                    score,
                    judgment,
                    safe_json(payload or {}),
                    SOURCE,
                ),
            )
            conn.commit()

        self.record_event(
            tension_id=tension_id,
            event_type="probe_selected",
            step=selected_step,
            status_after="probing",
            pressure_after=None,
            note=f"sonda selecionada em {pair_key(lower_id, upper_id)}",
            payload=payload or {},
        )

    def record_outcome(
        self,
        *,
        tension_id: str,
        step: Optional[int],
        outcome: str,
        observed: Optional[str],
        closure_deficit_after: float,
        outcome_lines: Iterable[str],
        payload: Optional[dict[str, Any]] = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO tension_outcomes (
                    tension_id, timestamp, step, outcome, observed,
                    closure_deficit_after, outcome_lines_json, payload_json, source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tension_id,
                    now_iso(),
                    step,
                    outcome,
                    observed,
                    closure_deficit_after,
                    safe_json(list(outcome_lines)),
                    safe_json(payload or {}),
                    SOURCE,
                ),
            )
            conn.commit()

        self.record_event(
            tension_id=tension_id,
            event_type="probe_outcome",
            step=step,
            status_after=outcome,
            pressure_after=None,
            note=f"desfecho narrativo registrado: {outcome}",
            payload=payload or {},
        )

    def case_to_payload(self, case: Any) -> dict[str, Any]:
        if is_dataclass(case):
            try:
                raw = asdict(case)
            except TypeError:
                raw = {}
        elif isinstance(case, dict):
            raw = dict(case)
        else:
            raw = {
                key: getattr(case, key)
                for key in dir(case)
                if not key.startswith("_") and not callable(getattr(case, key, None))
            }

        clean: dict[str, Any] = {}
        for key, value in raw.items():
            if key.startswith("_"):
                continue
            value = enum_value(value)
            if isinstance(value, tuple):
                value = list(value)
            clean[key] = value
        return clean

    def summarize_counts(self) -> dict[str, int]:
        with self.connect() as conn:
            result = {}
            for table in ("tension_cases", "tension_events", "tension_probes", "tension_outcomes"):
                row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
                result[table] = int(row["n"]) if row else 0
            return result

    def load_open_cases(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM tension_cases
                WHERE status NOT IN ('closed', 'archived', 'stale')
                ORDER BY economic_priority DESC, live_pressure DESC, updated_at DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]


def initialize_v47_tension_schema(db_path: Path | str = DEFAULT_DB_PATH) -> dict[str, int]:
    store = DarwinTensionStoreV47(db_path)
    store.initialize_schema()
    return store.summarize_counts()


if __name__ == "__main__":
    counts = initialize_v47_tension_schema()
    print("DARWIN v47 — schema de tensões inicializado.")
    for table, n in counts.items():
        print(f"- {table}: {n}")
