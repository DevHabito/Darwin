from __future__ import annotations

import argparse
import math
import os
import re
import sqlite3
import sys
from collections import Counter
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


def add_edge(G: nx.Graph, u: str, v: str, *, label: str = "", weight: float = 1.0) -> None:
    if u == v:
        return
    if G.has_edge(u, v):
        G[u][v]["weight"] = max(G[u][v].get("weight", 1.0), weight)
        old_label = G[u][v].get("label", "")
        if label and label not in old_label:
            G[u][v]["label"] = ", ".join([p for p in [old_label, label] if p])
    else:
        G.add_edge(u, v, label=label, weight=weight)


OBJ_RE = re.compile(r"^obj:([^:]+):([^:]+):(.+)$")
PAIR_RE = re.compile(r"^pair:([^>]+)>([^:]+):([^:]+):(.+)$")
RULE_RE = re.compile(r"^rule:(.+)$")
HYP_RE = re.compile(r"^hypothesis:([^>]+)>([^:]+):([^:]+):(.+)$")
COMPARE_RE = re.compile(r"^compare:([^:]+):(.+)$")


def add_semantic_row(G: nx.Graph, key: str, content: str, confidence: float) -> None:
    key_core = normalize_key(key)
    conf = max(0.05, min(1.0, float(confidence or 0.0)))

    m = OBJ_RE.match(key_core)
    if m:
        obj_id, relation, value = m.groups()
        obj_node = f"obj::{obj_id}"
        add_node(G, obj_node, obj_id, "object")
        relation_type = relation if relation in {"affordance"} else "property"
        prop_node = f"{relation}::{value}"
        add_node(G, prop_node, short_label(value), relation_type if relation_type != "property" else (relation if relation in COLOR_MAP else "property"))
        add_edge(G, obj_node, prop_node, label=relation, weight=conf)
        return

    m = PAIR_RE.match(key_core)
    if m:
        lower, upper, relation, value = m.groups()
        lower_node = f"obj::{lower}"
        upper_node = f"obj::{upper}"
        pair_node = f"pair::{lower}>{upper}"
        result_node = f"{relation}::{value}"
        add_node(G, lower_node, lower, "object")
        add_node(G, upper_node, upper, "object")
        add_node(G, pair_node, short_label(f"{lower}>{upper}"), "pair")
        add_node(G, result_node, short_label(f"{relation}:{value}"), "property")
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
        add_node(G, lower_node, lower, "object")
        add_node(G, upper_node, upper, "object")
        add_node(G, hyp_node, short_label(f"{lower}>{upper}:{relation}:{value}"), "hypothesis")
        add_edge(G, lower_node, hyp_node, label="hip.base", weight=conf)
        add_edge(G, upper_node, hyp_node, label="hip.topo", weight=conf)
        return

    m = RULE_RE.match(key_core)
    if m:
        raw = m.group(1)
        rule_node = f"rule::{raw}"
        node_type = "context" if "with_" in raw or ":conditional_" in raw else "rule"
        add_node(G, rule_node, short_label(raw), node_type)
        # tenta conectar objetos citados dentro da regra
        for obj_name in ["red_ball", "blue_cube", "yellow_triangle", "green_cylinder", "square_A", "square_B", "triangle_A"]:
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
        # tenta achar ids de objetos no payload
        objs = []
        for sep in [">", "~"]:
            if sep in payload:
                objs = payload.split(sep)
                break
        if objs:
            for obj in objs:
                obj = obj.strip()
                if obj:
                    obj_node = f"obj::{obj}"
                    add_node(G, obj_node, obj, "object")
                    add_edge(G, obj_node, cmp_node, label="compare", weight=conf)
        return

    # fallback genérico
    mem_node = f"mem::{key_core}"
    add_node(G, mem_node, short_label(key_core), "memory")
    if content and content.lower() not in {"true", "false", "none", ""}:
        val_node = f"content::{content}"
        add_node(G, val_node, short_label(content), "other")
        add_edge(G, mem_node, val_node, label="content", weight=conf)



