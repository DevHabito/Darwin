from __future__ import annotations

import argparse
import math
import os
import re
import sqlite3
from collections import Counter
from typing import Optional, Iterable

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
    "pair": "#ff7f0e",
    "rule": "#2ca02c",
    "hypothesis": "#9467bd",
    "compare": "#8c564b",
    "fit": "#17becf",
    "affordance": "#d62728",
    "property": "#bcbd22",
    "context": "#e377c2",
    "metric": "#7f7f7f",
    "memory": "#aec7e8",
    "episode": "#98df8a",
    "other": "#c7c7c7",
}

OBJ_RE = re.compile(r"^obj:([^:]+):([^:]+):(.+)$")
PAIR_RE = re.compile(r"^pair:([^>]+)>([^:]+):([^:]+):(.+)$")
RULE_RE = re.compile(r"^rule:(.+)$")
HYP_RE = re.compile(r"^hypothesis:([^>]+)>([^:]+):([^:]+):(.+)$")
COMPARE_RE = re.compile(r"^compare:([^:]+):(.+)$")
FIT_RE = re.compile(r"^fit:([^:]+):(.+)$")


def normalize_key(key: str) -> str:
    key = (key or "").strip()
    return key.split("=", 1)[0].strip()


def short_label(text: str, max_len: int = 28) -> str:
    text = str(text)
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def add_node(G: nx.Graph, node_id: str, label: str, node_type: str) -> None:
    if node_id not in G:
        G.add_node(node_id, label=label, node_type=node_type)


def add_edge(G: nx.Graph, u: str, v: str, label: str = "", weight: float = 1.0) -> None:
    if u == v:
        return
    if G.has_edge(u, v):
        G[u][v]["weight"] = max(G[u][v].get("weight", 1.0), weight)
        prev = G[u][v].get("label", "")
        if label and label not in prev:
            G[u][v]["label"] = ", ".join([p for p in [prev, label] if p])
    else:
        G.add_edge(u, v, label=label, weight=weight)


def add_semantic_row(G: nx.Graph, key: str, content: str, confidence: float) -> None:
    key_core = normalize_key(key)
    conf = max(0.05, min(1.0, float(confidence or 0.0)))

    m = OBJ_RE.match(key_core)
    if m:
        obj_id, relation, value = m.groups()
        obj_node = f"obj::{obj_id}"
        add_node(G, obj_node, obj_id, "object")
        relation_type = "affordance" if relation == "affordance" else "property"
        prop_node = f"{relation}::{value}"
        add_node(G, prop_node, short_label(value), relation_type)
        add_edge(G, obj_node, prop_node, label=relation, weight=conf)
        return

    m = PAIR_RE.match(key_core)
    if m:
        lower, upper, relation, value = m.groups()
        lower_node = f"obj::{lower}"
        upper_node = f"obj::{upper}"
        pair_node = f"pair::{lower}>{upper}"
        result_type = "fit" if relation.startswith("slot") else "property"
        result_node = f"{relation}::{value}"
        add_node(G, lower_node, lower, "object")
        add_node(G, upper_node, upper, "object")
        add_node(G, pair_node, short_label(f"{lower}>{upper}"), "pair")
        add_node(G, result_node, short_label(f"{relation}:{value}"), result_type)
        add_edge(G, lower_node, pair_node, label="base", weight=conf)
        add_edge(G, upper_node, pair_node, label="topo", weight=conf)
        add_edge(G, pair_node, result_node, label=relation, weight=conf)
        return

    m = HYP_RE.match(key_core)
    if m:
        lower, upper, relation, value = m.groups()
        lower_node = f"obj::{lower}"
        upper_node = f"obj::{upper}"
        hyp_node = f"hyp::{lower}>{upper}:{relation}:{value}"
        result_node = f"hyp-result::{relation}:{value}"
        add_node(G, lower_node, lower, "object")
        add_node(G, upper_node, upper, "object")
        add_node(G, hyp_node, short_label(f"{lower}>{upper}"), "hypothesis")
        add_node(G, result_node, short_label(f"{relation}:{value}"), "property")
        add_edge(G, lower_node, hyp_node, label="hip.base", weight=conf)
        add_edge(G, upper_node, hyp_node, label="hip.topo", weight=conf)
        add_edge(G, hyp_node, result_node, label="prevê", weight=conf)
        return

    m = RULE_RE.match(key_core)
    if m:
        raw = m.group(1)
        rule_node = f"rule::{raw}"
        node_type = "context" if ("with_" in raw or "conditional" in raw or "profile" in raw) else "rule"
        add_node(G, rule_node, short_label(raw), node_type)
        known_objects = ["red_ball", "blue_cube", "yellow_triangle", "green_cylinder", "square_A", "square_B", "triangle_A"]
        for obj_name in known_objects:
            if obj_name in raw:
                obj_node = f"obj::{obj_name}"
                add_node(G, obj_node, obj_name, "object")
                add_edge(G, obj_node, rule_node, label="regra", weight=conf)
        return

    m = COMPARE_RE.match(key_core)
    if m:
        relation, payload = m.groups()
        cmp_node = f"cmp::{relation}:{payload}"
        add_node(G, cmp_node, short_label(f"{relation}:{payload}"), "compare")
        parts = re.split(r"[>~|]", payload)
        for obj in parts:
            obj = obj.strip()
            if obj:
                obj_node = f"obj::{obj}"
                add_node(G, obj_node, obj, "object")
                add_edge(G, obj_node, cmp_node, label="compare", weight=conf)
        return

    m = FIT_RE.match(key_core)
    if m:
        relation, value = m.groups()
        fit_node = f"fit::{relation}:{value}"
        add_node(G, fit_node, short_label(f"{relation}:{value}"), "fit")
        return

    mem_node = f"mem::{key_core}"
    add_node(G, mem_node, short_label(key_core), "memory")
    if content and content.lower() not in {"", "true", "false", "none"}:
        val_node = f"content::{content}"
        add_node(G, val_node, short_label(content), "other")
        add_edge(G, mem_node, val_node, label="content", weight=conf)


