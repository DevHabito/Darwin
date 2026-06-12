from __future__ import annotations
"""
DARWIN — Freeze Baseline v48.6 Stable

Uso:
  py darwin_freeze_v48_6_stable.py --dry-run
  py darwin_freeze_v48_6_stable.py
  py darwin_freeze_v48_6_stable.py --include-logs
"""

import argparse, hashlib, json, shutil, sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.cwd()
HOME = ROOT / "darwin_home"
BASELINES = ROOT / "baselines"

REQ = [
    "darwin_v61_nursery_v47.py",
    "darwin_tension_persistence_v47.py",
    "darwin_home.py",
    "darwin_shape_sorter_nursery_v48.py",
    "darwin_shape_sorter_v48_test.py",
    "darwin_shape_sorter_live_v48_1_active_rotation.py",
    "darwin_check_v48_1_live_rotation.py",
    "darwin_shape_sorter_live_v48_2_controlled_error.py",
    "darwin_check_v48_2_controlled_error.py",
    "darwin_repair_v48_3_1_strategy_order.py",
    "darwin_shape_sorter_live_v48_3_1_strategy_after_error.py",
    "darwin_check_v48_3_1_strategy_after_error.py",
    "darwin_shape_sorter_live_v48_4_strategy_generalization.py",
    "darwin_check_v48_4_strategy_generalization.py",
    "darwin_shape_sorter_live_v48_5_variation_generalization.py",
    "darwin_check_v48_5_variation_generalization.py",
    "darwin_measure_angle_curriculum_v48_6.py",
    "darwin_check_v48_6_measure_angle_curriculum.py",
]

OPT = [
    "darwin_check_v47_tensions.py",
    "darwin_tension_dashboard_v47.py",
    "darwin_sleep_auto_guard.py",
    "darwin_sleep_consolidation.py",
    "darwin_shape_sorter_live_v48_1.py",
    "darwin_shape_sorter_live_v48_3_strategy_after_error.py",
    "darwin_check_v48_3_strategy_after_error.py",
]

V47_ZERO = [
    "tension_cases", "tension_events", "tension_probes", "tension_outcomes",
    "tension_resolution_routines", "tension_resolution_steps",
    "tension_context_comparisons", "tension_prediction_influences",
    "tension_hypothesis_lineage", "tension_cognitive_cycle_reports",
    "tension_cycle_memory_reviews",
]

V48_MIN = {
    "geometry_shapes_v48": 3,
    "geometry_pieces_v48": 6,
    "geometry_holes_v48": 3,
    "geometry_fit_attempts_v48": 27,
    "geometry_rules_v48": 3,
    "geometry_spatial_concepts_v48": 5,
}

README = """DARWIN — Baseline v48.6 Stable
==============================

Marco v48.6:
Darwin registrou conceitos explícitos de medida, tolerância e ângulo.

Cadeia preservada:
- v48.0: encaixe físico;
- v48.1: rotação ativa;
- v48.2: erro controlado;
- v48.3.1: estratégia após erro com ordem auditável;
- v48.4: generalização por tipo de falha;
- v48.5: generalização por variação de ambiente;
- v48.6: currículo quantitativo explícito.

Conceitos v48.6:
- maior que → rejeitar tamanho;
- diferença dentro da tolerância → aceitar;
- profundo demais → rejeitar profundidade;
- raso/cabe → aceitar;
- ângulo desalinhado → rotacionar;
- rotação mínima calculada corretamente;
- forma vs orientação;
- forma vs escala;
- forma diferente não é escala nem orientação.

Regra:
Não editar esta baseline diretamente. Use apenas como ponto de retorno/auditoria.

Próximo passo sugerido:
v48.7 — transferência conceitual para novos problemas.
Darwin deve usar os conceitos aprendidos em v48.6 para explicar por que uma peça falha
ou encaixa em um novo cenário, antes de agir.
"""

def stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")

def iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def ps(kind, msg):
    print(f"[{kind:<7}] {msg}")

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def table_names(conn):
    return [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]

def count(conn, table):
    if table not in set(table_names(conn)):
        return None
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except Exception:
        return None

def payload(s):
    try:
        return json.loads(s or "{}")
    except Exception:
        return {}

