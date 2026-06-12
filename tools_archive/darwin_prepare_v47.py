from __future__ import annotations

"""
DARWIN — Preparar v47 sem tocar na baseline

Este script faz o próximo passo lógico depois do freeze da v46:

1. Cria uma cópia operacional:
   darwin_v61_nursery_v46.py -> darwin_v61_nursery_v47.py

2. Cria o módulo:
   darwin_tension_persistence_v47.py

3. Faz backup do banco vivo:
   darwin_home/backups/darwin_pre_v47_YYYYMMDD_HHMMSS_UTC.db

4. Cria tabelas SQLite para memória executiva de tensões:
   - tension_cases
   - tension_events
   - tension_probes
   - tension_outcomes
   - darwin_schema_migrations

Importante:
- Não altera a baseline congelada.
- Não muda ainda o comportamento cognitivo do Darwin.
- A v47 começa como cópia funcional da v46, com infraestrutura persistente pronta.

Uso:
    py darwin_prepare_v47.py

Teste sem escrever nada:
    py darwin_prepare_v47.py --dry-run

Forçar recriação da cópia v47:
    py darwin_prepare_v47.py --force-copy

Forçar recriação do módulo de persistência:
    py darwin_prepare_v47.py --force-module
"""

import argparse
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path.cwd()
V46_FILE = PROJECT_ROOT / "darwin_v61_nursery_v46.py"
V47_FILE = PROJECT_ROOT / "darwin_v61_nursery_v47.py"
TENSION_MODULE = PROJECT_ROOT / "darwin_tension_persistence_v47.py"
DARWIN_HOME = PROJECT_ROOT / "darwin_home"
DB_PATH = DARWIN_HOME / "darwin.db"
BACKUP_DIR = DARWIN_HOME / "backups"
NEXT_STEPS_FILE = PROJECT_ROOT / "V47_NEXT_STEPS.txt"

