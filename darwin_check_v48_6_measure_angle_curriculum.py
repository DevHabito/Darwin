from __future__ import annotations
"""
DARWIN v48.6 — Diagnóstico do currículo de medidas e ângulos

Uso:
    py darwin_check_v48_6_measure_angle_curriculum.py
    py darwin_check_v48_6_measure_angle_curriculum.py --details
"""

import argparse, json, sqlite3
from collections import Counter
from pathlib import Path

DB=Path("darwin_home")/"darwin.db"
TABLE="geometry_measure_curriculum_v48_6"

def pj(x):
    try: return json.loads(x or "{}")
    except Exception: return {}

def fetch(limit):
    if not DB.exists(): raise FileNotFoundError(f"Banco não encontrado: {DB}")
    with sqlite3.connect(DB) as c:
        c.row_factory=sqlite3.Row
        ex=c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?",(TABLE,)).fetchone()
        if not ex: return None,0
        total=c.execute(f"SELECT COUNT(*) n FROM {TABLE}").fetchone()["n"]
        raw=c.execute(f"""SELECT id,timestamp,scenario_id,action_kind,case_id,concept_key,measurement_kind,
        piece_family,hole_family,piece_value,hole_value,delta,tolerance,angle_value,target_angle,
        symmetry_deg,relation,verdict,note,payload_json FROM {TABLE} ORDER BY id DESC LIMIT ?""",(limit,)).fetchall()
    rows=[]
    for r in reversed(raw):
        d={k:r[k] for k in r.keys()}; d["payload"]=pj(d["payload_json"]); rows.append(d)
    return rows,total

def latest(rows):
    done=[r["scenario_id"] for r in rows if r["action_kind"]=="curriculum_complete"]
    if done: return done[-1]
    ids=[r["scenario_id"] for r in rows if r["scenario_id"]]
    return ids[-1] if ids else None

def learned(rows, concept, relation, verdict, case_id=None):
    for r in rows:
        if r["action_kind"]!="concept_learned": continue
        if r["concept_key"]!=concept: continue
        if case_id and r["case_id"]!=case_id: continue
        if r["relation"]!=relation or r["verdict"]!=verdict: continue
        if not r["payload"].get("passed_expectation",False): continue
        return True
    return False

def varied(rows):
    init=[r for r in rows if r["action_kind"]=="curriculum_init"]
    if not init: return False
    p=init[-1]["payload"]
    req=["size_hole","size_large","size_within","size_tolerance","depth_hole","depth_deep","depth_shallow","angle","minimal_rotation"]
    return all(k in p for k in req) and p["size_large"]>p["size_hole"] and p["depth_deep"]>p["depth_hole"]

def rot_ok(rows):
    for r in rows:
        if r["action_kind"]!="concept_learned" or r["concept_key"]!="angle_rotation_minimum": continue
        p=r["payload"]; c=p.get("case",{}); res=p.get("result",{})
        angle=float(c.get("angle_value",0)); target=float(c.get("target_angle",0)); sym=float(c.get("symmetry_deg",90))
        exp=(target-angle)%sym
        if exp>sym/2: exp-=sym
        return abs(float(res.get("delta",999))-exp)<0.001
    return False

