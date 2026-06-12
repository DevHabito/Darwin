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

# Paleta simples, estável e legível
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
    "cause": "#ff9896",
    "basis": "#c7c7c7",
    "match": "#8c8c00",
    "metric": "#7f7f7f",
    "state": "#aec7e8",
    "other": "#dddddd",
}

# Prefixos/meta que antes estavam poluindo as camadas de objeto e par
META_PREFIXES = (
    "basis:",
    "predicted:",
    "validated:",
    "cause_focus:",
    "observed_cause:",
    "match:",
)

# Regex principais
OBJ_RE = re.compile(r"^obj:([^:]+):([^:]+):(.+)$")
PAIR_RE = re.compile(r"^pair:([^>]+)>([^:]+):([^:]+):(.+)$")
RULE_RE = re.compile(r"^rule:(.+)$")
HYP_RE = re.compile(r"^hypothesis:([^>]+)>([^:]+):([^:]+):(.+)$")
COMPARE_RE = re.compile(r"^compare:([^:]+):(.+)$")
FIT_RE = re.compile(r"^fit:([^:]+):(.+)$")

# Metacognição / justificativa
BASIS_RE = re.compile(r"^basis:(.+)$")
PRED_RE = re.compile(r"^predicted:([^:]+)(?::(.+))?$")
VALID_RE = re.compile(r"^validated:([^:]+)(?::(.+))?$")
CAUSE_RE = re.compile(r"^(cause_focus|observed_cause):(.+)$")
MATCH_RE = re.compile(r"^match:(.+)$")

# Palavras que sugerem relação física/encaixe/empilhamento
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
    # alguns registros podem ter "=..." no final; a parte útil está à esquerda
    return key.split("=", 1)[0].strip()


def short_label(text: str, max_len: int = 34) -> str:
    text = str(text)
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def add_node(G: nx.Graph, node_id: str, label: str, node_type: str) -> None:
    if node_id not in G:
        G.add_node(node_id, label=label, node_type=node_type)


def add_edge(G: nx.Graph, u: str, v: str, label: str = "", weight: float = 1.0) -> None:
    if u == v:
        return
    if G.has_edge(u, v):
        G[u][v]["weight"] = max(G[u][v].get("weight", 1.0), float(weight))
        prev = G[u][v].get("label", "")
        if label and label not in prev:
            G[u][v]["label"] = ", ".join([p for p in [prev, label] if p])
    else:
        G.add_edge(u, v, label=label, weight=float(weight))


def content_tokens(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z_][a-zA-Z0-9_:-]*", (text or "").lower())


def discover_object_names(rows: list[SemanticRow]) -> set[str]:
    names: set[str] = set()
    for row in rows:
        key = normalize_key(row.key)
        m = OBJ_RE.match(key)
        if m:
            names.add(m.group(1))
            continue
        m = PAIR_RE.match(key)
        if m:
            names.add(m.group(1))
            names.add(m.group(2))
            continue
        m = HYP_RE.match(key)
        if m:
            names.add(m.group(1))
            names.add(m.group(2))
            continue
        # alguns compare podem listar objetos separados por > ~ |
        m = COMPARE_RE.match(key)
        if m:
            payload = m.group(2)
            for part in re.split(r"[>~|]", payload):
                part = part.strip()
                if part:
                    names.add(part)
    return names


def is_meta_prefix(text: str) -> bool:
    lower = (text or "").lower().strip()
    return lower.startswith(META_PREFIXES)


def is_physical_relation(relation: str, value: str) -> bool:
    s = f"{relation}:{value}".lower()
    return any(hint in s for hint in PHYSICAL_RELATION_HINTS)


def connect_to_mentioned_objects(
    G: nx.Graph,
    source_node: str,
    text: str,
    object_names: set[str],
    edge_label: str,
    weight: float,
) -> None:
    hay = (text or "").lower()
    for obj in sorted(object_names):
        if obj.lower() in hay:
            obj_node = f"obj::{obj}"
            add_node(G, obj_node, obj, "object")
            add_edge(G, source_node, obj_node, label=edge_label, weight=weight)