TENSION_MODULE_CODE = 'from __future__ import annotations\n\n"""\nDARWIN v47 — Persistência de Tensões Vivas\n\nEste módulo é a primeira peça da memória executiva persistente do Darwin.\n\nEle NÃO substitui a economia de tensões da v46.\nEle apenas cria uma ponte segura entre os casos vivos do runtime e o banco SQLite.\n\nUso futuro dentro do agente:\n\n    from darwin_tension_persistence_v47 import DarwinTensionStoreV47\n\n    self.tension_store = DarwinTensionStoreV47()\n    self.tension_store.initialize_schema()\n    self.tension_store.upsert_case(case)\n    self.tension_store.record_event(...)\n\nA ideia da v47:\n- tensão deixa de ser só estado transitório do runtime;\n- tensão vira caso cognitivo persistente;\n- cada abertura, reabertura, sonda, preempção, atraso e fechamento ganha registro.\n"""\n\nimport json\nimport sqlite3\nfrom dataclasses import asdict, is_dataclass\nfrom datetime import datetime, timezone\nfrom pathlib import Path\nfrom typing import Any, Iterable, Optional\n\n\nDEFAULT_DB_PATH = Path("darwin_home") / "darwin.db"\nSOURCE = "darwin_tension_persistence_v47"\n\n\ndef now_iso() -> str:\n    return datetime.now(timezone.utc).isoformat(timespec="seconds")\n\n\ndef clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:\n    return max(low, min(high, float(value)))\n\n\ndef safe_json(value: Any) -> str:\n    try:\n        return json.dumps(value, ensure_ascii=False, sort_keys=True)\n    except TypeError:\n        return json.dumps(str(value), ensure_ascii=False)\n\n\ndef enum_value(value: Any) -> Any:\n    """Extrai .value de Enum quando existir, sem exigir import do Enum original."""\n    return getattr(value, "value", value)\n\n\ndef case_get(case: Any, name: str, default: Any = None) -> Any:\n    if isinstance(case, dict):\n        return case.get(name, default)\n    return getattr(case, name, default)\n\n\ndef pair_key(lower: str, upper: str) -> str:\n    return f"{lower}>{upper}"\n\n\nclass DarwinTensionStoreV47:\n    """\n    Camada de persistência de tensões vivas.\n\n    A classe foi desenhada para aceitar tanto LiveTensionCase do runtime quanto dicts.\n    Assim ela não acopla fortemente o banco ao arquivo principal do Darwin.\n    """\n\n    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:\n        self.db_path = Path(db_path)\n\n    def connect(self) -> sqlite3.Connection:\n        if not self.db_path.exists():\n            raise FileNotFoundError(f"Banco Darwin não encontrado: {self.db_path}")\n        conn = sqlite3.connect(self.db_path)\n        conn.row_factory = sqlite3.Row\n        return conn\n\n    def initialize_schema(self) -> None:\n        with self.connect() as conn:\n            conn.execute("PRAGMA foreign_keys = ON")\n            self._create_schema(conn)\n            self._record_migration(conn, "v47_tension_persistence_schema")\n            conn.commit()\n\n    def _create_schema(self, conn: sqlite3.Connection) -> None:\n        conn.executescript(\n            """\n            CREATE TABLE IF NOT EXISTS darwin_schema_migrations (\n                name TEXT PRIMARY KEY,\n                applied_at TEXT NOT NULL,\n                details_json TEXT NOT NULL DEFAULT \'{}\'\n            );\n\n            CREATE TABLE IF NOT EXISTS tension_cases (\n                tension_id TEXT PRIMARY KEY,\n                source_lower TEXT NOT NULL,\n                source_upper TEXT NOT NULL,\n                source_pair TEXT NOT NULL,\n                source_predicted TEXT,\n                source_observed TEXT,\n                source_labels_json TEXT NOT NULL DEFAULT \'[]\',\n                semantic_summary TEXT NOT NULL DEFAULT \'\',\n                opened_step INTEGER NOT NULL DEFAULT 0,\n                last_event_step INTEGER NOT NULL DEFAULT 0,\n\n                status TEXT NOT NULL DEFAULT \'open\',\n                outcome TEXT NOT NULL DEFAULT \'unknown\',\n\n                contradiction_magnitude REAL NOT NULL DEFAULT 1.0,\n                live_pressure REAL NOT NULL DEFAULT 0.0,\n                recency_score REAL NOT NULL DEFAULT 0.0,\n                continuity_score REAL NOT NULL DEFAULT 0.0,\n                ambiguity_score REAL NOT NULL DEFAULT 0.0,\n                closure_deficit REAL NOT NULL DEFAULT 1.0,\n                saturation_cost REAL NOT NULL DEFAULT 0.0,\n                economic_priority REAL NOT NULL DEFAULT 0.0,\n\n                last_probe_lower TEXT,\n                last_probe_upper TEXT,\n                last_probe_pair TEXT,\n                last_probe_step INTEGER,\n                last_probe_score REAL NOT NULL DEFAULT 0.0,\n                last_probe_judgment TEXT NOT NULL DEFAULT \'\',\n                last_probe_labels_json TEXT NOT NULL DEFAULT \'[]\',\n\n                inherited_pairs_json TEXT NOT NULL DEFAULT \'[]\',\n                continuity_lines_json TEXT NOT NULL DEFAULT \'[]\',\n                outcome_lines_json TEXT NOT NULL DEFAULT \'[]\',\n                trail_json TEXT NOT NULL DEFAULT \'[]\',\n\n                probe_count INTEGER NOT NULL DEFAULT 0,\n                closure_hits INTEGER NOT NULL DEFAULT 0,\n                reopening_hits INTEGER NOT NULL DEFAULT 0,\n                weakening_hits INTEGER NOT NULL DEFAULT 0,\n\n                created_at TEXT NOT NULL,\n                updated_at TEXT NOT NULL,\n                source TEXT NOT NULL DEFAULT \'darwin_v47\'\n            );\n\n            CREATE TABLE IF NOT EXISTS tension_events (\n                id INTEGER PRIMARY KEY AUTOINCREMENT,\n                tension_id TEXT NOT NULL,\n                timestamp TEXT NOT NULL,\n                step INTEGER,\n                event_type TEXT NOT NULL,\n                status_after TEXT,\n                pressure_after REAL,\n                note TEXT NOT NULL DEFAULT \'\',\n                payload_json TEXT NOT NULL DEFAULT \'{}\',\n                source TEXT NOT NULL DEFAULT \'darwin_v47\',\n                FOREIGN KEY(tension_id) REFERENCES tension_cases(tension_id)\n            );\n\n            CREATE TABLE IF NOT EXISTS tension_probes (\n                id INTEGER PRIMARY KEY AUTOINCREMENT,\n                tension_id TEXT NOT NULL,\n                selected_at TEXT NOT NULL,\n                selected_step INTEGER,\n                lower_id TEXT NOT NULL,\n                upper_id TEXT NOT NULL,\n                pair_key TEXT NOT NULL,\n                labels_json TEXT NOT NULL DEFAULT \'[]\',\n                score REAL NOT NULL DEFAULT 0.0,\n                judgment TEXT NOT NULL DEFAULT \'\',\n                validated_at TEXT,\n                observed TEXT,\n                outcome TEXT,\n                payload_json TEXT NOT NULL DEFAULT \'{}\',\n                source TEXT NOT NULL DEFAULT \'darwin_v47\',\n                FOREIGN KEY(tension_id) REFERENCES tension_cases(tension_id)\n            );\n\n            CREATE TABLE IF NOT EXISTS tension_outcomes (\n                id INTEGER PRIMARY KEY AUTOINCREMENT,\n                tension_id TEXT NOT NULL,\n                timestamp TEXT NOT NULL,\n                step INTEGER,\n                outcome TEXT NOT NULL,\n                observed TEXT,\n                closure_deficit_after REAL NOT NULL DEFAULT 0.0,\n                outcome_lines_json TEXT NOT NULL DEFAULT \'[]\',\n                payload_json TEXT NOT NULL DEFAULT \'{}\',\n                source TEXT NOT NULL DEFAULT \'darwin_v47\',\n                FOREIGN KEY(tension_id) REFERENCES tension_cases(tension_id)\n            );\n\n            CREATE INDEX IF NOT EXISTS idx_tension_cases_status\n                ON tension_cases(status);\n\n            CREATE INDEX IF NOT EXISTS idx_tension_cases_priority\n                ON tension_cases(economic_priority DESC, live_pressure DESC);\n\n            CREATE INDEX IF NOT EXISTS idx_tension_events_tension_time\n                ON tension_events(tension_id, timestamp);\n\n            CREATE INDEX IF NOT EXISTS idx_tension_probes_tension_step\n                ON tension_probes(tension_id, selected_step);\n\n            CREATE INDEX IF NOT EXISTS idx_tension_outcomes_tension_time\n                ON tension_outcomes(tension_id, timestamp);\n            """\n        )\n\n    def _record_migration(self, conn: sqlite3.Connection, name: str) -> None:\n        conn.execute(\n            """\n            INSERT INTO darwin_schema_migrations (name, applied_at, details_json)\n            VALUES (?, ?, ?)\n            ON CONFLICT(name) DO NOTHING\n            """,\n            (\n                name,\n                now_iso(),\n                safe_json(\n                    {\n                        "module": SOURCE,\n                        "purpose": "persistência executiva de tensões vivas para Darwin v47",\n                        "tables": [\n                            "tension_cases",\n                            "tension_events",\n                            "tension_probes",\n                            "tension_outcomes",\n                        ],\n                    }\n                ),\n            ),\n        )\n\n    def upsert_case(self, case: Any) -> None:\n        """\n        Insere/atualiza um caso de tensão.\n\n        Aceita:\n        - LiveTensionCase do runtime;\n        - dict com campos equivalentes.\n        """\n        now = now_iso()\n\n        tension_id = str(case_get(case, "tension_id"))\n        lower = str(case_get(case, "source_lower"))\n        upper = str(case_get(case, "source_upper"))\n\n        last_probe_lower = case_get(case, "last_probe_lower")\n        last_probe_upper = case_get(case, "last_probe_upper")\n        last_probe_pair = (\n            pair_key(str(last_probe_lower), str(last_probe_upper))\n            if last_probe_lower and last_probe_upper\n            else None\n        )\n\n        payload = self.case_to_payload(case)\n\n        with self.connect() as conn:\n            conn.execute("PRAGMA foreign_keys = ON")\n            conn.execute(\n                """\n                INSERT INTO tension_cases (\n                    tension_id,\n                    source_lower,\n                    source_upper,\n                    source_pair,\n                    source_predicted,\n                    source_observed,\n                    source_labels_json,\n                    semantic_summary,\n                    opened_step,\n                    last_event_step,\n                    status,\n                    outcome,\n                    contradiction_magnitude,\n                    live_pressure,\n                    recency_score,\n                    continuity_score,\n                    ambiguity_score,\n                    closure_deficit,\n                    saturation_cost,\n                    economic_priority,\n                    last_probe_lower,\n                    last_probe_upper,\n                    last_probe_pair,\n                    last_probe_step,\n                    last_probe_score,\n                    last_probe_judgment,\n                    last_probe_labels_json,\n                    inherited_pairs_json,\n                    continuity_lines_json,\n                    outcome_lines_json,\n                    trail_json,\n                    probe_count,\n                    closure_hits,\n                    reopening_hits,\n                    weakening_hits,\n                    created_at,\n                    updated_at,\n                    source\n                )\n                VALUES (\n                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,\n                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,\n                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,\n                    ?, ?, ?, ?, ?, ?, ?, ?\n                )\n                ON CONFLICT(tension_id) DO UPDATE SET\n                    source_lower=excluded.source_lower,\n                    source_upper=excluded.source_upper,\n                    source_pair=excluded.source_pair,\n                    source_predicted=excluded.source_predicted,\n                    source_observed=excluded.source_observed,\n                    source_labels_json=excluded.source_labels_json,\n                    semantic_summary=excluded.semantic_summary,\n                    last_event_step=excluded.last_event_step,\n                    status=excluded.status,\n                    outcome=excluded.outcome,\n                    contradiction_magnitude=excluded.contradiction_magnitude,\n                    live_pressure=excluded.live_pressure,\n                    recency_score=excluded.recency_score,\n                    continuity_score=excluded.continuity_score,\n                    ambiguity_score=excluded.ambiguity_score,\n                    closure_deficit=excluded.closure_deficit,\n                    saturation_cost=excluded.saturation_cost,\n                    economic_priority=excluded.economic_priority,\n                    last_probe_lower=excluded.last_probe_lower,\n                    last_probe_upper=excluded.last_probe_upper,\n                    last_probe_pair=excluded.last_probe_pair,\n                    last_probe_step=excluded.last_probe_step,\n                    last_probe_score=excluded.last_probe_score,\n                    last_probe_judgment=excluded.last_probe_judgment,\n                    last_probe_labels_json=excluded.last_probe_labels_json,\n                    inherited_pairs_json=excluded.inherited_pairs_json,\n                    continuity_lines_json=excluded.continuity_lines_json,\n                    outcome_lines_json=excluded.outcome_lines_json,\n                    trail_json=excluded.trail_json,\n                    probe_count=excluded.probe_count,\n                    closure_hits=excluded.closure_hits,\n                    reopening_hits=excluded.reopening_hits,\n                    weakening_hits=excluded.weakening_hits,\n                    updated_at=excluded.updated_at,\n                    source=excluded.source\n                """,\n                (\n                    tension_id,\n                    lower,\n                    upper,\n                    pair_key(lower, upper),\n                    case_get(case, "source_predicted", ""),\n                    case_get(case, "source_observed", ""),\n                    safe_json(list(case_get(case, "source_labels", []))),\n                    case_get(case, "semantic_summary", ""),\n                    int(case_get(case, "opened_step", 0) or 0),\n                    int(case_get(case, "last_event_step", 0) or 0),\n                    str(enum_value(case_get(case, "status", "open"))),\n                    str(enum_value(case_get(case, "outcome", "unknown"))),\n                    float(case_get(case, "contradiction_magnitude", 1.0) or 1.0),\n                    float(case_get(case, "live_pressure", 0.0) or 0.0),\n                    float(case_get(case, "recency_score", 0.0) or 0.0),\n                    float(case_get(case, "continuity_score", 0.0) or 0.0),\n                    float(case_get(case, "ambiguity_score", 0.0) or 0.0),\n                    float(case_get(case, "closure_deficit", 1.0) or 1.0),\n                    float(case_get(case, "saturation_cost", 0.0) or 0.0),\n                    float(case_get(case, "economic_priority", 0.0) or 0.0),\n                    last_probe_lower,\n                    last_probe_upper,\n                    last_probe_pair,\n                    case_get(case, "last_probe_step"),\n                    float(case_get(case, "last_probe_score", 0.0) or 0.0),\n                    case_get(case, "last_probe_judgment", ""),\n                    safe_json(list(case_get(case, "last_probe_labels", []))),\n                    safe_json(list(case_get(case, "inherited_pairs", []))),\n                    safe_json(list(case_get(case, "continuity_lines", []))),\n                    safe_json(list(case_get(case, "outcome_lines", []))),\n                    safe_json(list(case_get(case, "trail", []))),\n                    int(case_get(case, "probe_count", 0) or 0),\n                    int(case_get(case, "closure_hits", 0) or 0),\n                    int(case_get(case, "reopening_hits", 0) or 0),\n                    int(case_get(case, "weakening_hits", 0) or 0),\n                    now,\n                    now,\n                    SOURCE,\n                ),\n            )\n            conn.commit()\n\n        self.record_event(\n            tension_id=tension_id,\n            event_type="case_upserted",\n            step=case_get(case, "last_event_step"),\n            status_after=str(enum_value(case_get(case, "status", "open"))),\n            pressure_after=float(case_get(case, "live_pressure", 0.0) or 0.0),\n            note="caso sincronizado com persistência v47",\n            payload=payload,\n        )\n\n    def record_event(\n        self,\n        *,\n        tension_id: str,\n        event_type: str,\n        step: Optional[int] = None,\n        status_after: Optional[str] = None,\n        pressure_after: Optional[float] = None,\n        note: str = "",\n        payload: Optional[dict[str, Any]] = None,\n    ) -> None:\n        with self.connect() as conn:\n            conn.execute(\n                """\n                INSERT INTO tension_events (\n                    tension_id, timestamp, step, event_type, status_after,\n                    pressure_after, note, payload_json, source\n                )\n                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)\n                """,\n                (\n                    tension_id,\n                    now_iso(),\n                    step,\n                    event_type,\n                    status_after,\n                    pressure_after,\n                    note,\n                    safe_json(payload or {}),\n                    SOURCE,\n                ),\n            )\n            conn.commit()\n\n    def record_probe(\n        self,\n        *,\n        tension_id: str,\n        lower_id: str,\n        upper_id: str,\n        selected_step: Optional[int],\n        labels: Iterable[str],\n        score: float,\n        judgment: str,\n        payload: Optional[dict[str, Any]] = None,\n    ) -> None:\n        with self.connect() as conn:\n            conn.execute(\n                """\n                INSERT INTO tension_probes (\n                    tension_id, selected_at, selected_step, lower_id, upper_id,\n                    pair_key, labels_json, score, judgment, payload_json, source\n                )\n                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)\n                """,\n                (\n                    tension_id,\n                    now_iso(),\n                    selected_step,\n                    lower_id,\n                    upper_id,\n                    pair_key(lower_id, upper_id),\n                    safe_json(list(labels)),\n                    score,\n                    judgment,\n                    safe_json(payload or {}),\n                    SOURCE,\n                ),\n            )\n            conn.commit()\n\n        self.record_event(\n            tension_id=tension_id,\n            event_type="probe_selected",\n            step=selected_step,\n            status_after="probing",\n            pressure_after=None,\n            note=f"sonda selecionada em {pair_key(lower_id, upper_id)}",\n            payload=payload or {},\n        )\n\n    def record_outcome(\n        self,\n        *,\n        tension_id: str,\n        step: Optional[int],\n        outcome: str,\n        observed: Optional[str],\n        closure_deficit_after: float,\n        outcome_lines: Iterable[str],\n        payload: Optional[dict[str, Any]] = None,\n    ) -> None:\n        with self.connect() as conn:\n            conn.execute(\n                """\n                INSERT INTO tension_outcomes (\n                    tension_id, timestamp, step, outcome, observed,\n                    closure_deficit_after, outcome_lines_json, payload_json, source\n                )\n                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)\n                """,\n                (\n                    tension_id,\n                    now_iso(),\n                    step,\n                    outcome,\n                    observed,\n                    closure_deficit_after,\n                    safe_json(list(outcome_lines)),\n                    safe_json(payload or {}),\n                    SOURCE,\n                ),\n            )\n            conn.commit()\n\n        self.record_event(\n            tension_id=tension_id,\n            event_type="probe_outcome",\n            step=step,\n            status_after=outcome,\n            pressure_after=None,\n            note=f"desfecho narrativo registrado: {outcome}",\n            payload=payload or {},\n        )\n\n    def case_to_payload(self, case: Any) -> dict[str, Any]:\n        if is_dataclass(case):\n            try:\n                raw = asdict(case)\n            except TypeError:\n                raw = {}\n        elif isinstance(case, dict):\n            raw = dict(case)\n        else:\n            raw = {\n                key: getattr(case, key)\n                for key in dir(case)\n                if not key.startswith("_") and not callable(getattr(case, key, None))\n            }\n\n        clean: dict[str, Any] = {}\n        for key, value in raw.items():\n            if key.startswith("_"):\n                continue\n            value = enum_value(value)\n            if isinstance(value, tuple):\n                value = list(value)\n            clean[key] = value\n        return clean\n\n    def summarize_counts(self) -> dict[str, int]:\n        with self.connect() as conn:\n            result = {}\n            for table in ("tension_cases", "tension_events", "tension_probes", "tension_outcomes"):\n                row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()\n                result[table] = int(row["n"]) if row else 0\n            return result\n\n    def load_open_cases(self) -> list[dict[str, Any]]:\n        with self.connect() as conn:\n            rows = conn.execute(\n                """\n                SELECT *\n                FROM tension_cases\n                WHERE status NOT IN (\'closed\', \'archived\', \'stale\')\n                ORDER BY economic_priority DESC, live_pressure DESC, updated_at DESC\n                """\n            ).fetchall()\n            return [dict(row) for row in rows]\n\n\ndef initialize_v47_tension_schema(db_path: Path | str = DEFAULT_DB_PATH) -> dict[str, int]:\n    store = DarwinTensionStoreV47(db_path)\n    store.initialize_schema()\n    return store.summarize_counts()\n\n\nif __name__ == "__main__":\n    counts = initialize_v47_tension_schema()\n    print("DARWIN v47 — schema de tensões inicializado.")\n    for table, n in counts.items():\n        print(f"- {table}: {n}")\n'
NEXT_STEPS_TEXT = 'DARWIN v47 — Próximos passos após preparação\n================================================\n\nEstado atual:\n- A baseline v46 já está congelada.\n- Este passo cria uma cópia operacional darwin_v61_nursery_v47.py.\n- Este passo cria o módulo darwin_tension_persistence_v47.py.\n- Este passo cria tabelas SQLite para tensão executiva persistente.\n\nImportante:\n- A v47 ainda deve se comportar como a v46.\n- A persistência de tensão ainda não está conectada ao loop cognitivo.\n- O próximo passo é integrar, com mudanças pequenas, os seguintes pontos do agente:\n\n1. Na inicialização do DarwinNurseryAgent:\n   - importar DarwinTensionStoreV47;\n   - criar self.tension_store;\n   - chamar initialize_schema().\n\n2. Quando register_tension_from_contradiction abrir/reabrir tensão:\n   - chamar self.tension_store.upsert_case(case);\n   - registrar evento opened/reopened.\n\n3. Depois de refresh_tension_economy:\n   - sincronizar casos vivos com tension_cases;\n   - registrar preempção quando active_tension_id mudar.\n\n4. Quando mark_probe_selected for chamado:\n   - registrar em tension_probes.\n\n5. Quando finalize_probe_validation finalizar:\n   - registrar em tension_outcomes.\n\nObjetivo da v47:\nDarwin deixa de apenas ter tensões vivas no runtime e passa a ter casos cognitivos persistentes.\n'


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def print_status(kind: str, message: str) -> None:
    print(f"[{kind:<7}] {message}")