def build_graph(db_path: str, min_confidence: float) -> tuple[nx.Graph, dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    G = nx.Graph()

    rows = conn.execute(
        "SELECT key, content, confidence FROM semantic_memory ORDER BY confidence DESC, updated_at DESC"
    ).fetchall()

    used_rows = 0
    for row in rows:
        conf = float(row["confidence"] or 0.0)
        if conf < min_confidence:
            continue
        add_semantic_row(G, str(row["key"] or ""), str(row["content"] or ""), conf)
        used_rows += 1

    # métricas do estado atual
    try:
        state = conn.execute("SELECT * FROM current_state ORDER BY id DESC LIMIT 1").fetchone()
        if state:
            state_node = "metric::estado_atual"
            add_node(G, state_node, "estado_atual", "metric")
            for field in ["sigma", "energy", "pain_signal", "wellbeing_signal"]:
                if field in state.keys():
                    mnode = f"metric::{field}:{state[field]}"
                    add_node(G, mnode, short_label(f"{field}={state[field]}"), "metric")
                    add_edge(G, state_node, mnode, label=field, weight=1.0)
    except Exception:
        pass

    # episódios recentes como camada opcional leve
    try:
        eps = conn.execute(
            "SELECT id, module, action_taken, outcome FROM episodes ORDER BY id DESC LIMIT 12"
        ).fetchall()
        for ep in eps:
            ep_node = f"episode::{ep['id']}"
            add_node(G, ep_node, short_label(f"ep{ep['id']}:{ep['module']}"), "episode")
            if ep["action_taken"]:
                act_node = f"action::{ep['action_taken']}"
                add_node(G, act_node, short_label(str(ep["action_taken"])), "other")
                add_edge(G, ep_node, act_node, label="ação", weight=0.7)
            if ep["outcome"]:
                out_node = f"outcome::{ep['outcome']}"
                add_node(G, out_node, short_label(str(ep["outcome"])), "other")
                add_edge(G, ep_node, out_node, label="resultado", weight=0.7)
    except Exception:
        pass

    conn.close()
    meta = {
        "semantic_rows_total": len(rows),
        "semantic_rows_used": used_rows,
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
    }
    return G, meta


def subgraph_by_types(G: nx.Graph, allowed_types: set[str], extra_neighbors_of_objects: bool = False, max_nodes: int = 160) -> nx.Graph:
    selected = {n for n, d in G.nodes(data=True) if d.get("node_type") in allowed_types}
    if extra_neighbors_of_objects:
        for n, d in G.nodes(data=True):
            if d.get("node_type") == "object":
                selected.add(n)
                for nb in G.neighbors(n):
                    if G.nodes[nb].get("node_type") in allowed_types:
                        selected.add(nb)
    H = G.subgraph(selected).copy()
    if H.number_of_nodes() > max_nodes:
        ranked = sorted(H.degree, key=lambda x: x[1], reverse=True)
        keep = [n for n, _ in ranked[:max_nodes]]
        H = H.subgraph(keep).copy()
    return H


def draw_graph(G: nx.Graph, output_path: str, title: str) -> None:
    if G.number_of_nodes() == 0:
        plt.figure(figsize=(10, 6))
        plt.title(title)
        plt.text(0.5, 0.5, "Sem dados para esta camada.", ha="center", va="center", fontsize=16)
        plt.axis("off")
        plt.tight_layout()
        plt.savefig(output_path, dpi=220, bbox_inches="tight")
        plt.close()
        return

    n = max(1, G.number_of_nodes())
    k = max(0.25, 2.0 / math.sqrt(n))
    pos = nx.spring_layout(G, k=k, iterations=250, seed=42)

    fig_w = 18 if n < 120 else 24
    fig_h = 12 if n < 120 else 16
    plt.figure(figsize=(fig_w, fig_h))
    ax = plt.gca()
    ax.set_facecolor("white")
    plt.title(title, fontsize=16)
    plt.axis("off")

    widths = [0.5 + 2.2 * float(data.get("weight", 0.5)) for _, _, data in G.edges(data=True)]
    nx.draw_networkx_edges(G, pos, alpha=0.25, width=widths, edge_color="#888888")

    type_groups = {}
    for node, data in G.nodes(data=True):
        type_groups.setdefault(data.get("node_type", "other"), []).append(node)

    for t, nodes in type_groups.items():
        sizes = [130 + 40 * G.degree[n] for n in nodes]
        nx.draw_networkx_nodes(
            G,
            pos,
            nodelist=nodes,
            node_color=COLOR_MAP.get(t, COLOR_MAP["other"]),
            node_size=sizes,
            alpha=0.92,
            linewidths=0.8,
            edgecolors="#333333",
        )

    labels = {n: G.nodes[n].get("label", n) for n in G.nodes()}
    nx.draw_networkx_labels(G, pos, labels=labels, font_size=8, font_family="sans-serif")

    counts = Counter(data.get("node_type", "other") for _, data in G.nodes(data=True))
    legend = " | ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
    plt.figtext(0.01, 0.01, legend, ha="left", va="bottom", fontsize=9)

    plt.tight_layout()
    plt.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close()


def ensure_export_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def write_summary(path: str, summaries: list[tuple[str, nx.Graph]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("Ressonância por Camadas - Darwin\n")
        f.write("=" * 40 + "\n\n")
        for name, graph in summaries:
            counts = Counter(d.get("node_type", "other") for _, d in graph.nodes(data=True))
            f.write(f"{name}\n")
            f.write(f"  nós: {graph.number_of_nodes()}\n")
            f.write(f"  arestas: {graph.number_of_edges()}\n")
            f.write(f"  tipos: {dict(sorted(counts.items()))}\n\n")


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Exporta ressonâncias por camada da memória do Darwin.")
    parser.add_argument("--db", default=DEFAULT_DB, help="Caminho do banco darwin.db")
    parser.add_argument("--export-dir", default=DEFAULT_EXPORT_DIR, help="Pasta de saída")
    parser.add_argument("--min-confidence", type=float, default=0.30, help="Confiança mínima")
    parser.add_argument("--max-nodes", type=int, default=180, help="Máximo aproximado de nós por camada")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not os.path.exists(args.db):
        print(f"ERRO: banco não encontrado em: {args.db}")
        return 1

    ensure_export_dir(args.export_dir)
    G, meta = build_graph(args.db, min_confidence=args.min_confidence)

    layers = [
        (
            "01_objetos_propriedades",
            "Camada 1 - Objetos, propriedades e affordances",
            subgraph_by_types(G, {"object", "property", "affordance"}, extra_neighbors_of_objects=True, max_nodes=args.max_nodes),
        ),
        (
            "02_empilhamento_pares",
            "Camada 2 - Pares, empilhamentos e encaixes",
            subgraph_by_types(G, {"object", "pair", "fit", "property"}, extra_neighbors_of_objects=True, max_nodes=args.max_nodes),
        ),
        (
            "03_regras_contextos",
            "Camada 3 - Regras, contextos e abstrações",
            subgraph_by_types(G, {"object", "rule", "context", "compare", "metric"}, extra_neighbors_of_objects=True, max_nodes=args.max_nodes),
        ),
        (
            "04_hipoteses_validacoes",
            "Camada 4 - Hipóteses e previsões",
            subgraph_by_types(G, {"object", "hypothesis", "property", "episode", "metric"}, extra_neighbors_of_objects=True, max_nodes=args.max_nodes),
        ),
    ]

    saved = []
    for slug, title, graph in layers:
        out = os.path.join(args.export_dir, f"darwin_memory_{slug}.png")
        draw_graph(graph, out, f"{title} ({graph.number_of_nodes()} nós, {graph.number_of_edges()} arestas)")
        print(f"PNG salvo: {out}")
        saved.append((title, graph))

    summary_path = os.path.join(args.export_dir, "darwin_memory_layers_summary.txt")
    write_summary(summary_path, saved)
    print(f"Resumo salvo: {summary_path}")
    print(f"Grafo total: {meta['nodes']} nós, {meta['edges']} arestas | memórias usadas: {meta['semantic_rows_used']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
