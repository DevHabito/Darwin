from __future__ import annotations

"""
DARWIN v48.0 — Physical Geometry Nursery / Shape Sorter

Objetivo:
- Iniciar a fase pedagógica física do Darwin sem tocar no núcleo v47.13.
- Ensinar encaixe por experiência geométrica, não por associação verbal simples.
- Teste-base: brinquedo de encaixar formas nos buracos corretos.

Princípio:
Darwin não deve apenas decorar "quadrado vai no quadrado".
Darwin deve registrar por que uma peça encaixa:
- compatibilidade de contorno
- compatibilidade de tamanho
- compatibilidade de profundidade
- possibilidade de rotação
- ausência de colisão

Uso:
    py darwin_shape_sorter_nursery_v48.py --dry-run
    py darwin_shape_sorter_nursery_v48.py --reset
    py darwin_shape_sorter_nursery_v48.py --lesson basic
    py darwin_shape_sorter_nursery_v48.py --lesson all
    py darwin_shape_sorter_nursery_v48.py --dashboard

Este módulo usa o mesmo banco:
    darwin_home/darwin.db

Tabelas novas:
- geometry_shapes_v48
- geometry_pieces_v48
- geometry_holes_v48
- geometry_fit_attempts_v48
- geometry_rules_v48
- geometry_spatial_concepts_v48
- geometry_curriculum_events_v48
"""

import argparse
import json
import math
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DB_PATH = Path("darwin_home") / "darwin.db"
VERSION = "v48.0"


# ---------------------------------------------------------------------
# utilidades
# ---------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def print_header(title: str) -> None:
    print("=" * 72)
    print(title)
    print("=" * 72)


def safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def connect() -> sqlite3.Connection:
    if not DB_PATH.parent.exists():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def table_count(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if row is None:
        return -1
    count = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
    return int(count["n"]) if count else 0


# ---------------------------------------------------------------------
# modelos
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class ShapeProfile:
    shape_id: str
    family: str
    sides: int
    corners: int
    rotational_symmetry_degrees: float
    has_curved_boundary: bool
    angle_signature_json: str
    semantic_hint: str


@dataclass(frozen=True)
class Piece:
    piece_id: str
    shape_id: str
    width: float
    height: float
    depth: float
    orientation_deg: float
    label_stage: str


@dataclass(frozen=True)
class Hole:
    hole_id: str
    shape_id: str
    width: float
    height: float
    depth: float
    orientation_deg: float
    tolerance: float
    label_stage: str


@dataclass
class FitEvaluation:
    piece_id: str
    hole_id: str
    predicted_fit: bool
    observed_fit: bool
    contour_match: bool
    size_match: bool
    depth_match: bool
    rotation_match: bool
    collision_detected: bool
    fit_score: float
    failure_reason: str
    explanation: str


# ---------------------------------------------------------------------
# mundo pedagógico
# ---------------------------------------------------------------------

class ShapeSorterNurseryV48:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self.conn = connect()

    def close(self) -> None:
        self.conn.close()

    def bootstrap(self) -> None:
        self._create_schema()
        self._seed_shapes()
        self._seed_pieces_and_holes()
        self._seed_spatial_concepts()
        self._log_event("bootstrap", "shape sorter v48 initialized")

    def reset_v48(self) -> None:
        self._create_schema()
        for table in (
            "geometry_fit_attempts_v48",
            "geometry_rules_v48",
            "geometry_curriculum_events_v48",
            "geometry_pieces_v48",
            "geometry_holes_v48",
            "geometry_shapes_v48",
            "geometry_spatial_concepts_v48",
        ):
            self.conn.execute(f"DELETE FROM {table}")
        self.conn.commit()
        self.bootstrap()

    def _create_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS geometry_shapes_v48 (
                shape_id TEXT PRIMARY KEY,
                family TEXT NOT NULL,
                sides INTEGER NOT NULL,
                corners INTEGER NOT NULL,
                rotational_symmetry_degrees REAL NOT NULL,
                has_curved_boundary INTEGER NOT NULL,
                angle_signature_json TEXT NOT NULL,
                semantic_hint TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS geometry_pieces_v48 (
                piece_id TEXT PRIMARY KEY,
                shape_id TEXT NOT NULL,
                width REAL NOT NULL,
                height REAL NOT NULL,
                depth REAL NOT NULL,
                orientation_deg REAL NOT NULL,
                label_stage TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS geometry_holes_v48 (
                hole_id TEXT PRIMARY KEY,
                shape_id TEXT NOT NULL,
                width REAL NOT NULL,
                height REAL NOT NULL,
                depth REAL NOT NULL,
                orientation_deg REAL NOT NULL,
                tolerance REAL NOT NULL,
                label_stage TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS geometry_fit_attempts_v48 (
                attempt_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                lesson_id TEXT NOT NULL,
                piece_id TEXT NOT NULL,
                hole_id TEXT NOT NULL,
                predicted_fit INTEGER NOT NULL,
                observed_fit INTEGER NOT NULL,
                contour_match INTEGER NOT NULL,
                size_match INTEGER NOT NULL,
                depth_match INTEGER NOT NULL,
                rotation_match INTEGER NOT NULL,
                collision_detected INTEGER NOT NULL,
                fit_score REAL NOT NULL,
                failure_reason TEXT NOT NULL,
                explanation TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS geometry_rules_v48 (
                rule_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                rule_name TEXT NOT NULL,
                support_count INTEGER NOT NULL,
                contradiction_count INTEGER NOT NULL,
                confidence REAL NOT NULL,
                statement TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS geometry_spatial_concepts_v48 (
                concept_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                concept_name TEXT NOT NULL,
                learned_from TEXT NOT NULL,
                statement TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS geometry_curriculum_events_v48 (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                summary TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_geometry_fit_attempts_pair_v48
            ON geometry_fit_attempts_v48(piece_id, hole_id);

            CREATE INDEX IF NOT EXISTS idx_geometry_fit_attempts_lesson_v48
            ON geometry_fit_attempts_v48(lesson_id, timestamp);
            """
        )
        self.conn.commit()

    def _seed_shapes(self) -> None:
        shapes = [
            ShapeProfile(
                shape_id="shape_circle_v48",
                family="circle",
                sides=0,
                corners=0,
                rotational_symmetry_degrees=1.0,
                has_curved_boundary=True,
                angle_signature_json=safe_json([]),
                semantic_hint="contorno contínuo sem cantos",
            ),
            ShapeProfile(
                shape_id="shape_square_v48",
                family="square",
                sides=4,
                corners=4,
                rotational_symmetry_degrees=90.0,
                has_curved_boundary=False,
                angle_signature_json=safe_json([90, 90, 90, 90]),
                semantic_hint="quatro lados e quatro cantos retos",
            ),
            ShapeProfile(
                shape_id="shape_triangle_v48",
                family="triangle",
                sides=3,
                corners=3,
                rotational_symmetry_degrees=120.0,
                has_curved_boundary=False,
                angle_signature_json=safe_json([60, 60, 60]),
                semantic_hint="três lados e três cantos",
            ),
        ]

        for shape in shapes:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO geometry_shapes_v48 (
                    shape_id, family, sides, corners, rotational_symmetry_degrees,
                    has_curved_boundary, angle_signature_json, semantic_hint, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    shape.shape_id,
                    shape.family,
                    shape.sides,
                    shape.corners,
                    shape.rotational_symmetry_degrees,
                    int(shape.has_curved_boundary),
                    shape.angle_signature_json,
                    shape.semantic_hint,
                    now_iso(),
                ),
            )
        self.conn.commit()

    def _seed_pieces_and_holes(self) -> None:
        pieces = [
            Piece("piece_circle_small_v48", "shape_circle_v48", 4.0, 4.0, 1.0, 0.0, "pre_word"),
            Piece("piece_square_small_v48", "shape_square_v48", 4.0, 4.0, 1.0, 0.0, "pre_word"),
            Piece("piece_triangle_small_v48", "shape_triangle_v48", 4.0, 4.0, 1.0, 0.0, "pre_word"),
            Piece("piece_square_rotated_v48", "shape_square_v48", 4.0, 4.0, 1.0, 45.0, "pre_word"),
            Piece("piece_circle_large_v48", "shape_circle_v48", 5.2, 5.2, 1.0, 0.0, "pre_word"),
            Piece("piece_square_deep_v48", "shape_square_v48", 4.0, 4.0, 2.4, 0.0, "pre_word"),
        ]

        holes = [
            Hole("hole_circle_v48", "shape_circle_v48", 4.2, 4.2, 1.5, 0.0, 0.25, "pre_word"),
            Hole("hole_square_v48", "shape_square_v48", 4.2, 4.2, 1.5, 0.0, 0.25, "pre_word"),
            Hole("hole_triangle_v48", "shape_triangle_v48", 4.2, 4.2, 1.5, 0.0, 0.25, "pre_word"),
        ]

        for piece in pieces:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO geometry_pieces_v48 (
                    piece_id, shape_id, width, height, depth,
                    orientation_deg, label_stage, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    piece.piece_id,
                    piece.shape_id,
                    piece.width,
                    piece.height,
                    piece.depth,
                    piece.orientation_deg,
                    piece.label_stage,
                    now_iso(),
                ),
            )

        for hole in holes:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO geometry_holes_v48 (
                    hole_id, shape_id, width, height, depth,
                    orientation_deg, tolerance, label_stage, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    hole.hole_id,
                    hole.shape_id,
                    hole.width,
                    hole.height,
                    hole.depth,
                    hole.orientation_deg,
                    hole.tolerance,
                    hole.label_stage,
                    now_iso(),
                ),
            )

        self.conn.commit()

    def _seed_spatial_concepts(self) -> None:
        concepts = [
            ("concept_contour_compatibility_v48", "compatibilidade_de_contorno", "bootstrap",
             "Para encaixar, o contorno da peça precisa corresponder ao contorno da abertura."),
            ("concept_size_compatibility_v48", "compatibilidade_de_tamanho", "bootstrap",
             "Para encaixar, a peça precisa caber dentro da largura e altura da abertura com tolerância."),
            ("concept_depth_compatibility_v48", "compatibilidade_de_profundidade", "bootstrap",
             "Para encaixar completamente, a profundidade da peça não pode exceder a profundidade útil da abertura."),
            ("concept_rotation_v48", "rotação", "bootstrap",
             "Algumas peças com cantos podem exigir orientação compatível; círculo é quase invariável por rotação."),
            ("concept_collision_v48", "colisão", "bootstrap",
             "Falha de encaixe pode ser lida como colisão entre contornos, tamanho ou profundidade."),
        ]

        for concept_id, name, source, statement in concepts:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO geometry_spatial_concepts_v48 (
                    concept_id, created_at, concept_name, learned_from, statement, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    concept_id,
                    now_iso(),
                    name,
                    source,
                    statement,
                    safe_json({"version": VERSION, "source": source}),
                ),
            )
        self.conn.commit()

    # ------------------------------------------------------------------
    # consultas
    # ------------------------------------------------------------------

    def shape(self, shape_id: str) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT * FROM geometry_shapes_v48 WHERE shape_id=?",
            (shape_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"shape_id não encontrado: {shape_id}")
        return row

    def piece(self, piece_id: str) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT * FROM geometry_pieces_v48 WHERE piece_id=?",
            (piece_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"piece_id não encontrado: {piece_id}")
        return row

    def hole(self, hole_id: str) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT * FROM geometry_holes_v48 WHERE hole_id=?",
            (hole_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"hole_id não encontrado: {hole_id}")
        return row

    def list_pieces(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT piece_id FROM geometry_pieces_v48 ORDER BY piece_id"
        ).fetchall()
        return [str(r["piece_id"]) for r in rows]

    def list_holes(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT hole_id FROM geometry_holes_v48 ORDER BY hole_id"
        ).fetchall()
        return [str(r["hole_id"]) for r in rows]

    # ------------------------------------------------------------------
    # avaliação física
    # ------------------------------------------------------------------

    def _contour_match(self, piece_row: sqlite3.Row, hole_row: sqlite3.Row) -> bool:
        p_shape = self.shape(str(piece_row["shape_id"]))
        h_shape = self.shape(str(hole_row["shape_id"]))

        return (
            str(p_shape["family"]) == str(h_shape["family"])
            and int(p_shape["sides"]) == int(h_shape["sides"])
            and int(p_shape["corners"]) == int(h_shape["corners"])
            and int(p_shape["has_curved_boundary"]) == int(h_shape["has_curved_boundary"])
        )

    def _size_match(self, piece_row: sqlite3.Row, hole_row: sqlite3.Row) -> bool:
        tolerance = float(hole_row["tolerance"])
        return (
            float(piece_row["width"]) <= float(hole_row["width"]) + tolerance
            and float(piece_row["height"]) <= float(hole_row["height"]) + tolerance
        )

    def _depth_match(self, piece_row: sqlite3.Row, hole_row: sqlite3.Row) -> bool:
        return float(piece_row["depth"]) <= float(hole_row["depth"])

    def _rotation_match(self, piece_row: sqlite3.Row, hole_row: sqlite3.Row) -> bool:
        p_shape = self.shape(str(piece_row["shape_id"]))
        family = str(p_shape["family"])
        if family == "circle":
            return True

        symmetry = float(p_shape["rotational_symmetry_degrees"])
        p_angle = float(piece_row["orientation_deg"]) % 360.0
        h_angle = float(hole_row["orientation_deg"]) % 360.0
        delta = abs((p_angle - h_angle) % 360.0)

        if delta > 180.0:
            delta = 360.0 - delta

        # Se a diferença for múltiplo próximo da simetria, aceitamos.
        if symmetry <= 0:
            return delta <= 3.0

        remainder = min(delta % symmetry, symmetry - (delta % symmetry))
        return remainder <= 3.0

    def evaluate_fit(self, piece_id: str, hole_id: str) -> FitEvaluation:
        piece_row = self.piece(piece_id)
        hole_row = self.hole(hole_id)

        contour_match = self._contour_match(piece_row, hole_row)
        size_match = self._size_match(piece_row, hole_row)
        depth_match = self._depth_match(piece_row, hole_row)
        rotation_match = self._rotation_match(piece_row, hole_row)

        observed_fit = contour_match and size_match and depth_match and rotation_match
        collision_detected = not observed_fit

        score_parts = [
            0.40 if contour_match else 0.0,
            0.25 if size_match else 0.0,
            0.20 if depth_match else 0.0,
            0.15 if rotation_match else 0.0,
        ]
        fit_score = round(sum(score_parts), 4)

        predicted_fit = fit_score >= 0.85

        if observed_fit:
            failure_reason = ""
            explanation = (
                "encaixe bem-sucedido: contorno, tamanho, profundidade e orientação são compatíveis"
            )
        elif not contour_match:
            failure_reason = "contour_mismatch"
            explanation = "falha: o contorno da peça não corresponde ao contorno do buraco"
        elif not size_match:
            failure_reason = "size_mismatch"
            explanation = "falha: a peça excede a tolerância de largura/altura do buraco"
        elif not depth_match:
            failure_reason = "depth_mismatch"
            explanation = "falha: a peça é profunda demais para o buraco"
        elif not rotation_match:
            failure_reason = "rotation_mismatch"
            explanation = "falha: a orientação da peça com cantos não coincide com a abertura"
        else:
            failure_reason = "unknown_collision"
            explanation = "falha: colisão detectada por causa não classificada"

        return FitEvaluation(
            piece_id=piece_id,
            hole_id=hole_id,
            predicted_fit=predicted_fit,
            observed_fit=observed_fit,
            contour_match=contour_match,
            size_match=size_match,
            depth_match=depth_match,
            rotation_match=rotation_match,
            collision_detected=collision_detected,
            fit_score=fit_score,
            failure_reason=failure_reason,
            explanation=explanation,
        )

    def attempt_fit(self, piece_id: str, hole_id: str, lesson_id: str = "manual") -> FitEvaluation:
        evaluation = self.evaluate_fit(piece_id, hole_id)
        attempt_id = f"FIT:{lesson_id}:{piece_id}:{hole_id}:{self._next_attempt_index()}"

        payload = {
            "version": VERSION,
            "lesson_id": lesson_id,
            "evaluation": asdict(evaluation),
            "pedagogy": "pre-word physical geometry; fit by constraints, not by label association",
        }

        self.conn.execute(
            """
            INSERT INTO geometry_fit_attempts_v48 (
                attempt_id, timestamp, lesson_id, piece_id, hole_id,
                predicted_fit, observed_fit, contour_match, size_match,
                depth_match, rotation_match, collision_detected, fit_score,
                failure_reason, explanation, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attempt_id,
                now_iso(),
                lesson_id,
                evaluation.piece_id,
                evaluation.hole_id,
                int(evaluation.predicted_fit),
                int(evaluation.observed_fit),
                int(evaluation.contour_match),
                int(evaluation.size_match),
                int(evaluation.depth_match),
                int(evaluation.rotation_match),
                int(evaluation.collision_detected),
                evaluation.fit_score,
                evaluation.failure_reason,
                evaluation.explanation,
                safe_json(payload),
            ),
        )
        self.conn.commit()

        self._log_event(
            "fit_attempt",
            f"{piece_id} -> {hole_id}: {'FIT' if evaluation.observed_fit else 'NO_FIT'} ({evaluation.failure_reason or 'success'})",
            payload,
        )
        return evaluation

    def _next_attempt_index(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM geometry_fit_attempts_v48"
        ).fetchone()
        return int(row["n"]) + 1 if row else 1

    # ------------------------------------------------------------------
    # lições
    # ------------------------------------------------------------------

    def run_basic_lesson(self) -> list[FitEvaluation]:
        lesson_id = f"basic_shape_sorter_{now_iso()}"
        pairs = [
            ("piece_square_small_v48", "hole_square_v48"),
            ("piece_circle_small_v48", "hole_circle_v48"),
            ("piece_triangle_small_v48", "hole_triangle_v48"),
            ("piece_square_small_v48", "hole_circle_v48"),
            ("piece_square_small_v48", "hole_triangle_v48"),
            ("piece_circle_small_v48", "hole_square_v48"),
            ("piece_circle_small_v48", "hole_triangle_v48"),
            ("piece_triangle_small_v48", "hole_square_v48"),
            ("piece_triangle_small_v48", "hole_circle_v48"),
        ]
        results = [self.attempt_fit(piece, hole, lesson_id) for piece, hole in pairs]
        self.infer_rules()
        return results

    def run_all_lesson(self) -> list[FitEvaluation]:
        lesson_id = f"all_shape_sorter_{now_iso()}"
        results: list[FitEvaluation] = []

        for piece_id in self.list_pieces():
            for hole_id in self.list_holes():
                results.append(self.attempt_fit(piece_id, hole_id, lesson_id))

        self.infer_rules()
        return results

    # ------------------------------------------------------------------
    # regras inferidas
    # ------------------------------------------------------------------

    def infer_rules(self) -> None:
        rows = self.conn.execute(
            """
            SELECT *
            FROM geometry_fit_attempts_v48
            ORDER BY timestamp
            """
        ).fetchall()

        if not rows:
            return

        rules = []

        def count_where(predicate) -> tuple[int, int]:
            support = 0
            contradiction = 0
            for row in rows:
                expected = predicate(row)
                observed = bool(row["observed_fit"])
                if expected == observed:
                    support += 1
                else:
                    contradiction += 1
            return support, contradiction

        # Regra 1: contorno incompatível impede encaixe.
        support = 0
        contradiction = 0
        for row in rows:
            if not bool(row["contour_match"]):
                if not bool(row["observed_fit"]):
                    support += 1
                else:
                    contradiction += 1
        rules.append(
            (
                "rule_contour_mismatch_blocks_fit_v48",
                "contour_mismatch_blocks_fit",
                support,
                contradiction,
                "Se o contorno não corresponde, a peça não encaixa, mesmo que tamanho/profundidade pareçam suficientes.",
            )
        )

        # Regra 2: encaixe exige todas as compatibilidades.
        support = 0
        contradiction = 0
        for row in rows:
            expected = (
                bool(row["contour_match"])
                and bool(row["size_match"])
                and bool(row["depth_match"])
                and bool(row["rotation_match"])
            )
            if expected == bool(row["observed_fit"]):
                support += 1
            else:
                contradiction += 1
        rules.append(
            (
                "rule_fit_requires_all_constraints_v48",
                "fit_requires_all_constraints",
                support,
                contradiction,
                "Encaixe exige contorno, tamanho, profundidade e orientação compatíveis.",
            )
        )

        # Regra 3: forma correta mas tamanho/profundidade errado ainda falha.
        support = 0
        contradiction = 0
        for row in rows:
            if bool(row["contour_match"]) and (not bool(row["size_match"]) or not bool(row["depth_match"])):
                if not bool(row["observed_fit"]):
                    support += 1
                else:
                    contradiction += 1
        rules.append(
            (
                "rule_shape_alone_is_not_enough_v48",
                "shape_alone_is_not_enough",
                support,
                contradiction,
                "Mesmo com contorno correto, tamanho ou profundidade incompatíveis causam falha.",
            )
        )

        for rule_id, name, support, contradiction, statement in rules:
            total = support + contradiction
            confidence = round((support / total), 4) if total else 0.0
            self.conn.execute(
                """
                INSERT OR REPLACE INTO geometry_rules_v48 (
                    rule_id, created_at, rule_name, support_count,
                    contradiction_count, confidence, statement, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rule_id,
                    now_iso(),
                    name,
                    support,
                    contradiction,
                    confidence,
                    statement,
                    safe_json(
                        {
                            "version": VERSION,
                            "support": support,
                            "contradiction": contradiction,
                            "confidence": confidence,
                        }
                    ),
                ),
            )

        self.conn.commit()

    # ------------------------------------------------------------------
    # visualização
    # ------------------------------------------------------------------

    def dashboard(self) -> str:
        lines = [
            "DARWIN v48.0 — PAINEL GEOMÉTRICO / SHAPE SORTER",
            "-" * 72,
            f"Banco: {self.db_path}",
            "",
            "Tabelas:",
        ]

        for table in (
            "geometry_shapes_v48",
            "geometry_pieces_v48",
            "geometry_holes_v48",
            "geometry_fit_attempts_v48",
            "geometry_rules_v48",
            "geometry_spatial_concepts_v48",
            "geometry_curriculum_events_v48",
        ):
            count = table_count(self.conn, table)
            value = "AUSENTE" if count < 0 else str(count)
            lines.append(f"- {table}: {value}")

        lines.append("")
        lines.append("Peças:")
        for row in self.conn.execute(
            """
            SELECT p.piece_id, s.family, p.width, p.height, p.depth, p.orientation_deg
            FROM geometry_pieces_v48 p
            JOIN geometry_shapes_v48 s ON s.shape_id = p.shape_id
            ORDER BY p.piece_id
            """
        ).fetchall():
            lines.append(
                f"- {row['piece_id']}: family={row['family']} | "
                f"w={row['width']} h={row['height']} d={row['depth']} rot={row['orientation_deg']}"
            )

        lines.append("")
        lines.append("Buracos:")
        for row in self.conn.execute(
            """
            SELECT h.hole_id, s.family, h.width, h.height, h.depth, h.orientation_deg, h.tolerance
            FROM geometry_holes_v48 h
            JOIN geometry_shapes_v48 s ON s.shape_id = h.shape_id
            ORDER BY h.hole_id
            """
        ).fetchall():
            lines.append(
                f"- {row['hole_id']}: family={row['family']} | "
                f"w={row['width']} h={row['height']} d={row['depth']} rot={row['orientation_deg']} tol={row['tolerance']}"
            )

        lines.append("")
        lines.append("Últimas tentativas:")
        rows = self.conn.execute(
            """
            SELECT piece_id, hole_id, observed_fit, fit_score, failure_reason, explanation
            FROM geometry_fit_attempts_v48
            ORDER BY timestamp DESC
            LIMIT 12
            """
        ).fetchall()
        if not rows:
            lines.append("(nenhuma tentativa ainda)")
        else:
            for row in rows:
                lines.append(
                    f"- {row['piece_id']} -> {row['hole_id']} | "
                    f"{'FIT' if row['observed_fit'] else 'NO_FIT'} | "
                    f"score={row['fit_score']:.2f} | {row['failure_reason'] or 'success'}"
                )

        lines.append("")
        lines.append("Regras inferidas:")
        rows = self.conn.execute(
            """
            SELECT rule_name, support_count, contradiction_count, confidence, statement
            FROM geometry_rules_v48
            ORDER BY rule_name
            """
        ).fetchall()
        if not rows:
            lines.append("(nenhuma regra inferida ainda)")
        else:
            for row in rows:
                lines.append(
                    f"- {row['rule_name']}: conf={row['confidence']:.3f} | "
                    f"suporte={row['support_count']} contradições={row['contradiction_count']} | "
                    f"{row['statement']}"
                )

        return "\n".join(lines)

    def lesson_report(self, results: list[FitEvaluation]) -> str:
        total = len(results)
        fits = sum(1 for r in results if r.observed_fit)
        no_fits = total - fits
        predicted_correct = sum(1 for r in results if r.predicted_fit == r.observed_fit)
        accuracy = predicted_correct / total if total else 0.0

        lines = [
            "DARWIN v48.0 — RELATÓRIO DE LIÇÃO GEOMÉTRICA",
            "-" * 72,
            f"tentativas: {total}",
            f"encaixes: {fits}",
            f"falhas: {no_fits}",
            f"acurácia preditiva inicial: {accuracy:.3f}",
            "",
            "Tentativas:",
        ]

        for r in results:
            lines.append(
                f"- {r.piece_id} -> {r.hole_id}: "
                f"{'FIT' if r.observed_fit else 'NO_FIT'} | "
                f"score={r.fit_score:.2f} | {r.failure_reason or 'success'} | {r.explanation}"
            )

        lines.append("")
        lines.append("Leitura pedagógica:")
        lines.append("- Darwin avaliou encaixe por propriedades físicas, não por nome simbólico.")
        lines.append("- O próximo passo será rotação ativa: tentar girar a peça antes de desistir.")
        return "\n".join(lines)

    def _log_event(self, event_type: str, summary: str, payload: dict | None = None) -> None:
        payload = payload or {"version": VERSION}
        self.conn.execute(
            """
            INSERT INTO geometry_curriculum_events_v48 (
                timestamp, event_type, summary, payload_json
            )
            VALUES (?, ?, ?, ?)
            """,
            (now_iso(), event_type, summary, safe_json(payload)),
        )
        self.conn.commit()


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Darwin v48.0 Shape Sorter Nursery.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o plano sem escrever.")
    parser.add_argument("--reset", action="store_true", help="Apaga e recria as tabelas v48.")
    parser.add_argument(
        "--lesson",
        choices=["none", "basic", "all"],
        default="none",
        help="Executa lição pedagógica.",
    )
    parser.add_argument("--dashboard", action="store_true", help="Mostra painel geométrico.")
    parser.add_argument("--attempt", nargs=2, metavar=("PIECE_ID", "HOLE_ID"), help="Executa tentativa manual.")

    print_header("DARWIN v48.0 — PHYSICAL GEOMETRY NURSERY / SHAPE SORTER")
    print(f"Banco:   {DB_PATH}")
    print(f"Dry-run: {parser.parse_args().dry_run}")
    print()

    args = parser.parse_args()

    if args.dry_run:
        print("Este módulo irá:")
        print("1. Criar tabelas geométricas v48 no darwin_home/darwin.db.")
        print("2. Semear formas: círculo, quadrado, triângulo.")
        print("3. Semear peças e buracos com medidas, orientação e profundidade.")
        print("4. Executar tentativas de encaixe por propriedades físicas.")
        print("5. Inferir regras simples sobre contorno, tamanho, profundidade e rotação.")
        print()
        print("Nenhuma escrita foi feita.")
        return 0

    nursery = ShapeSorterNurseryV48()
    try:
        if args.reset:
            nursery.reset_v48()
            print("[OK] mundo geométrico v48 resetado e recriado.")
        else:
            nursery.bootstrap()
            print("[OK] mundo geométrico v48 inicializado/verificado.")

        if args.attempt:
            piece_id, hole_id = args.attempt
            result = nursery.attempt_fit(piece_id, hole_id, lesson_id="manual_attempt")
            nursery.infer_rules()
            print()
            print(nursery.lesson_report([result]))

        if args.lesson == "basic":
            results = nursery.run_basic_lesson()
            print()
            print(nursery.lesson_report(results))

        elif args.lesson == "all":
            results = nursery.run_all_lesson()
            print()
            print(nursery.lesson_report(results))

        if args.dashboard or args.lesson != "none" or args.attempt:
            print()
            print(nursery.dashboard())

    finally:
        nursery.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
