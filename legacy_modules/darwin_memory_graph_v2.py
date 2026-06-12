#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
darwin_memory_graph.py
Visualizador local do grafo de memória do Darwin.

Uso rápido:
    python darwin_memory_graph.py --open
    python darwin_memory_graph.py --watch --interval 3 --open

O script lê o banco SQLite do Darwin, interpreta semantic_memory/episodes/current_state,
e gera um HTML interativo em darwin_home/exports/darwin_memory_graph.html.

Não altera o banco. Apenas lê e gera visualização.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import sqlite3
import sys
import time
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

APP_NAME = "Darwin Memory Graph"
DEFAULT_DB_CANDIDATES = [
    Path("darwin_home") / "darwin.db",
    Path("darwin.db"),
]

# -----------------------------------------------------------------------------
# utilidades
# -----------------------------------------------------------------------------


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def strip_value_suffix(key: str, content: str = "") -> Tuple[str, str]:
    """Aceita tanto 'obj:x:color:red=true' quanto key='obj:x:color:red', content='true'."""
    if "=" in key:
        left, right = key.rsplit("=", 1)
        return left.strip(), right.strip()
    return key.strip(), str(content).strip()


def relation_label(text: str) -> str:
    return text.replace("_", " ")


def detect_db_path(user_path: Optional[str]) -> Path:
    if user_path:
        path = Path(user_path)
        if not path.exists():
            raise FileNotFoundError(f"Banco não encontrado: {path}")
        return path

    for candidate in DEFAULT_DB_CANDIDATES:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        "Não encontrei darwin_home/darwin.db nem darwin.db. "
        "Use --db caminho/para/darwin.db"
    )


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


# -----------------------------------------------------------------------------
# estrutura do grafo
# -----------------------------------------------------------------------------


@dataclass
class GraphNode:
    node_id: str
    label: str
    node_type: str
    confidence: float = 0.0
    observations: int = 1
    title_lines: List[str] = field(default_factory=list)
    last_updated: str = ""

    def merge(self, confidence: float = 0.0, title_line: str = "", updated_at: str = "") -> None:
        self.confidence = max(self.confidence, confidence)
        self.observations += 1
        if title_line and title_line not in self.title_lines:
            self.title_lines.append(title_line)
        if updated_at and updated_at > self.last_updated:
            self.last_updated = updated_at


@dataclass
class GraphEdge:
    edge_id: str
    source: str
    target: str
    relation: str
    confidence: float = 0.0
    observations: int = 1
    title_lines: List[str] = field(default_factory=list)
    last_updated: str = ""
    polarity: str = "neutral"  # positive, negative, uncertain, neutral

    def merge(self, confidence: float = 0.0, title_line: str = "", updated_at: str = "") -> None:
        self.confidence = max(self.confidence, confidence)
        self.observations += 1
        if title_line and title_line not in self.title_lines:
            self.title_lines.append(title_line)
        if updated_at and updated_at > self.last_updated:
            self.last_updated = updated_at