def build_graph(db_path: str, min_confidence: float) -> tuple[nx.Graph, dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    G = nx.Graph()

    rows = conn.execute(
        """
        SELECT key, content, confidence
        FROM semantic_memory
        ORDER BY confidence DESC, updated_at DESC
        """
    ).fetchall()

    used_rows = 0
    for row in rows:
        conf = float(row["confidence"] or 0.0)
        if conf < min_confidence:
            continue
        add_semantic_row(G, str(row["key"]), str(row["content"] or ""), conf)
        used_rows += 1

    # estado atual como um pequeno cluster de métricas
    try:
        state = conn.execute("SELECT * FROM current_state ORDER BY id DESC LIMIT 1").fetchone()
        if state is not None:
            state_node = "metric::estado_atual"
            add_node(G, state_node, "estado_atual", "metric")
            for name in ["sigma", "energy", "pain_signal", "wellbeing_signal"]:
                if name in state.keys():
                    metric_node = f"metric::{name}:{state[name]}"
                    add_node(G, metric_node, short_label(f"{name}={state[name]}"), "metric")
                    add_edge(G, state_node, metric_node, label=name, weight=1.0)
    except Exception:
        pass

    # episódios recentes
    try:
        eps = conn.execute(
            """
            SELECT id, module, action_taken, outcome
            FROM episodes
            ORDER BY id DESC
            LIMIT 20
            """
        ).fetchall()
        for ep in eps:
            ep_node = f"episode::{ep['id']}"
            add_node(G, ep_node, short_label(f"ep{ep['id']}:{ep['module']}"), "episode")
            if ep["action_taken"]:
                act_node = f"action::{ep['action_taken']}"
                add_node(G, act_node, short_label(str(ep["action_taken"])), "action")
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


IMPORTANT_TYPES = {"object", "pair", "rule", "hypothesis", "context", "compare", "fit", "affordance", "metric"}


def simplify_graph(G: nx.Graph, max_nodes: int = 150) -> nx.Graph:
    if G.number_of_nodes() <= max_nodes:
        return G.copy()

    important = [n for n, d in G.nodes(data=True) if d.get("node_type") in IMPORTANT_TYPES]
    high_degree = [n for n, deg in sorted(G.degree, key=lambda x: x[1], reverse=True)]

    selected = []
    seen = set()
    for source in (important + high_degree):
        if source not in seen:
            selected.append(source)
            seen.add(source)
        if len(selected) >= max_nodes:
            break

    H = G.subgraph(selected).copy()
    # adiciona vizinhos imediatos de objetos centrais, se couber
    if H.number_of_nodes() < max_nodes:
        room = max_nodes - H.number_of_nodes()
        extras = []
        for n in list(H.nodes()):
            for nb in G.neighbors(n):
                if nb not in H:
                    extras.append(nb)
                    if len(extras) >= room:
                        break
            if len(extras) >= room:
                break
        H = G.subgraph(list(H.nodes()) + extras).copy()
    return H



def find_focus_nodes(G: nx.Graph, focus: str) -> list[str]:
    focus = focus.lower().strip()
    matches = []
    for n, data in G.nodes(data=True):
        label = str(data.get("label", "")).lower()
        if focus in label or focus in str(n).lower():
            matches.append(n)
    return matches



def focused_graph(G: nx.Graph, focus: str, radius: int = 2, max_nodes: int = 120) -> nx.Graph:
    seeds = find_focus_nodes(G, focus)
    if not seeds:
        return simplify_graph(G, max_nodes=max_nodes)
    nodes = set()
    for seed in seeds[:10]:
        eg = nx.ego_graph(G, seed, radius=radius)
        nodes.update(eg.nodes())
        if len(nodes) >= max_nodes:
            break
    H = G.subgraph(list(nodes)[:max_nodes]).copy()
    return H



def draw_graph(G: nx.Graph, output_path: str, title: str) -> None:
    n = max(1, G.number_of_nodes())
    k = max(0.25, 2.2 / math.sqrt(n))
    pos = nx.spring_layout(G, k=k, iterations=250, seed=42)

    fig_w = 18 if n < 120 else 24
    fig_h = 12 if n < 120 else 16
    plt.figure(figsize=(fig_w, fig_h))
    ax = plt.gca()
    ax.set_facecolor("white")
    plt.title(title, fontsize=16)
    plt.axis("off")

    # arestas
    widths = []
    for _, _, data in G.edges(data=True):
        widths.append(0.5 + 2.6 * float(data.get("weight", 0.4)))
    nx.draw_networkx_edges(G, pos, alpha=0.25, width=widths, edge_color="#888888")

    # nós por tipo
    type_to_nodes = {}
    for node, data in G.nodes(data=True):
        node_type = data.get("node_type", "other")
        type_to_nodes.setdefault(node_type, []).append(node)

    for node_type, nodes in type_to_nodes.items():
        sizes = []
        for node in nodes:
            deg = G.degree[node]
            sizes.append(120 + 45 * deg)
        nx.draw_networkx_nodes(
            G,
            pos,
            nodelist=nodes,
            node_color=COLOR_MAP.get(node_type, COLOR_MAP["other"]),
            node_size=sizes,
            alpha=0.9,
            linewidths=0.8,
            edgecolors="#333333",
        )

    labels = {node: G.nodes[node].get("label", node) for node in G.nodes()}
    nx.draw_networkx_labels(G, pos, labels=labels, font_size=8, font_family="sans-serif")

    # legenda simples
    legend_items = []
    type_counts = Counter(data.get("node_type", "other") for _, data in G.nodes(data=True))
    for t, count in sorted(type_counts.items()):
        legend_items.append(f"{t}: {count}")
    plt.figtext(0.01, 0.01, " | ".join(legend_items), ha="left", va="bottom", fontsize=9)

    plt.tight_layout()
    plt.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close()



def ensure_export_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)