def add_semantic_row(G: nx.Graph, row: SemanticRow, object_names: set[str]) -> None:
    key = normalize_key(row.key)
    content = str(row.content or "")
    conf = max(0.05, min(1.0, float(row.confidence or 0.0)))
    key_low = key.lower()

    # 1) Ontologia de objeto: só objeto -> propriedade/affordance
    m = OBJ_RE.match(key)
    if m:
        obj_id, relation, value = m.groups()
        # corta qualquer meta acidental daqui
        if relation.lower().startswith(("basis", "predicted", "validated", "cause", "match")):
            return
        obj_node = f"obj::{obj_id}"
        add_node(G, obj_node, obj_id, "object")
        if relation == "affordance":
            node_type = "affordance"
        else:
            node_type = "property"
        prop_node = f"objprop::{relation}:{value}"
        add_node(G, prop_node, short_label(value), node_type)
        add_edge(G, obj_node, prop_node, label=relation, weight=conf)
        return

    # 2) Mundo físico relacional: pares, empilhamento, encaixe, match físico
    m = PAIR_RE.match(key)
    if m:
        lower, upper, relation, value = m.groups()
        lower_node = f"obj::{lower}"
        upper_node = f"obj::{upper}"
        pair_node = f"pair::{lower}>{upper}"
        add_node(G, lower_node, lower, "object")
        add_node(G, upper_node, upper, "object")
        add_node(G, pair_node, short_label(f"{lower}>{upper}"), "pair")
        result_type = "physical_result" if is_physical_relation(relation, value) else "property"
        result_node = f"pairres::{relation}:{value}"
        add_node(G, result_node, short_label(f"{relation}:{value}"), result_type)
        add_edge(G, lower_node, pair_node, label="base", weight=conf)
        add_edge(G, upper_node, pair_node, label="topo", weight=conf)
        add_edge(G, pair_node, result_node, label=relation, weight=conf)
        return

    # 3) Hipóteses / previsões: separam claramente a previsão do resto
    m = HYP_RE.match(key)
    if m:
        lower, upper, relation, value = m.groups()
        lower_node = f"obj::{lower}"
        upper_node = f"obj::{upper}"
        hyp_node = f"hyp::{lower}>{upper}:{relation}:{value}"
        pred_node = f"pred::{relation}:{value}"
        add_node(G, lower_node, lower, "object")
        add_node(G, upper_node, upper, "object")
        add_node(G, hyp_node, short_label(f"{lower}>{upper}"), "hypothesis")
        add_node(G, pred_node, short_label(f"predicted:{value}"), "predicted")
        add_edge(G, lower_node, hyp_node, label="hip.base", weight=conf)
        add_edge(G, upper_node, hyp_node, label="hip.topo", weight=conf)
        add_edge(G, hyp_node, pred_node, label=relation, weight=conf)
        return

    # 4) Regras, contextos e abstrações
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
            obj_node = f"obj::{obj}"
            add_node(G, obj_node, obj, "object")
            add_edge(G, obj_node, cmp_node, label="compare", weight=conf)
        connect_to_mentioned_objects(G, cmp_node, content, object_names, "compare", conf)
        return

    # 5) Metacognição / justificativa / validação
    m = BASIS_RE.match(key_low)
    if m:
        raw = m.group(1)
        basis_node = f"basis::{raw}"
        add_node(G, basis_node, short_label(f"basis:{raw}"), "basis")
        connect_to_mentioned_objects(G, basis_node, raw, object_names, "basis", conf)
        connect_to_mentioned_objects(G, basis_node, content, object_names, "basis", conf)
        return

    m = PRED_RE.match(key_low)
    if m:
        kind = m.group(1)
        detail = m.group(2) or ""
        pred_node = f"predmeta::{kind}:{detail}"
        add_node(G, pred_node, short_label(f"predicted:{kind}"), "predicted")
        connect_to_mentioned_objects(G, pred_node, detail, object_names, "pred", conf)
        connect_to_mentioned_objects(G, pred_node, content, object_names, "pred", conf)
        return

    m = VALID_RE.match(key_low)
    if m:
        kind = m.group(1)
        detail = m.group(2) or ""
        val_node = f"validation::{kind}:{detail}"
        add_node(G, val_node, short_label(f"validated:{kind}"), "validation")
        connect_to_mentioned_objects(G, val_node, detail, object_names, "validou", conf)
        connect_to_mentioned_objects(G, val_node, content, object_names, "validou", conf)
        return

    m = CAUSE_RE.match(key_low)
    if m:
        kind, detail = m.groups()
        cause_node = f"cause::{kind}:{detail}"
        add_node(G, cause_node, short_label(f"{kind}:{detail}"), "cause")
        connect_to_mentioned_objects(G, cause_node, detail, object_names, "causa", conf)
        connect_to_mentioned_objects(G, cause_node, content, object_names, "causa", conf)
        return

    m = MATCH_RE.match(key_low)
    if m:
        raw = m.group(1)
        match_node = f"match::{raw}"
        add_node(G, match_node, short_label(f"match:{raw}"), "match")
        connect_to_mentioned_objects(G, match_node, content, object_names, "match", conf)
        return

    # 6) fit: como resultado físico simples
    m = FIT_RE.match(key)
    if m:
        relation, value = m.groups()
        fit_node = f"fit::{relation}:{value}"
        add_node(G, fit_node, short_label(f"{relation}:{value}"), "physical_result")
        connect_to_mentioned_objects(G, fit_node, content, object_names, "fit", conf)
        return

    # Fallback: só cria algo se NÃO for obviamente meta poluente
    if not is_meta_prefix(key):
        other_node = f"other::{key}"
        add_node(G, other_node, short_label(key), "other")
        connect_to_mentioned_objects(G, other_node, content, object_names, "rel", conf)