class DarwinGraphBuilder:
    def __init__(self) -> None:
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: Dict[str, GraphEdge] = {}
        self.unparsed: List[Dict[str, Any]] = []

    def add_node(
        self,
        node_id: str,
        label: Optional[str] = None,
        node_type: str = "unknown",
        confidence: float = 0.0,
        title_line: str = "",
        updated_at: str = "",
    ) -> None:
        node_id = str(node_id)
        if node_id not in self.nodes:
            self.nodes[node_id] = GraphNode(
                node_id=node_id,
                label=label or node_id,
                node_type=node_type,
                confidence=confidence,
                observations=1,
                title_lines=[title_line] if title_line else [],
                last_updated=updated_at,
            )
        else:
            self.nodes[node_id].merge(confidence, title_line, updated_at)

    def add_edge(
        self,
        source: str,
        target: str,
        relation: str,
        confidence: float = 0.0,
        title_line: str = "",
        updated_at: str = "",
        polarity: str = "neutral",
    ) -> None:
        source = str(source)
        target = str(target)
        relation = str(relation)
        edge_id = f"{source}|{relation}|{target}"
        if edge_id not in self.edges:
            self.edges[edge_id] = GraphEdge(
                edge_id=edge_id,
                source=source,
                target=target,
                relation=relation,
                confidence=confidence,
                observations=1,
                title_lines=[title_line] if title_line else [],
                last_updated=updated_at,
                polarity=polarity,
            )
        else:
            self.edges[edge_id].merge(confidence, title_line, updated_at)
            if polarity != "neutral":
                self.edges[edge_id].polarity = polarity

    # -------------------------------------------------------------------------
    # parsing das chaves do Darwin
    # -------------------------------------------------------------------------

    def parse_memory_row(self, row: sqlite3.Row) -> None:
        raw_key = str(row["key"])
        content = str(row["content"])
        confidence = clamp(safe_float(row["confidence"], 0.0), 0.0, 1.0)
        source_module = str(row["source"])
        updated_at = str(row["updated_at"])
        key, value = strip_value_suffix(raw_key, content)
        parts = key.split(":")
        title = f"key: {html.escape(key)}<br>valor: {html.escape(value)}<br>confiança: {confidence:.2f}<br>fonte: {html.escape(source_module)}<br>atualizado: {html.escape(updated_at)}"

        if not parts:
            return

        kind = parts[0]

        try:
            if kind == "obj":
                self._parse_obj(parts, confidence, title, updated_at)
            elif kind == "shape":
                self._parse_shape(parts, confidence, title, updated_at)
            elif kind == "pair":
                self._parse_pair(parts, confidence, title, updated_at)
            elif kind == "compare":
                self._parse_compare(parts, confidence, title, updated_at)
            elif kind == "rule":
                self._parse_rule(parts, confidence, title, updated_at)
            elif kind == "hypothesis":
                self._parse_hypothesis(parts, confidence, title, updated_at)
            else:
                self._parse_unknown(key, value, confidence, title, updated_at)
        except Exception as exc:
            # Não derruba a visualização por uma chave nova. Guarda como memória bruta.
            self.unparsed.append({"key": key, "error": repr(exc)})
            self._parse_unknown(key, value, confidence, title, updated_at)

    def _parse_obj(self, parts: List[str], confidence: float, title: str, updated_at: str) -> None:
        # obj:<obj_id>:color:<color>
        if len(parts) < 4:
            self._parse_unknown(":".join(parts), "", confidence, title, updated_at)
            return

        obj_id = parts[1]
        attribute = parts[2]
        value = ":".join(parts[3:])
        obj_node = f"obj:{obj_id}"
        self.add_node(obj_node, obj_id, "object", confidence, title, updated_at)

        if attribute == "color":
            target = f"color:{value}"
            self.add_node(target, value, "color", confidence, title, updated_at)
            self.add_edge(obj_node, target, "tem_cor", confidence, title, updated_at, "neutral")
        elif attribute == "shape":
            target = f"shape:{value}"
            self.add_node(target, value, "shape", confidence, title, updated_at)
            self.add_edge(obj_node, target, "tem_forma", confidence, title, updated_at, "neutral")
        elif attribute == "category":
            target = f"category:{value}"
            self.add_node(target, value, "category", confidence, title, updated_at)
            self.add_edge(obj_node, target, "tem_categoria", confidence, title, updated_at, "neutral")
        elif attribute == "affordance":
            target = f"affordance:{value}"
            self.add_node(target, relation_label(value), "affordance", confidence, title, updated_at)
            self.add_edge(obj_node, target, "tem_affordance", confidence, title, updated_at, "positive")
        elif attribute == "fit" and len(parts) >= 5:
            slot_id = parts[3]
            outcome = parts[4]
            target = f"slot:{slot_id}"
            self.add_node(target, slot_id, "slot", confidence, title, updated_at)
            relation = "encaixa_em" if outcome == "success" else "nao_encaixa_em"
            polarity = "positive" if outcome == "success" else "negative"
            self.add_edge(obj_node, target, relation, confidence, title, updated_at, polarity)
        else:
            target = f"{attribute}:{value}"
            self.add_node(target, value, attribute, confidence, title, updated_at)
            self.add_edge(obj_node, target, attribute, confidence, title, updated_at, "neutral")

    def _parse_shape(self, parts: List[str], confidence: float, title: str, updated_at: str) -> None:
        # shape:<shape>:fit:<slot_shape>:success/failure
        if len(parts) >= 5 and parts[2] == "fit":
            shape = parts[1]
            slot_shape = parts[3]
            outcome = parts[4]
            shape_node = f"shape:{shape}"
            slot_node = f"slot_shape:{slot_shape}"
            self.add_node(shape_node, shape, "shape", confidence, title, updated_at)
            self.add_node(slot_node, slot_shape, "slot", confidence, title, updated_at)
            relation = "forma_encaixa" if outcome == "success" else "forma_nao_encaixa"
            polarity = "positive" if outcome == "success" else "negative"
            self.add_edge(shape_node, slot_node, relation, confidence, title, updated_at, polarity)
        else:
            self._parse_unknown(":".join(parts), "", confidence, title, updated_at)

    def _parse_pair(self, parts: List[str], confidence: float, title: str, updated_at: str) -> None:
        # pair:<lower>><upper>:stack:stable/unstable
        if len(parts) >= 4 and ">" in parts[1]:
            lower, upper = parts[1].split(">", 1)
            relation_family = parts[2]
            outcome = parts[3]
            lower_node = f"obj:{lower}"
            upper_node = f"obj:{upper}"
            self.add_node(lower_node, lower, "object", confidence, title, updated_at)
            self.add_node(upper_node, upper, "object", confidence, title, updated_at)

            relation = f"{relation_family}_{outcome}"
            polarity = "positive" if outcome in {"stable", "success"} else "negative" if outcome in {"unstable", "failure"} else "neutral"
            self.add_edge(lower_node, upper_node, relation, confidence, title, updated_at, polarity)

            outcome_node = f"outcome:{relation}"
            self.add_node(outcome_node, relation_label(relation), "outcome", confidence, title, updated_at)
            self.add_edge(f"pair:{lower}>{upper}", outcome_node, "resultado", confidence, title, updated_at, polarity)
            self.add_node(f"pair:{lower}>{upper}", f"{lower}>{upper}", "pair", confidence, title, updated_at)
        else:
            self._parse_unknown(":".join(parts), "", confidence, title, updated_at)

    def _parse_compare(self, parts: List[str], confidence: float, title: str, updated_at: str) -> None:
        # compare:roll:a>b=true | compare:roll:a~b=similar | compare:stack_support:a>b=true
        if len(parts) < 3:
            self._parse_unknown(":".join(parts), "", confidence, title, updated_at)
            return
        dimension = parts[1]
        relation_value = parts[2]
        if ">" in relation_value:
            a, b = relation_value.split(">", 1)
            a_node = f"obj:{a}"
            b_node = f"obj:{b}"
            self.add_node(a_node, a, "object", confidence, title, updated_at)
            self.add_node(b_node, b, "object", confidence, title, updated_at)
            self.add_edge(a_node, b_node, f"maior_{dimension}", confidence, title, updated_at, "positive")
        elif "~" in relation_value:
            a, b = relation_value.split("~", 1)
            a_node = f"obj:{a}"
            b_node = f"obj:{b}"
            self.add_node(a_node, a, "object", confidence, title, updated_at)
            self.add_node(b_node, b, "object", confidence, title, updated_at)
            self.add_edge(a_node, b_node, f"similar_{dimension}", confidence, title, updated_at, "neutral")
        else:
            self._parse_unknown(":".join(parts), "", confidence, title, updated_at)

    def _parse_rule(self, parts: List[str], confidence: float, title: str, updated_at: str) -> None:
        # rule:base_profile:<obj>:good/poor
        # rule:top_profile:<obj>:stackable/non_stackable
        # rule:conditional_base:<base>:<context>:good/poor
        # rule:global:<name>
        if len(parts) < 3:
            self._parse_unknown(":".join(parts), "", confidence, title, updated_at)
            return

        rule_family = parts[1]
        rule_node = f"rule:{':'.join(parts[1:])}"
        self.add_node(rule_node, relation_label(":".join(parts[1:])), "rule", confidence, title, updated_at)

        if rule_family in {"base_profile", "top_profile", "object_profile"} and len(parts) >= 4:
            obj_id = parts[2]
            result = parts[3]
            obj_node = f"obj:{obj_id}"
            self.add_node(obj_node, obj_id, "object", confidence, title, updated_at)
            polarity = "positive" if result in {"good", "stackable", "rolling_can_support"} else "negative" if result in {"poor", "non_stackable"} else "neutral"
            self.add_edge(obj_node, rule_node, f"tem_regra_{rule_family}", confidence, title, updated_at, polarity)
        elif rule_family == "conditional_base" and len(parts) >= 5:
            base = parts[2]
            context = parts[3]
            result = parts[4]
            base_node = f"obj:{base}"
            context_node = f"context:{context}"
            self.add_node(base_node, base, "object", confidence, title, updated_at)
            self.add_node(context_node, relation_label(context), "context", confidence, title, updated_at)
            polarity = "positive" if result == "good" else "negative" if result == "poor" else "neutral"
            self.add_edge(base_node, context_node, f"base_{result}_nesse_contexto", confidence, title, updated_at, polarity)
            self.add_edge(context_node, rule_node, "justifica_regra", confidence, title, updated_at, polarity)
        elif rule_family == "global":
            global_node = "system:global_rules"
            self.add_node(global_node, "regras globais", "system", confidence, title, updated_at)
            self.add_edge(global_node, rule_node, "contém", confidence, title, updated_at, "neutral")

    def _parse_hypothesis(self, parts: List[str], confidence: float, title: str, updated_at: str) -> None:
        # hypothesis:<lower>><upper>:predicted:<outcome> ou validated:<outcome>
        hyp_node = f"hyp:{':'.join(parts[1:])}"
        self.add_node(hyp_node, relation_label(":".join(parts[1:])), "hypothesis", confidence, title, updated_at)
        if len(parts) >= 4 and ">" in parts[1]:
            lower, upper = parts[1].split(">", 1)
            pair_node = f"pair:{lower}>{upper}"
            self.add_node(pair_node, f"{lower}>{upper}", "pair", confidence, title, updated_at)
            relation = f"hipotese_{parts[2]}"
            outcome = parts[3]
            polarity = "positive" if outcome == "stable" else "negative" if outcome == "unstable" else "uncertain"
            self.add_edge(pair_node, hyp_node, relation, confidence, title, updated_at, polarity)
        else:
            root = "system:hypotheses"
            self.add_node(root, "hipóteses", "system", confidence, title, updated_at)
            self.add_edge(root, hyp_node, "contém", confidence, title, updated_at, "neutral")

    def _parse_unknown(self, key: str, value: str, confidence: float, title: str, updated_at: str) -> None:
        node = f"memory:{key}"
        self.add_node(node, key, "unknown", confidence, title, updated_at)
        root = "system:memoria_bruta"
        self.add_node(root, "memória bruta", "system", confidence, "chaves ainda não parseadas", updated_at)
        self.add_edge(root, node, "contém", confidence, title, updated_at, "neutral")

    # -------------------------------------------------------------------------
    # episódios e estado
    # -------------------------------------------------------------------------

    def add_episode_row(self, row: sqlite3.Row) -> None:
        ep_id = int(row["id"])
        module = str(row["module"])
        outcome = str(row["outcome"])
        action = str(row["action_taken"])
        lesson = str(row["lesson"])
        timestamp = str(row["timestamp"])
        sigma_before = safe_float(row["sigma_before"])
        sigma_after = safe_float(row["sigma_after"])
        delta = sigma_after - sigma_before
        confidence = clamp(abs(delta) / 2.0 + 0.25, 0.0, 1.0)

        ep_node = f"episode:{ep_id}"
        label = f"ep {ep_id}: {outcome}"
        title = (
            f"episódio: {ep_id}<br>módulo: {html.escape(module)}<br>ação: {html.escape(action)}"
            f"<br>resultado: {html.escape(outcome)}<br>lição: {html.escape(lesson)}"
            f"<br>sigma: {sigma_before:.3f} → {sigma_after:.3f}<br>timestamp: {html.escape(timestamp)}"
        )
        self.add_node(ep_node, label, "episode", confidence, title, timestamp)
        module_node = f"module:{module}"
        self.add_node(module_node, module, "module", confidence, title, timestamp)
        self.add_edge(module_node, ep_node, "gerou_episodio", confidence, title, timestamp, "neutral")

        if "predict" in action or "previ" in action.lower():
            action_node = "action:predict"
        elif "validate" in action or "valid" in action.lower():
            action_node = "action:validate"
        elif "consolid" in action.lower():
            action_node = "action:consolidate"
        else:
            action_node = f"action:{action[:24]}"
        self.add_node(action_node, action_node.replace("action:", ""), "action", confidence, title, timestamp)
        self.add_edge(ep_node, action_node, "executou", confidence, title, timestamp, "neutral")

    def add_current_state(self, row: Optional[sqlite3.Row]) -> None:
        if row is None:
            return
        state_node = "state:current"
        sigma = safe_float(row["sigma"])
        energy = safe_float(row["energy"])
        info_self = safe_float(row["info_self"])
        info_external = safe_float(row["info_external"])
        latency = safe_float(row["latency"])
        pain = safe_float(row["pain_signal"])
        wellbeing = safe_float(row["wellbeing_signal"])
        timestamp = str(row["timestamp"])
        title = (
            f"estado atual<br>sigma: {sigma:.4f}<br>energia: {energy:.4f}"
            f"<br>info_self: {info_self:.4f}<br>info_external: {info_external:.4f}"
            f"<br>latência: {latency:.4f}<br>pain: {pain:.4f}<br>wellbeing: {wellbeing:.4f}"
            f"<br>timestamp: {html.escape(timestamp)}"
        )
        self.add_node(state_node, f"estado σ={sigma:.2f}", "state", clamp(sigma / 4.0), title, timestamp)

        for metric, value in [
            ("sigma", sigma),
            ("energy", energy),
            ("info_self", info_self),
            ("info_external", info_external),
            ("latency", latency),
            ("pain", pain),
            ("wellbeing", wellbeing),
        ]:
            metric_node = f"metric:{metric}"
            self.add_node(metric_node, f"{metric}: {value:.2f}", "metric", clamp(abs(value) / 4.0), title, timestamp)
            self.add_edge(state_node, metric_node, "mede", clamp(abs(value) / 4.0), title, timestamp, "neutral")