def rows(conn, table):
    if table not in set(table_names(conn)):
        return []
    cur = conn.execute(f"SELECT * FROM {table} ORDER BY id ASC")
    out = []
    for r in cur.fetchall():
        d = {k: r[k] for k in r.keys()}
        d["payload"] = payload(str(d.get("payload_json") or "{}"))
        out.append(d)
    return out

def has(rs, kind):
    return any(r.get("action_kind") == kind for r in rs)

def live_basic(conn, table, min_insert=3):
    rs = rows(conn, table)
    c = Counter(r.get("action_kind", "") for r in rs)
    checks = {
        "has_rows": bool(rs),
        "has_rotate_success": has(rs, "rotate_success"),
        "has_insert_success": sum(1 for r in rs if r.get("action_kind") == "insert_success") >= min_insert,
    }
    return {"total": len(rs), "counts": dict(c), "checks": checks, "ready": all(checks.values())}

def live_v48_2(conn):
    rs = rows(conn, "geometry_live_actions_v48_2")
    c = Counter(r.get("action_kind", "") for r in rs)
    checks = {
        "has_rows": bool(rs),
        "has_controlled_explore_choose": has(rs, "controlled_explore_choose"),
        "has_controlled_collision": has(rs, "controlled_collision"),
        "has_error_memory_write": has(rs, "error_memory_write"),
        "has_avoid_repeat": has(rs, "avoid_repeat"),
        "has_rotate_success": has(rs, "rotate_success"),
        "has_insert_success": sum(1 for r in rs if r.get("action_kind") == "insert_success") >= 3,
    }
    return {"total": len(rs), "counts": dict(c), "checks": checks, "ready": all(checks.values())}

def live_v48_3_1(conn):
    rs = rows(conn, "geometry_live_actions_v48_3_1")
    c = Counter(r.get("action_kind", "") for r in rs)
    checks = {
        "has_rows": bool(rs),
        "has_strategy_select": has(rs, "strategy_select"),
        "has_strategy_execute": has(rs, "strategy_execute"),
        "has_controlled_collision": has(rs, "controlled_collision"),
        "has_error_memory_write": has(rs, "error_memory_write"),
        "has_rotate_success": has(rs, "rotate_success"),
        "has_insert_success": sum(1 for r in rs if r.get("action_kind") == "insert_success") >= 3,
    }
    return {"total": len(rs), "counts": dict(c), "checks": checks, "ready": all(checks.values())}

def live_v48_4(conn):
    rs = rows(conn, "geometry_live_actions_v48_4")
    c = Counter(r.get("action_kind", "") for r in rs)
    notes = {str(r.get("note", "")) for r in rs if r.get("action_kind") == "strategy_select"}
    checks = {
        "has_rows": bool(rs),
        "try_alternate_hole": "try_alternate_hole" in notes,
        "reject_pair_size": "reject_pair_size" in notes,
        "reject_pair_depth": "reject_pair_depth" in notes,
        "cautious_exploration": "cautious_exploration" in notes,
        "rotate_piece": "rotate_piece" in notes,
        "rotate_success": has(rs, "rotate_success"),
        "insert_success": sum(1 for r in rs if r.get("action_kind") == "insert_success") >= 3,
    }
    return {"total": len(rs), "counts": dict(c), "checks": checks, "ready": all(checks.values())}

def latest_done(rs, action):
    done = [r.get("scenario_id") for r in rs if r.get("action_kind") == action]
    if done:
        return str(done[-1])
    ids = [r.get("scenario_id") for r in rs if r.get("scenario_id")]
    return str(ids[-1]) if ids else None

def live_v48_5(conn):
    allr = rows(conn, "geometry_live_actions_v48_5")
    sid = latest_done(allr, "scenario_complete")
    rs = [r for r in allr if r.get("scenario_id") == sid] if sid else []
    c = Counter(r.get("action_kind", "") for r in rs)
    piece_ids = {r.get("piece_id") for r in rs if r.get("piece_id")}
    hole_ids = {r.get("hole_id") for r in rs if r.get("hole_id")}
    checks = {
        "has_rows": bool(rs),
        "scenario_complete": has(rs, "scenario_complete"),
        "randomized_ids": len(piece_ids) >= 6 and len(hole_ids) >= 3 and all(str(x).startswith("object_") for x in piece_ids) and all(str(x).startswith("aperture_") for x in hole_ids),
        "strategy_count": sum(1 for r in rs if r.get("action_kind") == "strategy_select") >= 5,
        "rotate_success": has(rs, "rotate_success"),
        "insert_success": sum(1 for r in rs if r.get("action_kind") == "insert_success") >= 3,
    }
    return {"scenario_id": sid, "total": len(rs), "global_total": len(allr), "counts": dict(c), "checks": checks, "ready": all(checks.values())}