def ensure_project_root() -> None:
    missing = []
    if not V46_FILE.exists():
        missing.append(V46_FILE.name)
    if not DARWIN_HOME.exists():
        missing.append("darwin_home/")
    if not DB_PATH.exists():
        missing.append("darwin_home/darwin.db")

    if missing:
        raise FileNotFoundError(
            "Arquivos essenciais não encontrados na pasta atual:\n"
            + "\n".join(f"- {item}" for item in missing)
            + "\n\nRode este script dentro da pasta darwin_local."
        )


def backup_database(dry_run: bool) -> Path:
    backup_name = f"darwin_pre_v47_{now_stamp()}.db"
    backup_path = BACKUP_DIR / backup_name

    if dry_run:
        print_status("DRYRUN", f"criaria backup: {backup_path}")
        return backup_path

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DB_PATH, backup_path)
    print_status("OK", f"backup do banco criado: {backup_path}")
    return backup_path


def create_v47_copy(force: bool, dry_run: bool) -> None:
    if V47_FILE.exists() and not force:
        print_status("PULOU", f"{V47_FILE.name} já existe; use --force-copy para recriar")
        return

    if dry_run:
        action = "recriaria" if V47_FILE.exists() else "criaria"
        print_status("DRYRUN", f"{action} {V47_FILE.name} a partir de {V46_FILE.name}")
        return

    original = V46_FILE.read_text(encoding="utf-8")
    header = (
        "# ============================================================\n"
        "# DARWIN v47 — cópia operacional criada a partir da v46\n"
        f"# Criado em: {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"
        "# Objetivo inicial: preparar memória executiva persistente de tensões.\n"
        "# Esta cópia começa sem alterar comportamento cognitivo da v46.\n"
        "# ============================================================\n\n"
    )

    V47_FILE.write_text(header + original, encoding="utf-8")
    print_status("OK", f"cópia operacional criada: {V47_FILE.name}")


