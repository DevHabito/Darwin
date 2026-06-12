from __future__ import annotations

"""
darwin_sleep_auto_guard.py

Guarda homeostático do Darwin.

Objetivo:
- Ler o estado persistente em darwin_home/darwin.db.
- Decidir se Darwin precisa dormir/consolidar.
- Se necessário, aplicar ciclos de descanso operacional.
- Registrar episódio, histórico de estado e memória semântica.
- Opcionalmente ficar observando em modo --watch.

Uso básico:
    py darwin_sleep_auto_guard.py

Forçar sono:
    py darwin_sleep_auto_guard.py --force

Modo observador:
    py darwin_sleep_auto_guard.py --watch --interval 20

Apenas diagnóstico:
    py darwin_sleep_auto_guard.py --dry-run
"""

import argparse
import sqlite3
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DB_PATH = Path("darwin_home") / "darwin.db"
EXPORTS_DIR = Path("darwin_home") / "exports"
SOURCE = "darwin_sleep_auto_guard"


# ============================================================
# Utilidades
# ============================================================

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"Banco não encontrado: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# ============================================================
# Estado e decisão
# ============================================================

@dataclass
class CoreState:
    sigma: float
    energy: float
    info_self: float
    info_external: float
    latency: float
    pain_signal: float
    wellbeing_signal: float

    def copy(self) -> "CoreState":
        return CoreState(**asdict(self))


@dataclass
class SleepDecision:
    should_sleep: bool
    level: str
    risk_score: float
    reasons: list[str]
    suggested_cycles: int
    target_sigma: float


@dataclass
class SleepResult:
    before: CoreState
    after: CoreState
    decision: SleepDecision
    cycles_applied: int
    slept: bool
    report_path: str


def load_state(conn: sqlite3.Connection) -> CoreState:
    row = conn.execute("SELECT * FROM current_state WHERE id = 1").fetchone()
    if row is None:
        raise RuntimeError("Tabela current_state não possui id=1.")

    return CoreState(
        sigma=safe_float(row["sigma"], 1.0),
        energy=safe_float(row["energy"], 1.0),
        info_self=safe_float(row["info_self"], 0.35),
        info_external=safe_float(row["info_external"], 0.35),
        latency=safe_float(row["latency"], 1.0),
        pain_signal=safe_float(row["pain_signal"], 0.0),
        wellbeing_signal=safe_float(row["wellbeing_signal"], 1.0),
    )


def recompute_sigma(state: CoreState, bandwidth: float = 4.0) -> float:
    info_eff = max(state.info_self + state.info_external, 1e-8)
    latency = max(state.latency, 1e-8)
    return bandwidth / (info_eff * latency)


