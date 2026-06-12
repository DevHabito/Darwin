from __future__ import annotations
"""
DARWIN v48.3 — diagnóstico de estratégia após erro

Uso:
    py darwin_check_v48_3_strategy_after_error.py
    py darwin_check_v48_3_strategy_after_error.py --details
"""

import argparse, json, sqlite3
from collections import Counter
from pathlib import Path

DB_PATH = Path("darwin_home") / "darwin.db"
TABLE = "geometry_live_actions_v48_3"


def payload(s):
    try: return json.loads(s or "{}")
    except Exception: return {}


def rows(limit):
    if not DB_PATH.exists(): raise FileNotFoundError(f"Banco não encontrado: {DB_PATH}")
    with sqlite3.connect(DB_PATH) as c:
        c.row_factory = sqlite3.Row
        exists = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone()
        if not exists: return None, 0
        total = c.execute(f"SELECT COUNT(*) n FROM {TABLE}").fetchone()["n"]
        rs = c.execute(f"""SELECT id,timestamp,action_kind,piece_id,hole_id,score,outcome,note,payload_json
                           FROM {TABLE} ORDER BY id DESC LIMIT ?""", (limit,)).fetchall()
    out=[]
    for r in reversed(rs):
        d={k:r[k] for k in r.keys()}
        d["payload"]=payload(d["payload_json"])
        out.append(d)
    return out,total


def idx(rs, action=None, piece=None, hole=None, note_contains=None):
    out=[]
    for i,r in enumerate(rs):
        if action is not None and r["action_kind"] != action: continue
        if piece is not None and r["piece_id"] != piece: continue
        if hole is not None and r["hole_id"] != hole: continue
        if note_contains is not None and note_contains not in str(r["note"]): continue
        out.append(i)
    return out


def first_after(xs, a):
    for x in xs:
        if x > a: return x
    return None


def diagnose(rs):
    counts=Counter(r["action_kind"] for r in rs)
    explore=idx(rs,"controlled_explore_choose")
    col_start=idx(rs,"controlled_collision_start")
    collision=idx(rs,"controlled_collision")
    mem=idx(rs,"error_memory_write")
    strat=idx(rs,"strategy_select")
    execs=idx(rs,"strategy_execute")
    avoid=idx(rs,"avoid_repeat")
    strat_alt=idx(rs,"strategy_select","piece_triangle","hole_square","try_alternate_hole")
    exec_alt=idx(rs,"strategy_execute","piece_triangle","hole_triangle","try_alternate_hole")
    tri_ok=idx(rs,"insert_success","piece_triangle","hole_triangle")
    cir_ok=idx(rs,"insert_success","piece_circle","hole_circle")
    sq_ok=idx(rs,"insert_success","piece_square_rotated","hole_square")
    rot_ok=idx(rs,"rotate_success","piece_square_rotated","hole_square")

    ordered=False; trace=[]
    if explore:
        a=explore[0]
        b=first_after(col_start,a)
        c=first_after(collision,b if b is not None else a)
        d=first_after(mem,c if c is not None else a)
        e=first_after(strat,d if d is not None else a)
        f=first_after(execs,e if e is not None else a)
        g=first_after(tri_ok,f if f is not None else a)
        trace=[a,b,c,d,e,f,g]
        ordered=all(x is not None for x in trace)

    solved_after=False
    if execs:
        s=execs[0]
        solved_after=(first_after(tri_ok,s) is not None and first_after(cir_ok,s) is not None and first_after(sq_ok,s) is not None)

    checks={
        "has_rows": bool(rs),
        "has_controlled_explore_choose": bool(explore),
        "has_controlled_collision_start": bool(col_start),
        "has_controlled_collision": bool(collision),
        "has_error_memory_write": bool(mem),
        "has_strategy_select": bool(strat),
        "has_strategy_execute": bool(execs),
        "strategy_maps_contour_to_try_alternate": bool(strat_alt),
        "strategy_executes_alternate_hole": bool(exec_alt),
        "ordered_strategy_cycle": ordered,
        "has_avoid_repeat": bool(avoid),
        "has_triangle_success": bool(tri_ok),
        "has_circle_success": bool(cir_ok),
        "has_square_success": bool(sq_ok),
        "has_rotate_success": bool(rot_ok),
        "solved_after_strategy": solved_after,
    }
    return {"ok": all(checks.values()), "counts": dict(counts), "checks": checks, "trace": trace}


def summary(r):
    p=r.get("payload",{})
    info=p.get("failure_reason") or p.get("recommendation")
    if not info and isinstance(p.get("strategy"),dict): info=p["strategy"].get("recommendation")
    return f"#{r['id']} | {r['timestamp']} | {r['action_kind']} | {r['piece_id']} -> {r['hole_id']} | score={float(r['score']):.3f} | info={info or '-'} | note={r['note']}"


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--details",action="store_true")
    ap.add_argument("--recent",type=int,default=300)
    args=ap.parse_args()

    print("="*72)
    print("DARWIN v48.3 — DIAGNÓSTICO DE ESTRATÉGIA APÓS ERRO")
    print("="*72)
    print(f"Banco:  {DB_PATH}")
    print(f"Tabela: {TABLE}")
    print(f"Janela: últimos {args.recent} eventos\n")

    rs,total=rows(args.recent)
    if rs is None:
        print("[ERRO] tabela geometry_live_actions_v48_3 não existe.")
        print("Rode primeiro:")
        print("  py darwin_shape_sorter_live_v48_3_strategy_after_error.py")
        return 2

    rep=diagnose(rs)
    print("Resumo de eventos:")
    print(f"- total no banco: {total}")
    print(f"- analisados:     {len(rs)}")
    for k,v in sorted(rep["counts"].items()): print(f"- {k}: {v}")

    labels={
        "has_rows":"há eventos registrados",
        "has_controlled_explore_choose":"escolheu hipótese fraca",
        "has_controlled_collision_start":"iniciou teste seguro",
        "has_controlled_collision":"detectou colisão",
        "has_error_memory_write":"registrou memória do erro",
        "has_strategy_select":"selecionou estratégia",
        "has_strategy_execute":"executou estratégia",
        "strategy_maps_contour_to_try_alternate":"contour_mismatch → try_alternate_hole",
        "strategy_executes_alternate_hole":"executou outro buraco para a mesma peça",
        "ordered_strategy_cycle":"ordem correta: erro → memória → estratégia → execução → sucesso",
        "has_avoid_repeat":"evitou repetir par falho",
        "has_triangle_success":"triângulo foi resolvido",
        "has_circle_success":"círculo foi resolvido",
        "has_square_success":"quadrado foi resolvido",
        "has_rotate_success":"rotação ativa ainda funciona",
        "solved_after_strategy":"resolveu brinquedo após estratégia",
    }

    print("\nVerificações:")
    for k,v in rep["checks"].items(): print(f"- {labels.get(k,k)}: {'OK' if v else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if rep['ok'] else 'FALHOU'}")
    print("Leitura:", "Darwin classificou o erro e escolheu uma estratégia física adequada." if rep["ok"] else "Ainda falta evidência completa da política v48.3.")

    if args.details:
        print("\nEventos recentes:")
        for r in rs[-100:]: print("  "+summary(r))
        print("\nTraço ordenado da estratégia:")
        for i in rep["trace"]:
            print("  - AUSENTE" if i is None else "  "+summary(rs[i]))
    return 0 if rep["ok"] else 2

if __name__ == "__main__":
    raise SystemExit(main())
