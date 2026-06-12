from __future__ import annotations

import argparse
import math
import os
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Optional

try:
    import networkx as nx
except Exception:
    print("ERRO: o pacote 'networkx' não está instalado.")
    print("Instale com: py -m pip install networkx matplotlib")
    raise

try:
    import matplotlib.pyplot as plt
except Exception:
    print("ERRO: o pacote 'matplotlib' não está instalado.")
    print("Instale com: py -m pip install matplotlib")
    raise

DEFAULT_DB = os.path.join("darwin_home", "darwin.db")
DEFAULT_EXPORT_DIR = os.path.join("darwin_home", "exports")

COLOR_MAP = {
    "object": "#1f77b4",
    "property": "#bcbd22",
    "affordance": "#d62728",
    "pair": "#ff7f0e",
    "physical_result": "#17becf",
    "rule": "#2ca02c",
    "context": "#e377c2",
    "compare": "#8c564b",
    "hypothesis": "#9467bd",
    "predicted": "#c5b0d5",
    "validation": "#2ca02c",
    "physical_observation": "#00a087",
    "cause": "#ff9896",
    "basis": "#9edae5",
    "match": "#8c8c00",
    "rule_validation": "#98df8a",
    "metric": "#7f7f7f",
    "state": "#aec7e8",
    "other": "#dddddd",
}

OBJ_RE = re.compile(r"^obj:([^:]+):([^:]+):(.+)$")
PAIR_RE = re.compile(r"^pair:([^>]+)>([^:]+):([^:]+):(.+)$")
RULE_RE = re.compile(r"^rule:(.+)$")
COMPARE_RE = re.compile(r"^compare:([^:]+):(.+)$")
FIT_RE = re.compile(r"^fit:([^:]+):(.+)$")

# Hipótese: prefixo completo, mas agora separado por subtipo antes do parser genérico
HYP_PREFIX_RE = re.compile(r"^hypothesis:([^>]+)>([^:]+):(.+)$")
HYP_PRED_RE = re.compile(r"^hypothesis:([^>]+)>([^:]+):predicted:(.+)$")
HYP_VALID_RE = re.compile(r"^hypothesis:([^>]+)>([^:]+):validated:(.+)$")
HYP_CAUSE_RE = re.compile(r"^hypothesis:([^>]+)>([^:]+):observed_cause:(.+)$")
HYP_MATCH_RE = re.compile(r"^hypothesis:([^>]+)>([^:]+):match:(.+)$")
HYP_BASIS_RE = re.compile(r"^hypothesis:([^>]+)>([^:]+):basis:(.+)$")
HYP_FOCUS_RE = re.compile(r"^hypothesis:([^>]+)>([^:]+):cause_focus:(.+)$")

PHYSICAL_MANUAL_RE = re.compile(r"^physical_manual:([^>]+)>([^:]+):observed:(.+)$")
RULE_VALIDATION_RE = re.compile(r"^rule_validation:([^>]+)>([^:]+):([^:]+):(.+)$")

META_STANDALONE_RE = re.compile(r"^(basis|predicted|validated|cause_focus|observed_cause|match):(.+)$")

PHYSICAL_RELATION_HINTS = (
    "stack",
    "slot",
    "fit",
    "support",
    "stable",
    "unstable",
    "match",
)

@dataclass
class SemanticRow:
    key: str
    content: str
    confidence: float


def normalize_key(key: str) -> str:
    key = (key or "").strip()
    return key.split("=", 1)[0].strip()


def short_label(text: str, max_len: int = 36) -> str:
    text = str(text)
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def add_node(G: nx.Graph, node_id: str, label: str, node_type: str) -> None:
    if node_id not in G:
        G.add_node(node_id, label=label, node_type=node_type)


def add_edge(G: nx.Graph, u: str, v: str, label: str = "", weight: float = 1.0) -> None:
    if u == v:
        return
    weight = max(0.05, min(2.0, safe_float(weight, 1.0)))
    if G.has_edge(u, v):
        G[u][v]["weight"] = max(G[u][v].get("weight", 1.0), weight)
        prev = G[u][v].get("label", "")
        if label and label not in prev:
            G[u][v]["label"] = ", ".join([p for p in [prev, label] if p])
    else:
        G.add_edge(u, v, label=label, weight=weight)