def learned(rs, concept, relation, verdict, case_id):
    for r in rs:
        if r.get("action_kind") != "concept_learned":
            continue
        if r.get("concept_key") != concept or r.get("case_id") != case_id:
            continue
        if r.get("relation") != relation or r.get("verdict") != verdict:
            continue
        if not r.get("payload", {}).get("passed_expectation", False):
            continue
        return True
    return False

def values_varied_v48_6(rs):
    init = [r for r in rs if r.get("action_kind") == "curriculum_init"]
    if not init:
        return False
    p = init[-1].get("payload", {})
    req = ["size_hole", "size_large", "size_within", "size_tolerance", "depth_hole", "depth_deep", "depth_shallow", "angle", "minimal_rotation"]
    return all(k in p for k in req) and p["size_large"] > p["size_hole"] and p["depth_deep"] > p["depth_hole"]

def rotation_delta_ok(rs):
    for r in rs:
        if r.get("action_kind") != "concept_learned" or r.get("concept_key") != "angle_rotation_minimum":
            continue
        p = r.get("payload", {})
        case = p.get("case", {})
        result = p.get("result", {})
        angle = float(case.get("angle_value", 0.0))
        target = float(case.get("target_angle", 0.0))
        sym = float(case.get("symmetry_deg", 90.0))
        expected = (target - angle) % sym
        if expected > sym / 2:
            expected -= sym
        return abs(float(result.get("delta", 999.0)) - expected) < 0.001
    return False

def live_v48_6(conn):
    allr = rows(conn, "geometry_measure_curriculum_v48_6")
    sid = latest_done(allr, "curriculum_complete")
    rs = [r for r in allr if r.get("scenario_id") == sid] if sid else []
    c = Counter(r.get("action_kind", "") for r in rs)
    checks = {
        "has_rows": bool(rs),
        "curriculum_complete": has(rs, "curriculum_complete"),
        "measurement_values_varied": values_varied_v48_6(rs),
        "learned_larger_than": learned(rs, "larger_smaller", "larger_than", "reject_size", "case_size_larger"),
        "learned_tolerance": learned(rs, "tolerance", "within_tolerance", "accept", "case_size_tolerance"),
        "learned_deeper_than": learned(rs, "deep_shallow", "deeper_than", "reject_depth", "case_depth_deeper"),
        "learned_shallow_accept": learned(rs, "deep_shallow", "shallower_or_equal", "accept", "case_depth_shallow"),
        "learned_angle_rotation": learned(rs, "angle_rotation_minimum", "rotation_needed", "rotate", "case_angle_rotation"),
        "rotation_delta_valid": rotation_delta_ok(rs),
        "learned_shape_vs_orientation": learned(rs, "shape_vs_orientation", "same_shape_different_orientation", "rotate", "case_same_shape_orientation"),
        "learned_shape_vs_scale": learned(rs, "shape_vs_scale", "same_shape_different_scale", "compare_scale", "case_same_shape_scale"),
        "learned_different_shape": learned(rs, "shape_not_scale_or_orientation", "different_shape", "reject_shape", "case_different_shape"),
        "enough_concept_events": sum(1 for r in rs if r.get("action_kind") == "concept_learned") >= 8,
        "enough_compare_events": sum(1 for r in rs if r.get("action_kind") == "measure_compare") >= 8,
    }
    return {"scenario_id": sid, "total": len(rs), "global_total": len(allr), "counts": dict(c), "checks": checks, "ready": all(checks.values())}