def decide_sleep(
    state: CoreState,
    *,
    sigma_soft: float = 1.35,
    sigma_hard: float = 1.10,
    energy_soft: float = 0.75,
    energy_hard: float = 0.60,
    info_external_soft: float = 1.35,
    info_external_hard: float = 1.75,
    latency_soft: float = 1.45,
    pain_soft: float = 0.20,
    pain_hard: float = 0.35,
) -> SleepDecision:
    """
    Decide se Darwin precisa dormir.

    A decisão usa um score acumulado, para não depender de um único sinal.
    Um sinal muito ruim pode disparar sono; vários sinais medianos também.
    """
    reasons: list[str] = []
    risk = 0.0

    if state.sigma < sigma_hard:
        risk += 0.38
        reasons.append(f"sigma crítico ({state.sigma:.4f} < {sigma_hard:.2f})")
    elif state.sigma < sigma_soft:
        risk += 0.22
        reasons.append(f"sigma baixo ({state.sigma:.4f} < {sigma_soft:.2f})")

    if state.energy < energy_hard:
        risk += 0.28
        reasons.append(f"energia crítica ({state.energy:.4f} < {energy_hard:.2f})")
    elif state.energy < energy_soft:
        risk += 0.16
        reasons.append(f"energia baixa ({state.energy:.4f} < {energy_soft:.2f})")

    if state.info_external > info_external_hard:
        risk += 0.28
        reasons.append(f"carga externa crítica ({state.info_external:.4f} > {info_external_hard:.2f})")
    elif state.info_external > info_external_soft:
        risk += 0.16
        reasons.append(f"carga externa alta ({state.info_external:.4f} > {info_external_soft:.2f})")

    if state.latency > latency_soft:
        risk += 0.12
        reasons.append(f"latência elevada ({state.latency:.4f} > {latency_soft:.2f})")

    if state.pain_signal >= pain_hard:
        risk += 0.24
        reasons.append(f"dor operacional crítica ({state.pain_signal:.4f} >= {pain_hard:.2f})")
    elif state.pain_signal >= pain_soft:
        risk += 0.13
        reasons.append(f"dor operacional presente ({state.pain_signal:.4f} >= {pain_soft:.2f})")

    if state.wellbeing_signal < 0.90:
        risk += 0.10
        reasons.append(f"bem-estar operacional baixo ({state.wellbeing_signal:.4f} < 0.90)")

    risk = clamp(risk, 0.0, 1.0)

    if risk >= 0.72:
        level = "critical"
        cycles = 5
        target_sigma = 2.35
    elif risk >= 0.45:
        level = "sleep_needed"
        cycles = 4
        target_sigma = 2.15
    elif risk >= 0.25:
        level = "rest_recommended"
        cycles = 2
        target_sigma = 1.85
    else:
        level = "ok"
        cycles = 0
        target_sigma = 1.65

    should_sleep = risk >= 0.45 or state.sigma < sigma_hard or state.energy < energy_hard or state.pain_signal >= pain_hard

    if not reasons:
        reasons.append("estado regulatório estável; sono não necessário agora")

    return SleepDecision(
        should_sleep=should_sleep,
        level=level,
        risk_score=risk,
        reasons=reasons,
        suggested_cycles=cycles,
        target_sigma=target_sigma,
    )


# ============================================================
# Sono/consolidação
# ============================================================

def sleep_cycle_once(state: CoreState) -> CoreState:
    """
    Um ciclo de sono artificial.

    Efeitos:
    - reduz carga externa;
    - reduz um pouco info_self;
    - aproxima latência de 1.0;
    - recupera energia;
    - reduz pain_signal;
    - recalcula sigma;
    - ajusta wellbeing operacional.
    """
    before_sigma = state.sigma

    state.info_external = clamp(state.info_external * 0.56, 0.05, 4.0)
    state.info_self = clamp(state.info_self * 0.88, 0.0, 2.0)
    state.latency = clamp(1.0 + (state.latency - 1.0) * 0.62, 1.0, 3.0)
    state.energy = clamp(state.energy + 0.16, 0.0, 1.0)

    state.sigma = recompute_sigma(state)

    delta_sigma = state.sigma - before_sigma
    state.pain_signal = clamp(state.pain_signal * 0.22, 0.0, 5.0)
    state.wellbeing_signal = clamp(
        0.72 * state.wellbeing_signal + 0.28 * state.energy + max(0.0, delta_sigma) * 0.18,
        0.0,
        5.0,
    )

    return state


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


def add_episode(
    conn: sqlite3.Connection,
    *,
    context: str,
    action_taken: str,
    outcome: str,
    lesson: str,
    sigma_before: float,
    sigma_after: float,
) -> None:
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


def upsert_memory(conn: sqlite3.Connection, key: str, content: str, confidence: float = 0.70) -> None:
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