def build_graph(db_path: str, min_confidence: float) -> tuple[nx.Graph, dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    rows = [
        SemanticRow(
            key=str(row["key"] or ""),
            content=str(row["content"] or ""),
            confidence=float(row["confidence"] or 0.0),
        )
        for row in conn.execute(
            "SELECT key, content, confidence FROM semantic_memory ORDER BY confidence DESC, updated_at DESC"
        ).fetchall()
        if float(row["confidence"] or 0.0) >= min_confidence
    ]

    object_names = discover_object_names(rows)
    G = nx.Graph()

    for row in rows:
        add_semantic_row(G, row, object_names)

    # Camada do estado interno: separada e limpa
    try:
        state = conn.execute("SELECT * FROM current_state ORDER BY id DESC LIMIT 1").fetchone()
        if state is not None:
            state_node = "state::estado_atual"
            add_node(G, state_node, "estado_atual", "state")
            for field in ["sigma", "energy", "pain_signal", "wellbeing_signal", "latency", "info_load"]:
                if field in state.keys() and state[field] is not None:
                    metric_node = f"metric::{field}:{state[field]}"
                    add_node(G, metric_node, short_label(f"{field}={state[field]}"), "metric")
                    add_edge(G, state_node, metric_node, label=field, weight=1.0)
    except Exception:
        pass

    conn.close()
    meta = {
        "semantic_rows_used": len(rows),
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "object_names": sorted(object_names),
    }
    return G, meta


def remove_isolated_nodes(G: nx.Graph) -> nx.Graph:
    isolates = list(nx.isolates(G))
    H = G.copy()
    H.remove_nodes_from(isolates)
    return H


def trim_by_degree(G: nx.Graph, max_nodes: int) -> nx.Graph:
    if G.number_of_nodes() <= max_nodes:
        return G.copy()
    ranked = sorted(G.degree, key=lambda x: x[1], reverse=True)
    keep = [n for n, _ in ranked[:max_nodes]]
    return G.subgraph(keep).copy()


def subgraph_by_types(
    G: nx.Graph,
    allowed_types: set[str],
    *,
    keep_isolates: bool = False,
    max_nodes: int = 180,
) -> nx.Graph:
    selected = [n for n, d in G.nodes(data=True) if d.get("node_type") in allowed_types]
    H = G.subgraph(selected).copy()
    if not keep_isolates:
        H = remove_isolated_nodes(H)
    H = trim_by_degree(H, max_nodes)
    return H


def node_size(G: nx.Graph, node: str) -> float:
    deg = G.degree[node]
    base = 150
    bonus = 48 * deg
    t = G.nodes[node].get("node_type", "other")
    if t == "object":
        base += 140
    elif t in {"pair", "hypothesis", "rule", "context", "state"}:
        base += 70
    return base + bonus


def draw_graph(G: nx.Graph, output_path: str, title: str) -> None:
    if G.number_of_nodes() == 0:
        plt.figure(figsize=(12, 7))
        plt.title(title)
        plt.text(0.5, 0.5, "Sem dados para esta camada.", ha="center", va="center", fontsize=16)
        plt.axis("off")
        plt.tight_layout()
        plt.savefig(output_path, dpi=220, bbox_inches="tight")
        plt.close()
        return

    n = max(1, G.number_of_nodes())
    k = max(0.22, 2.0 / math.sqrt(n))
    pos = nx.spring_layout(G, k=k, iterations=300, seed=42)

    fig_w = 18 if n < 100 else 24
    fig_h = 12 if n < 100 else 16
    plt.figure(figsize=(fig_w, fig_h))
    ax = plt.gca()
    ax.set_facecolor("white")
    plt.title(title, fontsize=17)
    plt.axis("off")

    widths = [0.6 + 2.2 * float(data.get("weight", 0.5)) for _, _, data in G.edges(data=True)]
    nx.draw_networkx_edges(G, pos, alpha=0.22, width=widths, edge_color="#777777")

    grouped: dict[str, list[str]] = {}
    for n_id, data in G.nodes(data=True):
        grouped.setdefault(data.get("node_type", "other"), []).append(n_id)

    for node_type, nodes in grouped.items():
        nx.draw_networkx_nodes(
            G,
            pos,
            nodelist=nodes,
            node_color=COLOR_MAP.get(node_type, COLOR_MAP["other"]),
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
        f.write("Darwin Memory Graph Layers v2 - Resumo\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Memórias semânticas usadas: {meta['semantic_rows_used']}\n")
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
    parser = argparse.ArgumentParser(description="Exporta ressonâncias por camada v2 do grafo de memória do Darwin.")
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
            subgraph_by_types(G, {"object", "property", "affordance"}, max_nodes=args.max_nodes),
        ),
        (
            "02_mundo_fisico_relacional",
            "Camada 2 - Mundo físico relacional",
            subgraph_by_types(G, {"object", "pair", "physical_result"}, max_nodes=args.max_nodes),
        ),
        (
            "03_regras_abstracoes",
            "Camada 3 - Regras, contextos e abstrações",
            subgraph_by_types(G, {"object", "rule", "context", "compare"}, max_nodes=args.max_nodes),
        ),
        (
            "04_hipoteses_previsoes",
            "Camada 4 - Hipóteses e previsões",
            subgraph_by_types(G, {"object", "hypothesis", "predicted"}, max_nodes=args.max_nodes),
        ),
        (
            "05_validacoes_causas",
            "Camada 5 - Validações, causas e bases",
            subgraph_by_types(G, {"object", "validation", "cause", "basis", "match"}, max_nodes=args.max_nodes),
        ),
        (
            "06_estado_interno",
            "Camada 6 - Estado interno",
            subgraph_by_types(G, {"state", "metric"}, keep_isolates=True, max_nodes=50),
        ),
    ]

    summaries: list[tuple[str, nx.Graph]] = []
    for slug, title, graph in layers:
        out_path = os.path.join(args.export_dir, f"darwin_memory_{slug}.png")
        draw_graph(graph, out_path, f"{title} ({graph.number_of_nodes()} nós, {graph.number_of_edges()} arestas)")
        print(f"PNG salvo: {out_path}")
        summaries.append((title, graph))

    summary_path = os.path.join(args.export_dir, "darwin_memory_layers_v2_summary.txt")
    write_summary(summary_path, summaries, meta)
    print(f"Resumo salvo: {summary_path}")
    print(f"Grafo-base: {meta['nodes']} nós, {meta['edges']} arestas | memórias usadas: {meta['semantic_rows_used']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