def sqlite_summary(db_path):
    out = {
        "status": "not_found",
        "tables": {},
        "v47_clean": False,
        "v48_geometry_ready": False,
        "v48_1_live_rotation_ready": False,
        "v48_2_controlled_error_ready": False,
        "v48_3_1_strategy_ready": False,
        "v48_4_strategy_generalization_ready": False,
        "v48_5_variation_generalization_ready": False,
        "v48_6_measure_angle_curriculum_ready": False,
        "baseline_ready": False,
        "baseline_warnings": [],
    }
    if not db_path.exists():
        return out
    out["status"] = "ok"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        names = table_names(conn)
        for name in names:
            out["tables"][name] = count(conn, name)

        warnings = []
        for t in V47_ZERO:
            n = out["tables"].get(t, 0)
            if n not in (0, None):
                warnings.append(f"v47_not_clean:{t}={n}")

        for t, minimum in V48_MIN.items():
            n = out["tables"].get(t, 0)
            if n is None or int(n) < minimum:
                warnings.append(f"v48_missing_or_low:{t}={n}, expected>={minimum}")

        live1 = live_basic(conn, "geometry_live_actions_v48_1")
        live2 = live_v48_2(conn)
        live31 = live_v48_3_1(conn)
        live4 = live_v48_4(conn)
        live5 = live_v48_5(conn)
        live6 = live_v48_6(conn)

        out["live_v48_1_summary"] = live1
        out["live_v48_2_summary"] = live2
        out["live_v48_3_1_summary"] = live31
        out["live_v48_4_summary"] = live4
        out["live_v48_5_summary"] = live5
        out["live_v48_6_summary"] = live6

        pairs = [
            ("v48_1_live_rotation_ready", "v48_1_live_rotation_not_ready", live1),
            ("v48_2_controlled_error_ready", "v48_2_controlled_error_not_ready", live2),
            ("v48_3_1_strategy_ready", "v48_3_1_strategy_not_ready", live31),
            ("v48_4_strategy_generalization_ready", "v48_4_strategy_generalization_not_ready", live4),
            ("v48_5_variation_generalization_ready", "v48_5_variation_generalization_not_ready", live5),
            ("v48_6_measure_angle_curriculum_ready", "v48_6_measure_angle_curriculum_not_ready", live6),
        ]
        for flag, warn, live in pairs:
            out[flag] = bool(live.get("ready"))
            if not live.get("ready"):
                warnings.append(warn)

        out["v47_clean"] = not any(w.startswith("v47_not_clean:") for w in warnings)
        out["v48_geometry_ready"] = not any(w.startswith("v48_missing_or_low:") for w in warnings)
        out["baseline_ready"] = all(out[k] for k in [
            "v47_clean",
            "v48_geometry_ready",
            "v48_1_live_rotation_ready",
            "v48_2_controlled_error_ready",
            "v48_3_1_strategy_ready",
            "v48_4_strategy_generalization_ready",
            "v48_5_variation_generalization_ready",
            "v48_6_measure_angle_curriculum_ready",
        ])
        out["baseline_warnings"] = warnings
    finally:
        conn.close()
    return out