# -----------------------------------------------------------------------------
# leitura do banco
# -----------------------------------------------------------------------------


def load_graph_from_db(db_path: Path, episode_limit: int = 30) -> Tuple[DarwinGraphBuilder, Dict[str, Any]]:
    conn = sqlite3.connect(str(db_path), timeout=2.0)
    conn.row_factory = sqlite3.Row
    builder = DarwinGraphBuilder()
    meta: Dict[str, Any] = {
        "db_path": str(db_path),
        "generated_at": now_iso(),
        "semantic_count": 0,
        "episode_count": 0,
        "state_loaded": False,
        "warnings": [],
    }

    try:
        if table_exists(conn, "semantic_memory"):
            rows = conn.execute(
                "SELECT key, content, confidence, source, updated_at FROM semantic_memory ORDER BY updated_at ASC"
            ).fetchall()
            meta["semantic_count"] = len(rows)
            for row in rows:
                builder.parse_memory_row(row)
        else:
            meta["warnings"].append("Tabela semantic_memory não encontrada.")

        if table_exists(conn, "episodes"):
            rows = conn.execute(
                "SELECT * FROM episodes ORDER BY id DESC LIMIT ?",
                (int(episode_limit),),
            ).fetchall()
            meta["episode_count"] = len(rows)
            for row in rows:
                builder.add_episode_row(row)
        else:
            meta["warnings"].append("Tabela episodes não encontrada.")

        if table_exists(conn, "current_state"):
            row = conn.execute("SELECT * FROM current_state WHERE id = 1").fetchone()
            builder.add_current_state(row)
            meta["state_loaded"] = row is not None
        else:
            meta["warnings"].append("Tabela current_state não encontrada.")
    finally:
        conn.close()

    return builder, meta