def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Exporta o grafo da memória do Darwin em PNG.")
    parser.add_argument("--db", default=DEFAULT_DB, help="Caminho para o darwin.db")
    parser.add_argument("--export-dir", default=DEFAULT_EXPORT_DIR, help="Pasta de saída")
    parser.add_argument("--min-confidence", type=float, default=0.30, help="Confiança mínima para incluir memória")
    parser.add_argument("--max-nodes", type=int, default=150, help="Máximo de nós na versão simplificada")
    parser.add_argument("--focus", default="", help="Palavra para gerar grafo focado (ex.: red_ball, stable, with_block_top)")
    parser.add_argument("--full", action="store_true", help="Também exporta o grafo completo")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not os.path.exists(args.db):
        print(f"ERRO: banco não encontrado em: {args.db}")
        return 1

    ensure_export_dir(args.export_dir)
    G, meta = build_graph(args.db, min_confidence=args.min_confidence)

    if G.number_of_nodes() == 0:
        print("Nenhum nó encontrado para os filtros atuais.")
        return 1

    base_name = os.path.join(args.export_dir, "darwin_memory_graph")

    simplified = simplify_graph(G, max_nodes=args.max_nodes)
    simplified_png = base_name + "_simplificado.png"
    draw_graph(
        simplified,
        simplified_png,
        f"Darwin Memory Graph - Simplificado ({simplified.number_of_nodes()} nós, {simplified.number_of_edges()} arestas)",
    )
    print(f"PNG simplificado salvo em: {simplified_png}")

    focus_png = None
    if args.focus.strip():
        H = focused_graph(G, args.focus.strip(), radius=2, max_nodes=max(70, args.max_nodes))
        safe_focus = re.sub(r"[^a-zA-Z0-9_-]+", "_", args.focus.strip())
        focus_png = base_name + f"_focus_{safe_focus}.png"
        draw_graph(
            H,
            focus_png,
            f"Darwin Memory Graph - Foco em '{args.focus.strip()}' ({H.number_of_nodes()} nós, {H.number_of_edges()} arestas)",
        )
        print(f"PNG focado salvo em: {focus_png}")

    full_png = None
    if args.full:
        full_png = base_name + "_completo.png"
        draw_graph(
            G,
            full_png,
            f"Darwin Memory Graph - Completo ({G.number_of_nodes()} nós, {G.number_of_edges()} arestas)",
        )
        print(f"PNG completo salvo em: {full_png}")

    print(
        f"Resumo: {meta['semantic_rows_used']} memórias semânticas usadas | {meta['nodes']} nós totais | {meta['edges']} arestas totais"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
