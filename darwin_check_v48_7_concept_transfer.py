from __future__ import annotations
"""
DARWIN v48.7 — Diagnóstico de transferência conceitual

Uso:
    py darwin_check_v48_7_concept_transfer.py
    py darwin_check_v48_7_concept_transfer.py --details
"""
import argparse, json, sqlite3
from collections import Counter
from pathlib import Path

DB = Path("darwin_home") / "darwin.db"
TABLE = "geometry_concept_transfer_v48_7"

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
        raw = conn.execute(f"""SELECT id,timestamp,scenario_id,action_kind,problem_id,problem_kind,piece_id,hole_id,
                               recalled_concept,relation,decision,action,explanation,score,outcome,payload_json
                               FROM {TABLE} ORDER BY id DESC LIMIT ?""", (limit,)).fetchall()
    rows = []
    for r in reversed(raw):
        d = {k: r[k] for k in r.keys()}
        d["payload"] = pj(d["payload_json"])
        rows.append(d)
    return rows, total

def latest(rows):
    done = [r["scenario_id"] for r in rows if r["action_kind"] == "transfer_complete" and r["outcome"] == "success"]
    if done:
        return done[-1]
    ids = [r["scenario_id"] for r in rows if r["scenario_id"]]
    return ids[-1] if ids else None

def has(rows, action=None, problem_id=None, concept=None, relation=None, decision=None, outcome=None):
    for r in rows:
        if action is not None and r["action_kind"] != action: continue
        if problem_id is not None and r["problem_id"] != problem_id: continue
        if concept is not None and r["recalled_concept"] != concept: continue
        if relation is not None and r["relation"] != relation: continue
        if decision is not None and r["decision"] != decision: continue
        if outcome is not None and r["outcome"] != outcome: continue
        return True
    return False

def idx(rows, action, problem_id=None):
    out = []
    for i, r in enumerate(rows):
        if r["action_kind"] != action: continue
        if problem_id is not None and r["problem_id"] != problem_id: continue
        out.append(i)
    return out

def ordered_explain_before_action(rows, problem_id):
    p = idx(rows, "problem_present", problem_id)
    rec = idx(rows, "concept_recall", problem_id)
    exp = idx(rows, "explanation_before_action", problem_id)
    dec = idx(rows, "action_decide", problem_id)
    exe = idx(rows, "action_execute", problem_id)
    if not all([p, rec, exp, dec, exe]):
        return False
    return p[0] < rec[0] < exp[0] < dec[0] < exe[0]

def diagnose(rows):
    sid = latest(rows)
    rs = [r for r in rows if r["scenario_id"] == sid] if sid else []
    counts = Counter(r["action_kind"] for r in rs)
    problems = ["problem_oversize", "problem_tolerance", "problem_depth", "problem_rotation", "problem_shape"]
    checks = {
        "has_scenario": bool(sid),
        "transfer_complete": has(rs, "transfer_complete", outcome="success"),
        "all_problems_presented": all(has(rs, "problem_present", p) for p in problems),
        "all_have_recall": all(has(rs, "concept_recall", p) for p in problems),
        "all_explain_before_action": all(ordered_explain_before_action(rs, p) for p in problems),
        "oversize_explained": has(rs, "explanation_before_action", "problem_oversize", "larger_smaller", "larger_than", "reject_size"),
        "tolerance_explained": has(rs, "explanation_before_action", "problem_tolerance", "tolerance", "within_tolerance", "accept"),
        "depth_explained": has(rs, "explanation_before_action", "problem_depth", "deep_shallow", "deeper_than", "reject_depth"),
        "rotation_explained": has(rs, "explanation_before_action", "problem_rotation", "angle_rotation_minimum", "rotation_needed", "rotate"),
        "shape_explained": has(rs, "explanation_before_action", "problem_shape", "shape_not_scale_or_orientation", "different_shape", "reject_shape"),
        "rotation_applied": has(rs, "rotation_applied", "problem_rotation", outcome="success"),
        "rotation_insert_success": has(rs, "insert_success", "problem_rotation", outcome="success"),
        "tolerance_insert_success": has(rs, "insert_success", "problem_tolerance", outcome="success"),
        "safe_reject_oversize": has(rs, "safe_reject", "problem_oversize", decision="reject_size"),
        "safe_reject_depth": has(rs, "safe_reject", "problem_depth", decision="reject_depth"),
        "safe_reject_shape": has(rs, "safe_reject", "problem_shape", decision="reject_shape"),
        "concept_recall_from_v48_6": any(
            r["action_kind"] == "concept_recall" and r["payload"].get("source_table") == "geometry_measure_curriculum_v48_6"
            for r in rs
        ),
    }
    return {"ok": all(checks.values()), "scenario_id": sid, "rows": rs, "counts": dict(counts), "checks": checks}

def summary(r):
    info = r["recalled_concept"] or r["decision"] or r["outcome"] or "-"
    return f"#{r['id']} | {r['timestamp']} | {r['scenario_id']} | {r['action_kind']} | {r['problem_id']} | info={info} | relation={r['relation'] or '-'} | action={r['action'] or '-'} | outcome={r['outcome'] or '-'}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--details", action="store_true")
    ap.add_argument("--recent", type=int, default=800)
    args = ap.parse_args()
    print("="*72)
    print("DARWIN v48.7 — DIAGNÓSTICO DE TRANSFERÊNCIA CONCEITUAL")
    print("="*72)
    print(f"Banco:  {DB}")
    print(f"Tabela: {TABLE}")
    print(f"Janela: últimos {args.recent} eventos\n")
    rows, total = fetch(args.recent)
    if rows is None:
        print(f"[ERRO] tabela {TABLE} não existe.")
        print("Rode primeiro:")
        print("  py darwin_concept_transfer_v48_7.py")
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
        "transfer_complete": "transferência concluiu",
        "all_problems_presented": "todos os problemas foram apresentados",
        "all_have_recall": "todos recordaram conceito",
        "all_explain_before_action": "todos explicaram antes de agir",
        "oversize_explained": "tamanho maior → rejeitar",
        "tolerance_explained": "dentro da tolerância → aceitar",
        "depth_explained": "profundo demais → rejeitar profundidade",
        "rotation_explained": "ângulo desalinhado → rotacionar",
        "shape_explained": "forma diferente ≠ escala/orientação",
        "rotation_applied": "rotação foi aplicada",
        "rotation_insert_success": "inseriu após rotação",
        "tolerance_insert_success": "inseriu caso dentro da tolerância",
        "safe_reject_oversize": "rejeição segura por tamanho",
        "safe_reject_depth": "rejeição segura por profundidade",
        "safe_reject_shape": "rejeição segura por forma",
        "concept_recall_from_v48_6": "recordou conceitos da tabela v48.6",
    }
    print("\nVerificações:")
    for k, v in rep["checks"].items():
        print(f"- {labels.get(k, k)}: {'OK' if v else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if rep['ok'] else 'FALHOU'}")
    print("Leitura:", "Darwin transferiu conceitos da v48.6 para explicar antes de agir." if rep["ok"] else "Ainda falta evidência completa da transferência v48.7.")
    if args.details:
        print("\nEventos do cenário:")
        for r in rep["rows"]:
            print("  " + summary(r))
    return 0 if rep["ok"] else 2

if __name__ == "__main__":
    raise SystemExit(main())