def discover_object_names(rows: list[SemanticRow]) -> set[str]:
    names: set[str] = set()
    for row in rows:
        key = normalize_key(row.key)
        for regex in (OBJ_RE, PAIR_RE, HYP_PREFIX_RE, PHYSICAL_MANUAL_RE, RULE_VALIDATION_RE):
            m = regex.match(key)
            if not m:
                continue
            if regex is OBJ_RE:
                names.add(m.group(1))
            else:
                names.add(m.group(1))
                names.add(m.group(2))
            break
        m = COMPARE_RE.match(key)
        if m:
            payload = m.group(2)
            for part in re.split(r"[>~|]", payload):
                part = part.strip()
                if part:
                    names.add(part)
    return names


def is_physical_relation(relation: str, value: str) -> bool:
    text = f"{relation}:{value}".lower()
    return any(hint in text for hint in PHYSICAL_RELATION_HINTS)


def obj_node_name(obj: str) -> str:
    return f"obj::{obj}"


def pair_node_name(lower: str, upper: str) -> str:
    return f"pair::{lower}>{upper}"


def hyp_node_name(lower: str, upper: str) -> str:
    return f"hyp::{lower}>{upper}"


def ensure_obj_pair_hyp(G: nx.Graph, lower: str, upper: str, conf: float, include_pair: bool = True, include_hyp: bool = True) -> tuple[str, str, str, str]:
    lower_node = obj_node_name(lower)
    upper_node = obj_node_name(upper)
    pair_node = pair_node_name(lower, upper)
    hyp_node = hyp_node_name(lower, upper)

    add_node(G, lower_node, lower, "object")
    add_node(G, upper_node, upper, "object")

    if include_pair:
        add_node(G, pair_node, short_label(f"{lower}>{upper}"), "pair")
        add_edge(G, lower_node, pair_node, "base", conf)
        add_edge(G, upper_node, pair_node, "topo", conf)

    if include_hyp:
        add_node(G, hyp_node, short_label(f"H: {lower}>{upper}"), "hypothesis")
        add_edge(G, lower_node, hyp_node, "hip.base", conf)
        add_edge(G, upper_node, hyp_node, "hip.topo", conf)

    return lower_node, upper_node, pair_node, hyp_node


def connect_to_mentioned_objects(G: nx.Graph, source: str, text: str, object_names: set[str], label: str, weight: float) -> None:
    hay = (text or "").lower()
    for obj in sorted(object_names):
        if obj.lower() in hay:
            on = obj_node_name(obj)
            add_node(G, on, obj, "object")
            add_edge(G, source, on, label, weight)