def write_report(result: SleepResult) -> Path:
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = EXPORTS_DIR / f"darwin_sleep_auto_guard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    lines = [
        "DARWIN — Sleep Auto Guard",
        "=" * 52,
        f"gerado_em: {now_iso()}",
        "",
        "DECISÃO",
        f"- dormiu: {result.slept}",
        f"- nível: {result.decision.level}",
        f"- risco: {result.decision.risk_score:.3f}",
        f"- ciclos_aplicados: {result.cycles_applied}",
        f"- sigma_alvo: {result.decision.target_sigma:.3f}",
        "- motivos:",
    ]
    for reason in result.decision.reasons:
        lines.append(f"  • {reason}")

    lines += [
        "",
        "ANTES",
        f"- sigma: {result.before.sigma:.4f}",
        f"- energy: {result.before.energy:.4f}",
        f"- info_self: {result.before.info_self:.4f}",
        f"- info_external: {result.before.info_external:.4f}",
        f"- latency: {result.before.latency:.4f}",
        f"- pain: {result.before.pain_signal:.4f}",
        f"- wellbeing: {result.before.wellbeing_signal:.4f}",
        "",
        "DEPOIS",
        f"- sigma: {result.after.sigma:.4f}",
        f"- energy: {result.after.energy:.4f}",
        f"- info_self: {result.after.info_self:.4f}",
        f"- info_external: {result.after.info_external:.4f}",
        f"- latency: {result.after.latency:.4f}",
        f"- pain: {result.after.pain_signal:.4f}",
        f"- wellbeing: {result.after.wellbeing_signal:.4f}",
    ]

    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def run_guard_once(
    *,
    db_path: Path,
    dry_run: bool = False,
    force: bool = False,
    max_cycles: int | None = None,
) -> SleepResult:
    conn = connect(db_path)
    try:
        before = load_state(conn)
        state = before.copy()
        decision = decide_sleep(state)

        if force:
            decision.should_sleep = True
            decision.level = "forced"
            decision.risk_score = max(decision.risk_score, 0.45)
            decision.reasons = ["sono forçado pelo tutor"] + decision.reasons
            if decision.suggested_cycles <= 0:
                decision.suggested_cycles = 3
                decision.target_sigma = 2.1

        cycles_limit = max_cycles if max_cycles is not None else decision.suggested_cycles
        cycles_limit = max(0, int(cycles_limit))

        cycles_applied = 0
        slept = False

        if decision.should_sleep and not dry_run:
            for _ in range(cycles_limit):
                if state.sigma >= decision.target_sigma and state.energy >= 0.88 and state.info_external <= 0.90:
                    break
                state = sleep_cycle_once(state)
                cycles_applied += 1
            save_state(conn, state)
            slept = cycles_applied > 0

            action = f"auto_sleep:{cycles_applied}_cycle(s)"
            outcome = "recovered" if state.sigma > before.sigma else "unchanged"
            lesson = (
                f"auto-guard detectou necessidade de descanso; nível={decision.level}; "
                f"risco={decision.risk_score:.3f}; motivos={'; '.join(decision.reasons[:4])}"
            )
            add_episode(
                conn,
                context="guarda homeostático automático",
                action_taken=action,
                outcome=outcome,
                lesson=lesson,
                sigma_before=before.sigma,
                sigma_after=state.sigma,
            )

            upsert_memory(
                conn,
                "sleep:auto_guard:last_decision",
                f"level={decision.level}; risk={decision.risk_score:.3f}; slept={slept}; cycles={cycles_applied}; sigma={before.sigma:.4f}->{state.sigma:.4f}",
                0.78,
            )
            upsert_memory(
                conn,
                "sleep:auto_guard:last_reasons",
                " | ".join(decision.reasons),
                0.72,
            )

        elif not dry_run:
            upsert_memory(
                conn,
                "sleep:auto_guard:last_decision",
                f"level={decision.level}; risk={decision.risk_score:.3f}; slept=False; cycles=0; sigma={before.sigma:.4f}",
                0.62,
            )

        result = SleepResult(
            before=before,
            after=state,
            decision=decision,
            cycles_applied=cycles_applied,
            slept=slept,
            report_path="",
        )

        report = write_report(result)
        result.report_path = str(report)
        return result

    finally:
        conn.close()