# -----------------------------------------------------------------------------
# renderização HTML
# -----------------------------------------------------------------------------

NODE_COLORS = {
    "object": {"background": "#5DADE2", "border": "#21618C"},
    "pair": {"background": "#85C1E9", "border": "#2874A6"},
    "color": {"background": "#F7DC6F", "border": "#B7950B"},
    "shape": {"background": "#F8C471", "border": "#AF601A"},
    "category": {"background": "#D7BDE2", "border": "#6C3483"},
    "affordance": {"background": "#82E0AA", "border": "#1E8449"},
    "slot": {"background": "#A3E4D7", "border": "#117A65"},
    "outcome": {"background": "#F5B7B1", "border": "#922B21"},
    "context": {"background": "#D5F5E3", "border": "#239B56"},
    "rule": {"background": "#BB8FCE", "border": "#512E5F"},
    "hypothesis": {"background": "#FAD7A0", "border": "#B9770E"},
    "episode": {"background": "#D6DBDF", "border": "#566573"},
    "module": {"background": "#CCD1D1", "border": "#515A5A"},
    "action": {"background": "#AED6F1", "border": "#2471A3"},
    "state": {"background": "#F1948A", "border": "#943126"},
    "metric": {"background": "#F9E79F", "border": "#7D6608"},
    "system": {"background": "#E5E7E9", "border": "#626567"},
    "unknown": {"background": "#F2F3F4", "border": "#7B7D7D"},
}

