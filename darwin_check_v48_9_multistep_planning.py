from __future__ import annotations
"""
DARWIN v48.9 — Diagnóstico de planejamento multi-etapas

Uso:
    py darwin_check_v48_9_multistep_planning.py
    py darwin_check_v48_9_multistep_planning.py --details
"""

import argparse, json, sqlite3
from collections import Counter
from pathlib import Path

DB = Path("darwin_home") / "darwin.db"
TABLE = "geometry_multistep_plans_v48_9"

def pj(x):
    try: return json.loads(x or "{}")
    except Exception: return {}

def fetch(limit):
    if not DB.exists():
        raise FileNotFoundError(f"Banco não encontrado: {DB}")
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        exists = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone()
        if not exists:
            return None, 0
        total = conn.execute(f"SELECT COUNT(*) n FROM {TABLE}").fetchone()["n"]
        raw = conn.execute(f"""SELECT id,timestamp,scenario_id,action_kind,task_id,task_kind,plan_id,revision_id,
                               step_index,step_kind,decision,justification,expected_outcome,observed_outcome,
                               final_status,payload_json
                               FROM {TABLE} ORDER BY id DESC LIMIT ?""", (limit,)).fetchall()
    rows = []
    for r in reversed(raw):
        d = {k: r[k] for k in r.keys()}
        d["payload"] = pj(d["payload_json"])
        rows.append(d)
    return rows, total

def latest(rows):
    done = [r["scenario_id"] for r in rows if r["action_kind"] == "planning_complete" and r["observed_outcome"] == "success"]
    if done:
        return done[-1]
    done = [r["scenario_id"] for r in rows if r["action_kind"] == "planning_complete"]
    if done:
        return done[-1]
    ids = [r["scenario_id"] for r in rows if r["scenario_id"]]
    return ids[-1] if ids else None

def has(rows, action=None, task_id=None, step_kind=None, outcome=None, final_status=None, revision_id=None):
    for r in rows:
        if action is not None and r["action_kind"] != action: continue
        if task_id is not None and r["task_id"] != task_id: continue
        if step_kind is not None and r["step_kind"] != step_kind: continue
        if outcome is not None and r["observed_outcome"] != outcome: continue
        if final_status is not None and r["final_status"] != final_status: continue
        if revision_id is not None and int(r["revision_id"]) != revision_id: continue
        return True
    return False

def idx(rows, action, task_id):
    return [i for i, r in enumerate(rows) if r["action_kind"] == action and r["task_id"] == task_id]

def ordered_task(rows, task_id):
    present = idx(rows, "task_present", task_id)
    create = idx(rows, "plan_create", task_id)
    justify = idx(rows, "step_justify", task_id)
    execute = idx(rows, "step_execute", task_id)
    observe = idx(rows, "step_observe", task_id)
    complete = idx(rows, "task_complete", task_id)
    if not all([present, create, justify, execute, observe, complete]):
        return False
    return present[0] < create[0] < justify[0] < execute[0] < observe[0] < complete[-1]

def has_plan_steps(rows, task_id, min_steps):
    return sum(1 for r in rows if r["action_kind"] == "step_justify" and r["task_id"] == task_id and int(r["revision_id"]) == 0) >= min_steps

def has_revision_steps(rows, task_id, min_steps):
    return sum(1 for r in rows if r["action_kind"] == "revision_step_justify" and r["task_id"] == task_id and int(r["revision_id"]) == 1) >= min_steps

def diagnose(rows):
    sid = latest(rows)
    rs = [r for r in rows if r["scenario_id"] == sid] if sid else []
    counts = Counter(r["action_kind"] for r in rs)

    tasks = ["task_rotate_insert", "task_alternate_shape", "task_reject_oversize", "task_direct_insert", "task_revision_hidden_depth"]

    checks = {
        "has_scenario": bool(sid),
        "planning_complete": has(rs, "planning_complete", outcome="success"),
        "all_tasks_presented": all(has(rs, "task_present", t) for t in tasks),
        "all_tasks_have_plans": all(has(rs, "plan_create", t) for t in tasks),
        "all_tasks_ordered": all(ordered_task(rs, t) for t in tasks),

        "rotate_plan_has_three_steps": has_plan_steps(rs, "task_rotate_insert", 3),
        "rotate_step_executed": has(rs, "step_execute", "task_rotate_insert", "rotate_piece"),
        "rotate_inserted": has(rs, "step_observe", "task_rotate_insert", "insert_primary", "inserted"),
        "rotate_task_complete": has(rs, "task_complete", "task_rotate_insert", final_status="inserted"),

        "alternate_plan_has_four_steps": has_plan_steps(rs, "task_alternate_shape", 4),
        "alternate_selected": has(rs, "step_observe", "task_alternate_shape", "select_alternate_hole", "alternate_selected"),
        "alternate_inserted": has(rs, "step_observe", "task_alternate_shape", "insert_alternate", "inserted"),
        "alternate_task_complete": has(rs, "task_complete", "task_alternate_shape", final_status="inserted"),

        "oversize_plan_rejects": has(rs, "step_observe", "task_reject_oversize", "safe_reject_size", "rejected_size"),
        "oversize_task_complete": has(rs, "task_complete", "task_reject_oversize", final_status="rejected_size"),

        "direct_plan_has_two_steps": has_plan_steps(rs, "task_direct_insert", 2),
        "direct_inserted": has(rs, "step_observe", "task_direct_insert", "insert_primary", "inserted"),
        "direct_task_complete": has(rs, "task_complete", "task_direct_insert", final_status="inserted"),

        "revision_failure_detected": has(rs, "plan_failure_detected", "task_revision_hidden_depth", outcome="hidden_depth_failure"),
        "revision_plan_created": has(rs, "plan_revise", "task_revision_hidden_depth", revision_id=1),
        "revision_has_steps": has_revision_steps(rs, "task_revision_hidden_depth", 3),
        "revision_rejects_depth": has(rs, "step_observe", "task_revision_hidden_depth", "safe_reject", "rejected_depth", revision_id=1),
        "revision_task_complete": has(rs, "task_complete", "task_revision_hidden_depth", final_status="rejected_depth_after_revision"),

        "source_v48_8_available": any(
            r["action_kind"] == "planning_init"
            and r["payload"].get("source_table") == "geometry_contrastive_explanations_v48_8"
            and r["payload"].get("source_status", {}).get("available") is True
            for r in rs
        ),
    }

    return {"ok": all(checks.values()), "scenario_id": sid, "rows": rs, "counts": dict(counts), "checks": checks}

