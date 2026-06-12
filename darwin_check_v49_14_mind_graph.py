from __future__ import annotations

"""
DARWIN v49.14 - Diagnostico do Mind Graph Viewer

Uso:
    py darwin_check_v49_14_mind_graph.py
    py darwin_check_v49_14_mind_graph.py --details
"""

import argparse
import json
from typing import Any

from darwin_mind_graph_v49_14 import MindGraphBuilder


REQUIRED_MODULES = {
    "darwin",
    "rzs",
    "geometry",
    "first_words",
    "vocal_imitation",
    "joint_attention",
    "memory_cards",
    "companion",
    "semantic",
    "episodes",
}


def edge_exists(edges: list[Any], source: str, target: str, kind: str | None = None) -> bool:
    for edge in edges:
        if edge.source == source and edge.target == target and (kind is None or edge.kind == kind):
            return True
    return False


def build_report() -> dict[str, Any]:
    graph = MindGraphBuilder().build()
    kinds = {node.kind for node in graph.nodes.values()}
    node_ids = set(graph.nodes)
    concept_nodes = [n for n in graph.nodes.values() if n.kind == "concept"]
    word_nodes = [n for n in graph.nodes.values() if n.kind == "word"]
    meaning_nodes = [n for n in graph.nodes.values() if n.kind == "meaning"]
    entity_nodes = [n for n in graph.nodes.values() if n.kind == "entity"]
    symbol_nodes = [n for n in graph.nodes.values() if n.kind == "symbol"]
    memory_nodes = [n for n in graph.nodes.values() if n.kind == "memory"]
    episode_nodes = [n for n in graph.nodes.values() if n.kind == "episode"]
    rzs_edges = [e for e in graph.edges if e.source == "rzs" or e.target == "rzs"]
    grounded_edges = [e for e in graph.edges if e.kind in {"grounded_reference", "refers_to"}]
    word_meaning_edges = [e for e in graph.edges if e.kind == "means"]
    memory_card_edges = [e for e in graph.edges if e.source == "memory_cards" or e.target == "memory_cards"]

    checks = {
        "graph_built": len(graph.nodes) >= 60 and len(graph.edges) >= 60,
        "required_modules_present": REQUIRED_MODULES.issubset(node_ids),
        "rzs_connected": len(rzs_edges) >= 8 and edge_exists(graph.edges, "rzs", "memory_cards", "regulates"),
        "geometry_concepts_present": len(concept_nodes) >= 10,
        "first_words_present": len(word_nodes) >= 4 and len(meaning_nodes) >= 4 and len(word_meaning_edges) >= 4,
        "joint_attention_grounding_present": len(entity_nodes) >= 4 and len(grounded_edges) >= 4,
        "memory_cards_present": len(symbol_nodes) >= 4 and len(memory_card_edges) >= 4,
        "semantic_memory_present": len(memory_nodes) >= 10,
        "episodes_present": len(episode_nodes) >= 3,
        "layout_assigned": all(abs(node.x) + abs(node.y) > 0.001 or node.node_id == "darwin" for node in graph.nodes.values()),
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "counts": {
            "nodes": len(graph.nodes),
            "edges": len(graph.edges),
            "concepts": len(concept_nodes),
            "words": len(word_nodes),
            "meanings": len(meaning_nodes),
            "entities": len(entity_nodes),
            "symbols": len(symbol_nodes),
            "memories": len(memory_nodes),
            "episodes": len(episode_nodes),
            "rzs_edges": len(rzs_edges),
            "grounded_edges": len(grounded_edges),
        },
        "kinds": sorted(kinds),
        "sample_nodes": sorted(list(node_ids))[:20],
    }


def print_report(report: dict[str, Any], details: bool) -> None:
    print("DARWIN v49.14 - DIAGNOSTICO MIND GRAPH")
    print("=" * 52)
    c = report["counts"]
    print(f"- nos={c['nodes']} arestas={c['edges']}")
    print(
        f"- conceitos={c['concepts']} palavras={c['words']} entidades={c['entities']} "
        f"simbolos={c['symbols']} memorias={c['memories']}"
    )
    print(f"- tipos: {', '.join(report['kinds'])}")
    print()
    labels = {
        "graph_built": "grafo construido",
        "required_modules_present": "modulos principais presentes",
        "rzs_connected": "RZS conectado ao grafo",
        "geometry_concepts_present": "conceitos geometricos presentes",
        "first_words_present": "primeiras palavras presentes",
        "joint_attention_grounding_present": "referencias palavra-objeto presentes",
        "memory_cards_present": "jogo de memoria presente",
        "semantic_memory_present": "memoria semantica presente",
        "episodes_present": "episodios presentes",
        "layout_assigned": "layout calculado",
    }
    for key, value in report["checks"].items():
        print(f"- {labels.get(key, key)}: {'OK' if value else 'FALHOU'}")
    print(f"\nResultado final: {'OK' if report['ok'] else 'FALHOU'}")
    if report["ok"]:
        print("Leitura: o grafo mental sintetiza a jornada aprendida do Darwin.")
    else:
        print("Leitura: ainda falta evidencia para aceitar o visualizador do grafo mental.")
    if details:
        print("\nJSON:")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin v49.14 Mind Graph checker")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    report = build_report()
    print_report(report, args.details)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