EDGE_COLORS = {
    "positive": "#239B56",
    "negative": "#C0392B",
    "uncertain": "#B7950B",
    "neutral": "#566573",
}


def to_vis_data(builder: DarwinGraphBuilder) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []

    degree: Dict[str, int] = {node_id: 0 for node_id in builder.nodes}
    for edge in builder.edges.values():
        degree[edge.source] = degree.get(edge.source, 0) + 1
        degree[edge.target] = degree.get(edge.target, 0) + 1

    for node in builder.nodes.values():
        colors = NODE_COLORS.get(node.node_type, NODE_COLORS["unknown"])
        deg = degree.get(node.node_id, 0)
        size = 14 + min(22, deg * 2.0) + min(8, node.confidence * 8)
        title_lines = node.title_lines[:12]
        if node.last_updated:
            title_lines.append(f"última atualização: {html.escape(node.last_updated)}")
        title_lines.append(f"tipo: {html.escape(node.node_type)}")
        title_lines.append(f"observações no grafo: {node.observations}")
        title_lines.append(f"grau: {deg}")

        nodes.append({
            "id": node.node_id,
            "label": node.label,
            "group": node.node_type,
            "title": "<br>".join(title_lines),
            "value": max(1, deg + node.observations),
            "size": size,
            "color": colors,
            "font": {"size": 14},
        })

    for edge in builder.edges.values():
        color = EDGE_COLORS.get(edge.polarity, EDGE_COLORS["neutral"])
        width = 1.0 + 5.0 * clamp(edge.confidence) + min(2.0, math.log1p(edge.observations))
        title_lines = edge.title_lines[:10]
        title_lines.append(f"relação: {html.escape(edge.relation)}")
        title_lines.append(f"confiança: {edge.confidence:.2f}")
        title_lines.append(f"observações: {edge.observations}")
        if edge.last_updated:
            title_lines.append(f"última atualização: {html.escape(edge.last_updated)}")

        edges.append({
            "id": edge.edge_id,
            "from": edge.source,
            "to": edge.target,
            "label": relation_label(edge.relation),
            "title": "<br>".join(title_lines),
            "width": width,
            "color": {"color": color, "highlight": color, "hover": color},
            "arrows": "to",
            "font": {"align": "middle", "size": 10},
        })

    return nodes, edges