def summary(r):
    info = r["step_kind"] or r["final_status"] or r["observed_outcome"] or "-"
    return f"#{r['id']} | {r['timestamp']} | {r['scenario_id']} | {r['action_kind']} | {r['task_id']} | plan={r['plan_id'] or '-'} | rev={r['revision_id']} | step={info} | observed={r['observed_outcome'] or '-'} | final={r['final_status'] or '-'}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--details", action="store_true")
    ap.add_argument("--recent", type=int, default=1200)
    args = ap.parse_args()

    print("=" * 72)
    print("DARWIN v48.9 — DIAGNÓSTICO DE PLANEJAMENTO MULTI-ETAPAS")
    print("=" * 72)
    print(f"Banco:  {DB}")
    print(f"Tabela: {TABLE}")
    print(f"Janela: últimos {args.recent} eventos\n")

    rows, total = fetch(args.recent)
    if rows is None:
        print(f"[ERRO] tabela {TABLE} não existe.")
        print("Rode primeiro:")
        print("  py darwin_multistep_planning_v48_9.py")
        return 2

    rep = diagnose(rows)

    print("Resumo:")
    print(f"- total no banco: {total}")
    print(f"- cenário analisado: {rep['scenario_id']}")
    print(f"- eventos do cenário: {len(rep['rows'])}")
    for k, v in sorted(rep["counts"].items()):
        print(f"- {k}: {v}")

    labels = {
        "has_scenario": "há cenário analisável",
        "planning_complete": "planejamento concluiu",
        "all_tasks_presented": "todas as tarefas foram apresentadas",
        "all_tasks_have_plans": "todas as tarefas tiveram plano",
        "all_tasks_ordered": "ordem correta por tarefa",

        "rotate_plan_has_three_steps": "rotação: plano tem 3 etapas",
        "rotate_step_executed": "rotação: etapa de girar executada",
        "rotate_inserted": "rotação: inseriu após girar",
        "rotate_task_complete": "rotação: tarefa concluída",

        "alternate_plan_has_four_steps": "alternativo: plano tem 4 etapas",
        "alternate_selected": "alternativo: selecionou outro buraco",
        "alternate_inserted": "alternativo: inseriu no outro buraco",
        "alternate_task_complete": "alternativo: tarefa concluída",

        "oversize_plan_rejects": "tamanho: plano rejeitou com segurança",
        "oversize_task_complete": "tamanho: tarefa concluída",

        "direct_plan_has_two_steps": "direto: plano tem 2 etapas",
        "direct_inserted": "direto: inseriu",
        "direct_task_complete": "direto: tarefa concluída",

        "revision_failure_detected": "revisão: falha detectada",
        "revision_plan_created": "revisão: novo plano criado",
        "revision_has_steps": "revisão: etapas justificadas",
        "revision_rejects_depth": "revisão: rejeitou por profundidade",
        "revision_task_complete": "revisão: tarefa concluída",

        "source_v48_8_available": "fonte v48.8 estava disponível",
    }

    print("\nVerificações:")
    for k, v in rep["checks"].items():
        print(f"- {labels.get(k, k)}: {'OK' if v else 'FALHOU'}")

    print(f"\nResultado final: {'OK' if rep['ok'] else 'FALHOU'}")
    print("Leitura:", "Darwin planejou ações multi-etapas, justificou passos e revisou plano após falha." if rep["ok"] else "Ainda falta evidência completa da v48.9.")

    if args.details:
        print("\nEventos do cenário:")
        for r in rep["rows"]:
            print("  " + summary(r))

    return 0 if rep["ok"] else 2

if __name__ == "__main__":
    raise SystemExit(main())