def print_result(result: SleepResult, *, dry_run: bool = False) -> None:
    print("=" * 72)
    print("DARWIN — Sleep Auto Guard")
    print("=" * 72)
    if dry_run:
        print("Modo diagnóstico: nenhuma alteração foi salva.")
        print("")

    print("DECISÃO")
    print(f"- deve dormir?     : {'sim' if result.decision.should_sleep else 'não'}")
    print(f"- nível            : {result.decision.level}")
    print(f"- risco            : {result.decision.risk_score:.3f}")
    print(f"- ciclos sugeridos : {result.decision.suggested_cycles}")
    print(f"- ciclos aplicados : {result.cycles_applied}")
    print("")
    print("Motivos:")
    for reason in result.decision.reasons:
        print(f"- {reason}")

    print("")
    print("ANTES")
    print(f"- sigma          : {result.before.sigma:.4f}")
    print(f"- energia        : {result.before.energy:.4f}")
    print(f"- info_external  : {result.before.info_external:.4f}")
    print(f"- latência       : {result.before.latency:.4f}")
    print(f"- pain           : {result.before.pain_signal:.4f}")
    print(f"- wellbeing      : {result.before.wellbeing_signal:.4f}")

    print("")
    print("DEPOIS")
    print(f"- sigma          : {result.after.sigma:.4f}")
    print(f"- energia        : {result.after.energy:.4f}")
    print(f"- info_external  : {result.after.info_external:.4f}")
    print(f"- latência       : {result.after.latency:.4f}")
    print(f"- pain           : {result.after.pain_signal:.4f}")
    print(f"- wellbeing      : {result.after.wellbeing_signal:.4f}")

    print("")
    print(f"Relatório salvo em: {result.report_path}")


def watch_loop(args: argparse.Namespace) -> None:
    print("=" * 72)
    print("DARWIN — Sleep Auto Guard em modo observador")
    print("=" * 72)
    print(f"Intervalo: {args.interval}s")
    print("Pressione Ctrl+C para parar.")
    print("")

    while True:
        try:
            result = run_guard_once(
                db_path=Path(args.db),
                dry_run=args.dry_run,
                force=args.force,
                max_cycles=args.max_cycles,
            )
            compact = (
                f"[{now_iso()}] level={result.decision.level} "
                f"risk={result.decision.risk_score:.2f} "
                f"slept={result.slept} "
                f"sigma={result.before.sigma:.2f}->{result.after.sigma:.2f} "
                f"energy={result.before.energy:.2f}->{result.after.energy:.2f}"
            )
            print(compact)
            time.sleep(max(2, args.interval))
        except KeyboardInterrupt:
            print("\nAuto guard encerrado pelo tutor.")
            return


def main() -> None:
    parser = argparse.ArgumentParser(description="Guarda automático de sono/consolidação do Darwin.")
    parser.add_argument("--db", default=str(DB_PATH), help="Caminho para darwin.db")
    parser.add_argument("--dry-run", action="store_true", help="Mostra decisão sem alterar o banco.")
    parser.add_argument("--force", action="store_true", help="Força sono mesmo se o estado parecer estável.")
    parser.add_argument("--max-cycles", type=int, default=None, help="Limite manual de ciclos aplicados.")
    parser.add_argument("--watch", action="store_true", help="Fica observando e aplica sono quando necessário.")
    parser.add_argument("--interval", type=int, default=20, help="Intervalo do modo --watch em segundos.")
    args = parser.parse_args()

    if args.watch:
        watch_loop(args)
        return

    result = run_guard_once(
        db_path=Path(args.db),
        dry_run=args.dry_run,
        force=args.force,
        max_cycles=args.max_cycles,
    )
    print_result(result, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