def render_html(
    builder: DarwinGraphBuilder,
    meta: Dict[str, Any],
    output_path: Path,
    refresh_seconds: Optional[int] = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    nodes, edges = to_vis_data(builder)
    node_types = sorted({node.get("group", "unknown") for node in nodes})
    warnings = meta.get("warnings", [])

    # Não usamos meta refresh porque em grafos maiores isso pode recarregar
    # a página antes do vis-network terminar de renderizar. O recarregamento,
    # quando habilitado, é feito por JavaScript depois da inicialização.
    refresh_meta = ""
    nodes_json = json.dumps(nodes, ensure_ascii=False)
    edges_json = json.dumps(edges, ensure_ascii=False)
    node_types_json = json.dumps(node_types, ensure_ascii=False)
    meta_json = json.dumps(meta, ensure_ascii=False, indent=2)

    html_text = f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  {refresh_meta}
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{APP_NAME}</title>
  <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
  <style>
    :root {{
      --bg: #0f172a;
      --panel: #111827;
      --text: #e5e7eb;
      --muted: #9ca3af;
      --accent: #7dd3fc;
      --line: #334155;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; background: var(--bg); color: var(--text); }}
    header {{ padding: 14px 18px; border-bottom: 1px solid var(--line); background: #020617; }}
    h1 {{ margin: 0 0 4px 0; font-size: 20px; }}
    .subtitle {{ color: var(--muted); font-size: 13px; }}
    .wrap {{ display: grid; grid-template-columns: 320px 1fr; height: calc(100vh - 68px); }}
    aside {{ overflow: auto; padding: 14px; border-right: 1px solid var(--line); background: var(--panel); }}
    #network {{ width: 100%; height: 100%; background: #f8fafc; }}
    .card {{ border: 1px solid var(--line); border-radius: 12px; padding: 12px; margin-bottom: 12px; background: #0b1220; }}
    .card h2 {{ margin: 0 0 8px 0; font-size: 15px; color: var(--accent); }}
    .stat {{ display: flex; justify-content: space-between; gap: 8px; padding: 4px 0; border-bottom: 1px dotted #253047; }}
    .stat:last-child {{ border-bottom: 0; }}
    label {{ display: block; margin: 5px 0; color: var(--text); font-size: 13px; }}
    input[type="text"] {{ width: 100%; padding: 8px; border-radius: 8px; border: 1px solid var(--line); background: #020617; color: var(--text); }}
    button {{ width: 100%; padding: 9px; margin-top: 8px; border: 0; border-radius: 10px; background: #0284c7; color: white; cursor: pointer; font-weight: bold; }}
    button:hover {{ background: #0369a1; }}
    .legend-item {{ display: flex; align-items: center; gap: 8px; margin: 4px 0; font-size: 13px; }}
    .dot {{ width: 14px; height: 14px; border-radius: 50%; border: 2px solid #111; display: inline-block; }}
    .warn {{ color: #fbbf24; font-size: 13px; }}
    .small {{ font-size: 12px; color: var(--muted); line-height: 1.35; }}
    @media (max-width: 900px) {{ .wrap {{ grid-template-columns: 1fr; }} aside {{ height: 330px; border-right: 0; border-bottom: 1px solid var(--line); }} #network {{ height: calc(100vh - 398px); }} }}
  </style>
</head>
<body>
  <header>
    <h1>🌱 Darwin Memory Graph</h1>
    <div class="subtitle">Grafo local da memória relacional do Darwin — gerado em {html.escape(str(meta.get('generated_at', '')))}</div>
  </header>
  <div class="wrap">
    <aside>
      <div class="card">
        <h2>Estado do grafo</h2>
        <div class="stat"><span>Nós</span><strong id="nodeCount">{len(nodes)}</strong></div>
        <div class="stat"><span>Arestas</span><strong id="edgeCount">{len(edges)}</strong></div>
        <div class="stat"><span>Memórias semânticas</span><strong>{meta.get('semantic_count', 0)}</strong></div>
        <div class="stat"><span>Episódios recentes</span><strong>{meta.get('episode_count', 0)}</strong></div>
        <div class="stat"><span>Banco</span><strong>{html.escape(Path(str(meta.get('db_path', ''))).name)}</strong></div>
      </div>

      <div class="card">
        <h2>Busca</h2>
        <input id="search" type="text" placeholder="ex.: red_ball, stable, with_block_top">
        <button onclick="focusSearch()">Focar nó</button>
        <button onclick="resetView()">Resetar visão</button>
      </div>

      <div class="card">
        <h2>Filtros por tipo</h2>
        <div id="filters"></div>
        <button onclick="applyFilters()">Aplicar filtros</button>
      </div>

      <div class="card">
        <h2>Legenda</h2>
        <div id="legend"></div>
        <div class="small" style="margin-top:8px;">A espessura das arestas cresce com confiança/observações. Verde tende a relação favorável; vermelho tende a instabilidade/falha; amarelo indica incerteza.</div>
      </div>

      <div class="card">
        <h2>Notas</h2>
        <div class="small">Este visualizador só lê o banco. Ele não altera a memória do Darwin.</div>
        {'<div class="warn">' + '<br>'.join(html.escape(w) for w in warnings) + '</div>' if warnings else ''}
        <pre class="small" style="white-space:pre-wrap; display:none;" id="metaBlock">{html.escape(meta_json)}</pre>
      </div>
    </aside>

    <main id="network"></main>
  </div>

<script>
const allNodes = new vis.DataSet({nodes_json});
const allEdges = new vis.DataSet({edges_json});
const nodeTypes = {node_types_json};
const nodeColorMap = {json.dumps(NODE_COLORS, ensure_ascii=False)};
let activeTypes = new Set(nodeTypes);
let network = null;
let nodesView = new vis.DataSet(allNodes.get());
let edgesView = new vis.DataSet(allEdges.get());

function buildLegend() {{
  const legend = document.getElementById('legend');
  legend.innerHTML = '';
  nodeTypes.forEach(t => {{
    const c = nodeColorMap[t] || nodeColorMap.unknown;
    const item = document.createElement('div');
    item.className = 'legend-item';
    item.innerHTML = `<span class="dot" style="background:${{c.background}}; border-color:${{c.border}}"></span><span>${{t}}</span>`;
    legend.appendChild(item);
  }});
}}

function buildFilters() {{
  const filters = document.getElementById('filters');
  filters.innerHTML = '';
  nodeTypes.forEach(t => {{
    const id = `filter_${{t}}`;
    const label = document.createElement('label');
    label.innerHTML = `<input type="checkbox" id="${{id}}" checked> ${{t}}`;
    filters.appendChild(label);
  }});
}}

function applyFilters() {{
  activeTypes = new Set();
  nodeTypes.forEach(t => {{
    const cb = document.getElementById(`filter_${{t}}`);
    if (cb && cb.checked) activeTypes.add(t);
  }});
  const filteredNodes = allNodes.get().filter(n => activeTypes.has(n.group));
  const allowed = new Set(filteredNodes.map(n => n.id));
  const filteredEdges = allEdges.get().filter(e => allowed.has(e.from) && allowed.has(e.to));
  nodesView.clear(); nodesView.add(filteredNodes);
  edgesView.clear(); edgesView.add(filteredEdges);
  document.getElementById('nodeCount').textContent = filteredNodes.length;
  document.getElementById('edgeCount').textContent = filteredEdges.length;
}}

function focusSearch() {{
  const q = document.getElementById('search').value.trim().toLowerCase();
  if (!q) return;
  const matches = nodesView.get().filter(n => String(n.label).toLowerCase().includes(q) || String(n.id).toLowerCase().includes(q));
  if (matches.length === 0) {{ alert('Nenhum nó encontrado.'); return; }}
  const ids = matches.slice(0, 12).map(n => n.id);
  network.selectNodes(ids);
  network.focus(ids[0], {{ scale: 1.4, animation: true }});
}}

function resetView() {{
  network.fit({{ animation: true }});
}}

function initNetwork() {{
  const container = document.getElementById('network');
  const data = {{ nodes: nodesView, edges: edgesView }};
  const options = {{
    autoResize: true,
    layout: {{ improvedLayout: true }},
    physics: {{
      enabled: true,
      stabilization: {{ enabled: false }},
      barnesHut: {{ gravitationalConstant: -28000, springLength: 115, springConstant: 0.035, damping: 0.20 }}
    }},
    interaction: {{ hover: true, tooltipDelay: 120, navigationButtons: true, keyboard: true }},
    nodes: {{ shape: 'dot', borderWidth: 2, shadow: true }},
    edges: {{ smooth: {{ type: 'dynamic' }}, shadow: false }}
  }};
  network = new vis.Network(container, data, options);
  // Força enquadramento inicial. Isso corrige páginas que abrem em branco
  // porque o grafo nasceu fora da área visível ou recarregou cedo demais.
  setTimeout(() => {{
    try {{ network.fit({{ animation: true }}); }} catch (e) {{ console.warn(e); }}
  }}, 700);
  setTimeout(() => {{
    try {{ network.fit({{ animation: true }}); }} catch (e) {{ console.warn(e); }}
  }}, 2200);
}}

buildLegend();
buildFilters();
initNetwork();

const browserRefreshSeconds = {int(refresh_seconds) if refresh_seconds else 0};
if (browserRefreshSeconds > 0) {{
  setTimeout(() => window.location.reload(), browserRefreshSeconds * 1000);
}}
</script>
</body>
</html>
"""
    output_path.write_text(html_text, encoding="utf-8")


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


def generate_once(db_path: Path, output_path: Path, episode_limit: int, refresh_seconds: Optional[int]) -> Tuple[int, int]:
    builder, meta = load_graph_from_db(db_path, episode_limit=episode_limit)
    render_html(builder, meta, output_path, refresh_seconds=refresh_seconds)
    return len(builder.nodes), len(builder.edges)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Visualizador do grafo de memória do Darwin.")
    parser.add_argument("--db", default=None, help="Caminho para darwin.db. Padrão: darwin_home/darwin.db")
    parser.add_argument("--out", default=None, help="Caminho do HTML gerado. Padrão: darwin_home/exports/darwin_memory_graph.html")
    parser.add_argument("--watch", action="store_true", help="Regenera o HTML continuamente.")
    parser.add_argument("--interval", type=int, default=3, help="Intervalo de atualização em segundos no modo --watch.")
    parser.add_argument("--browser-refresh", type=int, default=0, help="Recarrega o HTML no navegador a cada N segundos. Use 12 ou mais para grafos grandes. Padrão: 0, sem recarregar automaticamente.")
    parser.add_argument("--open", action="store_true", help="Abre o HTML no navegador.")
    parser.add_argument("--episodes", type=int, default=40, help="Número de episódios recentes para incluir.")
    args = parser.parse_args(argv)

    try:
        db_path = detect_db_path(args.db)
    except FileNotFoundError as exc:
        print(f"[ERRO] {exc}", file=sys.stderr)
        return 2

    if args.out:
        output_path = Path(args.out)
    else:
        output_path = db_path.parent / "exports" / "darwin_memory_graph.html"

    if args.open:
        # Abre uma vez; no modo watch, o HTML se auto-atualiza.
        output_path.parent.mkdir(parents=True, exist_ok=True)

    # O terminal pode regenerar a cada 3s, mas o navegador não deve recarregar
    # tão rápido em grafos grandes. Use --browser-refresh 12/15 se quiser auto-refresh.
    refresh_seconds = max(10, int(args.browser_refresh)) if args.browser_refresh and args.browser_refresh > 0 else None

    opened = False
    if args.watch:
        print("Modo watch ativo: o terminal fica rodando até você apertar Ctrl+C.")
        if not refresh_seconds:
            print("Navegador sem auto-refresh. Para atualizar a visualização, aperte F5 ou use --browser-refresh 15.")
    try:
        while True:
            try:
                node_count, edge_count = generate_once(
                    db_path=db_path,
                    output_path=output_path,
                    episode_limit=args.episodes,
                    refresh_seconds=refresh_seconds,
                )
                print(f"[{datetime.now().strftime('%H:%M:%S')}] grafo atualizado: {node_count} nós, {edge_count} arestas -> {output_path}")
                if args.open and not opened:
                    webbrowser.open(output_path.resolve().as_uri())
                    opened = True
            except sqlite3.OperationalError as exc:
                # Pode acontecer se o Darwin estiver escrevendo no banco exatamente naquele instante.
                print(f"[{datetime.now().strftime('%H:%M:%S')}] banco ocupado/indisponível: {exc}")
            except Exception as exc:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] erro ao gerar grafo: {repr(exc)}", file=sys.stderr)
                if not args.watch:
                    return 1

            if not args.watch:
                break
            time.sleep(max(1, int(args.interval)))
    except KeyboardInterrupt:
        print("\nVisualizador encerrado.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