def add_semantic_row(G: nx.Graph, row: SemanticRow, object_names: set[str]) -> None:
    key = normalize_key(row.key)
    content = str(row.content or "")
    conf = max(0.05, min(1.0, row.confidence))

    # --- Camada 5: validações, observações, causas e bases ---
    # Estes parsers vêm ANTES do parser genérico de hypothesis para a Camada 5 não ficar vazia.
    m = HYP_VALID_RE.match(key)
    if m:
        lower, upper, result = m.groups()
        _, _, pair_node, hyp_node = ensure_obj_pair_hyp(G, lower, upper, conf)
        val_node = f"validation::{lower}>{upper}:{result}"
        add_node(G, val_node, short_label(f"validou:{result}"), "validation")
        add_edge(G, hyp_node, val_node, "validated", conf)
        add_edge(G, pair_node, val_node, "resultado", conf)
        return

    m = HYP_CAUSE_RE.match(key)
    if m:
        lower, upper, cause = m.groups()
        _, _, pair_node, hyp_node = ensure_obj_pair_hyp(G, lower, upper, conf)
        cause_node = f"cause::{lower}>{upper}:{cause}"
        add_node(G, cause_node, short_label(f"causa:{cause}"), "cause")
        add_edge(G, hyp_node, cause_node, "observed_cause", conf)
        add_edge(G, pair_node, cause_node, "causa", conf)
        return

    m = HYP_MATCH_RE.match(key)
    if m:
        lower, upper, match_value = m.groups()
        _, _, pair_node, hyp_node = ensure_obj_pair_hyp(G, lower, upper, conf)
        match_node = f"match::{lower}>{upper}:{match_value}"
        add_node(G, match_node, short_label(f"match:{match_value}"), "match")
        add_edge(G, hyp_node, match_node, "match", conf)
        add_edge(G, pair_node, match_node, "match", conf)
        return

    m = HYP_BASIS_RE.match(key)
    if m:
        lower, upper, basis = m.groups()
        _, _, pair_node, hyp_node = ensure_obj_pair_hyp(G, lower, upper, conf)
        basis_node = f"basis::{lower}>{upper}:{basis}"
        add_node(G, basis_node, short_label(f"basis:{basis}"), "basis")
        add_edge(G, hyp_node, basis_node, "basis", conf)
        add_edge(G, pair_node, basis_node, "base lógica", conf * 0.7)
        return

    m = HYP_FOCUS_RE.match(key)
    if m:
        lower, upper, focus = m.groups()
        _, _, pair_node, hyp_node = ensure_obj_pair_hyp(G, lower, upper, conf)
        focus_node = f"cause_focus::{lower}>{upper}:{focus}"
        add_node(G, focus_node, short_label(f"focus:{focus}"), "cause")
        add_edge(G, hyp_node, focus_node, "cause_focus", conf)
        add_edge(G, pair_node, focus_node, "foco", conf * 0.7)
        return

    m = PHYSICAL_MANUAL_RE.match(key)
    if m:
        lower, upper, observed = m.groups()
        _, _, pair_node, hyp_node = ensure_obj_pair_hyp(G, lower, upper, conf)
        obs_node = f"physical_observation::{lower}>{upper}:{observed}"
        add_node(G, obs_node, short_label(f"manual:{observed}"), "physical_observation")
        add_edge(G, pair_node, obs_node, "observed", conf)
        add_edge(G, hyp_node, obs_node, "mundo real", conf * 0.8)
        return

    m = RULE_VALIDATION_RE.match(key)
    if m:
        lower, upper, rule_kind, status = m.groups()
        _, _, pair_node, hyp_node = ensure_obj_pair_hyp(G, lower, upper, conf)
        rv_node = f"rule_validation::{lower}>{upper}:{rule_kind}:{status}"
        add_node(G, rv_node, short_label(f"{rule_kind}:{status}"), "rule_validation")
        add_edge(G, pair_node, rv_node, "rule_validation", conf)
        add_edge(G, hyp_node, rv_node, "confirma regra", conf * 0.8)
        return

    # --- Ontologia de objeto ---
    m = OBJ_RE.match(key)
    if m:
        obj_id, relation, value = m.groups()
        obj_node = obj_node_name(obj_id)
        add_node(G, obj_node, obj_id, "object")
        node_type = "affordance" if relation == "affordance" else "property"
        prop_node = f"objprop::{relation}:{value}"
        add_node(G, prop_node, short_label(value), node_type)
        add_edge(G, obj_node, prop_node, relation, conf)
        return

    # --- Mundo físico relacional ---
    m = PAIR_RE.match(key)
    if m:
        lower, upper, relation, value = m.groups()
        _, _, pair_node, _ = ensure_obj_pair_hyp(G, lower, upper, conf, include_hyp=False)
        result_type = "physical_result" if is_physical_relation(relation, value) else "property"
        result_node = f"pairres::{relation}:{value}"
        add_node(G, result_node, short_label(f"{relation}:{value}"), result_type)
        add_edge(G, pair_node, result_node, relation, conf)
        return

    # --- Hipóteses e previsões ---
    m = HYP_PRED_RE.match(key)
    if m:
        lower, upper, prediction = m.groups()
        _, _, _, hyp_node = ensure_obj_pair_hyp(G, lower, upper, conf)
        pred_node = f"pred::{prediction}"
        add_node(G, pred_node, short_label(f"predicted:{prediction}"), "predicted")
        add_edge(G, hyp_node, pred_node, "predicted", conf)
        return

    # fallback de hipótese genérica: mantém visível sem confundir com validação
    m = HYP_PREFIX_RE.match(key)
    if m:
        lower, upper, tail = m.groups()
        _, _, _, hyp_node = ensure_obj_pair_hyp(G, lower, upper, conf)
        other_node = f"hyp_other::{lower}>{upper}:{tail}"
        add_node(G, other_node, short_label(tail), "hypothesis")
        add_edge(G, hyp_node, other_node, "hyp.detail", conf)
        return

    # --- Regras, contextos, comparações ---
    m = RULE_RE.match(key)
    if m:
        raw = m.group(1)
        node_type = "context" if any(x in raw for x in ["with_", "conditional", "profile", "global", "context"]) else "rule"
        rule_node = f"rule::{raw}"
        add_node(G, rule_node, short_label(raw), node_type)
        connect_to_mentioned_objects(G, rule_node, raw, object_names, "regra", conf)
        connect_to_mentioned_objects(G, rule_node, content, object_names, "regra", conf)
        return

    m = COMPARE_RE.match(key)
    if m:
        relation, payload = m.groups()
        cmp_node = f"cmp::{relation}:{payload}"
        add_node(G, cmp_node, short_label(f"{relation}:{payload}"), "compare")
        parts = [p.strip() for p in re.split(r"[>~|]", payload) if p.strip()]
        for obj in parts:
            on = obj_node_name(obj)
            add_node(G, on, obj, "object")
            add_edge(G, on, cmp_node, "compare", conf)
        connect_to_mentioned_objects(G, cmp_node, content, object_names, "compare", conf)
        return

    m = FIT_RE.match(key)
    if m:
        relation, value = m.groups()
        fit_node = f"fit::{relation}:{value}"
        add_node(G, fit_node, short_label(f"{relation}:{value}"), "physical_result")
        connect_to_mentioned_objects(G, fit_node, content, object_names, "fit", conf)
        return

    # fallback metacognitivo solto
    m = META_STANDALONE_RE.match(key)
    if m:
        kind, detail = m.groups()
        node_type = {
            "basis": "basis",
            "predicted": "predicted",
            "validated": "validation",
            "cause_focus": "cause",
            "observed_cause": "cause",
            "match": "match",
        }.get(kind, "other")
        node = f"meta::{kind}:{detail}"
        add_node(G, node, short_label(f"{kind}:{detail}"), node_type)
        connect_to_mentioned_objects(G, node, detail, object_names, kind, conf)
        connect_to_mentioned_objects(G, node, content, object_names, kind, conf)
        return