def create_tension_module(force: bool, dry_run: bool) -> None:
    if TENSION_MODULE.exists() and not force:
        print_status("PULOU", f"{TENSION_MODULE.name} já existe; use --force-module para recriar")
        return

    if dry_run:
        action = "recriaria" if TENSION_MODULE.exists() else "criaria"
        print_status("DRYRUN", f"{action} {TENSION_MODULE.name}")
        return

    TENSION_MODULE.write_text(TENSION_MODULE_CODE, encoding="utf-8")
    print_status("OK", f"módulo criado: {TENSION_MODULE.name}")


def create_schema(dry_run: bool) -> None:
    if dry_run:
        print_status("DRYRUN", "criaria tabelas SQLite de tensão v47")
        return

    conn = sqlite3.connect(DB_PATH)
    try:
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

        conn.execute(
            """
            INSERT INTO darwin_schema_migrations (name, applied_at, details_json)
            VALUES (?, ?, ?)
            ON CONFLICT(name) DO NOTHING
            """,
            (
                "v47_tension_persistence_schema",
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                json.dumps(
                    {
                        "purpose": "memória executiva persistente de tensões vivas",
                        "created_by": "darwin_prepare_v47.py",
                    },
                    ensure_ascii=False,
                ),
            ),
        )

        conn.commit()
    finally:
        conn.close()

    print_status("OK", "schema SQLite v47 criado/verificado")