def copy_file(src, dst, dry, manifest, label=""):
    rel = src.relative_to(ROOT)
    if not src.exists():
        ps("AUSENTE", str(rel))
        manifest["missing"].append(str(rel))
        return
    if dry:
        ps("DRYRUN", f"copiaria {rel}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    item = {"source": str(src), "dest": str(dst), "size": src.stat().st_size, "sha256": sha(src)}
    if label:
        item["label"] = label
    manifest["files"].append(item)
    ps("OK", str(rel))

def copy_dir(src, dst, dry, manifest, include_logs=False):
    rel = src.relative_to(ROOT)
    if not src.exists():
        ps("AUSENTE", str(rel))
        manifest["missing"].append(str(rel))
        return
    if not src.is_dir():
        copy_file(src, dst, dry, manifest)
        return
    if rel.as_posix().endswith("logs") and not include_logs:
        ps("PULOU", f"{rel} (use --include-logs para incluir)")
        return
    if dry:
        n = sum(1 for p in src.rglob("*") if p.is_file())
        ps("DRYRUN", f"copiaria diretório {rel} -> {n} arquivo(s)")
        return
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    n = sum(1 for p in dst.rglob("*") if p.is_file())
    manifest["directories"].append({"source": str(src), "dest": str(dst), "files": n})
    ps("DIR", f"{rel} -> {n} arquivo(s)")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--include-logs", action="store_true")
    args = ap.parse_args()

    missing = [f for f in REQ if not (ROOT / f).exists()]
    if not (HOME / "darwin.db").exists():
        missing.append("darwin_home/darwin.db")
    if missing:
        raise FileNotFoundError("Arquivos essenciais ausentes:\n" + "\n".join(f"- {x}" for x in missing))

    bdir = BASELINES / f"baseline_v48_6_stable_{stamp()}"
    manifest = {
        "baseline": "v48.6_stable",
        "project_root": str(ROOT),
        "baseline_dir": str(bdir),
        "files": [],
        "directories": [],
        "missing": [],
        "sqlite_summary": {},
        "created_at": iso(),
    }

    print("=" * 72)
    print("DARWIN — FREEZE BASELINE v48.6 STABLE")
    print("=" * 72)
    print(f"Raiz do projeto: {ROOT}")
    print(f"Destino:         {bdir}")
    print(f"Dry-run:         {args.dry_run}\n")

    srcdir = bdir / "source_files"
    homedir = bdir / "darwin_home"

    print("Arquivos essenciais:")
    for f in REQ:
        copy_file(ROOT / f, srcdir / f, args.dry_run, manifest, "required")

    print("\nArquivos opcionais:")
    for f in OPT:
        if (ROOT / f).exists():
            copy_file(ROOT / f, srcdir / f, args.dry_run, manifest, "optional")
        else:
            ps("AUSENTE", f)

    print("\ndarwin_home/")
    for item in ["darwin.db", "snapshots", "exports", "backups"]:
        src = HOME / item
        dst = homedir / item
        if src.is_dir():
            copy_dir(src, dst, args.dry_run, manifest, args.include_logs)
        else:
            copy_file(src, dst, args.dry_run, manifest)

    logs = HOME / "logs"
    if logs.exists():
        copy_dir(logs, homedir / "logs", args.dry_run, manifest, args.include_logs)

    manifest["sqlite_summary"] = sqlite_summary(HOME / "darwin.db")

    if args.dry_run:
        ps("DRYRUN", "criaria README_BASELINE.txt e manifest.json")
        ps("DRYRUN", f"criaria ZIP: {bdir.with_suffix('.zip')}")
    else:
        bdir.mkdir(parents=True, exist_ok=True)
        (bdir / "README_BASELINE.txt").write_text(README, encoding="utf-8")
        (bdir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        ps("OK", "README_BASELINE.txt")
        ps("OK", "manifest.json")
        zip_path = bdir.with_suffix(".zip")
        if zip_path.exists():
            zip_path.unlink()
        shutil.make_archive(str(bdir), "zip", root_dir=bdir)
        print(f"\nZIP criado: {zip_path}")

    s = manifest["sqlite_summary"]
    live6 = s.get("live_v48_6_summary", {})

    print("\nResumo SQLite:")
    for k in [
        "status",
        "v47_clean",
        "v48_geometry_ready",
        "v48_1_live_rotation_ready",
        "v48_2_controlled_error_ready",
        "v48_3_1_strategy_ready",
        "v48_4_strategy_generalization_ready",
        "v48_5_variation_generalization_ready",
        "v48_6_measure_angle_curriculum_ready",
        "baseline_ready",
    ]:
        print(f"- {k}: {s.get(k)}")
    print(f"- v48_6_curriculum_id: {live6.get('scenario_id')}")
    print(f"- v48_6_curriculum_events_total: {live6.get('total')}")
    print(f"- v48_6_action_counts: {live6.get('counts')}")

    warnings = s.get("baseline_warnings") or []
    if warnings:
        print("- baseline_warnings:")
        for w in warnings:
            print(f"  - {w}")

    if not args.dry_run:
        for t in V47_ZERO + list(V48_MIN.keys()) + [
            "geometry_live_actions_v48_1",
            "geometry_live_actions_v48_2",
            "geometry_live_actions_v48_3_1",
            "geometry_live_actions_v48_4",
            "geometry_live_actions_v48_5",
            "geometry_measure_curriculum_v48_6",
        ]:
            print(f"- table:{t}: {s.get('tables', {}).get(t)}")
        print(f"\nBaseline v48.6 congelada com sucesso em: {bdir}")
        print(f"Pacote ZIP: {bdir.with_suffix('.zip')}")
        print("Próximo passo: iniciar v48.7 a partir da pasta operacional atual, não desta baseline.")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
