from __future__ import annotations

"""
DARWIN v49.28 - Diagnostico Formula Sketchbook

Uso:
    py darwin_check_v49_28_formula_sketchbook.py
    py darwin_check_v49_28_formula_sketchbook.py --details
"""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


DB = Path("darwin_home") / "darwin.db"

SOURCE = "darwin_formula_sketchbook_v49_28"

SK_SESSIONS = "formula_sketch_sessions_v49_28"
SK_SOURCES = "formula_sketch_sources_v49_28"
SK_INTENTIONS = "formula_sketch_intentions_v49_28"
SK_STROKES = "formula_sketch_strokes_v49_28"
SK_REFLECTIONS = "formula_sketch_reflections_v49_28"
SK_HANDOFFS = "formula_sketch_handoffs_v49_28"

REQUIRED_TABLES = [
    SK_SESSIONS,
    SK_SOURCES,
    SK_INTENTIONS,
    SK_STROKES,
    SK_REFLECTIONS,
    SK_HANDOFFS,
]


def pj(value: str | None, fallback: Any = None) -> Any:
    try:
        parsed = json.loads(value or "{}")
    except Exception:
        return {} if fallback is None else fallback
    if fallback is not None and isinstance(fallback, dict) and not isinstance(parsed, dict):
        return fallback
    if fallback is not None and isinstance(fallback, list) and not isinstance(parsed, list):
        return fallback
    return parsed


def connect() -> sqlite3.Connection:
    if not DB.exists():
        raise FileNotFoundError(f"Banco Darwin nao encontrado: {DB}")
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


def rows(conn: sqlite3.Connection, table: str, session_id: str | None = None) -> list[dict[str, Any]]:
    if not table_exists(conn, table):
        return []
    where = ""
    params: tuple[Any, ...] = ()
    if session_id is not None:
        where = " WHERE session_id=?"
        params = (session_id,)
    out = []
    for row in conn.execute(f"SELECT * FROM {table}{where} ORDER BY id ASC", params).fetchall():
        item = {k: row[k] for k in row.keys()}
        item["payload"] = pj(str(item.get("payload_json") or "{}"), {})
        if "evidence_refs_json" in item:
            item["evidence_refs"] = pj(str(item.get("evidence_refs_json") or "[]"), [])
        out.append(item)
    return out


def latest_completed(conn: sqlite3.Connection) -> tuple[str, dict[str, Any]]:
    if not table_exists(conn, SK_SESSIONS):
        return "", {}
    complete_rows = [
        r
        for r in rows(conn, SK_SESSIONS)
        if r.get("phase") == "sketch_complete" and r.get("payload", {}).get("session_complete") is True
    ]
    if not complete_rows:
        return "", {}
    row = complete_rows[-1]
    return str(row["session_id"]), row


def semantic_count(conn: sqlite3.Connection, session_id: str) -> int:
    if not table_exists(conn, "semantic_memory"):
        return 0
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM semantic_memory
        WHERE source=? AND key=?
        """,
        (SOURCE, f"formula_sketch_v49_28:{session_id}"),
    ).fetchone()
    return int(row["n"]) if row else 0


def episode_count(conn: sqlite3.Connection, session_id: str) -> int:
    if not table_exists(conn, "episodes"):
        return 0
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM episodes
        WHERE module=? AND context=?
        """,
        (SOURCE, f"formula_sketch:{session_id}"),
    ).fetchone()
    return int(row["n"]) if row else 0


def prior_count(conn: sqlite3.Connection, table: str) -> int:
    if not table_exists(conn, table):
        return 0
    row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
    return int(row["n"]) if row else 0