def build_graph(db_path: str, min_confidence: float) -> tuple[nx.Graph, dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    raw_rows = conn.execute(
        "SELECT key, content, confidence FROM semantic_memory ORDER BY confidence DESC, updated_at DESC"
    ).fetchall()
    rows = [
        SemanticRow(str(r["key"] or ""), str(r["content"] or ""), safe_float(r["confidence"], 0.0))
        for r in raw_rows
        if safe_float(r["confidence"], 0.0) >= min_confidence
    ]

    object_names = discover_object_names(rows)
    G = nx.Graph()
    for row in rows:
        add_semantic_row(G, row, object_names)

    try:
        state = conn.execute("SELECT * FROM current_state ORDER BY id DESC LIMIT 1").fetchone()
        if state is not None:
            state_node = "state::estado_atual"
            add_node(G, state_node, "estado_atual", "state")
            for field in ["sigma", "energy", "pain_signal", "wellbeing_signal", "latency", "info_load", "info_external", "info_self"]:
                if field in state.keys() and state[field] is not None:
                    metric_node = f"metric::{field}:{state[field]}"
                    add_node(G, metric_node, short_label(f"{field}={state[field]}"), "metric")
                    add_edge(G, state_node, metric_node, field, 1.0)
    except Exception:
        pass

    conn.close()
    return G, {
        "semantic_rows_used": len(rows),
        "semantic_rows_total": len(raw_rows),
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "object_names": sorted(object_names),
    }


def remove_isolates(G: nx.Graph) -> nx.Graph:
    H = G.copy()
    H.remove_nodes_from(list(nx.isolates(H)))
    return H


def trim_by_degree(G: nx.Graph, max_nodes: int, preferred_types: Optional[set[str]] = None) -> nx.Graph:
    if G.number_of_nodes() <= max_nodes:
        return G.copy()
    preferred_types = preferred_types or set()

    def score(item: tuple[str, int]) -> tuple[int, int]:
        node, deg = item
        type_bonus = 1000 if G.nodes[node].get("node_type") in preferred_types else 0
        return (type_bonus + deg, deg)

    ranked = sorted(G.degree, key=score, reverse=True)
    keep = [n for n, _ in ranked[:max_nodes]]
    return G.subgraph(keep).copy()


def subgraph_by_types(
    G: nx.Graph,
    allowed_types: set[str],
    *,
    keep_isolates: bool = False,
    max_nodes: int = 180,
    preferred_types: Optional[set[str]] = None,
) -> nx.Graph:
    selected = [n for n, d in G.nodes(data=True) if d.get("node_type") in allowed_types]
    H = G.subgraph(selected).copy()
    if not keep_isolates:
        H = remove_isolates(H)
    H = trim_by_degree(H, max_nodes, preferred_types=preferred_types)
    return H


def physical_manual_only(G: nx.Graph, max_nodes: int = 140) -> nx.Graph:
    selected: set[str] = set()
    for node, data in G.nodes(data=True):
        text = node.lower()
        if any(x in text for x in ["square_a", "square_b", "triangle_a"]):
            selected.add(node)
            selected.update(G.neighbors(node))
    H = G.subgraph(selected).copy()
    H = remove_isolates(H)
    return trim_by_degree(H, max_nodes, preferred_types={"object", "pair", "validation", "physical_observation"})


def node_size(G: nx.Graph, node: str) -> float:
    deg = G.degree[node]
    t = G.nodes[node].get("node_type", "other")
    base = 130
    if t == "object":
        base += 180
    elif t in {"pair", "hypothesis", "state"}:
        base += 100
    elif t in {"validation", "physical_observation", "physical_result"}:
        base += 70
    return base + 42 * deg


def draw_graph(G: nx.Graph, output_path: str, title: str) -> None:
    if G.number_of_nodes() == 0:
        plt.figure(figsize=(12, 7))
        plt.title(title, fontsize=16)
        plt.text(0.5, 0.5, "Sem dados para esta camada.", ha="center", va="center", fontsize=16)
        plt.axis("off")
        plt.tight_layout()
        plt.savefig(output_path, dpi=220, bbox_inches="tight")
        plt.close()
        return

    n = max(1, G.number_of_nodes())
    k = max(0.22, 2.15 / math.sqrt(n))
    pos = nx.spring_layout(G, k=k, iterations=320, seed=42)
    fig_w = 18 if n < 100 else 24
    fig_h = 12 if n < 100 else 16

    plt.figure(figsize=(fig_w, fig_h))
    ax = plt.gca()
    ax.set_facecolor("white")
    plt.title(title, fontsize=17)
    plt.axis("off")

    widths = [0.5 + 2.3 * safe_float(data.get("weight", 0.5), 0.5) for _, _, data in G.edges(data=True)]
    nx.draw_networkx_edges(G, pos, alpha=0.22, width=widths, edge_color="#777777")

    grouped: dict[str, list[str]] = {}
    for node, data in G.nodes(data=True):
        grouped.setdefault(data.get("node_type", "other"), []).append(node)

    for t, nodes in grouped.items():
        nx.draw_networkx_nodes(
            G,
            pos,
            nodelist=nodes,
            node_color=COLOR_MAP.get(t, COLOR_MAP["other"]),
            node_size=[node_size(G, n) for n in nodes],
            alpha=0.93,
            linewidths=0.8,
            edgecolors="#333333",
        )

    labels = {node: G.nodes[node].get("label", node) for node in G.nodes()}
    nx.draw_networkx_labels(G, pos, labels=labels, font_size=8, font_family="sans-serif")

    counts = Counter(data.get("node_type", "other") for _, data in G.nodes(data=True))
    legend = " | ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
    plt.figtext(0.01, 0.01, legend, ha="left", va="bottom", fontsize=9)

    plt.tight_layout()
    plt.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close()


def ensure_export_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def write_summary(path: str, summaries: list[tuple[str, nx.Graph]], meta: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("Darwin Memory Graph Layers v3 - Resumo\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Memórias semânticas usadas: {meta['semantic_rows_used']}\n")
        f.write(f"Memórias semânticas totais: {meta['semantic_rows_total']}\n")
        f.write(f"Nós totais no grafo-base: {meta['nodes']}\n")
        f.write(f"Arestas totais no grafo-base: {meta['edges']}\n")
        f.write(f"Objetos detectados: {', '.join(meta['object_names'])}\n\n")
        for name, graph in summaries:
            counts = Counter(d.get("node_type", "other") for _, d in graph.nodes(data=True))
            f.write(f"{name}\n")
            f.write(f"  nós: {graph.number_of_nodes()}\n")
            f.write(f"  arestas: {graph.number_of_edges()}\n")
            f.write(f"  tipos: {dict(sorted(counts.items()))}\n\n")


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Exporta ressonâncias por camada v3 do grafo de memória do Darwin.")
    parser.add_argument("--db", default=DEFAULT_DB, help="Caminho para o arquivo darwin.db")
    parser.add_argument("--export-dir", default=DEFAULT_EXPORT_DIR, help="Pasta de saída")
    parser.add_argument("--min-confidence", type=float, default=0.30, help="Confiança mínima para incluir memória")
    parser.add_argument("--max-nodes", type=int, default=180, help="Máximo aproximado de nós por camada")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not os.path.exists(args.db):
        print(f"ERRO: banco não encontrado em: {args.db}")
        return 1

    ensure_export_dir(args.export_dir)
    G, meta = build_graph(args.db, min_confidence=args.min_confidence)

    layers = [
        (
            "01_ontologia_objetos",
            "Camada 1 - Ontologia dos objetos",
            subgraph_by_types(G, {"object", "property", "affordance"}, max_nodes=args.max_nodes, preferred_types={"object"}),
        ),
        (
            "02_mundo_fisico_relacional",
            "Camada 2 - Mundo físico relacional",
            subgraph_by_types(G, {"object", "pair", "physical_result"}, max_nodes=args.max_nodes, preferred_types={"object", "pair"}),
        ),
        (
            "03_regras_abstracoes",
            "Camada 3 - Regras, contextos e abstrações",
            subgraph_by_types(G, {"object", "rule", "context", "compare"}, max_nodes=args.max_nodes, preferred_types={"object", "context"}),
        ),
        (
            "04_hipoteses_previsoes",
            "Camada 4 - Hipóteses e previsões",
            subgraph_by_types(G, {"object", "hypothesis", "predicted"}, max_nodes=args.max_nodes, preferred_types={"object", "hypothesis"}),
        ),
        (
            "05_validacoes_causas_bases",
            "Camada 5 - Validações, causas, bases e observações físicas",
            subgraph_by_types(
                G,
                {"object", "pair", "hypothesis", "validation", "physical_observation", "cause", "basis", "match", "rule_validation"},
                max_nodes=args.max_nodes,
                preferred_types={"validation", "physical_observation", "cause", "match", "rule_validation"},
            ),
        ),
        (
            "06_estado_interno",
            "Camada 6 - Estado interno",
            subgraph_by_types(G, {"state", "metric"}, keep_isolates=True, max_nodes=60),
        ),
        (
            "07_bercario_fisico_manual",
            "Camada 7 - Berçário físico manual",
            physical_manual_only(G, max_nodes=args.max_nodes),
        ),
    ]

    summaries: list[tuple[str, nx.Graph]] = []
    for slug, title, graph in layers:
        out_path = os.path.join(args.export_dir, f"darwin_memory_{slug}.png")
        draw_graph(graph, out_path, f"{title} ({graph.number_of_nodes()} nós, {graph.number_of_edges()} arestas)")
        print(f"PNG salvo: {out_path}")
        summaries.append((title, graph))

    summary_path = os.path.join(args.export_dir, "darwin_memory_layers_v3_summary.txt")
    write_summary(summary_path, summaries, meta)
    print(f"Resumo salvo: {summary_path}")
    print(f"Grafo-base: {meta['nodes']} nós, {meta['edges']} arestas | memórias usadas: {meta['semantic_rows_used']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