def sqlite_counts() -> dict[str, int]:
    tables = [
        "current_state",
        "episodes",
        "semantic_memory",
        "state_history",
        "tension_cases",
        "tension_events",
        "tension_probes",
        "tension_outcomes",
        "darwin_schema_migrations",
    ]
    result: dict[str, int] = {}

    conn = sqlite3.connect(DB_PATH)
    try:
        for table in tables:
            try:
                row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                result[table] = int(row[0]) if row else 0
            except sqlite3.Error:
                result[table] = -1
    finally:
        conn.close()

    return result


def write_manifest(backup_path: Path, dry_run: bool) -> None:
    if dry_run:
        print_status("DRYRUN", f"criaria {NEXT_STEPS_FILE.name}")
        return

    NEXT_STEPS_FILE.write_text(NEXT_STEPS_TEXT, encoding="utf-8")
    print_status("OK", f"guia criado: {NEXT_STEPS_FILE.name}")

    manifest_path = PROJECT_ROOT / "v47_preparation_manifest.json"
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "project_root": str(PROJECT_ROOT),
        "v46_file": str(V46_FILE),
        "v47_file": str(V47_FILE),
        "tension_module": str(TENSION_MODULE),
        "db_path": str(DB_PATH),
        "db_backup": str(backup_path),
        "hashes": {},
        "sqlite_counts": sqlite_counts(),
    }

    for path in (V46_FILE, V47_FILE, TENSION_MODULE, DB_PATH, backup_path):
        if path.exists() and path.is_file():
            manifest["hashes"][str(path)] = sha256_file(path)

    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print_status("OK", f"manifest criado: {manifest_path.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepara Darwin v47 sem tocar na baseline v46.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria feito sem escrever arquivos.")
    parser.add_argument("--force-copy", action="store_true", help="Recria darwin_v61_nursery_v47.py mesmo se já existir.")
    parser.add_argument("--force-module", action="store_true", help="Recria darwin_tension_persistence_v47.py mesmo se já existir.")
    args = parser.parse_args()

    print("=" * 72)
    print("DARWIN — PREPARAR v47")
    print("=" * 72)
    print(f"Raiz do projeto: {PROJECT_ROOT}")
    print(f"Dry-run:         {args.dry_run}")
    print()

    ensure_project_root()

    backup_path = backup_database(args.dry_run)
    create_v47_copy(force=args.force_copy, dry_run=args.dry_run)
    create_tension_module(force=args.force_module, dry_run=args.dry_run)
    create_schema(args.dry_run)
    write_manifest(backup_path, args.dry_run)

    if not args.dry_run:
        print()
        print("Resumo SQLite:")
        for table, count in sqlite_counts().items():
            status = "ausente" if count < 0 else str(count)
            print(f"- {table}: {status}")

    print()
    print("Preparação v47 concluída.")
    print("Próximo passo: integrar a persistência no agente, com mudanças pequenas e testáveis.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