def build_report(conn: sqlite3.Connection) -> dict[str, Any]:
    session_id, complete = latest_completed(conn)
    sources = rows(conn, SK_SOURCES, session_id) if session_id else []
    intentions = rows(conn, SK_INTENTIONS, session_id) if session_id else []
    strokes = rows(conn, SK_STROKES, session_id) if session_id else []
    reflections = rows(conn, SK_REFLECTIONS, session_id) if session_id else []
    handoffs = rows(conn, SK_HANDOFFS, session_id) if session_id else []
    payload = complete.get("payload", {}) if complete else {}

    families = {str(s.get("family")) for s in sources if s.get("family")}
    source_kinds = {str(s.get("source_kind")) for s in sources if s.get("source_kind")}
    concept_keys = {str(s.get("concept_key")) for s in sources if s.get("concept_key")}
    rzs_decisions = {str(i.get("rzs_decision")) for i in intentions if i.get("rzs_decision")}
    intention_kinds = {str(i.get("intention_kind")) for i in intentions if i.get("intention_kind")}
    stroke_kinds = {str(s.get("stroke_kind")) for s in strokes if s.get("stroke_kind")}
    layout_payloads = [i.get("payload", {}) for i in intentions if "layout_page" in i.get("payload", {})]
    layout_pages = {int(p["layout_page"]) for p in layout_payloads if p.get("layout_page") is not None}
    layout_slots = {int(p["layout_slot"]) for p in layout_payloads if p.get("layout_slot") is not None}
    mistake_intentions = [i for i in intentions if i.get("payload", {}).get("mistake") is True]
    correction_intentions = [i for i in intentions if i.get("intention_kind") == "correct_previous_mark"]
    fusion_intentions = [i for i in intentions if i.get("intention_kind") == "join_formulas" and str(i.get("formula_b") or "")]
    xs = [float(s.get("x1") or 0.0) for s in strokes] + [float(s.get("x2") or 0.0) for s in strokes]
    ys = [float(s.get("y1") or 0.0) for s in strokes] + [float(s.get("y2") or 0.0) for s in strokes]
    x_span = max(xs) - min(xs) if xs else 0.0
    y_span = max(ys) - min(ys) if ys else 0.0
    handoff = handoffs[-1] if handoffs else {}

    checks = {
        "tables_exist": all(table_exists(conn, t) for t in REQUIRED_TABLES),
        "completed_session": bool(session_id),
        "source_memory_loaded": len(sources) >= 8 and {"geometry_v49_7", "rzs_core"}.issubset(source_kinds),
        "formula_families_present": len(families) >= 5 and {"angle", "weight", "area"}.issubset(families),
        "intentions_written": len(intentions) >= 24 and len(intention_kinds) >= 4,
        "layout_pages_control_overlap": len(layout_payloads) == len(intentions) and layout_pages and layout_slots.issubset({0, 1, 2, 3}),
        "strokes_visible_and_varied": len(strokes) >= 120 and {"text", "line"}.issubset(stroke_kinds) and x_span > 260 and y_span > 180,
        "not_fixed_template": len(concept_keys) >= 8 and len({str(i.get("focus_key")) for i in intentions}) >= 8,
        "darwin_made_mistakes": len(mistake_intentions) >= 2,
        "darwin_corrected_marks": len(correction_intentions) >= 1,
        "formulas_were_joined": len(fusion_intentions) >= 1,
        "rzs_influenced_drawing": len(rzs_decisions) >= 2 and any(d != "continue" for d in rzs_decisions),
        "reflections_written": len(reflections) >= 2,
        "handoff_written": bool(handoff) and int(handoff.get("sketch_ready") or 0) == 1 and int(handoff.get("free_exploration_ready") or 0) == 1,
        "semantic_memory_written": semantic_count(conn, session_id) >= 1 if session_id else False,
        "episode_written": episode_count(conn, session_id) >= 1 if session_id else False,
        "prior_data_still_present": prior_count(conn, "geometry_concepts_v49_7") > 0 and prior_count(conn, "self_model_statements_v49_27") > 0,
        "protected_sources_unchanged": bool(payload.get("protected_sources_unchanged")),
    }
    return {
        "ok": all(checks.values()),
        "session_id": session_id,
        "checks": checks,
        "counts": {
            "sources": len(sources),
            "intentions": len(intentions),
            "strokes": len(strokes),
            "reflections": len(reflections),
            "handoffs": len(handoffs),
            "mistakes": len(mistake_intentions),
            "corrections": len(correction_intentions),
            "fusions": len(fusion_intentions),
            "semantic": semantic_count(conn, session_id) if session_id else 0,
            "episodes": episode_count(conn, session_id) if session_id else 0,
        },
        "families": sorted(families),
        "source_kinds": sorted(source_kinds),
        "concept_keys": sorted(concept_keys),
        "rzs_decisions": sorted(rzs_decisions),
        "intention_kinds": sorted(intention_kinds),
        "layout_pages": sorted(layout_pages),
        "layout_slots": sorted(layout_slots),
        "stroke_kinds": sorted(stroke_kinds),
        "x_span": round(x_span, 3),
        "y_span": round(y_span, 3),
        "handoff": {
            "next_action": handoff.get("next_action", ""),
            "sketch_ready": bool(int(handoff.get("sketch_ready") or 0)) if handoff else False,
            "free_exploration_ready": bool(int(handoff.get("free_exploration_ready") or 0)) if handoff else False,
            "confidence": float(handoff.get("confidence") or 0.0) if handoff else 0.0,
        },
        "payload": payload,
    }