def diagnose(rows):
    sid=latest(rows); rs=[r for r in rows if r["scenario_id"]==sid] if sid else []
    counts=Counter(r["action_kind"] for r in rs)
    checks={
        "has_scenario": bool(sid),
        "curriculum_complete": any(r["action_kind"]=="curriculum_complete" for r in rs),
        "measurement_values_varied": varied(rs),
        "learned_larger_than": learned(rs,"larger_smaller","larger_than","reject_size","case_size_larger"),
        "learned_tolerance": learned(rs,"tolerance","within_tolerance","accept","case_size_tolerance"),
        "learned_deeper_than": learned(rs,"deep_shallow","deeper_than","reject_depth","case_depth_deeper"),
        "learned_shallow_accept": learned(rs,"deep_shallow","shallower_or_equal","accept","case_depth_shallow"),
        "learned_angle_rotation": learned(rs,"angle_rotation_minimum","rotation_needed","rotate","case_angle_rotation"),
        "rotation_delta_valid": rot_ok(rs),
        "learned_shape_vs_orientation": learned(rs,"shape_vs_orientation","same_shape_different_orientation","rotate","case_same_shape_orientation"),
        "learned_shape_vs_scale": learned(rs,"shape_vs_scale","same_shape_different_scale","compare_scale","case_same_shape_scale"),
        "learned_different_shape": learned(rs,"shape_not_scale_or_orientation","different_shape","reject_shape","case_different_shape"),
        "enough_concept_events": sum(1 for r in rs if r["action_kind"]=="concept_learned")>=8,
        "enough_compare_events": sum(1 for r in rs if r["action_kind"]=="measure_compare")>=8,
    }
    return {"ok":all(checks.values()),"scenario_id":sid,"rows":rs,"counts":dict(counts),"checks":checks}

def summary(r):
    return f"#{r['id']} | {r['timestamp']} | {r['scenario_id']} | {r['action_kind']} | {r['case_id']} | {r['concept_key']} | {r['measurement_kind']} | delta={float(r['delta']):+.3f} | relation={r['relation'] or '-'} | verdict={r['verdict'] or '-'} | note={r['note']}"

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--details",action="store_true"); ap.add_argument("--recent",type=int,default=800); args=ap.parse_args()
    print("="*72); print("DARWIN v48.6 — DIAGNÓSTICO DO CURRÍCULO DE MEDIDAS E ÂNGULOS"); print("="*72)
    print(f"Banco:  {DB}\nTabela: {TABLE}\nJanela: últimos {args.recent} eventos\n")
    rows,total=fetch(args.recent)
    if rows is None:
        print(f"[ERRO] tabela {TABLE} não existe."); print("Rode primeiro:\n  py darwin_measure_angle_curriculum_v48_6.py"); return 2
    rep=diagnose(rows)
    print("Resumo:"); print(f"- total no banco: {total}"); print(f"- currículo analisado: {rep['scenario_id']}"); print(f"- eventos do currículo: {len(rep['rows'])}")
    for k,v in sorted(rep["counts"].items()): print(f"- {k}: {v}")
    labels={
        "has_scenario":"há currículo analisável","curriculum_complete":"currículo concluiu","measurement_values_varied":"valores quantitativos variaram",
        "learned_larger_than":"aprendeu maior que → rejeitar tamanho","learned_tolerance":"aprendeu tolerância → aceitar diferença pequena",
        "learned_deeper_than":"aprendeu profundo demais → rejeitar profundidade","learned_shallow_accept":"aprendeu raso/cabe → aceitar",
        "learned_angle_rotation":"aprendeu ângulo → rotacionar","rotation_delta_valid":"rotação mínima calculada corretamente",
        "learned_shape_vs_orientation":"aprendeu forma vs orientação","learned_shape_vs_scale":"aprendeu forma vs escala",
        "learned_different_shape":"aprendeu forma diferente ≠ escala/orientação","enough_concept_events":"registrou conceitos suficientes","enough_compare_events":"registrou comparações suficientes"}
    print("\nVerificações:")
    for k,v in rep["checks"].items(): print(f"- {labels.get(k,k)}: {'OK' if v else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if rep['ok'] else 'FALHOU'}")
    print("Leitura:", "Darwin registrou conceitos explícitos de medida, tolerância e ângulo." if rep["ok"] else "Ainda falta evidência completa do currículo v48.6.")
    if args.details:
        print("\nEventos do currículo:")
        for r in rep["rows"]: print("  "+summary(r))
    return 0 if rep["ok"] else 2

if __name__=="__main__":
    raise SystemExit(main())
