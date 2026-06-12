from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DB_PATH = Path("darwin_home") / "darwin.db"
EXPORTS_DIR = Path("darwin_home") / "exports"
SOURCE = "darwin_sleep_consolidation"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class CoreState:
    sigma: float
    energy: float
    info_self: float
    info_external: float
    latency: float
    pain_signal: float
    wellbeing_signal: float


def connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"Banco não encontrado: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def load_state(conn: sqlite3.Connection) -> CoreState:
    row = conn.execute("SELECT * FROM current_state WHERE id = 1").fetchone()
    if row is None:
        raise RuntimeError("Tabela current_state não possui id=1.")
    return CoreState(
        sigma=float(row["sigma"]),
        energy=float(row["energy"]),
        info_self=float(row["info_self"]),
        info_external=float(row["info_external"]),
        latency=float(row["latency"]),
        pain_signal=float(row["pain_signal"]),
        wellbeing_signal=float(row["wellbeing_signal"]),
    )


def recompute_sigma(state: CoreState, bandwidth: float = 4.0) -> float:
    info_eff = max(state.info_self + state.info_external, 1e-8)
    latency = max(state.latency, 1e-8)
    return bandwidth / (info_eff * latency)


def save_state(conn: sqlite3.Connection, state: CoreState) -> None:
    ts = now_iso()
    conn.execute(
        """
        UPDATE current_state
        SET timestamp=?, sigma=?, energy=?, info_self=?, info_external=?,
            latency=?, pain_signal=?, wellbeing_signal=?
        WHERE id=1
        """,
        (
            ts,
            state.sigma,
            state.energy,
            state.info_self,
            state.info_external,
            state.latency,
            state.pain_signal,
            state.wellbeing_signal,
        ),
    )
    conn.execute(
        """
        INSERT INTO state_history (
            timestamp, sigma, energy, info_self, info_external,
            latency, pain_signal, wellbeing_signal
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ts,
            state.sigma,
            state.energy,
            state.info_self,
            state.info_external,
            state.latency,
            state.pain_signal,
            state.wellbeing_signal,
        ),
    )
    conn.commit()


def add_episode(conn: sqlite3.Connection, context: str, action_taken: str, outcome: str, lesson: str, sigma_before: float, sigma_after: float) -> None:
    conn.execute(
        """
        INSERT INTO episodes (
            timestamp, module, context, action_taken, outcome, lesson,
            sigma_before, sigma_after
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (now_iso(), SOURCE, context, action_taken, outcome, lesson, sigma_before, sigma_after),
    )
    conn.commit()


def upsert_memory(conn: sqlite3.Connection, key: str, content: str, confidence: float) -> None:
    conn.execute(
        """
        INSERT INTO semantic_memory (key, content, confidence, source, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            content=excluded.content,
            confidence=excluded.confidence,
            source=excluded.source,
            updated_at=excluded.updated_at
        """,
        (key, content, clamp(confidence, 0.0, 0.99), SOURCE, now_iso()),
    )
    conn.commit()


def sleep_cycle_once(state: CoreState) -> CoreState:
    before_sigma = state.sigma

    # Sono artificial: reduz carga externa, reduz latência e recupera energia.
    state.info_external = clamp(state.info_external * 0.56, 0.05, 4.0)
    state.info_self = clamp(state.info_self * 0.88, 0.0, 2.0)
    state.latency = clamp(1.0 + (state.latency - 1.0) * 0.62, 1.0, 3.0)
    state.energy = clamp(state.energy + 0.16, 0.0, 1.0)

    state.sigma = recompute_sigma(state)

    # Dor operacional cai no descanso; bem-estar sobe se sigma/energia melhoram.
    delta = state.sigma - before_sigma
    state.pain_signal = clamp(state.pain_signal * 0.22, 0.0, 5.0)
    state.wellbeing_signal = clamp(state.energy + max(0.0, delta) * 0.45, 0.0, 5.0)

    return state


def find_synthetic_revalidation_targets(conn: sqlite3.Connection, limit: int = 8) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT key, content, confidence, updated_at
        FROM semantic_memory
        WHERE key LIKE 'physical_variation:%:source:synthetic_oracle'
           OR key LIKE 'oracle_validation:%'
           OR key LIKE 'synthetic_oracle:%'
        ORDER BY updated_at DESC
        LIMIT 200
        """
    ).fetchall()

    targets: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row["key"])
        parts = key.split(":")
        pair = None
        condition = None

        if key.startswith("physical_variation:") and len(parts) >= 5:
            pair = parts[1]
            if "condition" in parts:
                idx = parts.index("condition")
                if idx + 1 < len(parts):
                    condition = parts[idx + 1]
        elif key.startswith("oracle_validation:") and len(parts) >= 3:
            condition = parts[1]
            pair = parts[2]
        elif key.startswith("synthetic_oracle:") and len(parts) >= 3:
            condition = parts[1]
            pair = parts[2]

        if pair and condition:
            tid = f"{pair}|{condition}"
            score = 0
            # prioriza casos sintéticos médios e casos sobre triângulo/base crítica
            if "triangle_A>" in pair:
                score += 4
            if ">triangle_A" in pair:
                score += 2
            if "topo_desalinhado" in condition or "toque_forte" in condition:
                score += 3
            if "superficie_inclinada" in condition:
                score += 2
            current = targets.get(tid)
            if current is None or score > current["score"]:
                targets[tid] = {"pair": pair, "condition": condition, "score": score}

    ordered = sorted(targets.values(), key=lambda x: (-x["score"], x["pair"], x["condition"]))
    return ordered[:limit]


def write_report(before: CoreState, after: CoreState, cycles: int, targets: list[dict[str, Any]]) -> Path:
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = EXPORTS_DIR / f"darwin_sleep_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    lines = [
        "DARWIN — Relatório de Sono/Consolidação",
        "=" * 52,
        f"gerado_em: {now_iso()}",
        f"ciclos: {cycles}",
        "",
        "ANTES",
        f"- sigma: {before.sigma:.4f}",
        f"- energy: {before.energy:.4f}",
        f"- info_self: {before.info_self:.4f}",
        f"- info_external: {before.info_external:.4f}",
        f"- latency: {before.latency:.4f}",
        f"- pain: {before.pain_signal:.4f}",
        f"- wellbeing: {before.wellbeing_signal:.4f}",
        "",
        "DEPOIS",
        f"- sigma: {after.sigma:.4f}",
        f"- energy: {after.energy:.4f}",
        f"- info_self: {after.info_self:.4f}",
        f"- info_external: {after.info_external:.4f}",
        f"- latency: {after.latency:.4f}",
        f"- pain: {after.pain_signal:.4f}",
        f"- wellbeing: {after.wellbeing_signal:.4f}",
        "",
        "CASOS SINTÉTICOS PRIORITÁRIOS PARA REVALIDAÇÃO FÍSICA",
    ]

    if targets:
        for i, t in enumerate(targets, start=1):
            lines.append(f"{i}. {t['pair']} | condição={t['condition']} | prioridade={t['score']}")
    else:
        lines.append("(nenhum alvo sintético detectado)")

    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def run_sleep(cycles: int, min_target_sigma: float) -> None:
    conn = connect(DB_PATH)
    try:
        before = load_state(conn)
        state = CoreState(**before.__dict__)

        applied = 0
        for _ in range(max(1, cycles)):
            if state.sigma >= min_target_sigma and state.energy >= 0.90 and state.info_external <= 0.80:
                break
            state = sleep_cycle_once(state)
            applied += 1

        after = state
        save_state(conn, after)

        targets = find_synthetic_revalidation_targets(conn)

        add_episode(
            conn,
            context="sono/consolidação após lote de variação física sintética",
            action_taken=f"sleep_consolidation:{applied}_cycle(s)",
            outcome="recovered" if after.sigma > before.sigma else "stable",
            lesson=(
                "reduziu carga externa, recuperou energia, baixou dor operacional "
                "e separou casos sintéticos para revalidação física futura"
            ),
            sigma_before=before.sigma,
            sigma_after=after.sigma,
        )

        upsert_memory(
            conn,
            key="sleep:post_variation:last_cycle",
            content=(
                f"cycles={applied}; sigma={before.sigma:.4f}->{after.sigma:.4f}; "
                f"energy={before.energy:.4f}->{after.energy:.4f}; "
                f"info_external={before.info_external:.4f}->{after.info_external:.4f}"
            ),
            confidence=0.74,
        )

        for i, t in enumerate(targets, start=1):
            upsert_memory(
                conn,
                key=f"revalidation_target:{i}:{t['pair']}:{t['condition']}",
                content="synthetic_oracle_case_needs_future_physical_check",
                confidence=0.68,
            )

        report = write_report(before, after, applied, targets)

        print("=" * 72)
        print("DARWIN — Sono/Consolidação pós-variação")
        print("=" * 72)
        print(f"Ciclos aplicados: {applied}")
        print("")
        print("ANTES")
        print(f"- sigma          : {before.sigma:.4f}")
        print(f"- energia        : {before.energy:.4f}")
        print(f"- info_external  : {before.info_external:.4f}")
        print(f"- pain           : {before.pain_signal:.4f}")
        print(f"- wellbeing      : {before.wellbeing_signal:.4f}")
        print("")
        print("DEPOIS")
        print(f"- sigma          : {after.sigma:.4f}")
        print(f"- energia        : {after.energy:.4f}")
        print(f"- info_external  : {after.info_external:.4f}")
        print(f"- pain           : {after.pain_signal:.4f}")
        print(f"- wellbeing      : {after.wellbeing_signal:.4f}")
        print("")
        print("Alvos para revalidação física futura:")
        if not targets:
            print("- nenhum alvo detectado")
        else:
            for i, t in enumerate(targets, start=1):
                print(f"- {i}. {t['pair']} | condição={t['condition']} | prioridade={t['score']}")
        print("")
        print(f"Relatório salvo em: {report}")

    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Sono/consolidação do Darwin após variações físicas.")
    parser.add_argument("--cycles", type=int, default=4, help="Número máximo de ciclos de sono.")
    parser.add_argument("--target-sigma", type=float, default=2.0, help="Sigma alvo mínimo.")
    args = parser.parse_args()
    run_sleep(cycles=args.cycles, min_target_sigma=args.target_sigma)


if __name__ == "__main__":
    main()