def print_report(report: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.28 - DIAGNOSTICO FORMULA SKETCHBOOK")
    print("=" * 70)
    print(f"- sessao: {report['session_id'] or 'NENHUMA'}")
    c = report["counts"]
    print(
        f"- fontes={c['sources']} intencoes={c['intentions']} tracos={c['strokes']} "
        f"erros={c['mistakes']} correcoes={c['corrections']} fusoes={c['fusions']}"
    )
    print(f"- familias: {', '.join(report['families']) if report['families'] else 'nenhuma'}")
    print(f"- fontes memoria: {', '.join(report['source_kinds']) if report['source_kinds'] else 'nenhuma'}")
    print(f"- RZS: {', '.join(report['rzs_decisions']) if report['rzs_decisions'] else 'nenhum'}")
    print(f"- area visual usada: x_span={report['x_span']} y_span={report['y_span']}")
    print()
    labels = {
        "tables_exist": "tabelas v49.28 existem",
        "completed_session": "sessao completa encontrada",
        "source_memory_loaded": "fontes de memoria carregadas",
        "formula_families_present": "familias de formulas presentes",
        "intentions_written": "intencoes de desenho escritas",
        "layout_pages_control_overlap": "paginas e quadrantes controlam sobreposicao",
        "strokes_visible_and_varied": "tracos visiveis e variados",
        "not_fixed_template": "nao ficou em template fixo",
        "darwin_made_mistakes": "Darwin errou no desenho",
        "darwin_corrected_marks": "Darwin corrigiu marcas",
        "formulas_were_joined": "formulas foram juntadas",
        "rzs_influenced_drawing": "RZS influenciou desenho",
        "reflections_written": "reflexoes escritas",
        "handoff_written": "handoff escrito",
        "semantic_memory_written": "memoria semantica escrita",
        "episode_written": "episodio escrito",
        "prior_data_still_present": "dados anteriores ainda presentes",
        "protected_sources_unchanged": "fontes anteriores preservadas",
    }
    for key, value in report["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'FALHOU'}")
    if report["ok"]:
        print("Leitura: Darwin desenhou formulas como gesto exploratorio, com erro, correcao, fusao e RZS.")
    else:
        print("Leitura: ainda falta evidencia para aceitar o lapis de formulas como marco completo.")
    if details:
        print("\nJSON:")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.28 Formula Sketchbook checker")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    with connect() as conn:
        report = build_report(conn)
    print_report(report, args.details)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
