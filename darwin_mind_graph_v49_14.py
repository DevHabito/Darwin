from __future__ import annotations

"""
DARWIN v49.14 - Mind Graph Viewer

Objetivo:
Abrir uma janela com o grafo da "cabeca" do Darwin: marcos,
memorias, primeiras palavras, geometria, atencao compartilhada,
imitacao vocal, jogo de memoria e RZS, todos lidos do darwin.db.

Uso:
    py darwin_mind_graph_v49_14.py
    py darwin_mind_graph_v49_14.py --self-test --details
"""

import argparse
import json
import math
import sqlite3
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import ttk
from typing import Any


DB = Path("darwin_home") / "darwin.db"


KIND_COLORS = {
    "root": "#eaf6ff",
    "regulator": "#ffcc66",
    "module": "#58b0ff",
    "family": "#9cc9ff",
    "concept": "#75e7a8",
    "word": "#f2bf72",
    "meaning": "#b197fc",
    "entity": "#ff8ab3",
    "sound": "#8fd3ff",
    "symbol": "#5eead4",
    "memory": "#c7d2fe",
    "episode": "#fca5a5",
    "stat": "#a7f3d0",
}

MODULE_ORDER = [
    "rzs",
    "geometry",
    "first_words",
    "vocal_imitation",
    "joint_attention",
    "memory_cards",
    "companion",
    "semantic",
    "episodes",
]


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def pj(value: str | None, fallback: Any = None) -> Any:
    try:
        return json.loads(value or "{}")
    except Exception:
        return {} if fallback is None else fallback


def short(text: str, limit: int = 42) -> str:
    clean = " ".join(str(text).split())
    return clean if len(clean) <= limit else clean[: limit - 1] + "..."


@dataclass
class GraphNode:
    node_id: str
    label: str
    kind: str
    parent_id: str = ""
    weight: float = 0.5
    details: dict[str, Any] = field(default_factory=dict)
    x: float = 0.0
    y: float = 0.0


@dataclass
class GraphEdge:
    source: str
    target: str
    kind: str
    weight: float = 0.5
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class MindGraph:
    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)

    def add_node(self, node_id: str, label: str, kind: str, parent_id: str = "", weight: float = 0.5, details: dict[str, Any] | None = None) -> GraphNode:
        if node_id in self.nodes:
            node = self.nodes[node_id]
            node.weight = max(node.weight, weight)
            node.details.update(details or {})
            if parent_id and not node.parent_id:
                node.parent_id = parent_id
            return node
        node = GraphNode(node_id, label, kind, parent_id, clamp(weight, 0.05, 1.0), details or {})
        self.nodes[node_id] = node
        return node

    def add_edge(self, source: str, target: str, kind: str, weight: float = 0.5, details: dict[str, Any] | None = None) -> None:
        if source not in self.nodes or target not in self.nodes:
            return
        key = (source, target, kind)
        for edge in self.edges:
            if (edge.source, edge.target, edge.kind) == key:
                edge.weight = max(edge.weight, weight)
                edge.details.update(details or {})
                return
        self.edges.append(GraphEdge(source, target, kind, clamp(weight, 0.05, 1.0), details or {}))


