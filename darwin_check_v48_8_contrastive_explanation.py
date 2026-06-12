from __future__ import annotations
"""
DARWIN v48.8 — Diagnóstico de explicação causal contrastiva

Uso:
    py darwin_check_v48_8_contrastive_explanation.py
    py darwin_check_v48_8_contrastive_explanation.py --details
"""

import argparse, json, sqlite3
from collections import Counter
from pathlib import Path

DB = Path("darwin_home") / "darwin.db"
TABLE = "geometry_contrastive_explanations_v48_8"

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
                               relation,decision,action,rejected_alternative,contrast_reason,primary_contrast,
                               score,outcome,payload_json
                               FROM {TABLE} ORDER BY id DESC LIMIT ?""", (limit,)).fetchall()
    rows = []
    for r in reversed(raw):
        d = {k: r[k] for k in r.keys()}
        d["payload"] = pj(d["payload_json"])
        rows.append(d)
    return rows, total

def latest(rows):
    done = [r["scenario_id"] for r in rows if r["action_kind"] == "contrastive_complete" and r["outcome"] == "success"]
    if done:
        return done[-1]
    ids = [r["scenario_id"] for r in rows if r["scenario_id"]]
    return ids[-1] if ids else None

def has(rows, action=None, problem_id=None, relation=None, decision=None, primary=None, alt=None, outcome=None):
    for r in rows:
        if action is not None and r["action_kind"] != action: continue
        if problem_id is not None and r["problem_id"] != problem_id: continue
        if relation is not None and r["relation"] != relation: continue
        if decision is not None and r["decision"] != decision: continue
        if primary is not None and r["primary_contrast"] != primary: continue
        if alt is not None and r["rejected_alternative"] != alt: continue
        if outcome is not None and r["outcome"] != outcome: continue
        return True
    return False

def idx(rows, action, problem_id):
    return [i for i, r in enumerate(rows) if r["action_kind"] == action and r["problem_id"] == problem_id]

def ordered(rows, problem_id):
    chain = [
        idx(rows, "problem_present", problem_id),
        idx(rows, "causal_assess", problem_id),
        idx(rows, "contrastive_explanation", problem_id),
        idx(rows, "alternative_rejected", problem_id),
        idx(rows, "action_decide", problem_id),
        idx(rows, "action_execute", problem_id),
    ]
    if not all(chain):
        return False
    return chain[0][0] < chain[1][0] < chain[2][0] < chain[3][0] < chain[4][0] < chain[5][0]

def at_least_alts(rows, problem_id, n=2):
    return sum(1 for r in rows if r["action_kind"] == "alternative_rejected" and r["problem_id"] == problem_id) >= n

def diagnose(rows):
    sid = latest(rows)
    rs = [r for r in rows if r["scenario_id"] == sid] if sid else []
    counts = Counter(r["action_kind"] for r in rs)

    problems = ["contrast_oversize", "contrast_depth", "contrast_rotation", "contrast_insert", "contrast_shape"]

    checks = {
        "has_scenario": bool(sid),
        "contrastive_complete": has(rs, "contrastive_complete", outcome="success"),
        "all_problems_presented": all(has(rs, "problem_present", p) for p in problems),
        "all_have_contrastive_explanation": all(has(rs, "contrastive_explanation", p) for p in problems),
        "all_have_alternative_rejections": all(at_least_alts(rs, p, 2) for p in problems),
        "all_ordered": all(ordered(rs, p) for p in problems),

        "reject_size_not_rotate": has(rs, "contrastive_explanation", "contrast_oversize", "larger_than", "reject_size", "reject_size_not_rotate"),
        "oversize_rejected_rotate": has(rs, "alternative_rejected", "contrast_oversize", alt="rotate"),
        "oversize_safe_reject": has(rs, "safe_reject", "contrast_oversize", decision="reject_size"),

        "reject_depth_not_size_or_rotate": has(rs, "contrastive_explanation", "contrast_depth", "deeper_than", "reject_depth", "reject_depth_not_size_or_rotate"),
        "depth_rejected_rotate": has(rs, "alternative_rejected", "contrast_depth", alt="rotate"),
        "depth_safe_reject": has(rs, "safe_reject", "contrast_depth", decision="reject_depth"),

        "rotate_not_reject": has(rs, "contrastive_explanation", "contrast_rotation", "rotation_needed", "rotate", "rotate_not_reject"),
        "rotation_rejected_size": has(rs, "alternative_rejected", "contrast_rotation", alt="reject_size"),
        "rotation_applied": has(rs, "rotation_applied", "contrast_rotation", outcome="success"),
        "rotation_insert_success": has(rs, "insert_success", "contrast_rotation", outcome="success"),

        "insert_not_reject": has(rs, "contrastive_explanation", "contrast_insert", "within_tolerance", "accept", "insert_not_reject"),
        "insert_rejected_size": has(rs, "alternative_rejected", "contrast_insert", alt="reject_size"),
        "insert_success": has(rs, "insert_success", "contrast_insert", outcome="success"),

        "reject_shape_not_rotate_or_scale": has(rs, "contrastive_explanation", "contrast_shape", "different_shape", "reject_shape", "reject_not_rotate_or_scale"),
        "shape_rejected_rotate": has(rs, "alternative_rejected", "contrast_shape", alt="rotate"),
        "shape_rejected_scale": has(rs, "alternative_rejected", "contrast_shape", alt="scale"),
        "shape_safe_reject": has(rs, "safe_reject", "contrast_shape", decision="reject_shape"),

        "source_v48_7_available": any(
            r["action_kind"] == "contrastive_init"
            and r["payload"].get("source_table") == "geometry_concept_transfer_v48_7"
            and r["payload"].get("source_status", {}).get("available") is True
            for r in rs
        ),
    }

    return {"ok": all(checks.values()), "scenario_id": sid, "rows": rs, "counts": dict(counts), "checks": checks}

def summary(r):
    info = r["primary_contrast"] or r["rejected_alternative"] or r["decision"] or r["outcome"] or "-"
    return f"#{r['id']} | {r['timestamp']} | {r['scenario_id']} | {r['action_kind']} | {r['problem_id']} | info={info} | relation={r['relation'] or '-'} | decision={r['decision'] or '-'} | alt={r['rejected_alternative'] or '-'} | outcome={r['outcome'] or '-'}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--details", action="store_true")
    ap.add_argument("--recent", type=int, default=1000)
    args = ap.parse_args()

    print("=" * 72)
    print("DARWIN v48.8 — DIAGNÓSTICO DE EXPLICAÇÃO CAUSAL CONTRASTIVA")
    print("=" * 72)
    print(f"Banco:  {DB}")
    print(f"Tabela: {TABLE}")
    print(f"Janela: últimos {args.recent} eventos\n")

    rows, total = fetch(args.recent)
    if rows is None:
        print(f"[ERRO] tabela {TABLE} não existe.")
        print("Rode primeiro:")
        print("  py darwin_contrastive_explanation_v48_8.py")
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
        "contrastive_complete": "explicação contrastiva concluiu",
        "all_problems_presented": "todos os problemas foram apresentados",
        "all_have_contrastive_explanation": "todos têm explicação contrastiva",
        "all_have_alternative_rejections": "todos rejeitaram alternativas",
        "all_ordered": "ordem correta: avaliar → contrastar → decidir → agir",

        "reject_size_not_rotate": "tamanho: rejeitar em vez de girar",
        "oversize_rejected_rotate": "tamanho rejeitou alternativa girar",
        "oversize_safe_reject": "tamanho teve rejeição segura",

        "reject_depth_not_size_or_rotate": "profundidade: rejeitar sem confundir com tamanho/rotação",
        "depth_rejected_rotate": "profundidade rejeitou alternativa girar",
        "depth_safe_reject": "profundidade teve rejeição segura",

        "rotate_not_reject": "orientação: girar em vez de rejeitar",
        "rotation_rejected_size": "orientação rejeitou alternativa rejeitar tamanho",
        "rotation_applied": "rotação foi aplicada",
        "rotation_insert_success": "inseriu após rotação",

        "insert_not_reject": "tolerância: inserir em vez de rejeitar",
        "insert_rejected_size": "tolerância rejeitou alternativa rejeitar tamanho",
        "insert_success": "inserção teve sucesso",

        "reject_shape_not_rotate_or_scale": "forma: rejeitar, não tratar como rotação/escala",
        "shape_rejected_rotate": "forma rejeitou alternativa girar",
        "shape_rejected_scale": "forma rejeitou alternativa escala",
        "shape_safe_reject": "forma teve rejeição segura",

        "source_v48_7_available": "fonte v48.7 estava disponível",
    }

    print("\nVerificações:")
    for k, v in rep["checks"].items():
        print(f"- {labels.get(k, k)}: {'OK' if v else 'FALHOU'}")

    print(f"\nResultado final: {'OK' if rep['ok'] else 'FALHOU'}")
    print("Leitura:", "Darwin produziu explicações causais contrastivas antes de agir." if rep["ok"] else "Ainda falta evidência completa da v48.8.")

    if args.details:
        print("\nEventos do cenário:")
        for r in rep["rows"]:
            print("  " + summary(r))

    return 0 if rep["ok"] else 2

if __name__ == "__main__":
    raise SystemExit(main())