class MindGraphBuilder:
    def __init__(self, db_path: Path = DB) -> None:
        self.db_path = db_path
        self.graph = MindGraph()

    def connect(self) -> sqlite3.Connection:
        if not self.db_path.exists():
            raise FileNotFoundError(f"Banco Darwin nao encontrado: {self.db_path}")
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def table_exists(self, conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        return row is not None

    def rows(self, conn: sqlite3.Connection, table: str, where: str = "", params: tuple[Any, ...] = (), limit: int | None = None) -> list[dict[str, Any]]:
        if not self.table_exists(conn, table):
            return []
        sql = f"SELECT * FROM {table}{where} ORDER BY id ASC"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        out = []
        for row in conn.execute(sql, params).fetchall():
            item = {k: row[k] for k in row.keys()}
            item["payload"] = pj(str(item.get("payload_json") or "{}"))
            out.append(item)
        return out

    def latest_value(self, conn: sqlite3.Connection, table: str, column: str, where: str = "", params: tuple[Any, ...] = ()) -> str:
        if not self.table_exists(conn, table):
            return ""
        clause = f" WHERE {where}" if where else ""
        row = conn.execute(f"SELECT {column} AS value FROM {table}{clause} ORDER BY id DESC LIMIT 1", params).fetchone()
        return str(row["value"]) if row else ""

    def build(self) -> MindGraph:
        with self.connect() as conn:
            self.base()
            self.add_rzs(conn)
            self.add_geometry(conn)
            self.add_first_words(conn)
            self.add_vocal_imitation(conn)
            self.add_joint_attention(conn)
            self.add_memory_cards(conn)
            self.add_companion(conn)
            self.add_semantic_memory(conn)
            self.add_episode_modules(conn)
            self.layout()
        return self.graph

    def base(self) -> None:
        g = self.graph
        g.add_node("darwin", "DARWIN", "root", weight=1.0, details={"role": "root mind graph"})
        modules = {
            "rzs": ("RZS", "regulator"),
            "geometry": ("Geometria", "module"),
            "first_words": ("Primeiras palavras", "module"),
            "vocal_imitation": ("Imitacao vocal", "module"),
            "joint_attention": ("Atencao compartilhada", "module"),
            "memory_cards": ("Jogo de memoria", "module"),
            "companion": ("Companion", "module"),
            "semantic": ("Memoria semantica", "memory"),
            "episodes": ("Episodios", "episode"),
        }
        for node_id, (label, kind) in modules.items():
            g.add_node(node_id, label, kind, "darwin", 0.78, {"module": node_id})
            g.add_edge("darwin", node_id, "contains", 0.75)
        for module in ("geometry", "first_words", "vocal_imitation", "joint_attention", "memory_cards", "companion"):
            g.add_edge("rzs", module, "regulates", 0.72)

    def add_rzs(self, conn: sqlite3.Connection) -> None:
        g = self.graph
        latest = self.latest_value(conn, "rzs_stress_tests_v49_3", "scenario_id", "phase='scenario_complete'")
        if latest:
            g.nodes["rzs"].details["latest_scenario"] = latest
        decisions = ["continue", "narrow_focus", "replay_memory", "consolidate", "pause_for_stability"]
        for idx, decision in enumerate(decisions):
            nid = f"rzs:{decision}"
            g.add_node(nid, decision, "regulator", "rzs", 0.55 + idx * 0.04, {"decision": decision})
            g.add_edge("rzs", nid, "decision", 0.64)

    def add_geometry(self, conn: sqlite3.Connection) -> None:
        g = self.graph
        scenario = self.latest_value(conn, "geometry_learning_scenarios_v49_7", "scenario_id", "phase='geometry_complete'")
        if not scenario:
            return
        g.nodes["geometry"].details["scenario"] = scenario
        rows = self.rows(conn, "geometry_concepts_v49_7", " WHERE scenario_id=?", (scenario,))
        family_nodes: set[str] = set()
        for row in rows:
            family = str(row.get("family") or "geometry")
            fam_id = f"geometry_family:{family}"
            if fam_id not in family_nodes:
                g.add_node(fam_id, family, "family", "geometry", 0.52, {"source": "v49.7"})
                g.add_edge("geometry", fam_id, "has_family", 0.60)
                family_nodes.add(fam_id)
            key = str(row.get("concept_key") or "")
            if not key:
                continue
            nid = f"geometry:{key}"
            confidence = float(row.get("confidence") or 0.0)
            g.add_node(
                nid,
                key.replace("_", " "),
                "concept",
                fam_id,
                max(confidence, 0.22),
                {
                    "scenario": scenario,
                    "family": family,
                    "confidence": confidence,
                    "learning_weight": row.get("learning_weight"),
                    "definition": row.get("definition"),
                },
            )
            g.add_edge(fam_id, nid, "contains_concept", max(confidence, 0.35))

    def add_first_words(self, conn: sqlite3.Connection) -> None:
        g = self.graph
        session = self.latest_value(conn, "voice_first_word_sessions_v49_10", "session_id", "phase='first_words_complete'")
        if not session:
            return
        g.nodes["first_words"].details["session"] = session
        rows = self.rows(conn, "voice_word_meanings_v49_10", " WHERE session_id=?", (session,))
        for row in rows:
            word = str(row.get("canonical_word") or "")
            if not word:
                continue
            word_id = f"word:{word}"
            meaning_id = f"meaning:{row.get('meaning_key') or word}"
            confidence = float(row.get("meaning_confidence") or 0.0)
            sound_conf = float(row.get("sound_confidence") or 0.0)
            g.add_node(word_id, word, "word", "first_words", max(confidence, 0.35), {"session": session, "sound_confidence": sound_conf})
            g.add_node(
                meaning_id,
                str(row.get("meaning_key") or word).replace("_", " "),
                "meaning",
                word_id,
                max(confidence, 0.30),
                {"relational_meaning": row.get("relational_meaning"), "confidence": confidence, "exposures": row.get("exposure_count")},
            )
            g.add_edge("first_words", word_id, "heard_word", max(sound_conf, 0.32))
            g.add_edge(word_id, meaning_id, "means", max(confidence, 0.32))

    def add_vocal_imitation(self, conn: sqlite3.Connection) -> None:
        g = self.graph
        session = self.latest_value(conn, "vocal_imitation_sessions_v49_11", "session_id", "phase='vocal_imitation_complete'")
        if not session:
            return
        g.nodes["vocal_imitation"].details["session"] = session
        rows = self.rows(conn, "vocal_imitation_targets_v49_11", " WHERE session_id=?", (session,))
        for row in rows:
            word = str(row.get("target_word") or "")
            if not word:
                continue
            word_id = f"word:{word}"
            target_id = f"vocal_target:{word}"
            g.add_node(target_id, f"dizer {word}", "sound", "vocal_imitation", float(row.get("priority") or 0.45), {"session": session, "syllables": row.get("syllables_json")})
            g.add_edge("vocal_imitation", target_id, "practices", 0.58)
            if word_id in g.nodes:
                g.add_edge(word_id, target_id, "can_try_to_say", 0.68)

    def add_joint_attention(self, conn: sqlite3.Connection) -> None:
        g = self.graph
        session = self.latest_value(conn, "joint_attention_sessions_v49_12", "session_id", "phase='joint_attention_complete'")
        if not session:
            return
        g.nodes["joint_attention"].details["session"] = session
        scenes = self.rows(conn, "joint_attention_scenes_v49_12", " WHERE session_id=?", (session,))
        for row in scenes:
            entity_id = str(row.get("entity_id") or "")
            word = str(row.get("label_word") or "")
            if not entity_id or not word:
                continue
            nid = f"entity:{word}"
            g.add_node(
                nid,
                f"objeto {word}",
                "entity",
                "joint_attention",
                float(row.get("priority") or 0.45),
                {"entity_id": entity_id, "kind": row.get("entity_kind"), "meaning": row.get("relational_meaning"), "session": session},
            )
            g.add_edge("joint_attention", nid, "scene_entity", 0.55)
            word_id = f"word:{word}"
            if word_id in g.nodes:
                g.add_edge(word_id, nid, "refers_to", 0.76)
        bindings = self.rows(conn, "joint_attention_word_bindings_v49_12", " WHERE session_id=?", (session,))
        best: dict[tuple[str, str], dict[str, Any]] = {}
        for row in bindings:
            if int(row.get("is_correct") or 0) != 1:
                continue
            word = str(row.get("label_word") or "")
            entity = str(row.get("entity_id") or "").replace("entity:", "")
            key = (word, entity)
            if key not in best or float(row.get("confidence") or 0.0) > float(best[key].get("confidence") or 0.0):
                best[key] = row
        for (word, entity), row in best.items():
            word_id = f"word:{word}"
            ent_id = f"entity:{entity}"
            if word_id in g.nodes and ent_id in g.nodes:
                g.add_edge(word_id, ent_id, "grounded_reference", float(row.get("confidence") or 0.45), {"binding_strength": row.get("binding_strength")})

    def add_memory_cards(self, conn: sqlite3.Connection) -> None:
        g = self.graph
        game = self.latest_value(conn, "memory_card_games_v49_13", "game_id", "phase='game_complete'")
        if not game:
            return
        g.nodes["memory_cards"].details["latest_game"] = game
        complete_rows = self.rows(conn, "memory_card_games_v49_13", " WHERE game_id=? AND phase='game_complete'", (game,))
        if complete_rows:
            payload = complete_rows[-1].get("payload", {})
            stat_id = "memory_cards:stats"
            label = f"{payload.get('matches', 0)} pares em {payload.get('turn_count', 0)} turnos"
            g.add_node(stat_id, label, "stat", "memory_cards", 0.60, payload)
            g.add_edge("memory_cards", stat_id, "completed_game", 0.70)
        moves = self.rows(conn, "memory_card_moves_v49_13", " WHERE game_id=?", (game,))
        symbols = sorted({str(row.get("observed_symbol") or "") for row in moves if row.get("observed_symbol")})
        for symbol in symbols:
            nid = f"card_symbol:{symbol}"
            g.add_node(nid, symbol, "symbol", "memory_cards", 0.48, {"game": game})
            g.add_edge("memory_cards", nid, "observed_symbol", 0.46)

    def add_companion(self, conn: sqlite3.Connection) -> None:
        g = self.graph
        session = self.latest_value(conn, "companion_sessions_v49_8", "session_id", "phase='session_complete'")
        if not session:
            return
        g.nodes["companion"].details["session"] = session
        rows = self.rows(conn, "companion_dialogues_v49_8", " WHERE session_id=?", (session,))
        intents: dict[str, int] = {}
        for row in rows:
            intent = str(row.get("intent") or "")
            if intent:
                intents[intent] = intents.get(intent, 0) + 1
        for intent, count in sorted(intents.items()):
            nid = f"companion:intent:{intent}"
            g.add_node(nid, intent.replace("_", " "), "memory", "companion", min(1.0, 0.30 + count * 0.08), {"count": count, "session": session})
            g.add_edge("companion", nid, "dialogue_intent", 0.45)

    def add_semantic_memory(self, conn: sqlite3.Connection) -> None:
        g = self.graph
        if not self.table_exists(conn, "semantic_memory"):
            return
        rows = conn.execute(
            """
            SELECT key, content, confidence, source, updated_at
            FROM semantic_memory
            ORDER BY updated_at DESC, confidence DESC
            LIMIT 35
            """
        ).fetchall()
        for row in rows:
            key = str(row["key"])
            nid = f"semantic:{key}"
            label = short(key.replace("_", " "), 38)
            confidence = float(row["confidence"] or 0.0)
            g.add_node(nid, label, "memory", "semantic", max(confidence, 0.20), {"key": key, "content": row["content"], "source": row["source"], "confidence": confidence})
            g.add_edge("semantic", nid, "stored_memory", max(confidence, 0.22))

    def add_episode_modules(self, conn: sqlite3.Connection) -> None:
        g = self.graph
        if not self.table_exists(conn, "episodes"):
            return
        rows = conn.execute(
            """
            SELECT module, COUNT(*) AS n
            FROM episodes
            GROUP BY module
            ORDER BY n DESC
            LIMIT 24
            """
        ).fetchall()
        for row in rows:
            module = str(row["module"])
            count = int(row["n"])
            nid = f"episode_module:{module}"
            g.add_node(nid, short(module.replace("_", " "), 34), "episode", "episodes", min(1.0, 0.20 + count / 90.0), {"module": module, "episode_count": count})
            g.add_edge("episodes", nid, "has_episodes", min(1.0, 0.25 + count / 120.0))

    def layout(self) -> None:
        g = self.graph
        if "darwin" in g.nodes:
            g.nodes["darwin"].x = 0.0
            g.nodes["darwin"].y = 0.0
        module_radius = 250.0
        child_radius = 115.0
        module_ids = [m for m in MODULE_ORDER if m in g.nodes]
        for idx, node_id in enumerate(module_ids):
            angle = -math.pi / 2 + idx * (2 * math.pi / max(1, len(module_ids)))
            node = g.nodes[node_id]
            node.x = math.cos(angle) * module_radius
            node.y = math.sin(angle) * module_radius
        children_by_parent: dict[str, list[GraphNode]] = {}
        for node in g.nodes.values():
            if node.node_id == "darwin" or node.node_id in module_ids:
                continue
            parent = node.parent_id if node.parent_id in g.nodes else "darwin"
            children_by_parent.setdefault(parent, []).append(node)
        for parent_id, children in children_by_parent.items():
            parent = g.nodes[parent_id]
            children.sort(key=lambda n: (n.kind, n.label))
            count = len(children)
            for idx, node in enumerate(children):
                span = 2 * math.pi
                angle = idx * span / max(1, count) + (0.23 if count > 1 else 0.0)
                local_radius = child_radius + 9.0 * (idx % 5)
                if count > 14:
                    local_radius += 45.0 * (idx // 14)
                node.x = parent.x + math.cos(angle) * local_radius
                node.y = parent.y + math.sin(angle) * local_radius


class MindGraphApp:
    BG = "#071018"
    PANEL = "#10202d"
    INK = "#edf7fb"
    MUTED = "#93aabd"
    EDGE = "#31526d"
    HILITE = "#fff7ad"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Darwin Mind Graph v49.14")
        self.root.geometry("1200x820")
        self.root.minsize(980, 680)
        self.root.configure(bg=self.BG)
        self.graph = MindGraph()
        self.scale = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.drag_start: tuple[int, int] | None = None
        self.selected_id = ""
        self.node_screen: dict[str, tuple[float, float, float]] = {}

        top = tk.Frame(root, bg=self.PANEL)
        top.pack(fill="x")
        ttk.Button(top, text="Atualizar", command=self.reload).pack(side="left", padx=(14, 8), pady=10)
        ttk.Button(top, text="Centralizar", command=self.center_graph).pack(side="left", padx=(0, 8), pady=10)
        ttk.Button(top, text="+", command=lambda: self.zoom_at(1.15)).pack(side="left", padx=(0, 8), pady=10)
        ttk.Button(top, text="-", command=lambda: self.zoom_at(0.87)).pack(side="left", padx=(0, 14), pady=10)
        self.status_var = tk.StringVar(value="carregando grafo")
        tk.Label(top, textvariable=self.status_var, bg=self.PANEL, fg=self.MUTED, font=("Segoe UI", 10)).pack(side="left", padx=8)

        body = tk.Frame(root, bg=self.BG)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, bg=self.BG, highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.details = tk.Text(body, width=38, bg="#061019", fg=self.INK, insertbackground=self.INK, relief="flat", wrap="word", font=("Segoe UI", 10))
        self.details.pack(side="right", fill="y")
        self.details.config(state="disabled")

        self.canvas.bind("<ButtonPress-1>", self.on_click)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<MouseWheel>", self.on_wheel)
        self.canvas.bind("<Button-4>", lambda e: self.zoom_at(1.12, e.x, e.y))
        self.canvas.bind("<Button-5>", lambda e: self.zoom_at(0.89, e.x, e.y))
        self.root.after(100, self.reload)

    def reload(self) -> None:
        try:
            self.graph = MindGraphBuilder().build()
            self.selected_id = ""
            self.center_graph()
            self.write_details("Clique em um no para ver detalhes.\n\nO grafo e montado a partir do darwin.db.")
            self.status_var.set(f"nos={len(self.graph.nodes)}  arestas={len(self.graph.edges)}")
        except Exception as exc:
            self.graph = MindGraph()
            self.status_var.set(f"erro: {exc}")
            self.write_details(f"Erro ao carregar grafo:\n{exc}")
            self.draw()

    def center_graph(self) -> None:
        self.scale = 1.0
        self.offset_x = self.canvas.winfo_width() / 2
        self.offset_y = self.canvas.winfo_height() / 2
        if self.offset_x <= 1:
            self.offset_x = 430
            self.offset_y = 330
        self.draw()

    def world_to_screen(self, x: float, y: float) -> tuple[float, float]:
        return self.offset_x + x * self.scale, self.offset_y + y * self.scale

    def screen_to_world(self, x: float, y: float) -> tuple[float, float]:
        return (x - self.offset_x) / self.scale, (y - self.offset_y) / self.scale

    def zoom_at(self, factor: float, sx: float | None = None, sy: float | None = None) -> None:
        if sx is None:
            sx = self.canvas.winfo_width() / 2
        if sy is None:
            sy = self.canvas.winfo_height() / 2
        wx, wy = self.screen_to_world(sx, sy)
        self.scale = clamp(self.scale * factor, 0.25, 3.5)
        self.offset_x = sx - wx * self.scale
        self.offset_y = sy - wy * self.scale
        self.draw()

    def on_wheel(self, event: tk.Event) -> None:
        self.zoom_at(1.12 if event.delta > 0 else 0.89, event.x, event.y)

    def on_click(self, event: tk.Event) -> None:
        hit = self.hit_node(event.x, event.y)
        if hit:
            self.selected_id = hit
            self.show_node(hit)
            self.draw()
            self.drag_start = None
        else:
            self.drag_start = (event.x, event.y)

    def on_drag(self, event: tk.Event) -> None:
        if self.drag_start is None:
            return
        x0, y0 = self.drag_start
        self.offset_x += event.x - x0
        self.offset_y += event.y - y0
        self.drag_start = (event.x, event.y)
        self.draw()

    def hit_node(self, sx: float, sy: float) -> str:
        best = ""
        best_d = 999999.0
        for node_id, (x, y, r) in self.node_screen.items():
            d = math.hypot(sx - x, sy - y)
            if d <= r + 4 and d < best_d:
                best = node_id
                best_d = d
        return best

    def connected_to_selected(self, node_id: str) -> bool:
        if not self.selected_id:
            return False
        if node_id == self.selected_id:
            return True
        for edge in self.graph.edges:
            if edge.source == self.selected_id and edge.target == node_id:
                return True
            if edge.target == self.selected_id and edge.source == node_id:
                return True
        return False

    def draw(self) -> None:
        c = self.canvas
        c.delete("all")
        w = max(1, c.winfo_width())
        c.create_text(w / 2, 28, text="DARWIN MIND GRAPH v49.14", fill=self.INK, font=("Segoe UI", 20, "bold"))
        c.create_text(w / 2, 54, text="grafo construido do darwin.db", fill=self.MUTED, font=("Segoe UI", 10))
        self.node_screen.clear()
        for edge in self.graph.edges:
            if edge.source not in self.graph.nodes or edge.target not in self.graph.nodes:
                continue
            a = self.graph.nodes[edge.source]
            b = self.graph.nodes[edge.target]
            x1, y1 = self.world_to_screen(a.x, a.y)
            x2, y2 = self.world_to_screen(b.x, b.y)
            selected_edge = self.selected_id and (edge.source == self.selected_id or edge.target == self.selected_id)
            color = self.HILITE if selected_edge else self.EDGE
            width = 2.6 if selected_edge else 1.0 + edge.weight * 1.4
            c.create_line(x1, y1, x2, y2, fill=color, width=width)
        for node in sorted(self.graph.nodes.values(), key=lambda n: (n.kind != "root", n.kind, n.label)):
            x, y = self.world_to_screen(node.x, node.y)
            r = (12 + node.weight * 14) * self.scale ** 0.35
            self.node_screen[node.node_id] = (x, y, r)
            color = KIND_COLORS.get(node.kind, "#8ab4f8")
            outline = self.HILITE if self.connected_to_selected(node.node_id) else "#e5f7ff"
            width = 4 if node.node_id == self.selected_id else 2
            if node.kind == "root":
                c.create_oval(x - r * 1.25, y - r * 1.25, x + r * 1.25, y + r * 1.25, fill=color, outline=outline, width=width)
            elif node.kind in {"module", "regulator", "memory", "episode"}:
                c.create_rectangle(x - r * 1.35, y - r, x + r * 1.35, y + r, fill=color, outline=outline, width=width)
            else:
                c.create_oval(x - r, y - r, x + r, y + r, fill=color, outline=outline, width=width)
            if self.scale > 0.45 or node.kind in {"root", "module", "regulator", "memory", "episode"}:
                label = short(node.label, 24)
                c.create_text(x, y + r + 12, text=label, fill=self.INK, font=("Segoe UI", max(7, int(9 * self.scale ** 0.25))))
        self.draw_legend(c)

    def draw_legend(self, c: tk.Canvas) -> None:
        x = 18
        y = 86
        for kind in ["root", "regulator", "module", "concept", "word", "meaning", "entity", "symbol", "memory", "episode"]:
            color = KIND_COLORS.get(kind, "#8ab4f8")
            c.create_oval(x, y - 6, x + 12, y + 6, fill=color, outline="")
            c.create_text(x + 18, y, text=kind, fill=self.MUTED, anchor="w", font=("Segoe UI", 8))
            y += 18

    def show_node(self, node_id: str) -> None:
        node = self.graph.nodes[node_id]
        related_edges = [e for e in self.graph.edges if e.source == node_id or e.target == node_id]
        lines = [
            node.label,
            "=" * min(34, max(8, len(node.label))),
            f"id: {node.node_id}",
            f"tipo: {node.kind}",
            f"peso: {node.weight:.3f}",
            "",
            "Detalhes:",
        ]
        if node.details:
            for key, value in sorted(node.details.items()):
                lines.append(f"- {key}: {value}")
        else:
            lines.append("- sem detalhes adicionais")
        lines.extend(["", "Conexoes:"])
        for edge in related_edges[:40]:
            other = edge.target if edge.source == node_id else edge.source
            other_label = self.graph.nodes.get(other, GraphNode(other, other, "unknown")).label
            direction = "->" if edge.source == node_id else "<-"
            lines.append(f"- {direction} {other_label} ({edge.kind}, {edge.weight:.2f})")
        self.write_details("\n".join(lines))

    def write_details(self, text: str) -> None:
        self.details.config(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.config(state="disabled")


def run_self_test(details: bool = False) -> dict[str, Any]:
    graph = MindGraphBuilder().build()
    kinds = sorted({node.kind for node in graph.nodes.values()})
    required = {
        "darwin",
        "rzs",
        "geometry",
        "first_words",
        "vocal_imitation",
        "joint_attention",
        "memory_cards",
        "semantic",
        "episodes",
    }
    report = {
        "nodes": len(graph.nodes),
        "edges": len(graph.edges),
        "kinds": kinds,
        "has_required_modules": required.issubset(set(graph.nodes)),
        "concept_nodes": sum(1 for n in graph.nodes.values() if n.kind == "concept"),
        "word_nodes": sum(1 for n in graph.nodes.values() if n.kind == "word"),
        "entity_nodes": sum(1 for n in graph.nodes.values() if n.kind == "entity"),
        "symbol_nodes": sum(1 for n in graph.nodes.values() if n.kind == "symbol"),
    }
    report["ok"] = (
        report["nodes"] >= 60
        and report["edges"] >= 60
        and report["has_required_modules"]
        and report["concept_nodes"] >= 10
        and report["word_nodes"] >= 4
        and report["entity_nodes"] >= 4
    )
    if details:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"DARWIN v49.14 mind graph self-test: nodes={report['nodes']} edges={report['edges']} ok={report['ok']}")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Darwin Mind Graph Viewer v49.14")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        report = run_self_test(details=args.details)
        return 0 if report["ok"] else 2
    root = tk.Tk()
    MindGraphApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
