# ============================================================
# DARWIN v47 — cópia operacional criada a partir da v46
# Criado em: 2026-04-29T00:04:06+00:00
# Objetivo inicial: preparar memória executiva persistente de tensões.
# Esta cópia começa sem alterar comportamento cognitivo da v46.
# ============================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple
import math
import random
from enum import Enum

from darwin_home import DarwinHome, compute_valence

try:
    from darwin_tension_persistence_v47 import DarwinTensionStoreV47
except Exception:
    DarwinTensionStoreV47 = None  # type: ignore



def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


# ============================================================
# Núcleo relacional leve
# ============================================================

@dataclass
class CognitiveState:
    bandwidth: float = 4.0
    info_self: float = 0.35
    info_external: float = 0.35
    latency: float = 1.0
    energy: float = 1.0


@dataclass
class TaskEstimate:
    utility: float
    energy_cost: float
    info_task: float
    novelty: float
    conflict: float
    latency_cost: float


class RomeroLaw:
    def __init__(self, eps: float = 1e-8) -> None:
        self.eps = eps

    def sigma(self, state: CognitiveState, task: Optional[TaskEstimate] = None) -> float:
        bandwidth = state.bandwidth
        latency = state.latency
        info_eff = state.info_self + state.info_external

        if task is not None:
            bandwidth = max(state.bandwidth - task.energy_cost, self.eps)
            latency = max(state.latency + task.latency_cost, self.eps)
            info_eff += task.info_task + task.novelty + task.conflict

        info_eff = max(info_eff, self.eps)
        return bandwidth / (info_eff * latency)


# ============================================================
# Mundo do berçário
# ============================================================

@dataclass
class NurseryObject:
    obj_id: str
    color: str
    shape: str
    category: str
    can_roll: bool
    can_stack: bool
    fit_slot: Optional[str] = None
    position: str = "tapete"


@dataclass
class NurseryActionResult:
    success: bool
    summary: str
    utility: float
    novelty: float
    conflict: float
    info_gain: float
    learned: List[str] = field(default_factory=list)


class NurseryEnvironment:
    def __init__(self) -> None:
        self.objects: Dict[str, NurseryObject] = {}
        self.slots = {"slot_circle": "circle", "slot_square": "square", "slot_triangle": "triangle"}
        self._build_default_world()

    def _build_default_world(self) -> None:
        self.objects = {
            "red_ball": NurseryObject("red_ball", "vermelho", "circle", "toy", True, False, "circle"),
            "blue_cube": NurseryObject("blue_cube", "azul", "square", "block", False, True, "square"),
            "yellow_triangle": NurseryObject("yellow_triangle", "amarelo", "triangle", "block", False, True, "triangle"),
            "green_cylinder": NurseryObject("green_cylinder", "verde", "cylinder", "block", True, True, None),
        }

    def object_ids(self) -> List[str]:
        return list(self.objects.keys())

    def fit_capable_ids(self) -> List[str]:
        return [obj_id for obj_id, obj in self.objects.items() if obj.fit_slot is not None]

    def describe_world(self) -> str:
        parts = []
        for obj in self.objects.values():
            parts.append(f"{obj.obj_id}: cor={obj.color}, forma={obj.shape}, categoria={obj.category}, posicao={obj.position}")
        slot_text = ", ".join(f"{slot}->{shape}" for slot, shape in self.slots.items())
        return "Objetos: " + " | ".join(parts) + f"\nSlots: {slot_text}"

    def observe(self, obj_id: str) -> NurseryActionResult:
        obj = self.objects[obj_id]
        return NurseryActionResult(
            True,
            f"Observou {obj_id} e percebeu cor={obj.color}, forma={obj.shape}, categoria={obj.category}.",
            0.62, 0.56, 0.03, 0.72,
            [
                f"obj:{obj_id}:color:{obj.color}=true",
                f"obj:{obj_id}:shape:{obj.shape}=true",
                f"obj:{obj_id}:category:{obj.category}=true",
            ],
        )

    def touch(self, obj_id: str) -> NurseryActionResult:
        obj = self.objects[obj_id]
        if obj.can_roll:
            return NurseryActionResult(
                True,
                f"Tocou {obj_id}; o objeto responde como algo que pode rolar.",
                0.56, 0.38, 0.07, 0.60,
                [f"obj:{obj_id}:affordance:rola=true"],
            )
        return NurseryActionResult(
            True,
            f"Tocou {obj_id}; o objeto resiste ao rolamento fácil.",
            0.56, 0.34, 0.07, 0.56,
            [f"obj:{obj_id}:affordance:nao_rola_facil=true"],
        )

    def try_fit(self, obj_id: str, slot_id: str) -> NurseryActionResult:
        obj = self.objects[obj_id]
        slot_shape = self.slots[slot_id]
        if obj.fit_slot == slot_shape:
            obj.position = slot_id
            return NurseryActionResult(
                True,
                f"{obj_id} encaixou corretamente em {slot_id}.",
                1.14, 0.36, 0.03, 0.84,
                [
                    f"obj:{obj_id}:fit:{slot_id}:success=true",
                    f"shape:{obj.shape}:fit:{slot_shape}:success=true",
                ],
            )
        return NurseryActionResult(
            False,
            f"{obj_id} não encaixou em {slot_id}.",
            0.16, 0.32, 0.42, 0.48,
            [
                f"obj:{obj_id}:fit:{slot_id}:failure=true",
                f"shape:{obj.shape}:fit:{slot_shape}:failure=true",
            ],
        )

    def try_stack(self, lower_id: str, upper_id: str) -> NurseryActionResult:
        lower = self.objects[lower_id]
        upper = self.objects[upper_id]
        if lower_id == upper_id:
            return NurseryActionResult(False, "Não é possível empilhar um objeto sobre ele mesmo.", 0.05, 0.08, 0.38, 0.10, [])
        if lower.can_stack and upper.can_stack:
            upper.position = f"sobre_{lower_id}"
            return NurseryActionResult(
                True,
                f"{upper_id} ficou estável sobre {lower_id}.",
                0.92, 0.26, 0.05, 0.74,
                [
                    f"obj:{lower_id}:affordance:suporta_empilhar=true",
                    f"obj:{upper_id}:affordance:empilhavel=true",
                    f"pair:{lower_id}>{upper_id}:stack:stable=true",
                ],
            )
        return NurseryActionResult(
            False,
            f"A pilha {upper_id} sobre {lower_id} ficou instável.",
            0.12, 0.26, 0.48, 0.42,
            [f"pair:{lower_id}>{upper_id}:stack:unstable=true"],
        )

    def compare_objects(self, a_id: str, b_id: str) -> NurseryActionResult:
        a = self.objects[a_id]
        b = self.objects[b_id]
        learned: List[str] = []
        summary_parts: List[str] = []

        if a.can_roll != b.can_roll:
            if a.can_roll:
                learned.append(f"compare:roll:{a_id}>{b_id}=true")
                summary_parts.append(f"{a_id} rola mais facilmente que {b_id}")
            else:
                learned.append(f"compare:roll:{b_id}>{a_id}=true")
                summary_parts.append(f"{b_id} rola mais facilmente que {a_id}")
        else:
            learned.append(f"compare:roll:{a_id}~{b_id}=similar")
            summary_parts.append(f"{a_id} e {b_id} são semelhantes quanto a rolar")

        if a.can_stack != b.can_stack:
            if a.can_stack:
                learned.append(f"compare:stack_support:{a_id}>{b_id}=true")
                summary_parts.append(f"{a_id} sustenta empilhamento melhor que {b_id}")
            else:
                learned.append(f"compare:stack_support:{b_id}>{a_id}=true")
                summary_parts.append(f"{b_id} sustenta empilhamento melhor que {a_id}")
        else:
            learned.append(f"compare:stack_support:{a_id}~{b_id}=similar")
            summary_parts.append(f"{a_id} e {b_id} são semelhantes quanto a suporte")

        return NurseryActionResult(
            True,
            "Comparou " + a_id + " e " + b_id + ": " + "; ".join(summary_parts) + ".",
            0.74, 0.30, 0.04, 0.66, learned
        )


# ============================================================
# Memória conceitual + migração
# ============================================================

@dataclass
class ConceptNode:
    key: str
    observations: int = 0
    confidence: float = 0.10
    value: str = ""


class ConceptMemory:
    def __init__(self) -> None:
        self.nodes: Dict[str, ConceptNode] = {}

    def learn(self, key: str, value: str, confidence_boost: float = 0.12) -> None:
        node = self.nodes.get(key)
        if node is None:
            self.nodes[key] = ConceptNode(key, 1, clamp(0.22 + confidence_boost, 0.0, 0.99), value)
        else:
            node.observations += 1
            node.confidence = clamp(node.confidence + confidence_boost, 0.0, 0.99)
            node.value = value

    def adjust_confidence(self, key: str, delta: float, value: Optional[str] = None) -> None:
        node = self.nodes.get(key)
        if node is None:
            base_conf = clamp(0.25 + delta, 0.0, 0.99)
            self.nodes[key] = ConceptNode(key, 1, base_conf, value or "true")
            return
        node.confidence = clamp(node.confidence + delta, 0.0, 0.99)
        node.observations += 1
        if value is not None:
            node.value = value

    def hydrate(self, key: str, value: str, confidence: float) -> None:
        node = self.nodes.get(key)
        if node is None:
            self.nodes[key] = ConceptNode(key, max(1, int(round(confidence * 5))), clamp(confidence, 0.0, 0.99), value)
        else:
            node.confidence = max(node.confidence, clamp(confidence, 0.0, 0.99))
            node.value = value

    def confidence_of_prefix(self, prefix: str) -> float:
        vals = [n.confidence for k, n in self.nodes.items() if k.startswith(prefix)]
        return max(vals) if vals else 0.0

    def count_prefix(self, prefix: str, threshold: float = 0.30) -> int:
        return sum(1 for k, n in self.nodes.items() if k.startswith(prefix) and n.confidence >= threshold)

    def snapshot(self) -> str:
        if not self.nodes:
            return "(nenhum conceito local)"
        ordered = sorted(self.nodes.values(), key=lambda n: (-n.confidence, n.key))
        parts = []
        for n in ordered[:48]:
            parts.append(f"{n.key}[obs={n.observations}, conf={n.confidence:.2f}]")
        return " | ".join(parts)


def migrate_legacy_key(key: str, value: str) -> List[Tuple[str, str]]:
    if key.count(":") == 2 and key.endswith(":fits"):
        obj_key = key.rsplit(":", 1)[0]
        return [(f"{obj_key}:fit:{value}:success", "true")]
    if key.count(":") == 2 and key.endswith(":not_fit"):
        obj_key = key.rsplit(":", 1)[0]
        return [(f"{obj_key}:fit:{value}:failure", "true")]
    if key.count(":") == 2 and key.endswith(":affordance"):
        obj_key = key.rsplit(":", 1)[0]
        return [(f"{obj_key}:affordance:{value}", "true")]
    if key.count(":") == 2 and key.endswith(":color"):
        obj_key = key.rsplit(":", 1)[0]
        return [(f"{obj_key}:color:{value}", "true")]
    if key.count(":") == 2 and key.endswith(":shape"):
        obj_key = key.rsplit(":", 1)[0]
        return [(f"{obj_key}:shape:{value}", "true")]
    if key.count(":") == 2 and key.endswith(":category"):
        obj_key = key.rsplit(":", 1)[0]
        return [(f"{obj_key}:category:{value}", "true")]
    if key.count(":") == 2 and key.endswith(":fits_slot"):
        shape_key = key.rsplit(":", 1)[0]
        return [(f"{shape_key}:fit:{value}:success", "true")]
    if key.count(":") == 2 and key.endswith(":not_fit_slot"):
        shape_key = key.rsplit(":", 1)[0]
        return [(f"{shape_key}:fit:{value}:failure", "true")]
    return [(key, value)]


# ============================================================
# Hipóteses
# ============================================================

@dataclass
class PendingHypothesis:
    hypothesis_id: str
    lower_id: str
    upper_id: str
    predicted_outcome: str
    basis: str
    confidence_hint: float
    cause_focus: str


@dataclass
class LiveTensionRecord:
    tension_id: str
    source_lower: str
    source_upper: str
    source_predicted: str
    source_observed: str
    source_labels: List[str]
    opened_step: int
    status: str = "open"
    last_probe_lower: Optional[str] = None
    last_probe_upper: Optional[str] = None
    last_probe_labels: List[str] = field(default_factory=list)
    last_probe_score: float = 0.0
    last_probe_judgment: str = ""
    continuity_lines: List[str] = field(default_factory=list)
    outcome_lines: List[str] = field(default_factory=list)
    pressure_snapshot: float = 0.0
    closure_deficit: float = 1.0


class TensionStatus(str, Enum):
    OPEN = "open"
    PROBING = "probing"
    MAINTAINED = "maintained"
    REOPENED = "reopened"
    CLOSED = "closed"
    WEAKENED = "weakened"
    STALE = "stale"
    ARCHIVED = "archived"


class TensionOutcome(str, Enum):
    UNKNOWN = "unknown"
    CLOSED = "closed"
    MAINTAINED = "maintained"
    REOPENED = "reopened"
    WEAKENED = "weakened"


@dataclass(slots=True)
class LiveTensionCase:
    tension_id: str
    source_lower: str
    source_upper: str
    source_predicted: str
    source_observed: str
    source_labels: Tuple[str, ...]
    semantic_summary: str
    opened_step: int
    last_event_step: int
    contradiction_magnitude: float = 1.0
    status: TensionStatus = TensionStatus.OPEN
    outcome: TensionOutcome = TensionOutcome.UNKNOWN
    inherited_pairs: Tuple[str, ...] = field(default_factory=tuple)

    last_probe_lower: Optional[str] = None
    last_probe_upper: Optional[str] = None
    last_probe_step: Optional[int] = None
    last_probe_labels: Tuple[str, ...] = field(default_factory=tuple)
    last_probe_score: float = 0.0
    last_probe_judgment: str = ""

    continuity_lines: List[str] = field(default_factory=list)
    outcome_lines: List[str] = field(default_factory=list)
    trail: List[str] = field(default_factory=list)

    live_pressure: float = 0.0
    recency_score: float = 0.0
    continuity_score: float = 0.0
    ambiguity_score: float = 0.0
    closure_deficit: float = 1.0
    saturation_cost: float = 0.0
    economic_priority: float = 0.0

    probe_count: int = 0
    closure_hits: int = 0
    reopening_hits: int = 0
    weakening_hits: int = 0

    @property
    def source_pair(self) -> str:
        return f"{self.source_lower}>{self.source_upper}"

    @property
    def last_probe_pair(self) -> Optional[str]:
        if self.last_probe_lower is None or self.last_probe_upper is None:
            return None
        return f"{self.last_probe_lower}>{self.last_probe_upper}"


@dataclass(slots=True)
class TensionCandidateScore:
    tension_id: str
    pair_key: str
    strategic: float
    semantic: float
    ambiguity: float
    recency: float
    closure_deficit: float
    saturation_cost: float
    live_pressure: float
    note: str


# -----------------------------------------------------------------------------
# mixin principal
# -----------------------------------------------------------------------------


class DarwinV46TensionEconomyMixin:
    """
    Camada meta-narrativa para múltiplas tensões vivas.

    O host idealmente expõe:
    - self.step_counter: int
    - self.plan_recent_pairs: List[Tuple[str, str]]
    - self.plan_recent_context_labels: List[str]
    - self.last_contradiction_semantic_lines: List[str]
    - self.last_probe_continuity_lines: List[str]
    - self.last_tension_outcome_lines: List[str]

    Métodos opcionais que o host pode sobrescrever para ganhar precisão:
    - get_local_ambiguity(lower, upper, labels)
    - get_pair_semantic_relevance(pair_a, pair_b)
    - get_recent_pairs_window(window)
    - get_recent_contexts_window(window)
    - get_recent_low_gain_repetition(pair_key)
    - get_pair_info_estimate(lower, upper, labels)
    """

    # --------------------------
    # inicialização
    # --------------------------

    def init_live_tension_v46(self) -> None:
        self.live_tension_cases: Dict[str, LiveTensionCase] = {}
        self.archived_tension_cases: Dict[str, LiveTensionCase] = {}
        self.active_tension_id: Optional[str] = None
        self.live_tension_counter_v46: int = 0
        self.last_tension_market_lines: List[str] = []
        self.last_tension_archive_lines: List[str] = []
        self.last_tension_economy_note: str = ""

    # --------------------------
    # utilidades de host
    # --------------------------

    def get_local_ambiguity(self, lower: str, upper: str, labels: Sequence[str]) -> float:
        """Fallback conservador. O host pode sobrescrever com sua ambiguidade real."""
        shared = 0.0
        if hasattr(self, "plan_recent_context_labels"):
            recent = set(getattr(self, "plan_recent_context_labels", [])[-8:])
            shared = 0.12 * len(set(labels).intersection(recent))
        return clamp(0.35 + shared, 0.0, 1.0)

    def get_pair_semantic_relevance(self, pair_a: str, pair_b: str) -> float:
        if pair_a == pair_b:
            return 1.0
        try:
            a_l, a_u = pair_a.split(">", 1)
            b_l, b_u = pair_b.split(">", 1)
        except ValueError:
            return 0.0
        if a_l == b_l or a_l == b_u or a_u == b_l or a_u == b_u:
            return 0.68
        return 0.0

    def get_recent_pairs_window(self, window: int = 12) -> List[Tuple[str, str]]:
        return list(getattr(self, "plan_recent_pairs", [])[-window:])

    def get_recent_contexts_window(self, window: int = 12) -> List[str]:
        return list(getattr(self, "plan_recent_context_labels", [])[-window:])

    def get_recent_low_gain_repetition(self, pair_key: str) -> int:
        pairs = [f"{a}>{b}" for a, b in self.get_recent_pairs_window(window=10)]
        return sum(1 for p in pairs if p == pair_key)

    def get_pair_info_estimate(self, lower: str, upper: str, labels: Sequence[str]) -> float:
        return 0.25 + 0.35 * self.get_local_ambiguity(lower, upper, labels)

    # --------------------------
    # conversões auxiliares
    # --------------------------

    def _pair_key(self, lower: str, upper: str) -> str:
        return f"{lower}>{upper}"

    def _closure_deficit_for_status(self, status: TensionStatus) -> float:
        if status == TensionStatus.CLOSED:
            return 0.0
        if status == TensionStatus.MAINTAINED:
            return 0.46
        if status == TensionStatus.WEAKENED:
            return 0.34
        if status == TensionStatus.REOPENED:
            return 0.86
        if status == TensionStatus.PROBING:
            return 0.92
        if status == TensionStatus.STALE:
            return 0.12
        if status == TensionStatus.ARCHIVED:
            return 0.0
        return 1.0

    def _shared_context_fraction(self, labels_a: Sequence[str], labels_b: Sequence[str]) -> float:
        a = set(labels_a)
        b = set(labels_b)
        if not a or not b:
            return 0.0
        return len(a.intersection(b)) / max(1, len(a.union(b)))

    def _tension_matches_candidate(self, case: LiveTensionCase, lower: str, upper: str, labels: Sequence[str]) -> bool:
        pair_key = self._pair_key(lower, upper)
        if pair_key == case.source_pair:
            return True
        if self.get_pair_semantic_relevance(pair_key, case.source_pair) >= 0.60:
            return True
        if self._shared_context_fraction(labels, case.source_labels) >= 0.34:
            return True
        return False

    def _current_step(self) -> int:
        return int(getattr(self, "step_counter", 0))

    # --------------------------
    # persistência v47
    # --------------------------

    def _v47_enum_value(self, value):
        return getattr(value, "value", value)

    def _v47_note_persistence_error(self, exc: Exception) -> None:
        msg = f"falha na persistência de tensão v47: {exc!r}"
        if hasattr(self, "last_planner_error"):
            self.last_planner_error = msg

    def _v47_persist_case(self, case: "LiveTensionCase", event_type: str = "", note: str = "") -> None:
        store = getattr(self, "tension_store", None)
        if store is None or case is None:
            return
        try:
            store.upsert_case(case, emit_event=False)
            if event_type:
                store.record_event(
                    tension_id=case.tension_id,
                    event_type=event_type,
                    step=getattr(case, "last_event_step", self._current_step()),
                    status_after=str(self._v47_enum_value(getattr(case, "status", ""))),
                    pressure_after=float(getattr(case, "live_pressure", 0.0) or 0.0),
                    note=note,
                    payload={
                        "source_pair": case.source_pair,
                        "active_tension_id": getattr(self, "active_tension_id", None),
                    },
                )
        except Exception as exc:
            self._v47_note_persistence_error(exc)

    def _v47_record_probe(
        self,
        *,
        case: "LiveTensionCase",
        lower: str,
        upper: str,
        labels: Sequence[str],
        score: float,
        judgment: str,
    ) -> None:
        store = getattr(self, "tension_store", None)
        if store is None or case is None:
            return
        try:
            store.record_probe(
                tension_id=case.tension_id,
                lower_id=lower,
                upper_id=upper,
                selected_step=getattr(case, "last_probe_step", self._current_step()),
                labels=list(labels),
                score=float(score),
                judgment=judgment,
                payload={
                    "source_pair": case.source_pair,
                    "status": str(self._v47_enum_value(case.status)),
                    "live_pressure": float(getattr(case, "live_pressure", 0.0) or 0.0),
                },
            )
        except Exception as exc:
            self._v47_note_persistence_error(exc)

    def _v47_record_outcome(
        self,
        *,
        case: "LiveTensionCase",
        observed: str,
        outcome_note: str,
    ) -> None:
        store = getattr(self, "tension_store", None)
        if store is None or case is None:
            return
        try:
            store.record_outcome(
                tension_id=case.tension_id,
                step=getattr(case, "last_event_step", self._current_step()),
                outcome=outcome_note,
                observed=observed,
                closure_deficit_after=float(getattr(case, "closure_deficit", 0.0) or 0.0),
                outcome_lines=list(getattr(case, "outcome_lines", [])),
                payload={
                    "source_pair": case.source_pair,
                    "status": str(self._v47_enum_value(case.status)),
                    "outcome": str(self._v47_enum_value(case.outcome)),
                },
            )
        except Exception as exc:
            self._v47_note_persistence_error(exc)

    def _v47_sync_tension_cases(self, previous_active_tension_id: Optional[str] = None) -> None:
        store = getattr(self, "tension_store", None)
        if store is None:
            return

        try:
            for case in list(getattr(self, "live_tension_cases", {}).values()):
                store.upsert_case(case, emit_event=False)
            for case in list(getattr(self, "archived_tension_cases", {}).values()):
                store.upsert_case(case, emit_event=False)

            current_active = getattr(self, "active_tension_id", None)
            if previous_active_tension_id != current_active:
                if previous_active_tension_id:
                    store.record_event(
                        tension_id=previous_active_tension_id,
                        event_type="tension_preempted_out",
                        step=self._current_step(),
                        status_after="deprioritized",
                        pressure_after=None,
                        note=f"tensão ativa mudou de {previous_active_tension_id} para {current_active}",
                        payload={"new_active_tension_id": current_active},
                    )
                if current_active:
                    active_case = getattr(self, "live_tension_cases", {}).get(current_active)
                    pressure = float(getattr(active_case, "live_pressure", 0.0) or 0.0) if active_case else None
                    store.record_event(
                        tension_id=current_active,
                        event_type="tension_preempted_in",
                        step=self._current_step(),
                        status_after="active",
                        pressure_after=pressure,
                        note=f"tensão escolhida como foco executivo: {current_active}",
                        payload={"previous_active_tension_id": previous_active_tension_id},
                    )
            self._v47_last_executive_active_id = current_active
        except Exception as exc:
            self._v47_note_persistence_error(exc)


    # --------------------------
    # reidratação v47.5
    # --------------------------

    def _v47_json_list(self, raw) -> List[str]:
        import json

        if raw is None:
            return []
        if isinstance(raw, list):
            return [str(x) for x in raw]
        if isinstance(raw, tuple):
            return [str(x) for x in raw]

        text = str(raw)
        if not text:
            return []

        try:
            parsed = json.loads(text)
        except Exception:
            return [text]

        if isinstance(parsed, list):
            return [str(x) for x in parsed]
        if parsed is None:
            return []
        return [str(parsed)]

    def _v47_status_from_value(self, value) -> "TensionStatus":
        try:
            return TensionStatus(str(value))
        except Exception:
            return TensionStatus.OPEN

    def _v47_outcome_from_value(self, value) -> "TensionOutcome":
        try:
            return TensionOutcome(str(value))
        except Exception:
            return TensionOutcome.UNKNOWN

    def _v47_float_from_row(self, row: dict, key: str, default: float = 0.0) -> float:
        value = row.get(key, None)
        if value is None:
            return float(default)
        try:
            return float(value)
        except Exception:
            return float(default)

    def _v47_int_from_row(self, row: dict, key: str, default: int = 0) -> int:
        value = row.get(key, None)
        if value is None:
            return int(default)
        try:
            return int(value)
        except Exception:
            return int(default)

    def _v47_case_from_persistent_row(self, row: dict) -> "LiveTensionCase":
        status = self._v47_status_from_value(row.get("status", "open"))
        outcome = self._v47_outcome_from_value(row.get("outcome", "unknown"))

        case = LiveTensionCase(
            tension_id=str(row.get("tension_id", "")),
            source_lower=str(row.get("source_lower", "")),
            source_upper=str(row.get("source_upper", "")),
            source_predicted=str(row.get("source_predicted", "")),
            source_observed=str(row.get("source_observed", "")),
            source_labels=tuple(self._v47_json_list(row.get("source_labels_json"))),
            semantic_summary=str(row.get("semantic_summary", "")),
            opened_step=self._v47_int_from_row(row, "opened_step", 0),
            last_event_step=self._v47_int_from_row(row, "last_event_step", 0),
            contradiction_magnitude=self._v47_float_from_row(row, "contradiction_magnitude", 1.0),
            status=status,
            outcome=outcome,
            inherited_pairs=tuple(self._v47_json_list(row.get("inherited_pairs_json"))),
        )

        case.last_probe_lower = row.get("last_probe_lower") or None
        case.last_probe_upper = row.get("last_probe_upper") or None

        last_probe_step = row.get("last_probe_step")
        case.last_probe_step = None if last_probe_step is None else self._v47_int_from_row(row, "last_probe_step", 0)

        case.last_probe_score = self._v47_float_from_row(row, "last_probe_score", 0.0)
        case.last_probe_judgment = str(row.get("last_probe_judgment", "") or "")
        case.last_probe_labels = tuple(self._v47_json_list(row.get("last_probe_labels_json")))

        case.continuity_lines = self._v47_json_list(row.get("continuity_lines_json"))
        case.outcome_lines = self._v47_json_list(row.get("outcome_lines_json"))
        case.trail = self._v47_json_list(row.get("trail_json"))

        case.live_pressure = self._v47_float_from_row(row, "live_pressure", 0.0)
        case.recency_score = self._v47_float_from_row(row, "recency_score", 0.0)
        case.continuity_score = self._v47_float_from_row(row, "continuity_score", 0.0)
        case.ambiguity_score = self._v47_float_from_row(row, "ambiguity_score", 0.0)
        case.closure_deficit = self._v47_float_from_row(row, "closure_deficit", 1.0)
        case.saturation_cost = self._v47_float_from_row(row, "saturation_cost", 0.0)
        case.economic_priority = self._v47_float_from_row(row, "economic_priority", 0.0)

        case.probe_count = self._v47_int_from_row(row, "probe_count", 0)
        case.closure_hits = self._v47_int_from_row(row, "closure_hits", 0)
        case.reopening_hits = self._v47_int_from_row(row, "reopening_hits", 0)
        case.weakening_hits = self._v47_int_from_row(row, "weakening_hits", 0)

        if not case.trail:
            case.trail.append("reidratada da memória executiva persistente v47.5")

        return case

    def _v47_parse_tension_numeric_id(self, tension_id: str) -> int:
        digits = "".join(ch for ch in str(tension_id) if ch.isdigit())
        if not digits:
            return 0
        try:
            return int(digits)
        except Exception:
            return 0

    def _v47_rehydrate_open_tensions_from_store(self) -> int:
        """
        Reconstrói live_tension_cases a partir de tension_cases persistidos.

        Regra:
        - só reidrata casos não fechados/arquivados/stale;
        - não grava eventos no banco durante boot;
        - preserva active_tension_id pelo maior economic_priority/live_pressure;
        - atualiza live_tension_counter_v46 para evitar colisão de IDs futuros.
        """
        self.last_tension_rehydration_lines: List[str] = []

        store = getattr(self, "tension_store", None)
        if store is None:
            self.last_tension_rehydration_lines = [
                "REIDRATAÇÃO v47.5",
                "- persistência de tensões indisponível",
            ]
            return 0

        if not hasattr(self, "live_tension_cases"):
            self.init_live_tension_v46()

        try:
            rows = store.load_open_cases()
        except Exception as exc:
            self._v47_note_persistence_error(exc)
            self.last_tension_rehydration_lines = [
                "REIDRATAÇÃO v47.5",
                f"- falha ao carregar casos: {exc!r}",
            ]
            return 0

        if not rows:
            self.last_tension_rehydration_lines = [
                "REIDRATAÇÃO v47.5",
                "- nenhum caso executivo aberto no banco",
            ]
            return 0

        rehydrated: List[LiveTensionCase] = []
        max_numeric_id = int(getattr(self, "live_tension_counter_v46", 0) or 0)

        for row in rows:
            try:
                case = self._v47_case_from_persistent_row(dict(row))
            except Exception as exc:
                self._v47_note_persistence_error(exc)
                continue

            if not case.tension_id:
                continue

            self.live_tension_cases[case.tension_id] = case
            rehydrated.append(case)
            max_numeric_id = max(max_numeric_id, self._v47_parse_tension_numeric_id(case.tension_id))

        if not rehydrated:
            self.last_tension_rehydration_lines = [
                "REIDRATAÇÃO v47.5",
                "- nenhum caso pôde ser reconstruído",
            ]
            return 0

        # Evita colisão com IDs persistidos, inclusive IDs altos de testes.
        self.live_tension_counter_v46 = max(int(getattr(self, "live_tension_counter_v46", 0) or 0), max_numeric_id)

        ranked = sorted(
            rehydrated,
            key=lambda c: (
                float(getattr(c, "economic_priority", 0.0) or 0.0),
                float(getattr(c, "live_pressure", 0.0) or 0.0),
                int(getattr(c, "last_event_step", 0) or 0),
            ),
            reverse=True,
        )
        active = ranked[0]
        self.active_tension_id = active.tension_id
        self._v47_last_executive_active_id = active.tension_id

        self.last_tension_rehydration_lines = [
            "REIDRATAÇÃO v47.5",
            f"- casos reidratados: {len(rehydrated)}",
            f"- foco executivo restaurado: {active.tension_id} ({active.source_pair})",
        ]
        for case in ranked[:6]:
            self.last_tension_rehydration_lines.append(
                f"- {case.tension_id}: {case.source_pair} | status={case.status.value} | "
                f"pressão={case.live_pressure:.3f} | prioridade={case.economic_priority:.3f} | "
                f"déficit={case.closure_deficit:.3f}"
            )

        self.last_tension_market_lines = self.last_tension_rehydration_lines[:12]
        return len(rehydrated)

    def v47_rehydration_summary(self) -> str:
        lines = list(getattr(self, "last_tension_rehydration_lines", []))
        if not lines:
            lines = [
                "REIDRATAÇÃO v47.5",
                "- ainda não houve tentativa de reidratação nesta sessão",
            ]
        return "\n".join(lines)

    # --------------------------
    # abertura / merge de tensão
    # --------------------------

    def register_tension_from_contradiction(
        self,
        *,
        lower: str,
        upper: str,
        predicted: str,
        observed: str,
        context_families: Sequence[str],
        semantic_summary: str,
        inherited_pairs: Optional[Sequence[str]] = None,
        magnitude: float = 1.0,
    ) -> str:
        """
        Registra contradição como nova tensão ou reforça uma já existente.
        Retorna o id da tensão afetada.
        """
        now = self._current_step()
        pair_key = self._pair_key(lower, upper)
        labels = tuple(context_families)

        # Primeiro tenta reaproveitar / fundir com tensão semanticamente próxima.
        for tension_id, case in self.live_tension_cases.items():
            if case.status in {TensionStatus.CLOSED, TensionStatus.ARCHIVED}:
                continue
            same_pair = pair_key == case.source_pair
            close_semantics = self.get_pair_semantic_relevance(pair_key, case.source_pair) >= 0.68
            close_context = self._shared_context_fraction(labels, case.source_labels) >= 0.34
            if same_pair or (close_semantics and close_context):
                case.status = TensionStatus.REOPENED if case.status != TensionStatus.OPEN else TensionStatus.OPEN
                case.source_predicted = predicted
                case.source_observed = observed
                case.source_labels = tuple(sorted(set(case.source_labels).union(labels)))
                case.semantic_summary = semantic_summary or case.semantic_summary
                case.last_event_step = now
                case.contradiction_magnitude = clamp(case.contradiction_magnitude + 0.25 * magnitude, 0.0, 2.0)
                case.closure_deficit = 1.0
                case.outcome = TensionOutcome.REOPENED
                case.reopening_hits += 1
                case.trail.append(
                    f"reaberta por contradição em {pair_key} | previsto={predicted} | observado={observed}"
                )
                if inherited_pairs:
                    case.inherited_pairs = tuple(sorted(set(case.inherited_pairs).union(inherited_pairs)))
                self.active_tension_id = tension_id
                self._v47_persist_case(
                    case,
                    event_type="tension_reopened",
                    note=f"tensão reaberta por contradição em {pair_key}",
                )
                return tension_id

        # Se não houver caso compatível, abre novo.
        self.live_tension_counter_v46 += 1
        tension_id = f"TV{self.live_tension_counter_v46:03d}"
        case = LiveTensionCase(
            tension_id=tension_id,
            source_lower=lower,
            source_upper=upper,
            source_predicted=predicted,
            source_observed=observed,
            source_labels=labels,
            semantic_summary=semantic_summary,
            opened_step=now,
            last_event_step=now,
            contradiction_magnitude=clamp(magnitude, 0.0, 2.0),
            status=TensionStatus.OPEN,
            inherited_pairs=tuple(inherited_pairs or ()),
        )
        case.trail.append(f"aberta em {pair_key} | previsto={predicted} | observado={observed}")
        self.live_tension_cases[tension_id] = case
        self.active_tension_id = tension_id
        self._v47_persist_case(
            case,
            event_type="tension_opened",
            note=f"tensão aberta por contradição em {pair_key}",
        )
        return tension_id

    # --------------------------
    # economia competitiva
    # --------------------------

    def refresh_tension_economy(self, candidate_pairs: Optional[Sequence[str]] = None) -> None:
        """
        Recalcula pressão econômica das tensões vivas e escolhe a ativa.
        """
        previous_active_tension_id = getattr(self, "_v47_last_executive_active_id", None)
        now = self._current_step()
        market_lines: List[str] = ["ECONOMIA DE TENSÕES VIVAS"]
        scored: List[Tuple[float, str]] = []

        for tension_id, case in list(self.live_tension_cases.items()):
            if case.status == TensionStatus.ARCHIVED:
                continue

            # Decaimento por idade: a tensão permanece viva, mas perde força gradualmente.
            age_from_event = max(0, now - case.last_event_step)
            recency = clamp(math.exp(-age_from_event / 9.0))

            # Continuidade: como o caso ainda conversa com os candidatos atuais.
            continuity_inputs: List[float] = []
            for pair_key in candidate_pairs or ():
                continuity_inputs.append(self.get_pair_semantic_relevance(pair_key, case.source_pair))
            if case.last_probe_pair:
                continuity_inputs.append(self.get_pair_semantic_relevance(case.last_probe_pair, case.source_pair))
            continuity = clamp(max(continuity_inputs) if continuity_inputs else 0.0)

            # Ambiguidade: fonte + pares herdados.
            ambiguity_values = [self.get_local_ambiguity(case.source_lower, case.source_upper, case.source_labels)]
            for inherited in case.inherited_pairs[:6]:
                try:
                    i_lower, i_upper = inherited.split(">", 1)
                except ValueError:
                    continue
                ambiguity_values.append(self.get_local_ambiguity(i_lower, i_upper, case.source_labels))
            ambiguity = clamp(max(ambiguity_values) if ambiguity_values else 0.0)

            closure_deficit = self._closure_deficit_for_status(case.status)

            # Saturação: reabrir demais o mesmo caso sem ganho novo o torna caro.
            recent_same_pair = self.get_recent_low_gain_repetition(case.source_pair)
            same_probe_hits = max(0, case.probe_count - case.closure_hits)
            saturation = clamp(0.10 * recent_same_pair + 0.12 * same_probe_hits, 0.0, 0.85)

            contradiction_mass = clamp(0.45 + 0.25 * case.contradiction_magnitude, 0.0, 1.0)

            pressure = clamp(
                0.24 * recency
                + 0.18 * continuity
                + 0.22 * ambiguity
                + 0.20 * closure_deficit
                + 0.16 * contradiction_mass
                - 0.22 * saturation,
                0.0,
                1.0,
            )

            case.recency_score = recency
            case.continuity_score = continuity
            case.ambiguity_score = ambiguity
            case.closure_deficit = closure_deficit
            case.saturation_cost = saturation
            case.live_pressure = pressure
            case.economic_priority = pressure

            # Arquivamento suave.
            if case.status == TensionStatus.CLOSED and age_from_event >= 8:
                case.status = TensionStatus.ARCHIVED
                self.archived_tension_cases[tension_id] = case
                del self.live_tension_cases[tension_id]
                continue

            if pressure < 0.10 and age_from_event >= 12:
                case.status = TensionStatus.STALE

            market_lines.append(
                f"- {tension_id}: status={case.status.value} | pressão={pressure:.2f} | rec={recency:.2f} | cont={continuity:.2f} | amb={ambiguity:.2f} | déficit={closure_deficit:.2f} | saturação={saturation:.2f} | origem={case.source_pair}"
            )

            # Tensões fechadas ou obsoletas continuam visíveis no painel, mas não competem
            # como foco ativo. Isso evita ruminação operacional após fechamento narrativo.
            if case.status in {TensionStatus.CLOSED, TensionStatus.STALE}:
                continue

            scored.append((pressure, tension_id))

        scored.sort(reverse=True)
        if scored:
            best_pressure, best_id = scored[0]
            self.active_tension_id = best_id if best_pressure >= 0.16 else None
            if self.active_tension_id:
                active = self.live_tension_cases[self.active_tension_id]
                self.last_tension_economy_note = (
                    f"tensão ativa {active.tension_id}: {active.source_pair} | pressão={active.live_pressure:.2f}"
                )
            else:
                self.last_tension_economy_note = "nenhuma tensão superou o limiar competitivo atual"
        else:
            self.active_tension_id = None
            market_lines.append("(nenhuma tensão viva disponível)")
            self.last_tension_economy_note = "nenhuma tensão viva disponível"

        self.last_tension_market_lines = market_lines[:12]
        self._refresh_archive_lines()
        self._v47_sync_tension_cases(previous_active_tension_id=previous_active_tension_id)

    def _refresh_archive_lines(self) -> None:
        lines = ["ARQUIVO DE TENSÕES"]
        if not self.archived_tension_cases:
            lines.append("(nenhuma tensão arquivada)")
            self.last_tension_archive_lines = lines
            return

        ordered = sorted(
            self.archived_tension_cases.values(),
            key=lambda c: (-c.opened_step, c.tension_id),
        )
        for case in ordered[:8]:
            lines.append(
                f"- {case.tension_id}: status={case.status.value} | origem={case.source_pair} | outcome={case.outcome.value} | probes={case.probe_count}"
            )
        self.last_tension_archive_lines = lines

    # --------------------------
    # pontuação de candidatos
    # --------------------------

    def tension_bonus_for_candidate(
        self,
        *,
        lower: str,
        upper: str,
        labels: Sequence[str],
        raw_info_gain: float,
    ) -> Tuple[float, bool, str]:
        """
        Retorna (bonus, is_probe, note) para um candidato.

        O host soma o bônus ao score bruto do candidato e pode usar ``is_probe``
        para decidir se ele vira sonda justificada.
        """
        if not self.active_tension_id:
            return 0.0, False, ""

        case = self.live_tension_cases.get(self.active_tension_id)
        if case is None or case.status in {TensionStatus.CLOSED, TensionStatus.ARCHIVED, TensionStatus.STALE}:
            return 0.0, False, ""

        pair_key = self._pair_key(lower, upper)
        semantic = self.get_pair_semantic_relevance(pair_key, case.source_pair)
        context_overlap = self._shared_context_fraction(labels, case.source_labels)
        ambiguity = self.get_local_ambiguity(lower, upper, labels)
        strategic = clamp(raw_info_gain)

        direct_match = pair_key == case.source_pair
        neighborhood_match = semantic >= 0.68 or context_overlap >= 0.34
        if not direct_match and not neighborhood_match:
            return 0.0, False, ""

        repetition_cost = 0.14 * self.get_recent_low_gain_repetition(pair_key)
        probe_cost = 0.08 * max(0, case.probe_count - case.closure_hits)
        saturation = clamp(repetition_cost + probe_cost, 0.0, 0.60)

        bonus = clamp(
            0.32 * case.live_pressure
            + 0.18 * semantic
            + 0.18 * context_overlap
            + 0.16 * ambiguity
            + 0.16 * strategic
            - 0.24 * saturation,
            0.0,
            1.20,
        )

        is_probe = bonus >= 0.44 and (direct_match or neighborhood_match)
        note = (
            f"economia de tensão: ativa={case.tension_id} | sem={semantic:.2f} | ctx={context_overlap:.2f} | amb={ambiguity:.2f} | saturação={saturation:.2f}"
        )
        return bonus, is_probe, note

    # --------------------------
    # ciclo da sonda
    # --------------------------

    def mark_probe_selected(
        self,
        *,
        lower: str,
        upper: str,
        labels: Sequence[str],
        score: float,
        judgment: str,
    ) -> None:
        if not self.active_tension_id:
            return
        case = self.live_tension_cases.get(self.active_tension_id)
        if case is None:
            return
        if not self._tension_matches_candidate(case, lower, upper, labels):
            return

        case.status = TensionStatus.PROBING
        case.last_probe_lower = lower
        case.last_probe_upper = upper
        case.last_probe_labels = tuple(labels)
        case.last_probe_step = self._current_step()
        case.last_probe_score = float(score)
        case.last_probe_judgment = judgment
        case.last_event_step = self._current_step()
        case.probe_count += 1
        case.continuity_lines = list(getattr(self, "last_probe_continuity_lines", []))[:4]
        case.trail.append(f"sonda selecionada em {lower}>{upper} | score={score:.2f}")
        self._v47_record_probe(
            case=case,
            lower=lower,
            upper=upper,
            labels=labels,
            score=score,
            judgment=judgment,
        )
        self._v47_persist_case(
            case,
            event_type="probe_state_synced",
            note=f"estado de sonda sincronizado em {lower}>{upper}",
        )

    def finalize_probe_validation(
        self,
        *,
        lower: str,
        upper: str,
        observed: str,
    ) -> Optional[str]:
        """
        Fecha o desfecho narrativo da tensão ativa associada à sonda.
        Retorna o outcome em string quando aplicável.
        """
        pair_key = self._pair_key(lower, upper)
        now = self._current_step()

        # Busca a tensão cuja última sonda bate com o par validado.
        matched_case: Optional[LiveTensionCase] = None
        for case in self.live_tension_cases.values():
            if case.last_probe_pair == pair_key and case.status == TensionStatus.PROBING:
                matched_case = case
                break
        if matched_case is None:
            return None

        source_actual = matched_case.source_observed
        shared_pair = (lower in {matched_case.source_lower, matched_case.source_upper} or upper in {matched_case.source_lower, matched_case.source_upper})
        aligned = observed == source_actual

        if aligned and shared_pair:
            matched_case.status = TensionStatus.CLOSED
            matched_case.outcome = TensionOutcome.CLOSED
            matched_case.closure_hits += 1
            outcome_note = "closed"
        elif aligned:
            matched_case.status = TensionStatus.MAINTAINED
            matched_case.outcome = TensionOutcome.MAINTAINED
            matched_case.closure_hits += 1
            outcome_note = "maintained"
        elif shared_pair:
            matched_case.status = TensionStatus.REOPENED
            matched_case.outcome = TensionOutcome.REOPENED
            matched_case.reopening_hits += 1
            outcome_note = "reopened"
        else:
            matched_case.status = TensionStatus.WEAKENED
            matched_case.outcome = TensionOutcome.WEAKENED
            matched_case.weakening_hits += 1
            outcome_note = "weakened"

        shared_labels = sorted(set(matched_case.last_probe_labels).intersection(matched_case.source_labels))
        lines: List[str] = [f"- status narrativo da tensão: {outcome_note}"]
        if shared_labels:
            lines.append(f"- a sonda validada permaneceu na mesma faixa contextual da tensão: {', '.join(shared_labels[:3])}")
        if shared_pair:
            lines.append(f"- o desfecho permaneceu no mesmo bairro relacional de {matched_case.source_pair}")

        if matched_case.source_predicted == "stable" and matched_case.source_observed == "unstable":
            if observed == "unstable":
                lines.append(f"- a sonda consolidou a correção de um otimismo excessivo em {matched_case.source_pair}")
            else:
                lines.append(f"- a sonda reacendeu estabilidade ao redor de {matched_case.source_pair}")
        elif matched_case.source_predicted == "unstable" and matched_case.source_observed == "stable":
            if observed == "stable":
                lines.append(f"- a sonda consolidou a correção de um pessimismo excessivo em {matched_case.source_pair}")
            else:
                lines.append(f"- a sonda devolveu cautela local ao caso {matched_case.source_pair}")
        else:
            if aligned:
                lines.append(f"- a sonda manteve coerência com a leitura corrigida de {matched_case.source_pair}")
            else:
                lines.append(f"- a sonda abriu nova instabilidade interpretativa ao redor de {matched_case.source_pair}")

        matched_case.outcome_lines = lines[:4]
        matched_case.last_event_step = now
        matched_case.closure_deficit = self._closure_deficit_for_status(matched_case.status)
        matched_case.trail.append(f"sonda validada em {pair_key} | outcome={outcome_note} | observado={observed}")

        # Painel compatível com a base anterior.
        if hasattr(self, "last_tension_outcome_lines"):
            self.last_tension_outcome_lines = matched_case.outcome_lines[:]

        self._v47_record_outcome(
            case=matched_case,
            observed=observed,
            outcome_note=outcome_note,
        )
        self._v47_persist_case(
            matched_case,
            event_type="tension_outcome_synced",
            note=f"desfecho de tensão sincronizado: {outcome_note}",
        )

        return outcome_note

    # --------------------------
    # painéis
    # --------------------------

    def live_tension_market_summary(self) -> str:
        if not self.last_tension_market_lines:
            self.refresh_tension_economy()
        return "\n".join(self.last_tension_market_lines)

    def active_tension_summary(self) -> str:
        lines = ["TENSÃO ATIVA"]
        if not self.active_tension_id:
            lines.append("(nenhuma tensão ativa no momento)")
            return "\n".join(lines)
        case = self.live_tension_cases.get(self.active_tension_id)
        if case is None:
            lines.append("(referência ativa ausente)")
            return "\n".join(lines)

        lines.append(
            f"- {case.tension_id}: {case.source_pair} | status={case.status.value} | pressão={case.live_pressure:.2f} | déficit={case.closure_deficit:.2f}"
        )
        lines.append(
            f"- recência={case.recency_score:.2f} | continuidade={case.continuity_score:.2f} | ambiguidade={case.ambiguity_score:.2f} | saturação={case.saturation_cost:.2f}"
        )
        if case.last_probe_pair:
            lines.append(
                f"- última sonda: {case.last_probe_pair} | score={case.last_probe_score:.2f}"
            )
        if case.last_probe_judgment:
            lines.append(f"- juízo: {case.last_probe_judgment}")
        if case.outcome_lines:
            lines.extend(case.outcome_lines[:2])
        elif case.continuity_lines:
            lines.extend(case.continuity_lines[:2])
        return "\n".join(lines)

    def archived_tensions_summary(self) -> str:
        if not self.last_tension_archive_lines:
            self._refresh_archive_lines()
        return "\n".join(self.last_tension_archive_lines)

    def tension_economy_brief(self) -> str:
        if self.last_tension_economy_note:
            return self.last_tension_economy_note
        return "economia de tensão ainda não inicializada"


# ============================================================
# Planejamento curricular
# ============================================================

@dataclass
class ActionPlan:
    action_name: str
    target_a: str
    target_b: Optional[str]
    explanation: str
    novelty_residual: float
    curriculum_bucket: str
    lesson_phase: str
    signature: str


class DarwinNurseryAgent(DarwinV46TensionEconomyMixin):
    SURVEY_THRESHOLD = 0.45
    TOUCH_THRESHOLD = 0.40
    FIT_THRESHOLD = 0.40

    def __init__(self, home: DarwinHome, seed: int = 42) -> None:
        self.home = home
        self.rng = random.Random(seed)
        self.law = RomeroLaw()
        self.env = NurseryEnvironment()
        self.memory = ConceptMemory()
        self.state = CognitiveState()
        self.step_counter = 0
        self.last_episode_summary = ""
        self.last_planner_error = ""
        self._v47_last_executive_active_id = None
        self.tension_store = None
        if DarwinTensionStoreV47 is not None:
            try:
                self.tension_store = DarwinTensionStoreV47()
                self.tension_store.initialize_schema()
            except Exception as exc:
                self.last_planner_error = f"falha ao iniciar persistência de tensões v47: {exc!r}"
        self.recent_action_buckets: List[str] = []
        self.recent_signatures: List[str] = []
        self.pending_hypotheses: List[PendingHypothesis] = []
        self.hypothesis_counter = 0
        self.experiment_queue: List[Tuple[str, str, float, List[str], str]] = []
        self.last_experiment_plan_summary = ""
        self.current_plan_id = 0
        self.current_plan_step_index = 0
        self.plan_recent_pairs: List[Tuple[str, str]] = []
        self.plan_recent_context_labels: List[str] = []
        self.plan_recent_primary_families: List[str] = []
        self.current_plan_return_budget = 0
        self.last_justified_probe: Optional[Tuple[str, str, float, List[str]]] = None
        self.last_justified_probe_judgment: str = ""
        self.last_contradiction_case: Optional[Tuple[str, str, str, str, List[str]]] = None
        self.contradiction_repair_budget: int = 0
        self.last_contradiction_baseline: Optional[Dict[str, float]] = None
        self.last_contradiction_delta_lines: List[str] = []
        self.last_contradiction_semantic_lines: List[str] = []
        self.last_probe_continuity_lines: List[str] = []
        self.last_tension_outcome_lines: List[str] = []
        self.last_contradiction_step: int = -10**9
        self.active_contradiction_repair_plan_id: int = 0
        self.live_tension_counter: int = 0
        self.live_tension_record: Optional[LiveTensionRecord] = None
        self.init_live_tension_v46()
        self.hydrate_memory_from_home()
        self._v47_rehydrate_open_tensions_from_store()

    def hydrate_memory_from_home(self) -> None:
        rows = self.home.conn.execute(
            """
            SELECT key, content, confidence
            FROM semantic_memory
            WHERE source IN ('nursery_v1', 'nursery_v2', 'nursery_v3', 'nursery_v4', 'nursery_v5', 'nursery_v6', 'nursery_v7', 'nursery_v8', 'nursery_v9', 'nursery_v10', 'nursery_v11', 'nursery_v12', 'nursery_v13', 'nursery_v14', 'nursery_v15', 'nursery_v16', 'nursery_v17', 'nursery_v18', 'nursery_v19', 'nursery_v20', 'nursery_v21', 'nursery_v22', 'nursery_v23', 'nursery_v24', 'nursery_v25', 'nursery_v26', 'nursery_v27', 'nursery_v28', 'nursery_v29', 'nursery_v30', 'nursery_v31', 'nursery_v32', 'nursery_v33', 'nursery_v34', 'nursery_v35', 'nursery_v36', 'nursery_v37', 'nursery_v38', 'nursery_v39', 'nursery_v40', 'nursery_v41', 'nursery_v42', 'nursery_v43', 'nursery_v44', 'nursery_v45', 'nursery_v46', 'nursery_v47')
            ORDER BY updated_at DESC
            """
        ).fetchall()
        for row in rows:
            for new_key, new_value in migrate_legacy_key(str(row["key"]), str(row["content"])):
                self.memory.hydrate(new_key, new_value, float(row["confidence"]))

    def sigma_now(self) -> float:
        return self.law.sigma(self.state)

    def should_consolidate(self) -> bool:
        return self.sigma_now() < 1.10 or self.state.energy < 0.55 or self.state.info_external > 1.35

    def _task_for_action(self, novelty: float, conflict: float, info_gain: float, utility: float) -> TaskEstimate:
        return TaskEstimate(utility, 0.07 + 0.08 * conflict + 0.03 * novelty, 0.18 + info_gain, novelty, conflict, 0.04 + 0.02 * info_gain)

    def _observe_penalty(self, obj_id: str) -> float:
        return self.memory.confidence_of_prefix(f"obj:{obj_id}:color:") * 0.34 + self.memory.confidence_of_prefix(f"obj:{obj_id}:shape:") * 0.33 + self.memory.confidence_of_prefix(f"obj:{obj_id}:category:") * 0.33

    def _touch_penalty(self, obj_id: str) -> float:
        return max(self.memory.confidence_of_prefix(f"obj:{obj_id}:affordance:rola"), self.memory.confidence_of_prefix(f"obj:{obj_id}:affordance:nao_rola_facil"))

    def _fit_penalty(self, obj_id: str, slot_id: str) -> float:
        obj = self.env.objects[obj_id]
        return max(self.memory.confidence_of_prefix(f"obj:{obj_id}:fit:{slot_id}:"), self.memory.confidence_of_prefix(f"shape:{obj.shape}:fit:{self.env.slots[slot_id]}:"))

    def _stack_penalty(self, lower_id: str, upper_id: str) -> float:
        return max(
            self.memory.confidence_of_prefix(f"pair:{lower_id}>{upper_id}:stack:"),
            self.memory.confidence_of_prefix(f"obj:{lower_id}:affordance:suporta_empilhar"),
            self.memory.confidence_of_prefix(f"obj:{upper_id}:affordance:empilhavel"),
        )

    def _comparison_penalty(self, a_id: str, b_id: str) -> float:
        return max(
            self.memory.confidence_of_prefix(f"compare:roll:{a_id}>{b_id}"),
            self.memory.confidence_of_prefix(f"compare:roll:{b_id}>{a_id}"),
            self.memory.confidence_of_prefix(f"compare:roll:{a_id}~{b_id}"),
            self.memory.confidence_of_prefix(f"compare:stack_support:{a_id}>{b_id}"),
            self.memory.confidence_of_prefix(f"compare:stack_support:{b_id}>{a_id}"),
            self.memory.confidence_of_prefix(f"compare:stack_support:{a_id}~{b_id}"),
        )

    def _rule_penalty(self, rule_key: str) -> float:
        return self.memory.confidence_of_prefix(rule_key)

    def _hypothesis_penalty(self, lower_id: str, upper_id: str) -> float:
        return max(
            self.memory.confidence_of_prefix(f"hypothesis:{lower_id}>{upper_id}:predicted:"),
            self.memory.confidence_of_prefix(f"hypothesis:{lower_id}>{upper_id}:validated:"),
        )

    def _bucket_penalty(self, bucket: str) -> float:
        recent = self.recent_action_buckets[-4:]
        return 0.18 * sum(1 for b in recent if b == bucket)

    def _signature_penalty(self, signature: str) -> float:
        recent = self.recent_signatures[-6:]
        return 0.30 * sum(1 for sig in recent if sig == signature)

    def _survey_incomplete(self) -> List[str]:
        return [obj_id for obj_id in self.env.object_ids() if self._observe_penalty(obj_id) < self.SURVEY_THRESHOLD]

    def _touch_incomplete(self) -> List[str]:
        return [obj_id for obj_id in self.env.object_ids() if self._touch_penalty(obj_id) < self.TOUCH_THRESHOLD]

    def _fit_incomplete(self) -> List[str]:
        pending = []
        for obj_id in self.env.fit_capable_ids():
            slot_id = f"slot_{self.env.objects[obj_id].fit_slot}"
            if self._fit_penalty(obj_id, slot_id) < self.FIT_THRESHOLD:
                pending.append(obj_id)
        return pending

    def current_lesson_phase(self) -> str:
        if self._survey_incomplete():
            return "survey_all"
        if self._touch_incomplete():
            return "touch_all"
        if self._fit_incomplete():
            return "fit_all"
        return "hypothesis_validation_lab"

    def curriculum_status(self) -> str:
        survey = self._survey_incomplete()
        touch = self._touch_incomplete()
        fit = self._fit_incomplete()
        return (
            "CURRÍCULO NURSERY\n"
            f"- lição atual       : {self.current_lesson_phase()}\n"
            f"- survey pendente   : {', '.join(survey) if survey else '(concluído)'}\n"
            f"- toque pendente    : {', '.join(touch) if touch else '(concluído)'}\n"
            f"- encaixe pendente  : {', '.join(fit) if fit else '(concluído)'}"
        )

    def comparison_summary(self) -> str:
        lines = ["COMPARAÇÕES APRENDIDAS"]
        for obj_id in self.env.object_ids():
            role = []
            if self.memory.confidence_of_prefix(f"obj:{obj_id}:affordance:rola") > 0.30:
                role.append("rola")
            if self.memory.confidence_of_prefix(f"obj:{obj_id}:affordance:nao_rola_facil") > 0.30:
                role.append("não rola fácil")
            if self.memory.confidence_of_prefix(f"obj:{obj_id}:affordance:suporta_empilhar") > 0.30:
                role.append("suporta empilhar")
            if self.memory.confidence_of_prefix(f"obj:{obj_id}:affordance:empilhavel") > 0.30:
                role.append("empilhável")
            if not role:
                role.append("ainda pouco caracterizado")
            lines.append(f"- {obj_id}: " + ", ".join(role))
        return "\n".join(lines)

    def _count_exact_stack_type(self, obj_id: str, stack_type: str) -> int:
        count = 0
        prefix = f"pair:{obj_id}>"
        marker = f":stack:{stack_type}"
        for key, node in self.memory.nodes.items():
            if key.startswith(prefix) and marker in key and node.confidence >= 0.30:
                count += 1
        return count

    def infer_generalizations(self) -> NurseryActionResult:
        learned: List[str] = []
        summaries: List[str] = []

        for obj_id in self.env.object_ids():
            stable = self._count_exact_stack_type(obj_id, "stable")
            unstable = self._count_exact_stack_type(obj_id, "unstable")
            has_roll = self.memory.confidence_of_prefix(f"obj:{obj_id}:affordance:rola") > 0.30
            has_support = self.memory.confidence_of_prefix(f"obj:{obj_id}:affordance:suporta_empilhar") > 0.30

            if stable >= 1 and has_support and self._rule_penalty(f"rule:base_profile:{obj_id}:good") < 0.30:
                learned.append(f"rule:base_profile:{obj_id}:good=true")
                summaries.append(f"{obj_id} tende a funcionar como boa base")
            if unstable >= 2 and not has_support and self._rule_penalty(f"rule:base_profile:{obj_id}:poor") < 0.30:
                learned.append(f"rule:base_profile:{obj_id}:poor=true")
                summaries.append(f"{obj_id} tende a funcionar como base ruim")
            if has_roll and has_support and self._rule_penalty(f"rule:object_profile:{obj_id}:rolling_can_support") < 0.30:
                learned.append(f"rule:object_profile:{obj_id}:rolling_can_support=true")
                summaries.append(f"{obj_id} mostra que rolar não impede sustentar empilhamento")

        nonrolling_support_count = 0
        rolling_support_count = 0
        for obj_id in self.env.object_ids():
            nonrolling = self.memory.confidence_of_prefix(f"obj:{obj_id}:affordance:nao_rola_facil") > 0.30
            rolling = self.memory.confidence_of_prefix(f"obj:{obj_id}:affordance:rola") > 0.30
            support = self.memory.confidence_of_prefix(f"obj:{obj_id}:affordance:suporta_empilhar") > 0.30
            if nonrolling and support:
                nonrolling_support_count += 1
            if rolling and support:
                rolling_support_count += 1

        if nonrolling_support_count >= 2 and self._rule_penalty("rule:global:nonrolling_often_supports") < 0.30:
            learned.append("rule:global:nonrolling_often_supports=true")
            summaries.append("objetos que não rolam fácil costumam sustentar empilhamento")
        if rolling_support_count >= 1 and self._rule_penalty("rule:global:rolling_does_not_forbid_support") < 0.30:
            learned.append("rule:global:rolling_does_not_forbid_support=true")
            summaries.append("rolar não proíbe que um objeto sirva de base")

        if not learned:
            return NurseryActionResult(True, "Tentou generalizar relações, mas ainda não encontrou evidência nova forte o suficiente.", 0.24, 0.10, 0.04, 0.18, [])

        return NurseryActionResult(True, "Inferiu generalizações: " + "; ".join(summaries) + ".", 0.88, 0.28, 0.04, 0.82, learned)

    def _persist_memory_key(self, key: str) -> None:
        node = self.memory.nodes.get(key)
        if node is None:
            return
        self.home.upsert_semantic_memory(
            key=key,
            content=node.value,
            confidence=node.confidence,
            source="nursery_v47",
        )

    def _adjust_and_persist(self, key: str, delta: float, value: str = "true") -> None:
        self.memory.adjust_confidence(key, delta, value)
        self._persist_memory_key(key)

    def _arbitrate_conflict(self, good_key: str, poor_key: str) -> None:
        good_node = self.memory.nodes.get(good_key)
        poor_node = self.memory.nodes.get(poor_key)
        if good_node is None or poor_node is None:
            return
        if good_node.confidence > 0.40 and poor_node.confidence > 0.40:
            if abs(good_node.confidence - poor_node.confidence) < 0.08:
                good_node.confidence = clamp(good_node.confidence - 0.06, 0.0, 0.99)
                poor_node.confidence = clamp(poor_node.confidence - 0.06, 0.0, 0.99)
            elif good_node.confidence > poor_node.confidence:
                poor_node.confidence = clamp(poor_node.confidence - 0.08, 0.0, 0.99)
            else:
                good_node.confidence = clamp(good_node.confidence - 0.08, 0.0, 0.99)
            self._persist_memory_key(good_key)
            self._persist_memory_key(poor_key)

    def _infer_observed_cause(self, lower_id: str, upper_id: str, observed: str) -> str:
        lower_support = self.memory.confidence_of_prefix(f"obj:{lower_id}:affordance:suporta_empilhar") > 0.30
        lower_poor = self.memory.confidence_of_prefix(f"rule:base_profile:{lower_id}:poor") > 0.30
        lower_roll = self.memory.confidence_of_prefix(f"obj:{lower_id}:affordance:rola") > 0.30
        upper_empilhavel = self.memory.confidence_of_prefix(f"obj:{upper_id}:affordance:empilhavel") > 0.30
        upper_nonstack = self.memory.confidence_of_prefix(f"rule:top_profile:{upper_id}:non_stackable") > 0.30

        if observed == "stable":
            if lower_support and upper_empilhavel:
                return "pair"
            if lower_support:
                return "base"
            if upper_empilhavel:
                return "top"
            return "pair"

        if upper_nonstack or not upper_empilhavel:
            return "top"
        if lower_poor or (lower_roll and not lower_support):
            return "base"
        return "pair"

    def _top_context_labels(self, upper_id: str) -> list[str]:
        labels: list[str] = []

        if self.memory.confidence_of_prefix(f"rule:top_profile:{upper_id}:non_stackable") > 0.30:
            labels.append("with_nonstackable_top")
        elif self.memory.confidence_of_prefix(f"obj:{upper_id}:affordance:empilhavel") > 0.30 or self.memory.confidence_of_prefix(f"rule:top_profile:{upper_id}:stackable") > 0.30:
            labels.append("with_stackable_top")
        else:
            labels.append("with_unknown_top")

        if self.memory.confidence_of_prefix(f"obj:{upper_id}:affordance:rola") > 0.30:
            labels.append("with_rolling_top")
        elif self.memory.confidence_of_prefix(f"obj:{upper_id}:affordance:nao_rola_facil") > 0.30:
            labels.append("with_nonrolling_top")

        if self.memory.confidence_of_prefix(f"obj:{upper_id}:category:block") > 0.30:
            labels.append("with_block_top")
        elif self.memory.confidence_of_prefix(f"obj:{upper_id}:category:toy") > 0.30:
            labels.append("with_toy_top")

        return labels

    def _conditional_key_pairs(self, lower_id: str, upper_id: str) -> list[tuple[str, str, str]]:
        pairs: list[tuple[str, str, str]] = []
        for ctx in self._top_context_labels(upper_id):
            good_key = f"rule:conditional_base:{lower_id}:{ctx}:good"
            poor_key = f"rule:conditional_base:{lower_id}:{ctx}:poor"
            pairs.append((good_key, poor_key, ctx))
        return pairs

    def _conditional_evidence(self, lower_id: str, upper_id: str) -> tuple[float, float, float, list[str], list[str], list[str]]:
        positive = 0.0
        negative = 0.0
        pos_labels: list[str] = []
        neg_labels: list[str] = []
        mixed_labels: list[str] = []

        for good_key, poor_key, label in self._conditional_key_pairs(lower_id, upper_id):
            good_conf = self.memory.confidence_of_prefix(good_key)
            poor_conf = self.memory.confidence_of_prefix(poor_key)
            if good_conf > positive:
                positive = good_conf
            if poor_conf > negative:
                negative = poor_conf
            if good_conf > 0.30:
                pos_labels.append(label)
            if poor_conf > 0.30:
                neg_labels.append(label)
            if good_conf > 0.30 and poor_conf > 0.30:
                mixed_labels.append(label)

        net_score = positive - negative
        return positive, negative, net_score, pos_labels, neg_labels, mixed_labels

    def _contextual_net_for_label(self, lower_id: str, label: str) -> tuple[float, float, float]:
        good_key = f"rule:conditional_base:{lower_id}:{label}:good"
        poor_key = f"rule:conditional_base:{lower_id}:{label}:poor"
        good_conf = self.memory.confidence_of_prefix(good_key)
        poor_conf = self.memory.confidence_of_prefix(poor_key)
        return good_conf, poor_conf, good_conf - poor_conf

    def contextual_rules_summary(self) -> str:
        lines = ["REGRAS CONDICIONAIS"]
        rules = []
        for key, node in sorted(self.memory.nodes.items()):
            if key.startswith("rule:conditional_base:") and node.confidence >= 0.30:
                rules.append(f"- {key} [conf={node.confidence:.2f}]")
        if not rules:
            lines.append("(nenhuma regra condicional ainda)")
        else:
            lines.extend(rules[:28])
        return "\n".join(lines)

    def contextual_abstractions_summary(self) -> str:
        lines = ["ABSTRAÇÕES DE CONTEXTO"]
        labels = [
            "with_stackable_top",
            "with_nonstackable_top",
            "with_nonrolling_top",
            "with_rolling_top",
            "with_block_top",
            "with_toy_top",
        ]

        any_item = False
        base_ids = self.env.object_ids()

        for label in labels:
            scored = []
            for base in base_ids:
                good_conf, poor_conf, net = self._contextual_net_for_label(base, label)
                if max(good_conf, poor_conf) < 0.30:
                    continue
                any_item = True
                scored.append((base, net, good_conf, poor_conf))

            if scored:
                scored.sort(key=lambda x: abs(x[1]), reverse=True)
                parts = []
                for base, net, good_conf, poor_conf in scored[:4]:
                    if net > 0.08:
                        tag = f"{base}:+{net:.2f}"
                    elif net < -0.08:
                        tag = f"{base}:{net:.2f}"
                    else:
                        tag = f"{base}:≈0.00"
                    tag += f" (g={good_conf:.2f}, p={poor_conf:.2f})"
                    parts.append(tag)
                lines.append(f"- {label}: " + ", ".join(parts))

        if not any_item:
            lines.append("(nenhuma abstração contextual ainda)")
        return "\n".join(lines)

    def ambiguous_contexts_summary(self) -> str:
        lines = ["CONTEXTOS AMBÍGUOS PRIORITÁRIOS"]
        found = []
        for base, upper, labels, net in self._ambiguous_context_targets():
            label_text = ", ".join(labels[:3]) if labels else "(sem rótulo)"
            found.append(f"- {base} com topo {upper}: net={net:+.2f} | {label_text}")
        if not found:
            lines.append("(nenhum contexto ambíguo prioritário no momento)")
        else:
            lines.extend(found[:12])
        return "\n".join(lines)

    def experimental_plan_summary(self) -> str:
        lines = ["PLANOS EXPERIMENTAIS PRIORITÁRIOS"]
        plans = self._experimental_plan_targets()
        if not plans:
            lines.append("(nenhum experimento prioritário no momento)")
            return "\n".join(lines)
        for lower, upper, info_score, labels, reason in plans[:12]:
            label_text = ", ".join(labels[:3]) if labels else "(sem rótulo)"
            lines.append(f"- {lower} com topo {upper}: info={info_score:.2f} | {label_text} | {reason}")
        return "\n".join(lines)

    def active_experiment_queue_summary(self) -> str:
        lines = ["MICROPLANO EXPERIMENTAL ATIVO"]
        if not self.experiment_queue:
            lines.append("(nenhum microplano ativo no momento)")
        else:
            if self.last_experiment_plan_summary:
                lines.append(self.last_experiment_plan_summary)
            for idx, (lower, upper, info_score, labels, reason) in enumerate(self.experiment_queue[:6], start=1):
                label_text = ", ".join(labels[:3]) if labels else "(sem rótulo)"
                step_no = self.current_plan_step_index + idx
                lines.append(f"- etapa {step_no}: {lower} com topo {upper} | info={info_score:.2f} | {label_text} | {reason}")
        return "\n".join(lines)

    def _recent_pair_was_tested(self, lower: str, upper: str) -> bool:
        recent = self.recent_signatures[-12:]
        pair_predict = f"predict:{lower}:{upper}"
        pair_validate = f"validate:{lower}:{upper}"
        return pair_predict in recent or pair_validate in recent or (lower, upper) in self.plan_recent_pairs[-8:]

    def _boot_primary_family(self, labels: List[str]) -> str:
        priority = [
            "with_nonrolling_top",
            "with_nonstackable_top",
            "with_rolling_top",
            "with_block_top",
            "with_stackable_top",
            "with_toy_top",
        ]
        label_set = set(labels)
        for label in priority:
            if label in label_set:
                return label
        return labels[0] if labels else "(sem_familia)"

    def _boot_recent_primary_families(self, limit: int = 8) -> List[str]:
        return list(self.plan_recent_primary_families[-limit:])

    def _boot_core_seen(self) -> set:
        core = {"with_nonrolling_top", "with_nonstackable_top", "with_rolling_top"}
        return set(self._boot_recent_primary_families(8)).intersection(core)

    def _record_plan_pair(self, lower: str, upper: str) -> None:
        self.plan_recent_pairs.append((lower, upper))
        self.plan_recent_pairs = self.plan_recent_pairs[-12:]

    def _pair_recent_count(self, lower: str, upper: str) -> int:
        return sum(1 for pair in self.plan_recent_pairs[-12:] if pair == (lower, upper))

    def _pair_repeat_penalty(self, lower: str, upper: str) -> float:
        return 0.18 * self._pair_recent_count(lower, upper)

    def _record_plan_labels(self, labels: List[str]) -> None:
        self.plan_recent_context_labels.extend(labels)
        self.plan_recent_context_labels = self.plan_recent_context_labels[-24:]

        primary = self._boot_primary_family(labels)
        self.plan_recent_primary_families.append(primary)
        self.plan_recent_primary_families = self.plan_recent_primary_families[-12:]
    def _context_label_recent_count(self, label: str) -> int:
        return sum(1 for item in self.plan_recent_context_labels[-24:] if item == label)

    def _context_family_penalty(self, labels: List[str]) -> float:
        if not labels:
            return 0.0
        dominant = 0
        for label in labels:
            dominant = max(dominant, self._context_label_recent_count(label))
        return 0.08 * dominant

    def _recent_context_dominant_labels(self, top_n: int = 2) -> List[str]:
        counts = {}
        for label in self.plan_recent_context_labels[-24:]:
            counts[label] = counts.get(label, 0) + 1
        ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
        return [label for label, _count in ranked[:top_n]]

    def _introduces_fresh_context_family(self, labels: List[str]) -> bool:
        dominant = set(self._recent_context_dominant_labels())
        if not dominant:
            return True
        return len(set(labels) - dominant) > 0

    def _dominant_context_gate_penalty(self, labels: List[str]) -> float:
        dominant = set(self._recent_context_dominant_labels())
        if not dominant or not labels:
            return 0.0
        label_set = set(labels)
        if label_set.issubset(dominant):
            return 0.28 + 0.04 * len(label_set)
        overlap = len(label_set.intersection(dominant))
        return 0.06 * overlap

    def recent_context_families_summary(self) -> str:
        lines = ["FAMÍLIAS CONTEXTUAIS RECENTES"]
        dominant = self._recent_context_dominant_labels(top_n=4)
        if not dominant:
            lines.append("(nenhuma família contextual recente ainda)")
            return "\n".join(lines)
        for label in dominant:
            lines.append(f"- {label}: freq={self._context_label_recent_count(label)}")
        return "\n".join(lines)

    def _rotation_context_label(self) -> Optional[str]:
        dominant = self._recent_context_dominant_labels(top_n=1)
        if not dominant:
            return None
        label = dominant[0]
        if self._context_label_recent_count(label) >= 7:
            return label
        return None

    def rotation_gate_summary(self) -> str:
        lines = ["ROTAÇÃO CONTEXTUAL"]
        label = self._rotation_context_label()
        if label is None:
            lines.append("(nenhuma rotação obrigatória ativa)")
        else:
            lines.append(f"- contexto dominante bloqueado: {label}")
            lines.append("- novos planos removem esse eixo da fila de abertura enquanto houver alternativa fora dele")
        return "\n".join(lines)

    def _context_return_score(self, labels: List[str], lower: str, upper: str) -> float:
        if not labels:
            return 0.0

        score = 0.0
        for label in labels:
            good_conf, poor_conf, ctx_net = self._contextual_net_for_label(lower, label)
            if max(good_conf, poor_conf) >= 0.25 and abs(ctx_net) <= 0.18:
                score += 0.18  # conflito ou zona fina: vale revisitar
            if 0.18 < abs(ctx_net) <= 0.35:
                score += 0.08  # ainda não totalmente estabilizado

        pos, neg, net, pos_labels, neg_labels, mixed_labels = self._conditional_evidence(lower, upper)
        if mixed_labels:
            score += 0.20
        if abs(net) <= 0.15 and (pos > 0.25 or neg > 0.25):
            score += 0.16
        return score

    def _return_allowed_for_blocked_context(self, labels: List[str], lower: str, upper: str) -> bool:
        blocked = self._rotation_context_label()
        if blocked is None:
            return True
        label_set = set(labels)
        if blocked not in label_set:
            return True
        return self._context_return_score(labels, lower, upper) >= 0.18

    def contextual_return_summary(self) -> str:
        lines = ["RETORNO CONTEXTUAL OPORTUNO"]
        blocked = self._rotation_context_label()
        if blocked is None:
            lines.append("(nenhum contexto bloqueado precisando retorno seletivo)")
            return "\n".join(lines)

        found = []
        ids = self.env.object_ids()
        for lower in ids:
            for upper in ids:
                if lower == upper:
                    continue
                labels = sorted(set(self._top_context_labels(upper)))
                if blocked not in labels:
                    continue
                score = self._context_return_score(labels, lower, upper)
                if score >= 0.18:
                    found.append((score, lower, upper, labels))

        if not found:
            lines.append(f"- {blocked}: sem motivo forte novo para retorno agora")
            return "\n".join(lines)

        found.sort(reverse=True)
        for score, lower, upper, labels in found[:8]:
            lines.append(f"- {lower} com topo {upper}: return_score={score:.2f} | " + ", ".join(labels[:3]))
        return "\n".join(lines)

    def controlled_return_probe_summary(self) -> str:
        lines = ["SONDAS DE RETORNO CONTROLADO"]
        blocked = self._rotation_context_label()
        if blocked is None:
            lines.append("(nenhum contexto bloqueado ativo)")
            return "\n".join(lines)

        probes = self._strong_context_return_candidates(limit=6)
        if not probes:
            lines.append(f"- {blocked}: nenhuma sonda forte suficiente no momento")
            memory_line = self._fallback_probe_memory_line()
            if memory_line:
                lines.append(f"- {memory_line}")
            return "\n".join(lines)

        for lower, upper, score, labels, reason in probes[:6]:
            label_text = ", ".join(labels[:3]) if labels else "(sem rótulo)"
            lines.append(f"- {lower} com topo {upper}: probe={score:.2f} | {label_text} | {reason}")
        return "\n".join(lines)
    def _session_boot_active(self) -> bool:
        if self.current_lesson_phase() != "hypothesis_validation_lab":
            return False
        if self._rotation_context_label() is not None:
            return False

        seen = self._boot_core_seen()
        need_more_family_contrast = ("with_nonrolling_top" not in seen) or (len(seen) < 2)
        return self.step_counter < 16 and need_more_family_contrast
    def _boot_label_pressure(self, labels: List[str]) -> float:
        if not labels:
            return 0.0

        recent_labels = list(self.plan_recent_context_labels[-12:])
        recent_primary = self._boot_recent_primary_families(8)
        seen_primary = set(recent_primary)
        primary = self._boot_primary_family(labels)
        pressure = 0.0

        # penaliza repetir cedo a mesma família primária
        primary_freq = recent_primary.count(primary)
        if primary_freq >= 1:
            pressure += 0.12 * primary_freq

        # penaliza rolling antes de abrir contraste suficiente
        if primary == "with_rolling_top":
            pressure += 0.18
            if "with_nonrolling_top" not in seen_primary:
                pressure += 0.42
            if recent_primary.count("with_rolling_top") >= max(2, len(recent_primary) - recent_primary.count("with_rolling_top")):
                pressure += 0.24

        # recompensa abrir cedo não-rolling_top
        if primary == "with_nonrolling_top" and "with_nonrolling_top" not in seen_primary:
            pressure -= 0.52

        # recompensa abrir família primária nova
        if primary not in seen_primary:
            pressure -= 0.16

        # pequeno empurrão para qualquer rótulo ainda pouco visitado
        for label in set(labels):
            freq = sum(1 for item in recent_labels if item == label)
            if freq == 0:
                pressure -= 0.08
            elif freq >= 3:
                pressure += 0.05 * min(freq - 2, 2)

        return pressure
    def _boot_pair_pressure(self, lower: str, upper: str) -> float:
        repeat = self._pair_repeat_penalty(lower, upper)
        recent_same_lower = sum(1 for a, _b in self.plan_recent_pairs[-4:] if a == lower)
        recent_same_upper = sum(1 for _a, b in self.plan_recent_pairs[-4:] if b == upper)
        return repeat + 0.08 * recent_same_lower + 0.06 * recent_same_upper
    def session_boot_summary(self) -> str:
        lines = ["BOOT RELACIONAL DE ABERTURA"]
        recent_primary = self._boot_recent_primary_families(8)
        seen = self._boot_core_seen()

        if not self._session_boot_active():
            if recent_primary:
                lines.append("(boot por famílias inativo nesta fase da sessão)")
                lines.append("- famílias primárias recentes: " + ", ".join(recent_primary[-4:]))
            else:
                lines.append("(boot por famílias inativo nesta fase da sessão)")
            return "\n".join(lines)

        lines.append("- boot por famílias ativo: priorizar contraste antes do eixo dominante")
        lines.append(f"- primárias recentes: {', '.join(recent_primary) if recent_primary else '(nenhuma ainda)'}")
        lines.append(f"- contraste core já visto: {', '.join(sorted(seen)) if seen else '(nenhum ainda)'}")
        if "with_nonrolling_top" not in seen:
            lines.append("- alvo imediato: visitar mais cedo uma família with_nonrolling_top")
        return "\n".join(lines)
    def _capture_contradiction_baseline(
        self,
        lower: str,
        upper: str,
        labels: List[str],
    ) -> Dict[str, float]:
        snap: Dict[str, float] = {}
        pair_good = f"rule:pair_profile:{lower}>{upper}:compatible"
        pair_poor = f"rule:pair_profile:{lower}>{upper}:incompatible"
        snap[pair_good] = self.memory.confidence_of_prefix(pair_good)
        snap[pair_poor] = self.memory.confidence_of_prefix(pair_poor)

        for label in sorted(set(labels)):
            for base in self.env.object_ids():
                good_conf, poor_conf, net = self._contextual_net_for_label(base, label)
                snap[f"ctxnet:{base}:{label}"] = net
                snap[f"ctxgood:{base}:{label}"] = good_conf
                snap[f"ctxpoor:{base}:{label}"] = poor_conf
        return snap

    def _metric_value_after_repair(self, metric_key: str) -> float:
        if metric_key.startswith("ctxnet:"):
            _, base, label = metric_key.split(":", 2)
            _g, _p, net = self._contextual_net_for_label(base, label)
            return net
        if metric_key.startswith("ctxgood:"):
            _, base, label = metric_key.split(":", 2)
            g, _p, _net = self._contextual_net_for_label(base, label)
            return g
        if metric_key.startswith("ctxpoor:"):
            _, base, label = metric_key.split(":", 2)
            _g, p, _net = self._contextual_net_for_label(base, label)
            return p
        return self.memory.confidence_of_prefix(metric_key)

    def _metric_human_label(self, metric_key: str) -> str:
        if metric_key.startswith("ctxnet:"):
            _, base, label = metric_key.split(":", 2)
            return f"saldo contextual {base} em {label}"
        if metric_key.startswith("ctxgood:"):
            _, base, label = metric_key.split(":", 2)
            return f"evidência good de {base} em {label}"
        if metric_key.startswith("ctxpoor:"):
            _, base, label = metric_key.split(":", 2)
            return f"evidência poor de {base} em {label}"
        if metric_key.startswith("rule:pair_profile:") and metric_key.endswith(":compatible"):
            core = metric_key[len("rule:pair_profile:"):-len(":compatible")]
            return f"compatibilidade do par {core}"
        if metric_key.startswith("rule:pair_profile:") and metric_key.endswith(":incompatible"):
            core = metric_key[len("rule:pair_profile:"):-len(":incompatible")]
            return f"incompatibilidade do par {core}"
        return metric_key

    def _current_contradiction_delta_lines(self, limit: int = 10) -> List[str]:
        if self.last_contradiction_case is None or self.last_contradiction_baseline is None:
            return []

        rows = []
        for metric_key, before in self.last_contradiction_baseline.items():
            after = self._metric_value_after_repair(metric_key)
            delta = after - before
            if abs(delta) < 0.04:
                continue
            rows.append((abs(delta), delta, metric_key, before, after))

        rows.sort(key=lambda x: x[0], reverse=True)
        lines: List[str] = []
        for _abs_delta, delta, metric_key, before, after in rows[:limit]:
            sign = "+" if delta >= 0 else ""
            label = self._metric_human_label(metric_key)
            lines.append(f"- {label}: {before:.2f}->{after:.2f} ({sign}{delta:.2f})")
        return lines

    def _semantic_lines_from_delta(self, delta_lines: List[str]) -> List[str]:
        if self.last_contradiction_case is None or self.last_contradiction_baseline is None:
            return []

        raw_rows = []
        for metric_key, before in self.last_contradiction_baseline.items():
            after = self._metric_value_after_repair(metric_key)
            delta = after - before
            if abs(delta) < 0.04:
                continue
            raw_rows.append((abs(delta), delta, metric_key, before, after))

        raw_rows.sort(key=lambda x: x[0], reverse=True)
        lines: List[str] = []

        # resumo por direção
        poor_up = []
        good_up = []
        net_up = []
        net_down = []

        for _abs_delta, delta, metric_key, before, after in raw_rows[:12]:
            label = self._metric_human_label(metric_key)
            if metric_key.startswith("ctxpoor:") and delta > 0:
                poor_up.append(label)
            elif metric_key.startswith("ctxgood:") and delta > 0:
                good_up.append(label)
            elif metric_key.startswith("ctxnet:") and delta > 0:
                net_up.append(label)
            elif metric_key.startswith("ctxnet:") and delta < 0:
                net_down.append(label)

        if poor_up:
            lines.append(f"- o reparo fortaleceu sinais de risco em: {', '.join(poor_up[:2])}")
        if good_up:
            lines.append(f"- o reparo fortaleceu sinais favoráveis em: {', '.join(good_up[:2])}")
        if net_down:
            lines.append(f"- o reparo tornou mais cautelosa a leitura de: {', '.join(net_down[:2])}")
        if net_up:
            lines.append(f"- o reparo tornou mais confiante a leitura de: {', '.join(net_up[:2])}")

        # linha interpretativa do par/erro
        lower, upper, predicted, observed, labels = self.last_contradiction_case
        if predicted == "stable" and observed == "unstable":
            lines.append(f"- a contradição enfraqueceu uma leitura otimista para {lower}>{upper}")
        elif predicted == "unstable" and observed == "stable":
            lines.append(f"- a contradição enfraqueceu uma leitura pessimista para {lower}>{upper}")
        else:
            lines.append(f"- o reparo reposicionou a interpretação local de {lower}>{upper}")

        return lines[:6]

    def _finalize_contradiction_repair_if_ready(self) -> None:
        if self.active_contradiction_repair_plan_id <= 0:
            return
        if self.current_plan_id < self.active_contradiction_repair_plan_id:
            return
        if self.pending_hypotheses or self.experiment_queue:
            return

        self.last_contradiction_delta_lines = self._current_contradiction_delta_lines(limit=10)
        self.last_contradiction_semantic_lines = self._semantic_lines_from_delta(self.last_contradiction_delta_lines)
        self.active_contradiction_repair_plan_id = 0
    def _contradiction_primary_family(self, labels: List[str]) -> str:
        return self._boot_primary_family(labels)

    def _contradiction_repair_candidates(self, limit: int = 8) -> List[Tuple[str, str, float, List[str], str]]:
        if self.last_contradiction_case is None or self.contradiction_repair_budget <= 0:
            return []

        source_lower, source_upper, predicted, observed, source_labels = self.last_contradiction_case
        source_primary = self._contradiction_primary_family(source_labels)
        rows: List[Tuple[float, str, str, List[str], str]] = []

        for lower, upper, info_score, labels, reason in self._experimental_plan_targets():
            if lower == source_lower and upper == source_upper:
                continue

            share_pair_neighborhood = lower == source_lower or upper == source_upper or upper == source_lower or lower == source_upper
            share_family = self._contradiction_primary_family(labels) == source_primary
            label_overlap = len(set(labels).intersection(source_labels)) > 0
            if not (share_pair_neighborhood or share_family or label_overlap):
                continue

            bonus = 0.0
            if share_pair_neighborhood:
                bonus += 0.34
            if share_family:
                bonus += 0.18
            if label_overlap:
                bonus += 0.12

            repeat_penalty = self._pair_repeat_penalty(lower, upper)
            score = info_score + bonus - repeat_penalty
            repair_reason = "reparo local após contradição recente"
            if share_pair_neighborhood:
                repair_reason += " | vizinhança direta do erro"
            elif share_family:
                repair_reason += " | mesma família primária do erro"
            else:
                repair_reason += " | contexto vizinho do erro"
            if repeat_penalty > 0.0:
                repair_reason += f" | penalização de repetição={repeat_penalty:.2f}"
            rows.append((score, lower, upper, labels, repair_reason))

        rows.sort(key=lambda x: x[0], reverse=True)
        out: List[Tuple[str, str, float, List[str], str]] = []
        seen = set()
        for score, lower, upper, labels, repair_reason in rows:
            key = (lower, upper)
            if key in seen:
                continue
            seen.add(key)
            out.append((lower, upper, max(0.05, score), labels, repair_reason))
            if len(out) >= limit:
                break
        return out

    def _build_contradiction_repair_queue(self, limit: int = 3) -> List[Tuple[str, str, float, List[str], str]]:
        if self.last_contradiction_case is None or self.contradiction_repair_budget <= 0:
            return []

        candidates = self._contradiction_repair_candidates(limit=10)
        if len(candidates) < 2:
            return []

        queue: List[Tuple[str, str, float, List[str], str]] = []
        used_pairs = set()
        used_labels = set()

        for lower, upper, info_score, labels, reason in candidates:
            if (lower, upper) in used_pairs:
                continue
            if queue:
                if len(set(labels) - used_labels) == 0 and lower == queue[0][0] and upper == queue[0][1]:
                    continue
            queue.append((lower, upper, info_score, labels, reason))
            used_pairs.add((lower, upper))
            used_labels.update(labels)
            if len(queue) >= limit:
                break

        if len(queue) < 2:
            return []

        source_lower, source_upper, predicted, observed, source_labels = self.last_contradiction_case
        self.current_plan_id += 1
        self.current_plan_step_index = 0
        self.current_plan_return_budget = 0
        self.contradiction_repair_budget = 0
        self.active_contradiction_repair_plan_id = self.current_plan_id
        first_labels = ", ".join(queue[0][3][:3]) if queue[0][3] else "(sem rótulo)"
        self.last_experiment_plan_summary = (
            f"Plano P{self.current_plan_id:03d} (reparo por contradição) com {len(queue)} etapa(s); "
            f"erro-fonte={source_lower}>{source_upper} ({predicted}->{observed}) | foco={first_labels} | info inicial={queue[0][2]:.2f}"
        )
        return queue

    def probe_continuity_summary(self) -> str:
        lines = ["CONTINUIDADE ENTRE REPARO E SONDA"]
        if self.last_justified_probe is None:
            if self.last_contradiction_semantic_lines:
                lines.append("- há leitura semântica de reparo disponível, mas nenhuma sonda justificada a herdou ainda")
                lines.extend(self.last_contradiction_semantic_lines[:2])
            else:
                lines.append("(nenhuma continuidade explícita registrada ainda)")
            return "\n".join(lines)

        if not self.last_probe_continuity_lines:
            lines.append("(a última sonda não precisou herdar continuidade explícita do reparo)")
            return "\n".join(lines)

        lines.extend(self.last_probe_continuity_lines[:4])
        return "\n".join(lines)

    def live_tension_state_summary(self) -> str:
        lines = ["TENSÃO VIVA PERSISTENTE"]
        record = self.live_tension_record
        if record is None:
            lines.append("(nenhuma tensão viva persistente registrada)")
            return "\n".join(lines)

        lines.append(f"- {record.tension_id}: status={record.status} | pressão={record.pressure_snapshot:.2f} | déficit={record.closure_deficit:.2f}")
        lines.append(f"- origem: {record.source_lower}>{record.source_upper} | previsto={record.source_predicted} | observado={record.source_observed}")
        if record.last_probe_lower is not None and record.last_probe_upper is not None:
            lines.append(f"- última sonda associada: {record.last_probe_lower}>{record.last_probe_upper} | score={record.last_probe_score:.2f}")
        if record.outcome_lines:
            lines.extend(record.outcome_lines[:2])
        elif record.continuity_lines:
            lines.extend(record.continuity_lines[:2])
        return "\n".join(lines)

    def tension_outcome_summary(self) -> str:
        lines = ["DESFECHO DA TENSÃO REPARADA"]
        if not self.last_tension_outcome_lines:
            if self.last_probe_continuity_lines:
                lines.append("(há continuidade registrada, mas o desfecho da sonda ainda não foi fechado)")
            else:
                lines.append("(nenhum desfecho explícito de tensão registrado ainda)")
            return "\n".join(lines)

        lines.extend(self.last_tension_outcome_lines[:4])
        return "\n".join(lines)

    def contradiction_repair_summary(self) -> str:
        lines = ["REPARO LOCAL POR CONTRADIÇÃO"]
        if self.last_contradiction_case is None:
            lines.append("(nenhuma contradição forte registrada ainda)")
            return "\n".join(lines)

        lower, upper, predicted, observed, labels = self.last_contradiction_case
        label_text = ", ".join(labels[:3]) if labels else "(sem rótulo)"
        lines.append(f"- última contradição: {lower} com topo {upper} | previsto={predicted} | observado={observed} | {label_text}")
        lines.append(f"- orçamento de reparo local restante: {self.contradiction_repair_budget}")

        candidates = self._contradiction_repair_candidates(limit=4)
        if not candidates:
            lines.append("(nenhum reparo local pendente no momento)")
            return "\n".join(lines)

        for cand_lower, cand_upper, info_score, cand_labels, reason in candidates[:4]:
            cand_label_text = ", ".join(cand_labels[:3]) if cand_labels else "(sem rótulo)"
            lines.append(f"- {cand_lower} com topo {cand_upper}: info={info_score:.2f} | {cand_label_text} | {reason}")
        return "\n".join(lines)
    def _probe_repair_continuity_lines(self, lower: str, upper: str, labels: List[str]) -> List[str]:
        if self.last_contradiction_case is None:
            return []

        c_lower, c_upper, predicted, observed, c_labels = self.last_contradiction_case
        continuity: List[str] = []

        shared_labels = sorted(set(labels).intersection(c_labels))
        if shared_labels:
            continuity.append(f"- a sonda retomou a mesma faixa contextual do reparo: {', '.join(shared_labels[:3])}")

        if lower == c_lower or lower == c_upper or upper == c_lower or upper == c_upper:
            continuity.append(f"- a sonda permaneceu no bairro relacional do erro anterior: {c_lower}>{c_upper}")

        if self.last_contradiction_semantic_lines:
            first_semantic = self.last_contradiction_semantic_lines[0].lstrip("- ").strip()
            continuity.append(f"- ela aproveita a leitura do reparo: {first_semantic}")

        if predicted == "stable" and observed == "unstable":
            continuity.append(f"- esta pergunta tenta testar se o sistema abandonou de fato um otimismo excessivo em torno de {c_lower}>{c_upper}")
        elif predicted == "unstable" and observed == "stable":
            continuity.append(f"- esta pergunta tenta verificar se o sistema consolidou a correção de um pessimismo excessivo em torno de {c_lower}>{c_upper}")

        if not continuity:
            continuity.append("- a nova sonda não herdou continuidade explícita do último reparo")
        return continuity[:4]

    def _update_tension_outcome_after_probe_validation(self, lower: str, upper: str, observed: str) -> None:
        if self.last_justified_probe is None or self.last_contradiction_case is None:
            return

        probe_lower, probe_upper, _score, probe_labels = self.last_justified_probe
        if lower != probe_lower or upper != probe_upper:
            return

        c_lower, c_upper, predicted, actual, c_labels = self.last_contradiction_case
        shared_labels = sorted(set(probe_labels).intersection(c_labels))
        shared_pair = lower in {c_lower, c_upper} or upper in {c_lower, c_upper}
        aligned_with_correction = (observed == actual)

        if aligned_with_correction and shared_pair:
            status = "closed"
        elif aligned_with_correction:
            status = "maintained"
        elif shared_pair:
            status = "reopened"
        else:
            status = "weakened"

        lines: List[str] = [f"- status narrativo da tensão: {status}"]
        if shared_labels:
            lines.append(f"- a validação da sonda permaneceu na mesma faixa contextual da tensão: {', '.join(shared_labels[:3])}")
        if shared_pair:
            lines.append(f"- o desfecho ainda pertence ao mesmo bairro relacional de {c_lower}>{c_upper}")

        if predicted == "stable" and actual == "unstable":
            if observed == "unstable":
                lines.append(f"- a sonda consolidou a correção de um otimismo excessivo em {c_lower}>{c_upper}")
            else:
                lines.append(f"- a sonda reacendeu a possibilidade de estabilidade em torno de {c_lower}>{c_upper}")
        elif predicted == "unstable" and actual == "stable":
            if observed == "stable":
                lines.append(f"- a sonda consolidou a correção de um pessimismo excessivo em {c_lower}>{c_upper}")
            else:
                lines.append(f"- a sonda devolveu cautela ao caso {c_lower}>{c_upper}")
        else:
            if aligned_with_correction:
                lines.append(f"- a sonda manteve coerência com a leitura corrigida de {c_lower}>{c_upper}")
            else:
                lines.append(f"- a sonda enfraqueceu a leitura corrigida de {c_lower}>{c_upper}")

        if self.last_contradiction_semantic_lines:
            semantic = self.last_contradiction_semantic_lines[0].lstrip("- ").strip()
            lines.append(f"- leitura herdada do reparo: {semantic}")

        self.last_tension_outcome_lines = lines[:5]

        if self.live_tension_record is not None and self._live_tension_matches(lower, upper, probe_labels):
            self.live_tension_record.status = status
            self.live_tension_record.outcome_lines = self.last_tension_outcome_lines[:]
            self.live_tension_record.closure_deficit = self._live_tension_status_closure_deficit(status)

    def last_justified_probe_summary(self) -> str:
        lines = ["MEMÓRIA DA ÚLTIMA SONDA JUSTIFICADA"]
        if self.last_justified_probe is None:
            lines.append("(nenhuma sonda justificada registrada ainda)")
            return "\n".join(lines)

        lower, upper, score, labels = self.last_justified_probe
        label_text = ", ".join(labels[:3]) if labels else "(sem rótulo)"
        lines.append(f"- {lower} com topo {upper}: info={score:.2f} | {label_text}")
        if self.last_justified_probe_judgment:
            lines.append(f"- juízo: {self.last_justified_probe_judgment}")
        if self.last_probe_continuity_lines:
            lines.extend(self.last_probe_continuity_lines[:2])
        return "\n".join(lines)
    def _fallback_probe_memory_line(self) -> str:
        if self.last_justified_probe is None:
            return ""
        lower, upper, score, labels = self.last_justified_probe
        label_text = ", ".join(labels[:3]) if labels else "(sem rótulo)"
        return f"última sonda justificada: {lower} com topo {upper} | info={score:.2f} | {label_text}"

    def contradiction_effect_summary(self) -> str:
        lines = ["EFEITO DO REPARO LOCAL"]
        if self.last_contradiction_case is None or self.last_contradiction_baseline is None:
            lines.append("(nenhum baseline de contradição registrado ainda)")
            return "\n".join(lines)

        if self.active_contradiction_repair_plan_id > 0:
            lines.append("(reparo em andamento; mostrando delta parcial)")
            delta_lines = self._current_contradiction_delta_lines(limit=8)
        else:
            delta_lines = self.last_contradiction_delta_lines or self._current_contradiction_delta_lines(limit=8)

        if not delta_lines:
            lines.append("(nenhuma mudança local acima do limiar ainda)")
            return "\n".join(lines)

        lines.extend(delta_lines[:8])
        return "\n".join(lines)

    def contradiction_semantic_summary(self) -> str:
        lines = ["SÍNTESE SEMÂNTICA DO REPARO"]
        if self.last_contradiction_case is None or self.last_contradiction_baseline is None:
            lines.append("(nenhum reparo com síntese semântica disponível ainda)")
            return "\n".join(lines)

        if self.active_contradiction_repair_plan_id > 0:
            lines.append("(reparo em andamento; mostrando leitura semântica parcial)")
            semantic_lines = self._semantic_lines_from_delta(self._current_contradiction_delta_lines(limit=10))
        else:
            semantic_lines = self.last_contradiction_semantic_lines or self._semantic_lines_from_delta(self.last_contradiction_delta_lines)

        if not semantic_lines:
            lines.append("(o reparo ainda não produziu uma leitura semântica acima do limiar)")
            return "\n".join(lines)

        lines.extend(semantic_lines[:6])
        return "\n".join(lines)

    def controlled_return_budget_summary(self) -> str:
        lines = ["ORÇAMENTO DE RETORNO CONTROLADO"]
        if self.current_plan_id <= 0:
            lines.append("(nenhum microplano ativo ainda)")
            return "\n".join(lines)
        lines.append(f"- plano atual: P{self.current_plan_id:03d}")
        lines.append(f"- sondas bloqueadas restantes neste plano: {self.current_plan_return_budget}")
        if self.current_plan_return_budget <= 0:
            lines.append("- novas entradas no contexto bloqueado devem ceder lugar ao resgate fora dele")
        return "\n".join(lines)

    def _probe_exit_leverage(self, lower: str, upper: str) -> float:
        blocked = self._rotation_context_label()
        if blocked is None:
            return 0.0

        leverage = 0.0
        ids = self.env.object_ids()
        for other in ids:
            if other == lower:
                continue

            labels1 = sorted(set(self._top_context_labels(other)))
            if labels1 and blocked not in set(labels1):
                if other == upper:
                    leverage += 0.10
                if lower != other:
                    leverage += 0.06

        for other in ids:
            if other == upper:
                continue

            labels2 = sorted(set(self._top_context_labels(upper)))
            if labels2 and blocked in set(labels2):
                # no blocked reuse here
                continue

        return min(leverage, 0.36)

    def _probe_disagreement_bonus(self, lower: str, upper: str, labels: List[str]) -> float:
        bonus = 0.0
        for label in labels:
            good_conf, poor_conf, ctx_net = self._contextual_net_for_label(lower, label)
            if good_conf >= 0.25 and poor_conf >= 0.25:
                bonus += 0.14
            elif abs(ctx_net) <= 0.12 and max(good_conf, poor_conf) >= 0.25:
                bonus += 0.10

        pos, neg, net, pos_labels, neg_labels, mixed_labels = self._conditional_evidence(lower, upper)
        if mixed_labels:
            bonus += 0.14
        if abs(net) <= 0.18 and (pos >= 0.20 or neg >= 0.20):
            bonus += 0.10
        return min(bonus, 0.42)

    def _probe_strategic_score(self, lower: str, upper: str, labels: List[str]) -> float:
        return_score = self._context_return_score(labels, lower, upper)
        exit_leverage = self._probe_exit_leverage(lower, upper)
        disagreement = self._probe_disagreement_bonus(lower, upper, labels)
        repeat_penalty = self._pair_repeat_penalty(lower, upper)
        family_penalty = self._context_family_penalty(labels)
        return max(
            0.0,
            1.10 * return_score + 0.80 * exit_leverage + 0.90 * disagreement - 0.55 * repeat_penalty - 0.45 * family_penalty
        )

    def _semantic_structure_bonus(self, labels: List[str]) -> float:
        bonus = 0.0
        label_set = set(labels)
        if "with_block_top" in label_set:
            bonus += 0.16
        if "with_stackable_top" in label_set:
            bonus += 0.14
        if "with_nonrolling_top" in label_set:
            bonus += 0.12
        if "with_toy_top" in label_set:
            bonus += 0.05
        if "with_nonstackable_top" in label_set:
            bonus += 0.04
        return min(bonus, 0.36)

    def _semantic_global_ambiguity_bonus(self, lower: str, upper: str, labels: List[str]) -> float:
        blocked = self._rotation_context_label()
        if blocked is None:
            return 0.0

        bonus = 0.0
        for amb_lower, amb_upper, amb_labels, amb_net in self._ambiguous_context_targets():
            amb_set = set(amb_labels)
            if blocked not in amb_set:
                continue
            if amb_lower == lower:
                bonus += 0.14
            if amb_upper == upper:
                bonus += 0.10
            if set(labels).intersection(amb_set):
                bonus += 0.06
            if abs(amb_net) <= 0.18:
                bonus += 0.08
        return min(bonus, 0.34)

    def _semantic_exit_bonus(self, lower: str, upper: str) -> float:
        blocked = self._rotation_context_label()
        if blocked is None:
            return 0.0

        bonus = 0.0
        for cand_lower, cand_upper, score, labels, _reason in self._rotation_rescue_candidates(limit=12):
            label_set = set(labels)
            if blocked in label_set:
                continue
            if cand_lower == lower or cand_upper == lower:
                bonus += 0.10
            if cand_lower == upper or cand_upper == upper:
                bonus += 0.06
        return min(bonus, 0.32)

    def _probe_semantic_tiebreak_score(self, lower: str, upper: str, labels: List[str]) -> float:
        strategic = self._probe_strategic_score(lower, upper, labels)
        structure = self._semantic_structure_bonus(labels)
        ambiguity = self._semantic_global_ambiguity_bonus(lower, upper, labels)
        exit_bonus = self._semantic_exit_bonus(lower, upper)
        return max(
            0.0,
            0.75 * strategic + 0.95 * structure + 1.00 * ambiguity + 0.85 * exit_bonus
        )

    def _probe_justification_text(self, lower: str, upper: str, labels: List[str]) -> str:
        blocked = self._rotation_context_label()
        parts: List[str] = []

        return_score = self._context_return_score(labels, lower, upper)
        strategic = self._probe_strategic_score(lower, upper, labels)
        semantic = self._probe_semantic_tiebreak_score(lower, upper, labels)
        exit_bonus = self._semantic_exit_bonus(lower, upper)

        if blocked is not None and blocked in set(labels):
            parts.append("o eixo bloqueado ainda contém uma ambiguidade que merece toque seletivo")
        if return_score >= 0.30:
            parts.append("o retorno local pode reorganizar uma incerteza relevante")
        elif return_score >= 0.22:
            parts.append("há motivo novo suficiente para revisitar esse ponto")
        if semantic >= 0.90:
            parts.append("esta pergunta parece semanticamente mais esclarecedora do problema inteiro")
        elif semantic >= 0.75:
            parts.append("esta pergunta tem bom valor semântico para reduzir confusão global")
        if strategic >= 0.22:
            parts.append("ela também oferece boa alavanca estratégica")
        if exit_bonus >= 0.18:
            parts.append("e ainda preserva uma saída útil logo depois da sonda")

        if not parts:
            return "sonda escolhida por utilidade integrada moderada"

        first = parts[0]
        rest = parts[1:]
        if not rest:
            return first
        if len(rest) == 1:
            return first + " e " + rest[0]
        return first + ", " + ", ".join(rest[:-1]) + " e " + rest[-1]

    def probe_justification_summary(self) -> str:
        lines = ["JUÍZO JUSTIFICATIVO DE SONDA"]
        blocked = self._rotation_context_label()
        if blocked is None:
            lines.append("(nenhum contexto bloqueado exigindo juízo justificativo)")
            return "\n".join(lines)

        probes = self._strong_context_return_candidates(limit=4)
        if not probes:
            lines.append(f"- {blocked}: sem sonda forte para justificar agora")
            if self.last_justified_probe_judgment:
                lines.append(f"- último juízo registrado: {self.last_justified_probe_judgment}")
            return "\n".join(lines)

        for lower, upper, score, labels, _reason in probes[:4]:
            just = self._probe_justification_text(lower, upper, labels)
            lines.append(f"- {lower} com topo {upper}: {just}")
        return "\n".join(lines)
    def semantic_probe_tiebreak_summary(self) -> str:
        lines = ["DESEMPATADOR SEMÂNTICO DE SONDA"]
        blocked = self._rotation_context_label()
        if blocked is None:
            lines.append("(nenhum contexto bloqueado exigindo desempate semântico)")
            return "\n".join(lines)

        probes = self._strong_context_return_candidates(limit=6)
        if not probes:
            lines.append(f"- {blocked}: sem sondas fortes para desempatar agora")
            memory_line = self._fallback_probe_memory_line()
            if memory_line:
                lines.append(f"- {memory_line}")
            return "\n".join(lines)

        for lower, upper, score, labels, _reason in probes[:6]:
            sem_score = self._probe_semantic_tiebreak_score(lower, upper, labels)
            strategic = self._probe_strategic_score(lower, upper, labels)
            label_text = ", ".join(labels[:3]) if labels else "(sem rótulo)"
            lines.append(f"- {lower} com topo {upper}: semantic={sem_score:.2f} | strategic={strategic:.2f} | {label_text}")
        return "\n".join(lines)
    def strategic_probe_selector_summary(self) -> str:
        lines = ["SELETOR ESTRATÉGICO DE SONDA"]
        blocked = self._rotation_context_label()
        if blocked is None:
            lines.append("(nenhum contexto bloqueado exigindo seletor de sonda)")
            return "\n".join(lines)

        probes = self._strong_context_return_candidates(limit=6)
        if not probes:
            lines.append(f"- {blocked}: sem sonda estratégica forte agora")
            memory_line = self._fallback_probe_memory_line()
            if memory_line:
                lines.append(f"- {memory_line}")
            return "\n".join(lines)

        for lower, upper, score, labels, reason in probes[:6]:
            strategic = self._probe_strategic_score(lower, upper, labels)
            semantic = self._probe_semantic_tiebreak_score(lower, upper, labels)
            label_text = ", ".join(labels[:3]) if labels else "(sem rótulo)"
            lines.append(f"- {lower} com topo {upper}: strategic={strategic:.2f} | semantic={semantic:.2f} | probe={score:.2f} | {label_text}")
        return "\n".join(lines)
    def _rotation_gate_allows(self, labels: List[str]) -> bool:
        blocked = self._rotation_context_label()
        if blocked is None:
            return True
        label_set = set(labels)
        if not label_set:
            return False
        return blocked not in label_set

    def _rotation_hard_permits(self, labels: List[str]) -> bool:
        blocked = self._rotation_context_label()
        if blocked is None:
            return True
        label_set = set(labels)
        if not label_set:
            return False
        return blocked not in label_set

    def _rotation_gate_penalty(self, labels: List[str]) -> float:
        blocked = self._rotation_context_label()
        if blocked is None or not labels:
            return 0.0
        label_set = set(labels)
        if blocked in label_set:
            return 0.60
        return 0.0

    def _infer_streak(self) -> int:
        streak = 0
        for bucket in reversed(self.recent_action_buckets):
            if bucket == "infer":
                streak += 1
            else:
                break
        return streak

    def _best_compare_action(self, phase: str) -> Optional[ActionPlan]:
        ids = self.env.object_ids()
        candidates: List[Tuple[float, ActionPlan]] = []
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                residual = clamp(1.0 - self._comparison_penalty(a, b), 0.02, 1.0)
                sig = f"compare:{a}:{b}"
                score = 0.70 * residual - self._bucket_penalty("compare") - self._signature_penalty(sig)
                candidates.append((
                    score + self.rng.uniform(0.0, 0.03),
                    ActionPlan("compare", a, b, "laboratório: comparação destravadora para evitar infer repetitivo", residual, "compare", phase, sig)
                ))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    def _rotation_rescue_candidates(self, limit: int = 12) -> List[Tuple[str, str, float, List[str], str]]:
        blocked = self._rotation_context_label()
        if blocked is None:
            return []

        ids = self.env.object_ids()
        rows: List[Tuple[float, str, str, List[str], str]] = []

        for lower in ids:
            for upper in ids:
                if lower == upper:
                    continue

                labels = sorted(set(self._top_context_labels(upper)))
                if not labels:
                    continue
                if blocked in set(labels):
                    continue

                hypothesis_residual = clamp(1.0 - self._hypothesis_penalty(lower, upper), 0.0, 1.0)
                stack_residual = clamp(1.0 - self._stack_penalty(lower, upper), 0.0, 1.0)
                repeat_penalty = self._pair_repeat_penalty(lower, upper)
                family_penalty = self._context_family_penalty(labels)

                score = (
                    0.30
                    + 0.28 * hypothesis_residual
                    + 0.22 * stack_residual
                    + 0.18
                    - repeat_penalty
                    - family_penalty
                )

                reason = "resgate de rotação: visitar família fora do contexto bloqueado"
                if repeat_penalty > 0.0:
                    reason += f" | penalização de repetição={repeat_penalty:.2f}"
                if family_penalty > 0.0:
                    reason += f" | penalização de contexto={family_penalty:.2f}"

                rows.append((max(0.05, score), lower, upper, labels, reason))

        rows.sort(key=lambda x: x[0], reverse=True)
        dedup: List[Tuple[str, str, float, List[str], str]] = []
        seen = set()
        for score, lower, upper, labels, reason in rows:
            key = (lower, upper)
            if key in seen:
                continue
            seen.add(key)
            dedup.append((lower, upper, score, labels, reason))
            if len(dedup) >= limit:
                break
        return dedup
    def _build_ambiguity_fallback_queue(self, limit: int = 3) -> List[Tuple[str, str, float, List[str], str]]:
        rescue = self._rotation_rescue_candidates(limit=12)
        probe = self._strong_context_return_candidates(limit=8)

        controlled = self._build_controlled_return_queue(probe, rescue, limit=limit)
        if controlled:
            return controlled

        if rescue:
            queue: List[Tuple[str, str, float, List[str], str]] = []
            used_pairs = set()
            used_labels = set()
            used_lowers = set()
            used_uppers = set()

            for lower, upper, score, labels, reason in rescue:
                if (lower, upper) in used_pairs:
                    continue
                if queue:
                    pair_ok = lower not in used_lowers or upper not in used_uppers
                    label_ok = len(set(labels) - used_labels) > 0
                    if not (pair_ok or label_ok):
                        continue
                queue.append((lower, upper, score, labels, reason))
                used_pairs.add((lower, upper))
                used_lowers.add(lower)
                used_uppers.add(upper)
                used_labels.update(labels)
                if len(queue) >= limit:
                    break

            if len(queue) >= 2:
                self.current_plan_id += 1
                self.current_plan_step_index = 0
                self.current_plan_return_budget = 0
                first_labels = ", ".join(queue[0][3][:3]) if queue[0][3] else "(sem rótulo)"
                self.last_experiment_plan_summary = (
                    f"Plano P{self.current_plan_id:03d} em resgate não-bloqueado com {len(queue)} etapa(s); início em {queue[0][0]} com topo {queue[0][1]} "
                    f"| foco={first_labels} | info inicial={queue[0][2]:.2f}"
                )
                return queue

        targets = self._ambiguous_context_targets()
        if not targets:
            self.last_experiment_plan_summary = ""
            return []

        ids = self.env.object_ids()
        seed_lower, seed_upper, seed_labels, seed_net = targets[0]
        seed_label_set = set(seed_labels)

        candidate_rows: List[Tuple[float, str, str, List[str], str]] = []
        used = set()

        def add_candidate(lower: str, upper: str, labels: List[str], base_reason: str, base_score: float) -> None:
            if lower == upper or (lower, upper) in used:
                return
            repeat_penalty = self._pair_repeat_penalty(lower, upper)
            family_penalty = self._context_family_penalty(labels)
            gate_penalty = self._dominant_context_gate_penalty(labels)
            rotation_penalty = self._rotation_gate_penalty(labels)
            fresh_family_bonus = 0.14 if self._introduces_fresh_context_family(labels) else 0.0
            score = max(0.05, base_score + fresh_family_bonus - repeat_penalty - family_penalty - gate_penalty - rotation_penalty)
            reason = base_reason
            if fresh_family_bonus > 0:
                reason += " | bônus por família contextual fresca"
            if repeat_penalty > 0:
                reason += f" | penalização de repetição={repeat_penalty:.2f}"
            if family_penalty > 0:
                reason += f" | penalização de contexto={family_penalty:.2f}"
            if gate_penalty > 0:
                reason += f" | gating dominante={gate_penalty:.2f}"
            if rotation_penalty > 0:
                reason += f" | rotação obrigatória={rotation_penalty:.2f}"
            candidate_rows.append((score, lower, upper, labels, reason))
            used.add((lower, upper))

        seed_info = 0.52 + (1.0 - min(abs(seed_net), 1.0)) * 0.40
        add_candidate(seed_lower, seed_upper, seed_labels, "fallback ambíguo: sem alternativa fora do contexto bloqueado", seed_info)

        for lower in ids:
            for upper in ids:
                if lower == upper or (lower, upper) == (seed_lower, seed_upper):
                    continue
                pos, neg, net, pos_labels, neg_labels, mixed_labels = self._conditional_evidence(lower, upper)
                labels = sorted(set(mixed_labels if mixed_labels else (pos_labels + neg_labels)))
                if not labels:
                    labels = sorted(set(self._top_context_labels(upper)))

                overlap = len(seed_label_set.intersection(labels))
                if overlap <= 0:
                    continue

                diversity_bonus = 0.0
                if lower != seed_lower:
                    diversity_bonus += 0.12
                if upper != seed_upper:
                    diversity_bonus += 0.12
                if len(set(labels) - seed_label_set) > 0:
                    diversity_bonus += 0.18

                info = 0.42 + overlap * 0.10 + (1.0 - min(abs(net), 1.0)) * 0.20 + diversity_bonus
                add_candidate(lower, upper, labels, "vizinho útil do contexto ambíguo", info)

        candidate_rows.sort(key=lambda x: x[0], reverse=True)

        queue: List[Tuple[str, str, float, List[str], str]] = []
        used_pairs = set()
        used_lowers = set()
        used_uppers = set()
        used_labels = set()

        for score, lower, upper, labels, reason in candidate_rows:
            if (lower, upper) in used_pairs:
                continue
            if queue:
                pair_ok = lower not in used_lowers or upper not in used_uppers
                label_ok = len(set(labels) - used_labels) > 0
                if not (pair_ok or label_ok):
                    continue
            queue.append((lower, upper, score, labels, reason))
            used_pairs.add((lower, upper))
            used_lowers.add(lower)
            used_uppers.add(upper)
            used_labels.update(labels)
            if len(queue) >= limit:
                break

        if len(queue) < 2:
            for score, lower, upper, labels, reason in candidate_rows:
                if (lower, upper) in used_pairs:
                    continue
                queue.append((lower, upper, score, labels, reason))
                used_pairs.add((lower, upper))
                used_labels.update(labels)
                if len(queue) >= 2:
                    break

        if not queue:
            self.last_experiment_plan_summary = ""
            return []

        self.current_plan_id += 1
        self.current_plan_step_index = 0
        self.current_plan_return_budget = 0
        first_labels = ", ".join(queue[0][3][:3]) if queue[0][3] else "(sem rótulo)"
        self.last_experiment_plan_summary = (
            f"Plano P{self.current_plan_id:03d} em exceção ao bloqueio com {len(queue)} etapa(s); início em {queue[0][0]} com topo {queue[0][1]} "
            f"| foco={first_labels} | info inicial={queue[0][2]:.2f}"
        )
        return queue

    def _live_tension_status_closure_deficit(self, status: str) -> float:
        if status == "closed":
            return 0.0
        if status == "maintained":
            return 0.58
        if status == "reopened":
            return 0.82
        if status == "weakened":
            return 0.36
        return 1.0

    def _live_tension_matches(self, lower: str, upper: str, labels: List[str]) -> bool:
        record = self.live_tension_record
        if record is None:
            return False
        if lower in {record.source_lower, record.source_upper} or upper in {record.source_lower, record.source_upper}:
            return True
        return len(set(labels).intersection(record.source_labels)) > 0

    def _open_live_tension_record(self, lower: str, upper: str, predicted: str, observed: str, labels: List[str]) -> None:
        self.live_tension_counter += 1
        self.live_tension_record = LiveTensionRecord(
            tension_id=f"T{self.live_tension_counter:03d}",
            source_lower=lower,
            source_upper=upper,
            source_predicted=predicted,
            source_observed=observed,
            source_labels=labels[:],
            opened_step=self.step_counter,
            status="open",
        )

    def _sync_live_tension_probe_state(self, lower: str, upper: str, score: float, labels: List[str], judgment: str) -> None:
        record = self.live_tension_record
        if record is None:
            return
        if not self._live_tension_matches(lower, upper, labels):
            return
        record.last_probe_lower = lower
        record.last_probe_upper = upper
        record.last_probe_labels = labels[:]
        record.last_probe_score = score
        record.last_probe_judgment = judgment
        record.continuity_lines = self.last_probe_continuity_lines[:]
        if record.status == "closed":
            record.status = "maintained"
        else:
            record.status = "open"
        record.closure_deficit = self._live_tension_status_closure_deficit(record.status)

    def _live_tension_signal(self) -> Tuple[float, List[str]]:
        record = self.live_tension_record
        if record is None:
            return 0.0, ["- nenhuma tensão viva persistente disponível"]
        if record.status == "closed":
            return 0.0, [f"- a tensão {record.tension_id} já recebeu fechamento explícito"]

        age = self.step_counter - record.opened_step
        if age < 0 or age > 36:
            return 0.0, [f"- a tensão {record.tension_id} perdeu calor operativo (idade={age})"]

        age_score = max(0.0, 1.0 - age / 36.0)
        semantic_source = self.last_contradiction_semantic_lines or record.continuity_lines
        semantic_mass = min(1.0, 0.28 * len(semantic_source))
        continuity_mass = 0.42 if (self.last_probe_continuity_lines or record.continuity_lines) else 0.0
        contradiction_mass = 1.0 if record.source_predicted != record.source_observed else 0.45
        blocked_mass = 0.30 if self._rotation_context_label() is not None else 0.0
        closure_deficit = self._live_tension_status_closure_deficit(record.status)

        neighborhood_mass = 0.0
        ambiguity_mass = 0.0
        for lower, upper, labels, net in self._ambiguous_context_targets():
            shared_pair = 1.0 if (lower in {record.source_lower, record.source_upper} or upper in {record.source_lower, record.source_upper}) else 0.0
            shared_labels = len(set(labels).intersection(record.source_labels))
            if shared_pair <= 0.0 and shared_labels <= 0:
                continue
            neighborhood_mass = max(neighborhood_mass, min(1.0, 0.56 * shared_pair + 0.16 * shared_labels))
            ambiguity_mass = max(ambiguity_mass, max(0.0, 0.34 - abs(net)) / 0.34)

        if neighborhood_mass <= 0.0 and self.last_contradiction_semantic_lines:
            neighborhood_mass = 0.40
        if ambiguity_mass <= 0.0 and self.last_contradiction_semantic_lines:
            ambiguity_mass = 0.26

        pressure = (
            0.20 * age_score
            + 0.14 * semantic_mass
            + 0.14 * continuity_mass
            + 0.12 * contradiction_mass
            + 0.16 * neighborhood_mass
            + 0.10 * ambiguity_mass
            + 0.08 * blocked_mass
            + 0.20 * closure_deficit
        )

        record.pressure_snapshot = pressure
        record.closure_deficit = closure_deficit

        lines = [f"- tensão={record.tension_id} | status={record.status} | pressão composta={pressure:.2f}"]
        lines.append(f"- recência operativa={age_score:.2f} | idade={age}")
        lines.append(f"- déficit explícito de fechamento={closure_deficit:.2f}")
        if semantic_mass > 0.0:
            lines.append(f"- herança semântica do reparo={semantic_mass:.2f}")
        if continuity_mass > 0.0:
            lines.append(f"- continuidade narrativa ativa={continuity_mass:.2f}")
        if neighborhood_mass > 0.0:
            lines.append(f"- continuidade de vizinhança={neighborhood_mass:.2f}")
        if ambiguity_mass > 0.0:
            lines.append(f"- ambiguidade local remanescente={ambiguity_mass:.2f}")
        if blocked_mass > 0.0:
            lines.append(f"- pressão extra por gate contextual ativo={blocked_mass:.2f}")
        return pressure, lines[:6]

    def _live_tension_probe_active(self) -> bool:
        pressure, _lines = self._live_tension_signal()
        return pressure >= 0.42

    def _live_tension_probe_justification_text(self, lower: str, upper: str, labels: List[str]) -> str:
        if self.last_contradiction_case is None:
            return "sonda escolhida para continuar uma tensão cognitiva recente"

        pressure, _lines = self._live_tension_signal()
        c_lower, c_upper, predicted, observed, c_labels = self.last_contradiction_case
        parts: List[str] = ["a contradição recente ainda projeta uma tensão cognitiva que pede fechamento mais cedo"]
        if lower in {c_lower, c_upper} or upper in {c_lower, c_upper}:
            parts.append("esta pergunta toca diretamente o bairro relacional do erro")
        elif set(labels).intersection(c_labels):
            parts.append("esta pergunta herda o mesmo eixo contextual do reparo")

        semantic = self._probe_semantic_tiebreak_score(lower, upper, labels)
        strategic = self._probe_strategic_score(lower, upper, labels)
        if pressure >= 0.72:
            parts.append("a pressão viva está alta o bastante para justificar abertura imediata")
        if semantic >= 0.70:
            parts.append("ela parece semanticamente esclarecedora para organizar o caso aberto")
        if strategic >= 0.16:
            parts.append("e oferece boa alavanca para transformar reparo em decisão clara")

        first = parts[0]
        rest = parts[1:]
        if not rest:
            return first
        if len(rest) == 1:
            return first + " e " + rest[0]
        return first + ", " + ", ".join(rest[:-1]) + " e " + rest[-1]

    def _live_tension_probe_candidates(self, limit: int = 8) -> List[Tuple[str, str, float, List[str], str]]:
        pressure, _lines = self._live_tension_signal()
        if pressure < 0.48 or self.last_contradiction_case is None:
            return []

        c_lower, c_upper, predicted, observed, c_labels = self.last_contradiction_case
        ambiguous_rows = self._ambiguous_context_targets()
        ambiguous_map = {(lower, upper): (labels, net) for lower, upper, labels, net in ambiguous_rows}

        ids = self.env.object_ids()
        rows: List[Tuple[float, float, str, str, List[str], str]] = []

        for lower in ids:
            for upper in ids:
                if lower == upper:
                    continue

                pos, neg, net, pos_labels, neg_labels, mixed_labels = self._conditional_evidence(lower, upper)
                labels = sorted(set(mixed_labels if mixed_labels else self._top_context_labels(upper)))
                if not labels:
                    continue

                shared_pair = 0.0
                if lower in {c_lower, c_upper}:
                    shared_pair += 0.18
                if upper in {c_lower, c_upper}:
                    shared_pair += 0.18
                if lower == c_lower and upper == c_upper:
                    shared_pair += 0.12
                if lower == c_upper and upper == c_lower:
                    shared_pair += 0.10

                shared_label_count = len(set(labels).intersection(c_labels))
                shared_label_bonus = 0.08 * shared_label_count

                direct_ambiguity = 0.0
                if (lower, upper) in ambiguous_map:
                    amb_labels, amb_net = ambiguous_map[(lower, upper)]
                    direct_ambiguity += 0.14
                    direct_ambiguity += max(0.0, 0.24 - abs(amb_net))
                    if set(amb_labels).intersection(c_labels):
                        direct_ambiguity += 0.06

                ambiguity = 1.0 - min(abs(net), 1.0)
                ambiguity = max(ambiguity, min(1.0, direct_ambiguity))
                hypothesis_residual = clamp(1.0 - self._hypothesis_penalty(lower, upper), 0.0, 1.0)
                repeat_penalty = self._pair_repeat_penalty(lower, upper)
                family_penalty = self._context_family_penalty(labels)
                gate_penalty = self._dominant_context_gate_penalty(labels)

                strategic = self._probe_strategic_score(lower, upper, labels)
                semantic = self._probe_semantic_tiebreak_score(lower, upper, labels)
                semantic_carry = 0.16 if self.last_contradiction_semantic_lines else 0.0

                relevance = max(shared_pair + shared_label_bonus, direct_ambiguity)
                if relevance < 0.10 and pressure < 0.72:
                    continue
                if ambiguity < 0.16 and hypothesis_residual < 0.20 and relevance < 0.26:
                    continue

                score = (
                    0.10
                    + 0.42 * pressure
                    + 0.28 * ambiguity
                    + 0.16 * hypothesis_residual
                    + 0.22 * strategic
                    + 0.24 * semantic
                    + semantic_carry
                    + shared_pair
                    + shared_label_bonus
                    + 0.24 * direct_ambiguity
                    - 0.75 * repeat_penalty
                    - 0.35 * family_penalty
                    - 0.20 * gate_penalty
                )

                if score < 0.44:
                    continue

                reason = "sonda por tensão viva: contradição recente ainda irradia ambiguidade"
                reason += f" | pressão viva={pressure:.2f}"
                if shared_pair > 0.0:
                    reason += " | bairro relacional do erro"
                if shared_label_bonus > 0.0:
                    reason += " | herança contextual do reparo"
                if direct_ambiguity > 0.0:
                    reason += " | ambiguidade remanescente no entorno"
                if repeat_penalty > 0.0:
                    reason += f" | penalização de repetição={repeat_penalty:.2f}"
                if family_penalty > 0.0:
                    reason += f" | penalização de contexto={family_penalty:.2f}"
                if gate_penalty > 0.0:
                    reason += f" | gating dominante={gate_penalty:.2f}"

                rows.append((score, semantic, lower, upper, labels, reason))

        rows.sort(key=lambda x: (x[0], x[1]), reverse=True)
        dedup: List[Tuple[str, str, float, List[str], str]] = []
        seen = set()
        for score, semantic, lower, upper, labels, reason in rows:
            key = (lower, upper)
            if key in seen:
                continue
            seen.add(key)
            dedup.append((lower, upper, max(0.05, score), labels, reason))
            if len(dedup) >= limit:
                break
        return dedup

    def live_tension_probe_summary(self) -> str:
        lines = ["SONDAS JUSTIFICADAS POR TENSÃO VIVA"]
        pressure, signal_lines = self._live_tension_signal()
        if pressure <= 0.0:
            lines.append("(nenhuma tensão viva recente pedindo sonda independente do bloqueio)")
            return "\n".join(lines)

        lines.extend(signal_lines[:4])
        probes = self._live_tension_probe_candidates(limit=6)
        if not probes:
            lines.append("(a tensão recente existe, mas ainda não gerou sonda forte o bastante)")
            return "\n".join(lines)

        for lower, upper, score, labels, reason in probes[:6]:
            label_text = ", ".join(labels[:3]) if labels else "(sem rótulo)"
            lines.append(f"- {lower} com topo {upper}: probe={score:.2f} | {label_text} | {reason}")
        return "\n".join(lines)

    def _build_live_tension_probe_queue(self, limit: int = 3) -> List[Tuple[str, str, float, List[str], str]]:
        probe_rows = self._live_tension_probe_candidates(limit=8)
        if not probe_rows:
            return []

        probe_lower, probe_upper, probe_score, probe_labels, probe_reason = probe_rows[0]
        judgment = self._live_tension_probe_justification_text(probe_lower, probe_upper, probe_labels)
        self.last_justified_probe = (probe_lower, probe_upper, probe_score, probe_labels[:])
        self.last_justified_probe_judgment = judgment
        self.last_probe_continuity_lines = self._probe_repair_continuity_lines(probe_lower, probe_upper, probe_labels)
        self._sync_live_tension_probe_state(probe_lower, probe_upper, probe_score, probe_labels, judgment)
        self.mark_probe_selected(lower=probe_lower, upper=probe_upper, labels=probe_labels, score=probe_score, judgment=judgment)

        queue: List[Tuple[str, str, float, List[str], str]] = [
            (
                probe_lower,
                probe_upper,
                probe_score,
                probe_labels,
                probe_reason + " | sonda viva 1/1 | juízo: " + judgment
            )
        ]

        used_pairs = {(probe_lower, probe_upper)}
        used_lowers = {probe_lower}
        used_uppers = {probe_upper}
        used_labels = set(probe_labels)

        rescue_rows = self._rotation_rescue_candidates(limit=12)
        plan_rows = self._experimental_plan_targets()
        tail_rows = rescue_rows + [row for row in plan_rows if row not in rescue_rows]

        for lower, upper, score, labels, reason in tail_rows:
            if (lower, upper) in used_pairs:
                continue
            pair_ok = lower not in used_lowers or upper not in used_uppers
            label_ok = len(set(labels) - used_labels) > 0
            if not (pair_ok or label_ok):
                continue
            queue.append((lower, upper, score, labels, reason + " | saída obrigatória após sonda viva"))
            used_pairs.add((lower, upper))
            used_lowers.add(lower)
            used_uppers.add(upper)
            used_labels.update(labels)
            if len(queue) >= limit:
                break

        if len(queue) < 2:
            return []

        self.current_plan_id += 1
        self.current_plan_step_index = 0
        self.current_plan_return_budget = 0
        first_labels = ", ".join(queue[0][3][:3]) if queue[0][3] else "(sem rótulo)"
        self.last_experiment_plan_summary = (
            f"Plano P{self.current_plan_id:03d} (sonda por tensão viva sensível) com {len(queue)} etapa(s); início em {queue[0][0]} com topo {queue[0][1]} "
            f"| foco={first_labels} | info inicial={queue[0][2]:.2f} | fechamento prioritário ativo"
        )
        return queue

    def _strong_context_return_candidates(self, limit: int = 8) -> List[Tuple[str, str, float, List[str], str]]:
        blocked = self._rotation_context_label()
        if blocked is None:
            return []

        ids = self.env.object_ids()
        rows: List[Tuple[float, float, str, str, List[str], str]] = []

        for lower in ids:
            for upper in ids:
                if lower == upper:
                    continue

                labels = sorted(set(self._top_context_labels(upper)))
                if blocked not in set(labels):
                    continue

                return_score = self._context_return_score(labels, lower, upper)
                if return_score < 0.22:
                    continue

                repeat_penalty = self._pair_repeat_penalty(lower, upper)
                family_penalty = self._context_family_penalty(labels)
                hypothesis_residual = clamp(1.0 - self._hypothesis_penalty(lower, upper), 0.0, 1.0)
                strategic_score = self._probe_strategic_score(lower, upper, labels)
                semantic_score = self._probe_semantic_tiebreak_score(lower, upper, labels)

                score = max(
                    0.14,
                    0.22 + 0.55 * semantic_score + 0.25 * strategic_score + 0.14 * hypothesis_residual
                )

                reason = "retorno contextual oportuno: nova evidência justifica revisita seletiva"
                reason += f" | seletor estratégico={strategic_score:.2f}"
                reason += f" | desempate semântico={semantic_score:.2f}"
                if repeat_penalty > 0.0:
                    reason += f" | penalização de repetição={repeat_penalty:.2f}"
                if family_penalty > 0.0:
                    reason += f" | penalização de contexto={family_penalty:.2f}"

                rows.append((score, semantic_score, lower, upper, labels, reason))

        rows.sort(key=lambda x: (x[0], x[1]), reverse=True)
        dedup: List[Tuple[str, str, float, List[str], str]] = []
        seen = set()
        for score, semantic_score, lower, upper, labels, reason in rows:
            key = (lower, upper)
            if key in seen:
                continue
            seen.add(key)
            dedup.append((lower, upper, score, labels, reason))
            if len(dedup) >= limit:
                break
        return dedup
    def _build_controlled_return_queue(
        self,
        probe_rows: List[Tuple[str, str, float, List[str], str]],
        rescue_rows: List[Tuple[str, str, float, List[str], str]],
        limit: int = 3,
    ) -> List[Tuple[str, str, float, List[str], str]]:
        if not probe_rows or len(rescue_rows) < 1:
            return []

        probe_lower, probe_upper, probe_score, probe_labels, probe_reason = probe_rows[0]
        judgment = self._probe_justification_text(probe_lower, probe_upper, probe_labels)
        self.last_justified_probe = (probe_lower, probe_upper, probe_score, probe_labels[:])
        self.last_justified_probe_judgment = judgment
        self.last_probe_continuity_lines = self._probe_repair_continuity_lines(probe_lower, probe_upper, probe_labels)
        self._sync_live_tension_probe_state(probe_lower, probe_upper, probe_score, probe_labels, judgment)
        self.mark_probe_selected(lower=probe_lower, upper=probe_upper, labels=probe_labels, score=probe_score, judgment=judgment)

        queue: List[Tuple[str, str, float, List[str], str]] = [
            (
                probe_lower,
                probe_upper,
                probe_score,
                probe_labels,
                probe_reason + " | sonda 1/1 | escolhida pelo desempatador semântico | juízo: " + judgment
            )
        ]
        used_pairs = {(probe_lower, probe_upper)}
        used_lowers = {probe_lower}
        used_uppers = {probe_upper}
        used_labels = set(probe_labels)

        blocked = self._rotation_context_label()

        for lower, upper, score, labels, reason in rescue_rows:
            if (lower, upper) in used_pairs:
                continue
            if blocked is not None and blocked in set(labels):
                continue
            pair_ok = lower not in used_lowers or upper not in used_uppers
            label_ok = len(set(labels) - used_labels) > 0
            if not (pair_ok or label_ok):
                continue
            queue.append((lower, upper, score, labels, reason + " | saída obrigatória após sonda"))
            used_pairs.add((lower, upper))
            used_lowers.add(lower)
            used_uppers.add(upper)
            used_labels.update(labels)
            if len(queue) >= limit:
                break

        if len(queue) < 2:
            return []

        self.current_plan_id += 1
        self.current_plan_step_index = 0
        self.current_plan_return_budget = 1
        first_labels = ", ".join(queue[0][3][:3]) if queue[0][3] else "(sem rótulo)"
        self.last_experiment_plan_summary = (
            f"Plano P{self.current_plan_id:03d} (retorno controlado) com {len(queue)} etapa(s); início em {queue[0][0]} com topo {queue[0][1]} "
            f"| foco={first_labels} | info inicial={queue[0][2]:.2f} | orçamento de sonda=1 | memória justificativa ativa"
        )
        return queue
    def _build_session_boot_queue(self, limit: int = 3) -> List[Tuple[str, str, float, List[str], str]]:
        if not self._session_boot_active():
            return []

        base_targets = self._experimental_plan_targets()
        if not base_targets:
            return []

        recent_primary = self._boot_recent_primary_families(8)
        seen_primary = set(recent_primary)

        candidates: List[Tuple[float, str, str, float, List[str], str, str]] = []
        for lower, upper, info_score, labels, reason in base_targets:
            primary = self._boot_primary_family(labels)

            family_gain = 0.0
            if primary == "with_nonrolling_top" and "with_nonrolling_top" not in seen_primary:
                family_gain += 0.72
            elif primary not in seen_primary:
                family_gain += 0.34

            # bônus para abrir contraste estrutural fora do eixo rolling puro
            if any(label in {"with_block_top", "with_nonrolling_top", "with_stackable_top"} for label in labels):
                family_gain += 0.18

            # penaliza forte rolling cedo demais, especialmente sem nonrolling_top já visto
            if primary == "with_rolling_top" and "with_nonrolling_top" not in seen_primary:
                family_gain -= 0.48

            boot_pressure = self._boot_label_pressure(labels)
            pair_pressure = self._boot_pair_pressure(lower, upper)
            score = info_score + family_gain - boot_pressure - pair_pressure

            boot_reason = reason
            if family_gain != 0:
                boot_reason += f" | boot por famílias={family_gain:.2f}"
            if boot_pressure > 0:
                boot_reason += f" | pressão de família inicial={boot_pressure:.2f}"
            if pair_pressure > 0:
                boot_reason += f" | pressão de repetição inicial={pair_pressure:.2f}"

            candidates.append((score, lower, upper, info_score, labels, boot_reason, primary))

        candidates.sort(key=lambda x: x[0], reverse=True)
        if not candidates:
            return []

        queue: List[Tuple[str, str, float, List[str], str]] = []
        used_pairs = set()
        used_labels = set()
        used_lowers = set()
        used_uppers = set()
        used_primary = set()

        for _score, lower, upper, info_score, labels, reason, primary in candidates:
            if (lower, upper) in used_pairs:
                continue

            # exigir contraste de família primária quando possível
            if queue and primary in used_primary:
                alternatives_exist = any(
                    p2 not in used_primary and (l2, u2) not in used_pairs
                    for _s2, l2, u2, _i2, _lab2, _r2, p2 in candidates
                )
                if alternatives_exist:
                    continue

            if queue:
                pair_ok = lower not in used_lowers or upper not in used_uppers
                label_ok = len(set(labels) - used_labels) > 0
                if not (pair_ok or label_ok):
                    continue

            queue.append((lower, upper, info_score, labels, reason))
            used_pairs.add((lower, upper))
            used_lowers.add(lower)
            used_uppers.add(upper)
            used_labels.update(labels)
            used_primary.add(primary)
            if len(queue) >= limit:
                break

        if len(queue) < 2:
            return []

        self.current_plan_id += 1
        self.current_plan_step_index = 0
        self.current_plan_return_budget = 0
        first_labels = ", ".join(queue[0][3][:3]) if queue[0][3] else "(sem rótulo)"
        self.last_experiment_plan_summary = (
            f"Plano P{self.current_plan_id:03d} (boot por famílias) com {len(queue)} etapa(s); início em {queue[0][0]} com topo {queue[0][1]} "
            f"| foco={first_labels} | info inicial={queue[0][2]:.2f}"
        )
        return queue
    def _build_experiment_queue(self, limit: int = 3) -> List[Tuple[str, str, float, List[str], str]]:
        boot_queue = self._build_session_boot_queue(limit=limit)
        if boot_queue:
            return boot_queue

        contradiction_queue = self._build_contradiction_repair_queue(limit=limit)
        if contradiction_queue:
            return contradiction_queue

        live_tension_queue = self._build_live_tension_probe_queue(limit=limit)
        if live_tension_queue:
            return live_tension_queue

        plans = self._experimental_plan_targets()
        rescue = self._rotation_rescue_candidates(limit=12)
        probe = self._strong_context_return_candidates(limit=8)

        controlled = self._build_controlled_return_queue(probe, rescue, limit=limit)
        if controlled:
            return controlled

        if rescue:
            candidate_pool = rescue
            mode_tag = "rotação binária"
        else:
            if not plans:
                return self._build_ambiguity_fallback_queue(limit=limit)
            candidate_pool = plans
            mode_tag = "sem alternativa"

        filtered = []
        for lower, upper, info_score, labels, reason in candidate_pool:
            if not self._recent_pair_was_tested(lower, upper):
                filtered.append((lower, upper, info_score, labels, reason))

        if len(filtered) < 2:
            filtered = candidate_pool[:]

        if not filtered:
            return self._build_ambiguity_fallback_queue(limit=limit)

        seed_lower, seed_upper, seed_info, seed_labels, seed_reason = filtered[0]
        queue: List[Tuple[str, str, float, List[str], str]] = [(seed_lower, seed_upper, seed_info, seed_labels, seed_reason)]
        used = {(seed_lower, seed_upper)}
        used_lowers = {seed_lower}
        used_uppers = {seed_upper}
        used_labels = set(seed_labels)
        seed_label_set = set(seed_labels)

        for lower, upper, info_score, labels, reason in filtered[1:]:
            if (lower, upper) in used:
                continue
            label_overlap = len(seed_label_set.intersection(labels))
            diverse_pair = lower not in used_lowers or upper not in used_uppers
            diverse_label = len(set(labels) - used_labels) > 0
            if label_overlap > 0 and (diverse_pair or diverse_label):
                queue.append((lower, upper, info_score, labels, reason))
                used.add((lower, upper))
                used_lowers.add(lower)
                used_uppers.add(upper)
                used_labels.update(labels)
            if len(queue) >= limit:
                break

        if len(queue) < 2:
            for lower, upper, info_score, labels, reason in filtered[1:]:
                if (lower, upper) in used:
                    continue
                if lower in used_lowers and upper in used_uppers and len(set(labels) - used_labels) == 0:
                    continue
                queue.append((lower, upper, info_score, labels, reason))
                used.add((lower, upper))
                used_lowers.add(lower)
                used_uppers.add(upper)
                used_labels.update(labels)
                if len(queue) >= limit:
                    break

        if len(queue) < 2:
            return self._build_ambiguity_fallback_queue(limit=limit)

        self.current_plan_id += 1
        self.current_plan_step_index = 0
        self.current_plan_return_budget = 0
        first_labels = ", ".join(queue[0][3][:3]) if queue[0][3] else "(sem rótulo)"
        self.last_experiment_plan_summary = (
            f"Plano P{self.current_plan_id:03d} ({mode_tag}) com {len(queue)} etapa(s) distintas; início em {queue[0][0]} com topo {queue[0][1]} "
            f"| foco={first_labels} | info inicial={queue[0][2]:.2f}"
        )
        return queue
    def _next_plan_predict_action(self, phase: str) -> Optional[ActionPlan]:
        if not self.experiment_queue:
            return None
        lower, upper, info_score, labels, reason = self.experiment_queue.pop(0)
        self.current_plan_step_index += 1
        if "sonda 1/1" in reason and self.current_plan_return_budget > 0:
            self.current_plan_return_budget -= 1
        self._record_plan_pair(lower, upper)
        self._record_plan_labels(labels)
        residual = clamp(1.0 - self._hypothesis_penalty(lower, upper), 0.08, 1.0)
        sig = f"predict:{lower}:{upper}"
        label_text = ", ".join(labels[:3]) if labels else "contexto experimental"
        prefix = "iniciar" if self.current_plan_step_index == 1 else "seguir"
        explanation = (
            f"laboratório: {prefix} microplano P{self.current_plan_id:03d} "
            f"(etapa {self.current_plan_step_index}; {label_text}; {reason}; info={info_score:.2f})"
        )
        return ActionPlan("predict", lower, upper, explanation, residual, "predict", phase, sig)

    def _ambiguous_context_targets(self) -> list[tuple[str, str, list[str], float]]:
        targets: list[tuple[float, str, str, list[str], float]] = []
        ids = self.env.object_ids()

        for lower in ids:
            for upper in ids:
                if lower == upper:
                    continue
                pos, neg, net, pos_labels, neg_labels, mixed_labels = self._conditional_evidence(lower, upper)
                labels = sorted(set(mixed_labels))
                if not labels and abs(net) <= 0.10 and (pos > 0.25 or neg > 0.25):
                    labels = sorted(set(pos_labels + neg_labels))

                if not labels:
                    continue

                priority = 1.0 - min(abs(net), 1.0)
                if "with_rolling_top" in labels:
                    priority += 0.35
                if "with_nonstackable_top" in labels:
                    priority += 0.10
                targets.append((priority, lower, upper, labels, net))

        targets.sort(key=lambda x: x[0], reverse=True)
        final_targets: list[tuple[str, str, list[str], float]] = []
        seen = set()
        for _priority, lower, upper, labels, net in targets:
            key = (lower, upper)
            if key in seen:
                continue
            seen.add(key)
            final_targets.append((lower, upper, labels, net))
        return final_targets

    def _experimental_plan_targets(self) -> list[tuple[str, str, float, list[str], str]]:
        targets: list[tuple[float, str, str, list[str], str]] = []
        ids = self.env.object_ids()

        for lower in ids:
            for upper in ids:
                if lower == upper:
                    continue

                pos, neg, net, pos_labels, neg_labels, mixed_labels = self._conditional_evidence(lower, upper)
                label_set = sorted(set(self._top_context_labels(upper)))
                hypothesis_residual = clamp(1.0 - self._hypothesis_penalty(lower, upper), 0.0, 1.0)
                stack_residual = clamp(1.0 - self._stack_penalty(lower, upper), 0.0, 1.0)

                if hypothesis_residual < 0.05 and stack_residual < 0.05 and abs(net) > 0.35:
                    continue

                ambiguity = 1.0 - min(abs(net), 1.0)
                local_bonus = 0.0
                unresolved_labels: list[str] = []

                for label in label_set:
                    good_conf, poor_conf, ctx_net = self._contextual_net_for_label(lower, label)
                    if max(good_conf, poor_conf) < 0.25 or abs(ctx_net) < 0.18:
                        local_bonus += 0.18
                        unresolved_labels.append(label)
                    if label == "with_rolling_top":
                        local_bonus += 0.12
                    if label == "with_toy_top":
                        local_bonus += 0.06

                if mixed_labels:
                    local_bonus += 0.15
                    unresolved_labels.extend(mixed_labels)

                labels = sorted(set(unresolved_labels if unresolved_labels else label_set))
                repeat_penalty = self._pair_repeat_penalty(lower, upper)
                family_penalty = self._context_family_penalty(labels)
                gate_penalty = self._dominant_context_gate_penalty(labels)
                rotation_penalty = self._rotation_gate_penalty(labels)
                fresh_family_bonus = 0.14 if self._introduces_fresh_context_family(labels) else 0.0
                rotation_bonus = 0.22 if self._rotation_gate_allows(labels) and self._rotation_context_label() is not None and self._rotation_context_label() not in set(labels) else 0.0

                info_score = (
                    0.40 * ambiguity
                    + 0.32 * hypothesis_residual
                    + 0.20 * stack_residual
                    + local_bonus
                    + fresh_family_bonus
                    + rotation_bonus
                    - repeat_penalty
                    - family_penalty
                    - gate_penalty
                    - rotation_penalty
                )

                tension_bonus, tension_probe, tension_note = self.tension_bonus_for_candidate(
                    lower=lower,
                    upper=upper,
                    labels=labels,
                    raw_info_gain=max(0.05, info_score),
                )
                info_score += tension_bonus

                if mixed_labels:
                    reason = "resolver conflito local e aumentar cobertura"
                elif labels and any(label in {"with_rolling_top", "with_toy_top"} for label in labels):
                    reason = "contexto ainda sensível e potencialmente informativo"
                elif ambiguity > 0.55:
                    reason = "alto ganho por reduzir incerteza contextual"
                else:
                    reason = "boa oportunidade de consolidar regra útil"

                if fresh_family_bonus > 0.0:
                    reason += " | bônus por família contextual fresca"
                if rotation_bonus > 0.0:
                    reason += " | bônus por rotação contextual"
                if repeat_penalty > 0.0:
                    reason += f" | penalização de repetição={repeat_penalty:.2f}"
                if family_penalty > 0.0:
                    reason += f" | penalização de contexto={family_penalty:.2f}"
                if gate_penalty > 0.0:
                    reason += f" | gating dominante={gate_penalty:.2f}"
                if rotation_penalty > 0.0:
                    reason += f" | rotação obrigatória={rotation_penalty:.2f}"
                if tension_bonus > 0.0:
                    reason += f" | bônus de tensão viva={tension_bonus:.2f}"
                    if tension_probe:
                        reason += " | puxado pela tensão ativa"
                    if tension_note:
                        reason += " | " + tension_note

                targets.append((info_score, lower, upper, labels, reason))

        targets.sort(key=lambda x: x[0], reverse=True)
        final_targets: list[tuple[str, str, float, list[str], str]] = []
        seen = set()
        for info_score, lower, upper, labels, reason in targets:
            key = (lower, upper)
            if key in seen:
                continue
            seen.add(key)
            final_targets.append((lower, upper, max(0.05, info_score), labels, reason))
        return final_targets
    def rules_summary(self) -> str:
        lines = ["REGRAS GENERALIZADAS"]
        rules = []
        for key, node in sorted(self.memory.nodes.items()):
            if key.startswith("rule:") and node.confidence >= 0.30:
                rules.append(f"- {key} [conf={node.confidence:.2f}]")
        if not rules:
            lines.append("(nenhuma regra generalizada ainda)")
        else:
            lines.extend(rules[:24])
        return "\n".join(lines)

    def propose_hypothesis(self, lower_id: str, upper_id: str) -> NurseryActionResult:
        self.hypothesis_counter += 1

        lower_good = self.memory.confidence_of_prefix(f"rule:base_profile:{lower_id}:good") > 0.30
        lower_poor = self.memory.confidence_of_prefix(f"rule:base_profile:{lower_id}:poor") > 0.30
        lower_support = self.memory.confidence_of_prefix(f"obj:{lower_id}:affordance:suporta_empilhar") > 0.30

        upper_empilhavel = self.memory.confidence_of_prefix(f"obj:{upper_id}:affordance:empilhavel") > 0.30
        upper_nonstack = self.memory.confidence_of_prefix(f"rule:top_profile:{upper_id}:non_stackable") > 0.30

        lower_roll = self.memory.confidence_of_prefix(f"obj:{lower_id}:affordance:rola") > 0.30
        base_conflict = lower_good and lower_poor

        cond_pos, cond_neg, cond_net, pos_labels, neg_labels, mixed_labels = self._conditional_evidence(lower_id, upper_id)

        predicted = "uncertain"
        basis = "evidência insuficiente"
        cause_focus = "pair"

        if mixed_labels and abs(cond_net) < 0.12:
            predicted = "uncertain"
            basis = "contexto ambíguo prioritário: " + ", ".join(sorted(set(mixed_labels))[:3])
            cause_focus = "pair"
        elif cond_net > 0.12 and cond_pos > 0.30:
            predicted = "stable"
            basis = "saldo contextual favorável: " + ", ".join(sorted(set(pos_labels))[:3])
            cause_focus = "pair"
        elif cond_net < -0.12 and cond_neg > 0.30:
            predicted = "unstable"
            basis = "saldo contextual desfavorável: " + ", ".join(sorted(set(neg_labels))[:3])
            cause_focus = "pair"
        elif cond_pos > 0.30 and cond_neg > 0.30:
            predicted = "uncertain"
            basis = "regras condicionais conflitantes neste contexto; precisa de desambiguação"
            cause_focus = "pair"
        elif upper_nonstack:
            predicted = "unstable"
            basis = "topo já marcado como não empilhável"
            cause_focus = "top"
        elif not upper_empilhavel:
            predicted = "uncertain"
            basis = "topo sem evidência suficiente de ser empilhável; investigar antes de concluir falha"
            cause_focus = "top"
        elif base_conflict and upper_empilhavel:
            predicted = "uncertain"
            basis = "base com regras conflitantes, mas topo parece compatível"
            cause_focus = "base"
        elif lower_poor:
            predicted = "unstable"
            basis = "base já marcada como ruim"
            cause_focus = "base"
        elif (lower_good or lower_support) and upper_empilhavel:
            predicted = "stable"
            basis = "base boa ou suporte conhecido + topo empilhável"
            cause_focus = "pair"
        elif lower_roll and not lower_support:
            predicted = "unstable"
            basis = "base rola e não há evidência de suporte"
            cause_focus = "base"
        elif lower_support and upper_empilhavel:
            predicted = "stable"
            basis = "suporte conhecido da base + topo compatível"
            cause_focus = "pair"
        else:
            predicted = "uncertain"
            basis = "hipótese conservadora por ausência de suporte suficiente"
            cause_focus = "pair"

        hyp = PendingHypothesis(
            hypothesis_id=f"H{self.hypothesis_counter:03d}",
            lower_id=lower_id,
            upper_id=upper_id,
            predicted_outcome=predicted,
            basis=basis,
            confidence_hint=0.58 if predicted != "uncertain" else 0.30,
            cause_focus=cause_focus,
        )
        self.pending_hypotheses.append(hyp)

        learned = [
            f"hypothesis:{lower_id}>{upper_id}:predicted:{predicted}=true",
            f"hypothesis:{lower_id}>{upper_id}:basis:{basis}=true",
            f"hypothesis:{lower_id}>{upper_id}:cause_focus:{cause_focus}=true",
        ]
        summary = f"Propôs hipótese {hyp.hypothesis_id}: {upper_id} sobre {lower_id} tende a resultar em {predicted}."
        return NurseryActionResult(True, summary, 0.68, 0.26, 0.04, 0.58, learned)

    def validate_oldest_hypothesis(self) -> NurseryActionResult:
        if not self.pending_hypotheses:
            return NurseryActionResult(True, "Não havia hipótese pendente para validar.", 0.10, 0.04, 0.03, 0.08, [])

        hyp = self.pending_hypotheses.pop(0)
        stack_result = self.env.try_stack(hyp.lower_id, hyp.upper_id)
        observed = "stable" if stack_result.success else "unstable"
        observed_cause = self._infer_observed_cause(hyp.lower_id, hyp.upper_id, observed)
        match = hyp.predicted_outcome == observed

        learned = list(stack_result.learned)
        learned.append(f"hypothesis:{hyp.lower_id}>{hyp.upper_id}:validated:{observed}=true")
        learned.append(f"hypothesis:{hyp.lower_id}>{hyp.upper_id}:observed_cause:{observed_cause}=true")

        base_good = f"rule:base_profile:{hyp.lower_id}:good"
        base_poor = f"rule:base_profile:{hyp.lower_id}:poor"
        top_good = f"rule:top_profile:{hyp.upper_id}:stackable"
        top_poor = f"rule:top_profile:{hyp.upper_id}:non_stackable"
        pair_good = f"rule:pair_profile:{hyp.lower_id}>{hyp.upper_id}:compatible"
        pair_poor = f"rule:pair_profile:{hyp.lower_id}>{hyp.upper_id}:incompatible"
        cond_pairs = self._conditional_key_pairs(hyp.lower_id, hyp.upper_id)

        def adjust_context_rules(stable: bool) -> None:
            for cond_good, cond_poor, _label in cond_pairs:
                if stable:
                    self._adjust_and_persist(cond_good, 0.14)
                    self._adjust_and_persist(cond_poor, -0.08)
                else:
                    self._adjust_and_persist(cond_poor, 0.14)
                    self._adjust_and_persist(cond_good, -0.08)

        if hyp.predicted_outcome == "uncertain":
            learned.append(f"hypothesis:{hyp.lower_id}>{hyp.upper_id}:match:refined=true")
            if observed == "stable":
                self._adjust_and_persist(pair_good, 0.14)
                self._adjust_and_persist(pair_poor, -0.06)
                adjust_context_rules(True)
                if observed_cause == "pair":
                    self._adjust_and_persist(base_good, 0.04)
                    self._adjust_and_persist(top_good, 0.04)
                elif observed_cause == "base":
                    self._adjust_and_persist(base_good, 0.08)
                elif observed_cause == "top":
                    self._adjust_and_persist(top_good, 0.08)
                summary = f"Validou {hyp.hypothesis_id}: previsão cautelosa refinada para stable."
                utility = 0.82
                info_gain = 0.90
                conflict = 0.12
            else:
                self._adjust_and_persist(pair_poor, 0.14)
                self._adjust_and_persist(pair_good, -0.06)
                adjust_context_rules(False)
                if observed_cause == "base":
                    self._adjust_and_persist(base_poor, 0.08)
                elif observed_cause == "top":
                    self._adjust_and_persist(top_poor, 0.08)
                else:
                    self._adjust_and_persist(pair_poor, 0.05)
                summary = f"Validou {hyp.hypothesis_id}: previsão cautelosa refinada para unstable."
                utility = 0.82
                info_gain = 0.90
                conflict = 0.12

        elif match:
            learned.append(f"hypothesis:{hyp.lower_id}>{hyp.upper_id}:match:true=true")
            if observed == "stable":
                learned.append(f"rule_validation:{hyp.lower_id}>{hyp.upper_id}:pair_good:confirmed=true")
                self._adjust_and_persist(pair_good, 0.16)
                self._adjust_and_persist(pair_poor, -0.08)
                adjust_context_rules(True)
                if observed_cause == "base":
                    self._adjust_and_persist(base_good, 0.10)
                    self._adjust_and_persist(base_poor, -0.05)
                elif observed_cause == "top":
                    self._adjust_and_persist(top_good, 0.10)
                    self._adjust_and_persist(top_poor, -0.05)
                else:
                    self._adjust_and_persist(base_good, 0.04)
                    self._adjust_and_persist(top_good, 0.04)
            else:
                learned.append(f"rule_validation:{hyp.lower_id}>{hyp.upper_id}:pair_poor:confirmed=true")
                self._adjust_and_persist(pair_poor, 0.16)
                self._adjust_and_persist(pair_good, -0.08)
                adjust_context_rules(False)
                if observed_cause == "base":
                    self._adjust_and_persist(base_poor, 0.10)
                    self._adjust_and_persist(base_good, -0.05)
                elif observed_cause == "top":
                    self._adjust_and_persist(top_poor, 0.10)
                    self._adjust_and_persist(top_good, -0.05)
                else:
                    self._adjust_and_persist(pair_poor, 0.05)
            summary = f"Validou {hyp.hypothesis_id}: previsão confirmada. Previsto={hyp.predicted_outcome}, observado={observed}."
            utility = 1.02
            info_gain = 0.94
            conflict = 0.05 if stack_result.success else 0.18

        else:
            learned.append(f"hypothesis:{hyp.lower_id}>{hyp.upper_id}:match:false=true")
            learned.append(f"rule_validation:{hyp.lower_id}>{hyp.upper_id}:contradiction=true")
            self.last_contradiction_case = (
                hyp.lower_id,
                hyp.upper_id,
                hyp.predicted_outcome,
                observed,
                sorted(set(self._top_context_labels(hyp.upper_id))),
            )
            self.contradiction_repair_budget = 1
            self.last_contradiction_delta_lines = []
            self.last_contradiction_semantic_lines = []
            self.last_probe_continuity_lines = []
            self.last_tension_outcome_lines = []
            self.last_contradiction_step = self.step_counter
            contradiction_labels = sorted(set(self._top_context_labels(hyp.upper_id)))
            self._open_live_tension_record(
                hyp.lower_id,
                hyp.upper_id,
                hyp.predicted_outcome,
                observed,
                contradiction_labels,
            )
            inherited_pairs = [f"{hyp.lower_id}>{hyp.upper_id}"]
            if self.last_justified_probe is not None:
                inherited_pairs.append(f"{self.last_justified_probe[0]}>{self.last_justified_probe[1]}")
            semantic_summary = f"contradição em {hyp.lower_id}>{hyp.upper_id}: previsto={hyp.predicted_outcome}, observado={observed}"
            self.register_tension_from_contradiction(
                lower=hyp.lower_id,
                upper=hyp.upper_id,
                predicted=hyp.predicted_outcome,
                observed=observed,
                context_families=contradiction_labels,
                semantic_summary=semantic_summary,
                inherited_pairs=inherited_pairs,
                magnitude=1.0,
            )
            if hyp.predicted_outcome == "stable":
                self._adjust_and_persist(pair_good, -0.18)
                self._adjust_and_persist(pair_poor, 0.10)
                adjust_context_rules(False)
                if observed_cause == "base":
                    self._adjust_and_persist(base_good, -0.10)
                    self._adjust_and_persist(base_poor, 0.10)
                elif observed_cause == "top":
                    self._adjust_and_persist(top_good, -0.14)
                    self._adjust_and_persist(top_poor, 0.12)
                    self._adjust_and_persist(base_poor, -0.04)
                else:
                    self._adjust_and_persist(base_good, -0.03)
                    self._adjust_and_persist(top_good, -0.03)
            elif hyp.predicted_outcome == "unstable":
                self._adjust_and_persist(pair_poor, -0.18)
                self._adjust_and_persist(pair_good, 0.10)
                adjust_context_rules(True)
                if observed_cause == "base":
                    self._adjust_and_persist(base_poor, -0.12)
                    self._adjust_and_persist(base_good, 0.08)
                elif observed_cause == "top":
                    self._adjust_and_persist(top_poor, -0.14)
                    self._adjust_and_persist(top_good, 0.12)
                    self._adjust_and_persist(base_poor, -0.03)
                else:
                    self._adjust_and_persist(base_good, 0.05)
                    self._adjust_and_persist(top_good, 0.05)
            self.last_contradiction_baseline = self._capture_contradiction_baseline(
                hyp.lower_id,
                hyp.upper_id,
                sorted(set(self._top_context_labels(hyp.upper_id))),
            )
            summary = f"Validou {hyp.hypothesis_id}: previsão falhou. Previsto={hyp.predicted_outcome}, observado={observed}."
            utility = 0.46
            info_gain = 0.96
            conflict = 0.56

        self._arbitrate_conflict(base_good, base_poor)
        self._arbitrate_conflict(top_good, top_poor)
        self._arbitrate_conflict(pair_good, pair_poor)
        self._update_tension_outcome_after_probe_validation(hyp.lower_id, hyp.upper_id, observed)
        self.finalize_probe_validation(lower=hyp.lower_id, upper=hyp.upper_id, observed=observed)
        self.refresh_tension_economy(candidate_pairs=[f"{hyp.lower_id}>{hyp.upper_id}"])
        for cond_good, cond_poor, _label in cond_pairs:
            self._arbitrate_conflict(cond_good, cond_poor)

        return NurseryActionResult(True, summary, utility, 0.30, conflict, info_gain, learned)

    def hypotheses_summary(self) -> str:
        lines = ["HIPÓTESES"]
        if not self.pending_hypotheses:
            lines.append("(nenhuma hipótese pendente)")
            return "\n".join(lines)
        for hyp in self.pending_hypotheses[:12]:
            lines.append(f"- {hyp.hypothesis_id}: {hyp.upper_id} sobre {hyp.lower_id} -> {hyp.predicted_outcome} | base={hyp.basis}")
        return "\n".join(lines)

    def _pending_probe_hypothesis(self) -> Optional[PendingHypothesis]:
        if not self.pending_hypotheses or self.last_justified_probe is None:
            return None
        probe_lower, probe_upper, _score, _labels = self.last_justified_probe
        for hyp in self.pending_hypotheses:
            if hyp.lower_id == probe_lower and hyp.upper_id == probe_upper:
                return hyp
        return None

    def probe_closure_priority_summary(self) -> str:
        lines = ["FECHAMENTO PRIORITÁRIO DA SONDA"]
        hyp = self._pending_probe_hypothesis()
        if hyp is None:
            lines.append("(nenhuma sonda justificada pendente exigindo fechamento imediato)")
            return "\n".join(lines)
        lines.append(f"- validação protegida ativa: {hyp.lower_id} com topo {hyp.upper_id}")
        lines.append("- a consolidação deve esperar o fechamento do desfecho desta sonda")
        return "\n".join(lines)


    # --------------------------
    # compromisso executivo v47.6
    # --------------------------

    def _v47_6_make_action_plan(
        self,
        *,
        action_name: str,
        lower: str,
        upper: Optional[str],
        explanation: str,
        novelty_residual: float,
        bucket: str,
        phase: str,
        signature: str,
    ) -> "ActionPlan":
        # Cria ActionPlan de forma compatível com a dataclass atual.
        try:
            from dataclasses import fields as dataclass_fields

            values = {
                "action_name": action_name,
                "target_a": lower,
                "target_b": upper,
                "explanation": explanation,
                "novelty_residual": novelty_residual,
                "curriculum_bucket": bucket,
                "lesson_phase": phase,
                "signature": signature,
            }
            kwargs = {}
            for field in dataclass_fields(ActionPlan):
                if field.name in values:
                    kwargs[field.name] = values[field.name]
                elif field.default is not field.default_factory:
                    kwargs[field.name] = field.default
                else:
                    kwargs[field.name] = None
            return ActionPlan(**kwargs)
        except Exception:
            return ActionPlan(action_name, lower, upper, explanation, novelty_residual, bucket, phase, signature)

    def _v47_6_pending_hypothesis_for_pair(self, lower: str, upper: str) -> Optional["PendingHypothesis"]:
        for hyp in list(getattr(self, "pending_hypotheses", [])):
            if getattr(hyp, "lower_id", None) == lower and getattr(hyp, "upper_id", None) == upper:
                return hyp
        return None

    def _v47_6_case_is_actionable(self, case: "LiveTensionCase") -> bool:
        if case is None:
            return False
        if case.status in {TensionStatus.CLOSED, TensionStatus.ARCHIVED, TensionStatus.STALE}:
            return False
        if float(getattr(case, "closure_deficit", 0.0) or 0.0) <= 0.05:
            return False
        return True

    def _v47_6_mark_commitment_probe_if_needed(self, case: "LiveTensionCase") -> None:
        already_probe = (
            case.status == TensionStatus.PROBING
            and case.last_probe_pair == case.source_pair
        )
        if already_probe:
            return

        try:
            self.mark_probe_selected(
                lower=case.source_lower,
                upper=case.source_upper,
                labels=list(case.source_labels),
                score=max(0.72, float(getattr(case, "live_pressure", 0.0) or 0.0)),
                judgment=(
                    "compromisso executivo v47.6: a tensão reidratada deve "
                    "ser tratada como dívida operacional antes da exploração comum"
                ),
            )
        except Exception as exc:
            self._v47_note_persistence_error(exc)

    def _v47_6_commitment_plan_from_active_tension(self) -> Optional["ActionPlan"]:
        active_id = getattr(self, "active_tension_id", None)
        if not active_id:
            self.last_executive_commitment_lines = [
                "COMPROMISSO EXECUTIVO v47.6",
                "- nenhum foco executivo ativo",
            ]
            return None

        case = getattr(self, "live_tension_cases", {}).get(active_id)
        if not self._v47_6_case_is_actionable(case):
            self.last_executive_commitment_lines = [
                "COMPROMISSO EXECUTIVO v47.6",
                f"- foco {active_id} não acionável ou já fechado",
            ]
            return None

        lower = case.source_lower
        upper = case.source_upper
        pair = case.source_pair

        pending = self._v47_6_pending_hypothesis_for_pair(lower, upper)

        self._v47_6_mark_commitment_probe_if_needed(case)

        if pending is not None:
            explanation = (
                f"compromisso executivo v47.6: validar hipótese pendente ligada à "
                f"tensão ativa {case.tension_id} ({pair}); a pendência reidratada "
                "tem prioridade sobre exploração comum"
            )
            plan = self._v47_6_make_action_plan(
                action_name="validate",
                lower=lower,
                upper=upper,
                explanation=explanation,
                novelty_residual=0.92,
                bucket="validate_commitment",
                phase="executive_commitment_lab",
                signature=f"commitment_validate:{case.tension_id}:{pair}",
            )
            action_line = f"- próximo ato comprometido: validate({pair})"
        else:
            explanation = (
                f"compromisso executivo v47.6: formular hipótese diretamente sobre "
                f"a tensão ativa {case.tension_id} ({pair}) antes de explorar outro caso"
            )
            plan = self._v47_6_make_action_plan(
                action_name="predict",
                lower=lower,
                upper=upper,
                explanation=explanation,
                novelty_residual=0.88,
                bucket="predict_commitment",
                phase="executive_commitment_lab",
                signature=f"commitment_predict:{case.tension_id}:{pair}",
            )
            action_line = f"- próximo ato comprometido: predict({pair})"

        self.last_executive_commitment_lines = [
            "COMPROMISSO EXECUTIVO v47.6",
            f"- tensão ativa: {case.tension_id} ({pair})",
            f"- status: {case.status.value} | pressão={case.live_pressure:.3f} | déficit={case.closure_deficit:.3f}",
            action_line,
        ]

        try:
            self._v47_persist_case(
                case,
                event_type="executive_commitment_selected",
                note=action_line.replace("- ", "", 1),
            )
        except Exception:
            pass

        return plan

    def executive_commitment_summary(self) -> str:
        """
        Relatório do compromisso executivo.

        v47.6.1:
        - se já houve uma decisão comprometida nesta sessão, mostra essa decisão;
        - se ainda não houve, mas existe tensão ativa aberta/reidratada, mostra
          a dívida executiva aguardando o próximo passo autônomo;
        - se não há tensão ativa, informa que não existe foco executivo pendente.
        """
        lines = list(getattr(self, "last_executive_commitment_lines", []))

        if lines and not (
            len(lines) >= 2
            and "ainda não houve decisão comprometida" in str(lines[1])
        ):
            return "\n".join(lines)

        active_id = getattr(self, "active_tension_id", None)
        case = getattr(self, "live_tension_cases", {}).get(active_id) if active_id else None

        if case is not None and self._v47_6_case_is_actionable(case):
            pending = self._v47_6_pending_hypothesis_for_pair(case.source_lower, case.source_upper)
            next_action = "validate" if pending is not None else "predict"

            return "\n".join(
                [
                    "COMPROMISSO EXECUTIVO v47.6.1",
                    f"- dívida executiva ativa: {case.tension_id} ({case.source_pair})",
                    f"- status: {case.status.value} | pressão={case.live_pressure:.3f} | déficit={case.closure_deficit:.3f}",
                    f"- próximo ato esperado: {next_action}({case.source_pair})",
                    "- aguardando o próximo passo autônomo para cumprir essa pendência",
                ]
            )

        if active_id:
            return "\n".join(
                [
                    "COMPROMISSO EXECUTIVO v47.6.1",
                    f"- foco executivo {active_id} não acionável ou já fechado",
                ]
            )

        return "\n".join(
            [
                "COMPROMISSO EXECUTIVO v47.6.1",
                "- nenhuma dívida executiva ativa no runtime",
            ]
        )

    def _choose_autonomous_action_v47_6_commitment(self) -> "ActionPlan":
        commitment_plan = self._v47_6_commitment_plan_from_active_tension()
        if commitment_plan is not None:
            return commitment_plan

        return self._choose_autonomous_action_v47_base()


    # --------------------------
    # micro-rotina de resolução v47.7
    # --------------------------

    def _v47_7_routine_db_path(self):
        from pathlib import Path
        return Path("darwin_home") / "darwin.db"

    def _v47_7_initialize_resolution_tables(self) -> None:
        import sqlite3

        db_path = self._v47_7_routine_db_path()
        if not db_path.exists():
            return

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tension_resolution_routines (
                    routine_id TEXT PRIMARY KEY,
                    tension_id TEXT NOT NULL,
                    source_pair TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    current_stage TEXT NOT NULL DEFAULT 'assess',
                    next_action TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_reason TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tension_resolution_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    routine_id TEXT NOT NULL,
                    tension_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    step INTEGER,
                    stage TEXT NOT NULL,
                    action_name TEXT NOT NULL,
                    source_pair TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tension_resolution_routines_tension
                ON tension_resolution_routines(tension_id, status)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tension_resolution_steps_routine
                ON tension_resolution_steps(routine_id, id)
                """
            )
            conn.commit()

    def _v47_7_now_iso(self) -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _v47_7_safe_json(self, value) -> str:
        import json
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            return json.dumps(str(value), ensure_ascii=False)

    def _v47_7_routine_id(self, tension_id: str) -> str:
        return f"RR:{tension_id}"

    def _v47_7_case_payload(self, case: "LiveTensionCase", stage: str, next_action: str) -> dict:
        return {
            "tension_id": case.tension_id,
            "source_pair": case.source_pair,
            "status": getattr(case.status, "value", str(case.status)),
            "outcome": getattr(case.outcome, "value", str(case.outcome)),
            "live_pressure": float(getattr(case, "live_pressure", 0.0) or 0.0),
            "economic_priority": float(getattr(case, "economic_priority", 0.0) or 0.0),
            "closure_deficit": float(getattr(case, "closure_deficit", 0.0) or 0.0),
            "saturation_cost": float(getattr(case, "saturation_cost", 0.0) or 0.0),
            "stage": stage,
            "next_action": next_action,
        }

    def _v47_7_upsert_routine(self, case: "LiveTensionCase", stage: str, next_action: str, reason: str) -> str:
        import sqlite3

        self._v47_7_initialize_resolution_tables()

        db_path = self._v47_7_routine_db_path()
        routine_id = self._v47_7_routine_id(case.tension_id)
        now = self._v47_7_now_iso()
        payload = self._v47_7_case_payload(case, stage, next_action)

        if not db_path.exists():
            return routine_id

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO tension_resolution_routines (
                    routine_id, tension_id, source_pair, status, current_stage,
                    next_action, created_at, updated_at, last_reason, payload_json
                )
                VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)
                ON CONFLICT(routine_id) DO UPDATE SET
                    status='active',
                    current_stage=excluded.current_stage,
                    next_action=excluded.next_action,
                    updated_at=excluded.updated_at,
                    last_reason=excluded.last_reason,
                    payload_json=excluded.payload_json
                """,
                (
                    routine_id,
                    case.tension_id,
                    case.source_pair,
                    stage,
                    next_action,
                    now,
                    now,
                    reason,
                    self._v47_7_safe_json(payload),
                ),
            )
            conn.commit()

        return routine_id

    def _v47_7_record_routine_step(
        self,
        *,
        case: "LiveTensionCase",
        routine_id: str,
        stage: str,
        action_name: str,
        reason: str,
    ) -> None:
        import sqlite3

        db_path = self._v47_7_routine_db_path()
        if not db_path.exists():
            return

        payload = self._v47_7_case_payload(case, stage, action_name)

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO tension_resolution_steps (
                    routine_id, tension_id, timestamp, step, stage,
                    action_name, source_pair, reason, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    routine_id,
                    case.tension_id,
                    self._v47_7_now_iso(),
                    self._current_step(),
                    stage,
                    action_name,
                    case.source_pair,
                    reason,
                    self._v47_7_safe_json(payload),
                ),
            )
            conn.commit()

    def _v47_7_close_routine_if_case_closed(self, case: "LiveTensionCase") -> None:
        import sqlite3

        if case is None:
            return

        if case.status not in {TensionStatus.CLOSED, TensionStatus.ARCHIVED, TensionStatus.STALE}:
            return

        db_path = self._v47_7_routine_db_path()
        if not db_path.exists():
            return

        routine_id = self._v47_7_routine_id(case.tension_id)

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                UPDATE tension_resolution_routines
                SET status=?, current_stage=?, next_action='', updated_at=?, last_reason=?
                WHERE routine_id=?
                """,
                (
                    getattr(case.status, "value", str(case.status)),
                    "done",
                    self._v47_7_now_iso(),
                    f"rotina encerrada porque a tensão está {getattr(case.status, 'value', case.status)}",
                    routine_id,
                ),
            )
            conn.commit()

    def _v47_7_stage_for_case(self, case: "LiveTensionCase") -> tuple[str, str]:
        """
        v47.8.1 — seletor ampliado de micro-rotina.

        Retorna:
            (stage, executable_action)

        A política distingue mais tipos de reparo, mas ainda retorna apenas
        action_name executável e seguro para o runtime atual: predict/validate.
        """
        pending = self._v47_6_pending_hypothesis_for_pair(case.source_lower, case.source_upper)

        if pending is not None:
            return "validate_pending_hypothesis", "validate"

        saturation = float(getattr(case, "saturation_cost", 0.0) or 0.0)
        probe_count = int(getattr(case, "probe_count", 0) or 0)
        inherited = list(getattr(case, "inherited_pairs", ()) or ())
        ambiguity = float(getattr(case, "ambiguity_score", 0.0) or 0.0)
        closure_deficit = float(getattr(case, "closure_deficit", 0.0) or 0.0)

        if saturation >= 0.65 or probe_count >= 3:
            return "reduce_saturation_before_retry", "predict"

        if inherited and ambiguity >= 0.25:
            return "compare_context_before_prediction", "predict"

        if case.status == TensionStatus.PROBING:
            return "repair_missing_prediction", "predict"

        if closure_deficit >= 0.75:
            return "formulate_probe_hypothesis", "predict"

        return "low_deficit_probe_check", "predict"

    def tension_resolution_policy_summary(self) -> str:
        active_id = getattr(self, "active_tension_id", None)
        case = getattr(self, "live_tension_cases", {}).get(active_id) if active_id else None

        if case is None:
            return chr(10).join(
                [
                    "SELETOR DE MICRO-ROTINA v47.8.1",
                    "- nenhuma tensão ativa no runtime",
                ]
            )

        if not self._v47_6_case_is_actionable(case):
            return chr(10).join(
                [
                    "SELETOR DE MICRO-ROTINA v47.8.1",
                    f"- tensão {case.tension_id} não acionável ou já fechada",
                ]
            )

        stage, action = self._v47_7_stage_for_case(case)
        inherited = list(getattr(case, "inherited_pairs", ()) or [])

        return chr(10).join(
            [
                "SELETOR DE MICRO-ROTINA v47.8.1",
                f"- tensão ativa: {case.tension_id} ({case.source_pair})",
                f"- estágio selecionado: {stage}",
                f"- ação executável: {action}({case.source_pair})",
                f"- pressão={case.live_pressure:.3f} | déficit={case.closure_deficit:.3f} | saturação={case.saturation_cost:.3f}",
                f"- pares herdados considerados: {len(inherited)}",
                "- operadores ricos ainda são classificados como estágio, não executados diretamente",
            ]
        )


    # --------------------------
    # operador compare_context v47.9
    # --------------------------

    def _v47_9_compare_db_path(self):
        from pathlib import Path
        return Path("darwin_home") / "darwin.db"

    def _v47_9_now_iso(self) -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _v47_9_safe_json(self, value) -> str:
        import json
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            return json.dumps(str(value), ensure_ascii=False)

    def _v47_9_initialize_compare_tables(self) -> None:
        import sqlite3

        db_path = self._v47_9_compare_db_path()
        if not db_path.exists():
            return

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tension_context_comparisons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    comparison_id TEXT NOT NULL,
                    tension_id TEXT NOT NULL,
                    source_pair TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    step INTEGER,
                    stage TEXT NOT NULL,
                    inherited_pairs_json TEXT NOT NULL DEFAULT '[]',
                    source_labels_json TEXT NOT NULL DEFAULT '[]',
                    overlap_score REAL NOT NULL DEFAULT 0.0,
                    ambiguity_score REAL NOT NULL DEFAULT 0.0,
                    summary TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tension_context_comparisons_tension
                ON tension_context_comparisons(tension_id, id)
                """
            )
            conn.commit()

    def _v47_9_pair_parts(self, pair: str) -> tuple[str, str]:
        text = str(pair or "")
        if ">" not in text:
            return text, ""
        left, right = text.split(">", 1)
        return left.strip(), right.strip()

    def _v47_9_context_overlap(self, case: "LiveTensionCase") -> dict:
        inherited = [str(x) for x in list(getattr(case, "inherited_pairs", ()) or [])]
        labels = [str(x) for x in list(getattr(case, "source_labels", ()) or [])]
        lower = str(getattr(case, "source_lower", "") or "")
        upper = str(getattr(case, "source_upper", "") or "")

        lower_refs = 0
        upper_refs = 0
        cross_refs = 0
        inherited_parts = []

        for pair in inherited:
            a, b = self._v47_9_pair_parts(pair)
            inherited_parts.append([a, b])
            if lower and (a == lower or b == lower):
                lower_refs += 1
            if upper and (a == upper or b == upper):
                upper_refs += 1
            if lower and upper and ((a == lower and b == upper) or (a == upper and b == lower)):
                cross_refs += 1

        ambiguity = float(getattr(case, "ambiguity_score", 0.0) or 0.0)
        inherited_weight = min(0.45, 0.09 * len(inherited))
        label_weight = min(0.25, 0.04 * len(labels))
        reference_weight = min(0.25, 0.05 * (lower_refs + upper_refs + cross_refs))
        ambiguity_weight = min(0.20, 0.20 * ambiguity)
        overlap_score = min(1.0, inherited_weight + label_weight + reference_weight + ambiguity_weight)

        return {
            "source_pair": case.source_pair,
            "source_lower": lower,
            "source_upper": upper,
            "inherited_pairs": inherited,
            "inherited_parts": inherited_parts,
            "source_labels": labels,
            "lower_refs": lower_refs,
            "upper_refs": upper_refs,
            "cross_refs": cross_refs,
            "ambiguity_score": ambiguity,
            "overlap_score": overlap_score,
        }

    def _v47_9_run_compare_context(self, case: "LiveTensionCase") -> str:
        import sqlite3

        self._v47_9_initialize_compare_tables()
        db_path = self._v47_9_compare_db_path()
        context = self._v47_9_context_overlap(case)
        step = self._current_step()
        comparison_id = f"CTX:{case.tension_id}:{step}"
        now = self._v47_9_now_iso()

        inherited = context["inherited_pairs"]
        labels = context["source_labels"]
        overlap = float(context["overlap_score"])
        ambiguity = float(context["ambiguity_score"])

        if inherited:
            summary = (
                f"compare_context v47.9: {case.source_pair} comparado com "
                f"{len(inherited)} par(es) herdado(s); overlap={overlap:.3f}; "
                f"ambiguidade={ambiguity:.3f}; seguir para hipótese controlada"
            )
        else:
            summary = (
                f"compare_context v47.9: {case.source_pair} sem pares herdados úteis; "
                "seguir para hipótese controlada"
            )

        payload = {
            "comparison_id": comparison_id,
            "tension_id": case.tension_id,
            "stage": "compare_context_before_prediction",
            "context": context,
            "decision": "predict_after_context_comparison",
        }

        if db_path.exists():
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO tension_context_comparisons (
                        comparison_id, tension_id, source_pair, timestamp, step, stage,
                        inherited_pairs_json, source_labels_json, overlap_score,
                        ambiguity_score, summary, payload_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    ,
                    (
                        comparison_id,
                        case.tension_id,
                        case.source_pair,
                        now,
                        step,
                        "compare_context_before_prediction",
                        self._v47_9_safe_json(inherited),
                        self._v47_9_safe_json(labels),
                        overlap,
                        ambiguity,
                        summary,
                        self._v47_9_safe_json(payload),
                    ),
                )
                conn.commit()

        self.last_context_comparison_lines = [
            "COMPARAÇÃO CONTEXTUAL v47.9",
            f"- comparação: {comparison_id}",
            f"- tensão: {case.tension_id} ({case.source_pair})",
            f"- pares herdados: {len(inherited)}",
            f"- labels de origem: {len(labels)}",
            f"- overlap={overlap:.3f} | ambiguidade={ambiguity:.3f}",
            f"- decisão: predict_after_context_comparison",
            f"- resumo: {summary}",
        ]

        return summary

    def context_comparison_summary(self) -> str:
        import sqlite3

        lines = list(getattr(self, "last_context_comparison_lines", []))
        if lines:
            return chr(10).join(lines)

        db_path = self._v47_9_compare_db_path()
        if not db_path.exists():
            return chr(10).join(["COMPARAÇÃO CONTEXTUAL v47.9", "- banco não encontrado"])

        self._v47_9_initialize_compare_tables()
        active_id = getattr(self, "active_tension_id", None)

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            if active_id:
                row = conn.execute(
                    """
                    SELECT comparison_id, tension_id, source_pair, timestamp, stage,
                           overlap_score, ambiguity_score, summary
                    FROM tension_context_comparisons
                    WHERE tension_id=?
                    ORDER BY id DESC
                    LIMIT 1
                    """
                    ,
                    (active_id,),
                ).fetchone()
            else:
                row = None

            if row is None:
                row = conn.execute(
                    """
                    SELECT comparison_id, tension_id, source_pair, timestamp, stage,
                           overlap_score, ambiguity_score, summary
                    FROM tension_context_comparisons
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ).fetchone()

        if row is None:
            return chr(10).join(
                [
                    "COMPARAÇÃO CONTEXTUAL v47.9",
                    "- nenhuma comparação contextual registrada nesta sessão/banco",
                ]
            )

        return chr(10).join(
            [
                "COMPARAÇÃO CONTEXTUAL v47.9",
                f"- comparação: {row['comparison_id']}",
                f"- tensão: {row['tension_id']} ({row['source_pair']})",
                f"- estágio: {row['stage']}",
                f"- overlap={float(row['overlap_score']):.3f} | ambiguidade={float(row['ambiguity_score']):.3f}",
                f"- resumo: {row['summary']}",
            ]
        )

    # --------------------------
    # influência contextual na hipótese v47.10
    # --------------------------

    def _v47_10_initialize_influence_tables(self) -> None:
        import sqlite3

        db_path = self._v47_9_compare_db_path()
        if not db_path.exists():
            return

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tension_prediction_influences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    influence_id TEXT NOT NULL,
                    comparison_id TEXT NOT NULL DEFAULT '',
                    tension_id TEXT NOT NULL,
                    source_pair TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    step INTEGER,
                    influence_kind TEXT NOT NULL,
                    bias_label TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    overlap_score REAL NOT NULL DEFAULT 0.0,
                    ambiguity_score REAL NOT NULL DEFAULT 0.0,
                    summary TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tension_prediction_influences_tension
                ON tension_prediction_influences(tension_id, id)
                """
            )
            conn.commit()

    def _v47_10_latest_context_comparison(self, case: "LiveTensionCase") -> dict:
        import json
        import sqlite3

        self._v47_9_initialize_compare_tables()
        self._v47_10_initialize_influence_tables()

        db_path = self._v47_9_compare_db_path()
        if not db_path.exists():
            return {}

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT comparison_id, tension_id, source_pair, timestamp, step, stage,
                       inherited_pairs_json, source_labels_json, overlap_score,
                       ambiguity_score, summary, payload_json
                FROM tension_context_comparisons
                WHERE tension_id=?
                ORDER BY id DESC
                LIMIT 1
                """
                ,
                (case.tension_id,),
            ).fetchone()

        if row is None:
            return {}

        def parse_json(value, fallback):
            try:
                return json.loads(value) if value else fallback
            except Exception:
                return fallback

        return {
            "comparison_id": str(row["comparison_id"] or ""),
            "tension_id": str(row["tension_id"] or ""),
            "source_pair": str(row["source_pair"] or ""),
            "timestamp": str(row["timestamp"] or ""),
            "step": row["step"],
            "stage": str(row["stage"] or ""),
            "inherited_pairs": parse_json(row["inherited_pairs_json"], []),
            "source_labels": parse_json(row["source_labels_json"], []),
            "overlap_score": float(row["overlap_score"] or 0.0),
            "ambiguity_score": float(row["ambiguity_score"] or 0.0),
            "summary": str(row["summary"] or ""),
            "payload": parse_json(row["payload_json"], {}),
        }

    def _v47_10_bias_from_context(self, comparison: dict) -> tuple[str, float, str]:
        labels = [str(x) for x in comparison.get("source_labels", [])]
        inherited = [str(x) for x in comparison.get("inherited_pairs", [])]
        overlap = float(comparison.get("overlap_score", 0.0) or 0.0)
        ambiguity = float(comparison.get("ambiguity_score", 0.0) or 0.0)

        stable_markers = {
            "with_block_top",
            "with_nonrolling_top",
            "with_stackable_context",
        }
        unstable_markers = {
            "with_rolling_top",
            "with_toy_top",
            "with_nonstackable_top",
        }

        stable_hits = sum(1 for label in labels if label in stable_markers)
        unstable_hits = sum(1 for label in labels if label in unstable_markers)

        confidence = min(1.0, 0.35 + 0.35 * overlap + 0.20 * ambiguity + 0.03 * len(inherited))

        if stable_hits > unstable_hits:
            return "bias_toward_stable_probe", confidence, "marcadores contextuais favorecem estabilidade"
        if unstable_hits > stable_hits:
            return "bias_toward_unstable_probe", confidence, "marcadores contextuais favorecem instabilidade"
        if overlap >= 0.55 and ambiguity >= 0.25:
            return "bias_toward_context_guarded_probe", confidence, "overlap e ambiguidade exigem hipótese guardada"
        return "bias_toward_cautious_probe", confidence, "comparação insuficiente para viés forte"

    def _v47_10_build_prediction_influence(self, case: "LiveTensionCase") -> str:
        import sqlite3

        comparison = self._v47_10_latest_context_comparison(case)
        if not comparison:
            self.last_prediction_influence_lines = [
                "INFLUÊNCIA CONTEXTUAL v47.10",
                f"- tensão: {case.tension_id} ({case.source_pair})",
                "- nenhuma comparação contextual disponível para influenciar a hipótese",
            ]
            return ""

        bias_label, confidence, rationale = self._v47_10_bias_from_context(comparison)
        step = self._current_step()
        influence_id = f"INF:{case.tension_id}:{step}"
        now = self._v47_9_now_iso()
        overlap = float(comparison.get("overlap_score", 0.0) or 0.0)
        ambiguity = float(comparison.get("ambiguity_score", 0.0) or 0.0)
        comparison_id = str(comparison.get("comparison_id", "") or "")

        summary = (
            f"influência contextual v47.10: {bias_label} com confiança={confidence:.3f}; "
            f"overlap={overlap:.3f}; ambiguidade={ambiguity:.3f}; {rationale}"
        )

        payload = {
            "influence_id": influence_id,
            "comparison_id": comparison_id,
            "tension_id": case.tension_id,
            "source_pair": case.source_pair,
            "bias_label": bias_label,
            "confidence": confidence,
            "rationale": rationale,
            "comparison": comparison,
            "decision": "prediction_reason_modified_by_context",
        }

        self._v47_10_initialize_influence_tables()
        db_path = self._v47_9_compare_db_path()
        if db_path.exists():
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO tension_prediction_influences (
                        influence_id, comparison_id, tension_id, source_pair, timestamp, step,
                        influence_kind, bias_label, confidence, overlap_score,
                        ambiguity_score, summary, payload_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    ,
                    (
                        influence_id,
                        comparison_id,
                        case.tension_id,
                        case.source_pair,
                        now,
                        step,
                        "contextual_prediction_bias",
                        bias_label,
                        confidence,
                        overlap,
                        ambiguity,
                        summary,
                        self._v47_9_safe_json(payload),
                    ),
                )
                conn.commit()

        self.last_prediction_influence_lines = [
            "INFLUÊNCIA CONTEXTUAL v47.10",
            f"- influência: {influence_id}",
            f"- comparação-base: {comparison_id}",
            f"- tensão: {case.tension_id} ({case.source_pair})",
            f"- viés: {bias_label}",
            f"- confiança={confidence:.3f} | overlap={overlap:.3f} | ambiguidade={ambiguity:.3f}",
            f"- racional: {rationale}",
            "- efeito: motivo da hipótese modificado pela comparação contextual",
        ]

        return summary

    def prediction_influence_summary(self) -> str:
        import sqlite3

        lines = list(getattr(self, "last_prediction_influence_lines", []))
        if lines:
            return chr(10).join(lines)

        db_path = self._v47_9_compare_db_path()
        if not db_path.exists():
            return chr(10).join(["INFLUÊNCIA CONTEXTUAL v47.10", "- banco não encontrado"])

        self._v47_10_initialize_influence_tables()
        active_id = getattr(self, "active_tension_id", None)

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            if active_id:
                row = conn.execute(
                    """
                    SELECT influence_id, comparison_id, tension_id, source_pair, timestamp,
                           bias_label, confidence, overlap_score, ambiguity_score, summary
                    FROM tension_prediction_influences
                    WHERE tension_id=?
                    ORDER BY id DESC
                    LIMIT 1
                    """
                    ,
                    (active_id,),
                ).fetchone()
            else:
                row = None

            if row is None:
                row = conn.execute(
                    """
                    SELECT influence_id, comparison_id, tension_id, source_pair, timestamp,
                           bias_label, confidence, overlap_score, ambiguity_score, summary
                    FROM tension_prediction_influences
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ).fetchone()

        if row is None:
            return chr(10).join(
                [
                    "INFLUÊNCIA CONTEXTUAL v47.10",
                    "- nenhuma influência contextual registrada nesta sessão/banco",
                ]
            )

        return chr(10).join(
            [
                "INFLUÊNCIA CONTEXTUAL v47.10",
                f"- influência: {row['influence_id']}",
                f"- comparação-base: {row['comparison_id']}",
                f"- tensão: {row['tension_id']} ({row['source_pair']})",
                f"- viés: {row['bias_label']}",
                f"- confiança={float(row['confidence']):.3f} | overlap={float(row['overlap_score']):.3f} | ambiguidade={float(row['ambiguity_score']):.3f}",
                f"- resumo: {row['summary']}",
            ]
        )

    # --------------------------
    # revisão de ciclos passados v47.13
    # --------------------------

    def _v47_13_initialize_cycle_review_tables(self) -> None:
        import sqlite3

        db_path = self._v47_9_compare_db_path()
        if not db_path.exists():
            return

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tension_cycle_memory_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_id TEXT NOT NULL,
                    tension_id TEXT NOT NULL,
                    source_pair TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    step INTEGER,
                    matches_count INTEGER NOT NULL DEFAULT 0,
                    best_report_id TEXT NOT NULL DEFAULT '',
                    best_source_pair TEXT NOT NULL DEFAULT '',
                    best_hypothesis_id TEXT NOT NULL DEFAULT '',
                    best_closure_assessment TEXT NOT NULL DEFAULT '',
                    best_bias_label TEXT NOT NULL DEFAULT '',
                    best_confidence REAL NOT NULL DEFAULT 0.0,
                    similarity_score REAL NOT NULL DEFAULT 0.0,
                    review_summary TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tension_cycle_memory_reviews_tension
                ON tension_cycle_memory_reviews(tension_id, id)
                """
            )
            conn.commit()

    def _v47_13_pair_tokens(self, pair: str) -> set:
        text = str(pair or "")
        if ">" in text:
            left, right = text.split(">", 1)
            return {left.strip(), right.strip()}
        return {text.strip()} if text.strip() else set()

    def _v47_13_json_from_text(self, value, fallback):
        import json
        try:
            return json.loads(value) if value else fallback
        except Exception:
            return fallback

    def _v47_13_recent_cycle_reports(self, limit: int = 30) -> list[dict]:
        import sqlite3

        db_path = self._v47_9_compare_db_path()
        if not db_path.exists():
            return []

        self._v47_12_initialize_cycle_report_tables()

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT report_id, tension_id, source_pair, status_after, outcome_after,
                       comparison_id, influence_id, lineage_id, hypothesis_id,
                       closure_assessment, narrative, payload_json
                FROM tension_cognitive_cycle_reports
                ORDER BY id DESC
                LIMIT ?
                """
                ,
                (int(limit),),
            ).fetchall()

        reports = []
        for row in rows:
            payload = self._v47_13_json_from_text(row["payload_json"], {})
            reports.append(
                {
                    "report_id": str(row["report_id"] or ""),
                    "tension_id": str(row["tension_id"] or ""),
                    "source_pair": str(row["source_pair"] or ""),
                    "status_after": str(row["status_after"] or ""),
                    "outcome_after": str(row["outcome_after"] or ""),
                    "comparison_id": str(row["comparison_id"] or ""),
                    "influence_id": str(row["influence_id"] or ""),
                    "lineage_id": str(row["lineage_id"] or ""),
                    "hypothesis_id": str(row["hypothesis_id"] or ""),
                    "closure_assessment": str(row["closure_assessment"] or ""),
                    "narrative": str(row["narrative"] or ""),
                    "payload": payload,
                    "bias_label": str(payload.get("bias_label", "") or ""),
                    "confidence": float(payload.get("confidence", 0.0) or 0.0),
                }
            )
        return reports

    def _v47_13_score_cycle_report(self, case: "LiveTensionCase", report: dict) -> float:
        case_pair = str(getattr(case, "source_pair", "") or "")
        report_pair = str(report.get("source_pair", "") or "")
        case_tokens = self._v47_13_pair_tokens(case_pair)
        report_tokens = self._v47_13_pair_tokens(report_pair)

        score = 0.0
        if case_pair and report_pair and case_pair == report_pair:
            score += 1.00

        if case_tokens and report_tokens:
            shared = len(case_tokens.intersection(report_tokens))
            score += 0.25 * shared

        closure = str(report.get("closure_assessment", "") or "")
        if "resolved" in closure or "validated" in closure or str(report.get("status_after", "")) == "closed":
            score += 0.25

        confidence = float(report.get("confidence", 0.0) or 0.0)
        score += min(0.25, 0.25 * confidence)

        return min(1.75, score)

    def _v47_13_review_past_cycles(self, case: "LiveTensionCase") -> str:
        import sqlite3

        self._v47_13_initialize_cycle_review_tables()
        reports = self._v47_13_recent_cycle_reports(limit=30)
        scored = []
        for report in reports:
            score = self._v47_13_score_cycle_report(case, report)
            if score >= 0.75:
                item = dict(report)
                item["similarity_score"] = score
                scored.append(item)

        scored.sort(key=lambda item: float(item.get("similarity_score", 0.0)), reverse=True)
        best = scored[0] if scored else {}
        step = self._current_step()
        review_id = f"REV:{case.tension_id}:{step}"
        now = self._v47_9_now_iso()

        if best:
            summary = (
                f"revisão de ciclo v47.13: encontrou ciclo passado {best.get('report_id')} "
                f"para {best.get('source_pair')} com similaridade={float(best.get('similarity_score', 0.0)):.3f}; "
                f"hipótese anterior={best.get('hypothesis_id', '') or 'ausente'}; "
                f"fechamento anterior={best.get('closure_assessment', '') or 'ausente'}"
            )
        else:
            summary = ""

        db_path = self._v47_9_compare_db_path()
        if db_path.exists():
            payload = {
                "review_id": review_id,
                "tension_id": case.tension_id,
                "source_pair": case.source_pair,
                "matches_count": len(scored),
                "best": best,
                "all_matches": scored[:5],
                "decision": "use_prior_cycle_as_contextual_memory" if best else "no_prior_cycle_available",
            }
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO tension_cycle_memory_reviews (
                        review_id, tension_id, source_pair, timestamp, step, matches_count,
                        best_report_id, best_source_pair, best_hypothesis_id,
                        best_closure_assessment, best_bias_label, best_confidence,
                        similarity_score, review_summary, payload_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    ,
                    (
                        review_id,
                        case.tension_id,
                        case.source_pair,
                        now,
                        step,
                        len(scored),
                        str(best.get("report_id", "") or ""),
                        str(best.get("source_pair", "") or ""),
                        str(best.get("hypothesis_id", "") or ""),
                        str(best.get("closure_assessment", "") or ""),
                        str(best.get("bias_label", "") or ""),
                        float(best.get("confidence", 0.0) or 0.0),
                        float(best.get("similarity_score", 0.0) or 0.0),
                        summary,
                        self._v47_9_safe_json(payload),
                    ),
                )
                conn.commit()

        if best:
            self.last_cycle_memory_review_lines = [
                "REVISÃO DE CICLOS PASSADOS v47.13",
                f"- revisão: {review_id}",
                f"- tensão atual: {case.tension_id} ({case.source_pair})",
                f"- ciclos similares encontrados: {len(scored)}",
                f"- melhor ciclo: {best.get('report_id', '')}",
                f"- par anterior: {best.get('source_pair', '')}",
                f"- hipótese anterior: {best.get('hypothesis_id', '')}",
                f"- fechamento anterior: {best.get('closure_assessment', '')}",
                f"- similaridade={float(best.get('similarity_score', 0.0)):.3f}",
                "- efeito: memória de ciclo anterior anexada ao motivo da próxima hipótese",
            ]
            return summary

        self.last_cycle_memory_review_lines = [
            "REVISÃO DE CICLOS PASSADOS v47.13",
            f"- revisão: {review_id}",
            f"- tensão atual: {case.tension_id} ({case.source_pair})",
            "- nenhum ciclo passado suficientemente similar encontrado",
        ]
        return ""

    def cycle_memory_review_summary(self) -> str:
        import sqlite3

        lines = list(getattr(self, "last_cycle_memory_review_lines", []))
        if lines:
            return chr(10).join(lines)

        db_path = self._v47_9_compare_db_path()
        if not db_path.exists():
            return chr(10).join(["REVISÃO DE CICLOS PASSADOS v47.13", "- banco não encontrado"])

        self._v47_13_initialize_cycle_review_tables()
        active_id = getattr(self, "active_tension_id", None)

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            if active_id:
                row = conn.execute(
                    """
                    SELECT review_id, tension_id, source_pair, matches_count, best_report_id,
                           best_source_pair, best_hypothesis_id, best_closure_assessment,
                           similarity_score, review_summary
                    FROM tension_cycle_memory_reviews
                    WHERE tension_id=?
                    ORDER BY id DESC
                    LIMIT 1
                    """
                    ,
                    (active_id,),
                ).fetchone()
            else:
                row = None

            if row is None:
                row = conn.execute(
                    """
                    SELECT review_id, tension_id, source_pair, matches_count, best_report_id,
                           best_source_pair, best_hypothesis_id, best_closure_assessment,
                           similarity_score, review_summary
                    FROM tension_cycle_memory_reviews
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ).fetchone()

        if row is None:
            return chr(10).join(
                [
                    "REVISÃO DE CICLOS PASSADOS v47.13",
                    "- nenhuma revisão de ciclo registrada nesta sessão/banco",
                ]
            )

        return chr(10).join(
            [
                "REVISÃO DE CICLOS PASSADOS v47.13",
                f"- revisão: {row['review_id']}",
                f"- tensão: {row['tension_id']} ({row['source_pair']})",
                f"- ciclos similares: {row['matches_count']}",
                f"- melhor ciclo: {row['best_report_id']}",
                f"- par anterior: {row['best_source_pair']}",
                f"- hipótese anterior: {row['best_hypothesis_id']}",
                f"- fechamento anterior: {row['best_closure_assessment']}",
                f"- similaridade={float(row['similarity_score']):.3f}",
                f"- resumo: {row['review_summary']}",
            ]
        )

    def _v47_7_resolution_routine_plan(self) -> Optional["ActionPlan"]:
        active_id = getattr(self, "active_tension_id", None)
        if not active_id:
            self.last_resolution_routine_lines = [
                "MICRO-ROTINA DE RESOLUÇÃO v47.7",
                "- nenhuma tensão ativa",
            ]
            return None

        case = getattr(self, "live_tension_cases", {}).get(active_id)
        if case is None:
            self.last_resolution_routine_lines = [
                "MICRO-ROTINA DE RESOLUÇÃO v47.7",
                f"- foco {active_id} ausente do runtime",
            ]
            return None

        self._v47_7_close_routine_if_case_closed(case)

        if not self._v47_6_case_is_actionable(case):
            self.last_resolution_routine_lines = [
                "MICRO-ROTINA DE RESOLUÇÃO v47.7",
                f"- foco {active_id} não acionável ou já fechado",
            ]
            return None

        stage, next_action = self._v47_7_stage_for_case(case)
        cycle_memory_review_summary = ""
        compare_context_summary = ""
        if stage == "compare_context_before_prediction":
            cycle_memory_review_summary = self._v47_13_review_past_cycles(case)
            compare_context_summary = self._v47_9_run_compare_context(case)

        try:
            self._v47_6_mark_commitment_probe_if_needed(case)
        except Exception as exc:
            self._v47_note_persistence_error(exc)

        if next_action == "validate":
            novelty = 0.94
            bucket = "routine_validate"
            reason = (
                f"micro-rotina v47.7: validar a hipótese pendente da tensão ativa "
                f"{case.tension_id} ({case.source_pair}) para tentar reduzir ou fechar a dívida"
            )
        else:
            novelty = 0.90
            bucket = "routine_predict"
            reason = (
                f"micro-rotina v47.7: formular hipótese sobre a tensão ativa "
                f"{case.tension_id} ({case.source_pair}) antes de qualquer exploração comum"
            )

        if compare_context_summary:
            prediction_influence_summary = self._v47_10_build_prediction_influence(case)
            if cycle_memory_review_summary:
                bucket = "routine_reviewed_compare_influenced_predict"
            else:
                bucket = "routine_compare_influenced_predict"
            if prediction_influence_summary and cycle_memory_review_summary:
                reason = f"{cycle_memory_review_summary}; {compare_context_summary}; {prediction_influence_summary}; {reason}"
            elif prediction_influence_summary:
                reason = f"{compare_context_summary}; {prediction_influence_summary}; {reason}"
            elif cycle_memory_review_summary:
                reason = f"{cycle_memory_review_summary}; {compare_context_summary}; {reason}"
            else:
                reason = f"{compare_context_summary}; {reason}"

        routine_id = self._v47_7_upsert_routine(case, stage, next_action, reason)
        self._v47_7_record_routine_step(
            case=case,
            routine_id=routine_id,
            stage=stage,
            action_name=next_action,
            reason=reason,
        )

        self.last_resolution_routine_lines = [
            "MICRO-ROTINA DE RESOLUÇÃO v47.7",
            f"- rotina: {routine_id}",
            f"- tensão ativa: {case.tension_id} ({case.source_pair})",
            f"- estágio: {stage}",
            f"- próximo ato: {next_action}({case.source_pair})",
            f"- pressão={case.live_pressure:.3f} | déficit={case.closure_deficit:.3f} | prioridade={case.economic_priority:.3f}",
        ]

        try:
            self._v47_persist_case(
                case,
                event_type="resolution_routine_step_selected",
                note=f"{stage} -> {next_action}({case.source_pair})",
            )
        except Exception:
            pass

        return self._v47_6_make_action_plan(
            action_name=next_action,
            lower=case.source_lower,
            upper=case.source_upper,
            explanation=reason,
            novelty_residual=novelty,
            bucket=bucket,
            phase="executive_resolution_routine",
            signature=f"routine:{routine_id}:{stage}:{next_action}:{case.source_pair}",
        )

    def tension_resolution_routine_summary(self) -> str:
        lines = list(getattr(self, "last_resolution_routine_lines", []))
        if lines:
            return "\n".join(lines)

        active_id = getattr(self, "active_tension_id", None)
        case = getattr(self, "live_tension_cases", {}).get(active_id) if active_id else None

        if case is not None and self._v47_6_case_is_actionable(case):
            stage, next_action = self._v47_7_stage_for_case(case)
            return "\n".join(
                [
                    "MICRO-ROTINA DE RESOLUÇÃO v47.7",
                    f"- rotina aguardando próximo passo para {case.tension_id} ({case.source_pair})",
                    f"- estágio previsto: {stage}",
                    f"- próximo ato provável: {next_action}({case.source_pair})",
                    f"- pressão={case.live_pressure:.3f} | déficit={case.closure_deficit:.3f}",
                ]
            )

        return "\n".join(
            [
                "MICRO-ROTINA DE RESOLUÇÃO v47.7",
                "- nenhuma rotina ativa no runtime",
            ]
        )

    def choose_autonomous_action(self) -> "ActionPlan":
        routine_plan = self._v47_7_resolution_routine_plan()
        if routine_plan is not None:
            return routine_plan

        return self._choose_autonomous_action_v47_6_commitment()


    def _choose_autonomous_action_v47_base(self) -> ActionPlan:
        self._finalize_contradiction_repair_if_ready()
        try:
            preview_pairs = [f"{lower}>{upper}" for lower, upper, _score, _labels, _reason in self._experimental_plan_targets()[:16]]
            self.refresh_tension_economy(candidate_pairs=preview_pairs)
            self.last_planner_error = ""
        except Exception as exc:
            self.last_planner_error = repr(exc)
            self.refresh_tension_economy(candidate_pairs=[])

        phase = self.current_lesson_phase()

        protected_probe = self._pending_probe_hypothesis()
        if protected_probe is not None:
            return ActionPlan(
                "validate",
                protected_probe.lower_id,
                protected_probe.upper_id,
                "laboratório: fechar sonda justificada antes de consolidar e registrar o desfecho da tensão",
                0.78,
                "validate",
                phase,
                f"validate:{protected_probe.lower_id}:{protected_probe.upper_id}:protected_probe"
            )

        if phase == "hypothesis_validation_lab" and not self.pending_hypotheses and not self.experiment_queue:
            live_queue = self._build_live_tension_probe_queue(limit=3)
            if live_queue:
                self.experiment_queue = live_queue
                plan_action = self._next_plan_predict_action(phase)
                if plan_action is not None:
                    return plan_action

        if self.should_consolidate():
            return ActionPlan("consolidate", "self", None, "o estado relacional sugere pausa para consolidar memória e recuperar estabilidade", 0.0, "consolidate", phase, "consolidate:self")

        candidates: List[Tuple[float, ActionPlan]] = []

        if phase == "survey_all":
            for obj_id in self._survey_incomplete():
                residual = clamp(1.0 - self._observe_penalty(obj_id), 0.02, 1.0)
                sig = f"observe:{obj_id}"
                score = 1.15 * residual - self._bucket_penalty("observe") - self._signature_penalty(sig)
                candidates.append((score + self.rng.uniform(0.0, 0.05), ActionPlan("observe", obj_id, None, "lição atual: completar survey básico deste objeto", residual, "observe", phase, sig)))

        elif phase == "touch_all":
            for obj_id in self._touch_incomplete():
                residual = clamp(1.0 - self._touch_penalty(obj_id), 0.02, 1.0)
                sig = f"touch:{obj_id}"
                score = 1.00 * residual - self._bucket_penalty("touch") - self._signature_penalty(sig)
                candidates.append((score + self.rng.uniform(0.0, 0.05), ActionPlan("touch", obj_id, None, "lição atual: completar affordance básica deste objeto", residual, "touch", phase, sig)))

        elif phase == "fit_all":
            for obj_id in self._fit_incomplete():
                slot_id = f"slot_{self.env.objects[obj_id].fit_slot}"
                residual = clamp(1.0 - self._fit_penalty(obj_id, slot_id), 0.02, 1.0)
                sig = f"fit:{obj_id}:{slot_id}"
                score = 0.95 * residual - self._bucket_penalty("fit") - self._signature_penalty(sig)
                candidates.append((score + self.rng.uniform(0.0, 0.05), ActionPlan("fit", obj_id, slot_id, "lição atual: completar compatibilidade de encaixe", residual, "fit", phase, sig)))

        else:
            if self.pending_hypotheses:
                hyp = self.pending_hypotheses[0]
                return ActionPlan("validate", hyp.lower_id, hyp.upper_id, "laboratório: testar hipótese pendente", 0.72, "validate", phase, f"validate:{hyp.lower_id}:{hyp.upper_id}")

            plan_action = self._next_plan_predict_action(phase)
            if plan_action is not None:
                return plan_action

            has_ambiguity = bool(self._ambiguous_context_targets())
            self.experiment_queue = self._build_experiment_queue(limit=3)
            plan_action = self._next_plan_predict_action(phase)
            if plan_action is not None:
                return plan_action

            compare_action = self._best_compare_action(phase)
            if compare_action is not None and (has_ambiguity or self._infer_streak() >= 1):
                return compare_action

            if has_ambiguity:
                lower, upper, labels, net = self._ambiguous_context_targets()[0]
                residual = clamp(1.0 - self._hypothesis_penalty(lower, upper), 0.08, 1.0)
                label_text = ", ".join(labels[:3]) if labels else "contexto ambíguo"
                return ActionPlan(
                    "predict",
                    lower,
                    upper,
                    f"laboratório: fallback direto por ambiguidade residual ({label_text}, net={net:+.2f})",
                    residual,
                    "predict",
                    phase,
                    f"predict:{lower}:{upper}"
                )

            if self._infer_streak() >= 1 and compare_action is not None:
                return compare_action

            infer_residual = clamp(1.0 - self._rule_penalty("rule:"), 0.05, 1.0)
            return ActionPlan("infer", "memory", None, "laboratório: generalizar regras a partir das relações já observadas", infer_residual, "infer", phase, "infer:relations")

        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    def _consolidate(self) -> NurseryActionResult:
        return NurseryActionResult(True, "Entrou em consolidação: reduziu carga externa, reorganizou memória recente e recuperou estabilidade.", 0.80, 0.05, 0.02, 0.18, ["nursery:self:consolidated=true"])

    # --------------------------
    # linhagem contextual da hipótese v47.11
    # --------------------------

    def _v47_11_initialize_lineage_tables(self) -> None:
        import sqlite3

        db_path = self._v47_9_compare_db_path()
        if not db_path.exists():
            return

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tension_hypothesis_lineage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lineage_id TEXT NOT NULL,
                    hypothesis_id TEXT NOT NULL DEFAULT '',
                    tension_id TEXT NOT NULL,
                    source_pair TEXT NOT NULL,
                    comparison_id TEXT NOT NULL DEFAULT '',
                    influence_id TEXT NOT NULL DEFAULT '',
                    bias_label TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 0.0,
                    timestamp TEXT NOT NULL,
                    step INTEGER,
                    action_signature TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'recorded',
                    result_excerpt TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tension_hypothesis_lineage_tension
                ON tension_hypothesis_lineage(tension_id, id)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tension_hypothesis_lineage_hypothesis
                ON tension_hypothesis_lineage(hypothesis_id, id)
                """
            )
            conn.commit()

    def _v47_11_latest_prediction_influence(self, tension_id: str) -> dict:
        import json
        import sqlite3

        self._v47_10_initialize_influence_tables()
        db_path = self._v47_9_compare_db_path()
        if not db_path.exists():
            return {}

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT influence_id, comparison_id, tension_id, source_pair, timestamp,
                       bias_label, confidence, overlap_score, ambiguity_score, summary, payload_json
                FROM tension_prediction_influences
                WHERE tension_id=?
                ORDER BY id DESC
                LIMIT 1
                """
                ,
                (tension_id,),
            ).fetchone()

        if row is None:
            return {}

        def parse_json(value, fallback):
            try:
                return json.loads(value) if value else fallback
            except Exception:
                return fallback

        return {
            "influence_id": str(row["influence_id"] or ""),
            "comparison_id": str(row["comparison_id"] or ""),
            "tension_id": str(row["tension_id"] or ""),
            "source_pair": str(row["source_pair"] or ""),
            "timestamp": str(row["timestamp"] or ""),
            "bias_label": str(row["bias_label"] or ""),
            "confidence": float(row["confidence"] or 0.0),
            "overlap_score": float(row["overlap_score"] or 0.0),
            "ambiguity_score": float(row["ambiguity_score"] or 0.0),
            "summary": str(row["summary"] or ""),
            "payload": parse_json(row["payload_json"], {}),
        }

    def _v47_11_plan_pair(self, plan) -> tuple[str, str, str]:
        lower = str(getattr(plan, "target_a", "") or "")
        upper = str(getattr(plan, "target_b", "") or "")
        pair = f"{lower}>{upper}" if lower or upper else ""
        return lower, upper, pair

    def _v47_11_hypothesis_id_from_object(self, hyp) -> str:
        for attr in ("hypothesis_id", "id", "hid", "name", "uid"):
            value = getattr(hyp, attr, None)
            if value:
                return str(value)
        text = str(hyp)
        if "H" in text:
            import re
            match = re.search(r"H\d+", text)
            if match:
                return match.group(0)
        return ""

    def _v47_11_latest_hypothesis_for_pair(self, lower: str, upper: str) -> tuple[str, object]:
        candidates = []
        for hyp in list(getattr(self, "pending_hypotheses", []) or []):
            if getattr(hyp, "lower_id", None) == lower and getattr(hyp, "upper_id", None) == upper:
                candidates.append(hyp)
        if not candidates:
            return "", None
        hyp = candidates[-1]
        return self._v47_11_hypothesis_id_from_object(hyp), hyp

    def _v47_11_lineage_already_recorded(self, tension_id: str, influence_id: str, hypothesis_id: str) -> bool:
        import sqlite3

        db_path = self._v47_9_compare_db_path()
        if not db_path.exists():
            return False

        self._v47_11_initialize_lineage_tables()
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM tension_hypothesis_lineage
                WHERE tension_id=? AND influence_id=? AND hypothesis_id=?
                """
                ,
                (tension_id, influence_id, hypothesis_id),
            ).fetchone()
        return bool(row and int(row[0]) > 0)

    def _v47_11_record_hypothesis_lineage_after_predict(self, plan, result_text: str) -> None:
        import sqlite3

        try:
            action_name = str(getattr(plan, "action_name", "") or "")
            bucket = str(getattr(plan, "curriculum_bucket", "") or "")
            if action_name != "predict":
                return
            if bucket not in {"routine_compare_influenced_predict", "routine_reviewed_compare_influenced_predict"}:
                return

            active_id = getattr(self, "active_tension_id", None)
            case = getattr(self, "live_tension_cases", {}).get(active_id) if active_id else None
            lower, upper, pair = self._v47_11_plan_pair(plan)

            if case is None:
                # fallback por par, caso o foco tenha mudado por algum motivo
                for candidate in list(getattr(self, "live_tension_cases", {}).values()):
                    if getattr(candidate, "source_lower", None) == lower and getattr(candidate, "source_upper", None) == upper:
                        case = candidate
                        break

            if case is None:
                return

            influence = self._v47_11_latest_prediction_influence(case.tension_id)
            if not influence:
                return

            hypothesis_id, hyp = self._v47_11_latest_hypothesis_for_pair(lower, upper)
            if not hypothesis_id:
                hypothesis_id = "HYPOTHESIS_PENDING_UNRESOLVED"

            influence_id = str(influence.get("influence_id", "") or "")
            if self._v47_11_lineage_already_recorded(case.tension_id, influence_id, hypothesis_id):
                return

            self._v47_11_initialize_lineage_tables()
            db_path = self._v47_9_compare_db_path()
            if not db_path.exists():
                return

            step = self._current_step()
            lineage_id = f"LIN:{case.tension_id}:{hypothesis_id}:{step}"
            now = self._v47_9_now_iso()
            result_excerpt = str(result_text or "")[:800]
            comparison_id = str(influence.get("comparison_id", "") or "")
            bias_label = str(influence.get("bias_label", "") or "")
            confidence = float(influence.get("confidence", 0.0) or 0.0)
            action_signature = str(getattr(plan, "signature", "") or "")

            payload = {
                "lineage_id": lineage_id,
                "hypothesis_id": hypothesis_id,
                "tension_id": case.tension_id,
                "source_pair": case.source_pair,
                "comparison_id": comparison_id,
                "influence_id": influence_id,
                "bias_label": bias_label,
                "confidence": confidence,
                "action_signature": action_signature,
                "plan_explanation": str(getattr(plan, "explanation", "") or ""),
                "result_excerpt": result_excerpt,
                "effect": "hypothesis_lineage_bound_to_contextual_influence",
            }

            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO tension_hypothesis_lineage (
                        lineage_id, hypothesis_id, tension_id, source_pair, comparison_id,
                        influence_id, bias_label, confidence, timestamp, step,
                        action_signature, status, result_excerpt, payload_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    ,
                    (
                        lineage_id,
                        hypothesis_id,
                        case.tension_id,
                        case.source_pair,
                        comparison_id,
                        influence_id,
                        bias_label,
                        confidence,
                        now,
                        step,
                        action_signature,
                        "recorded",
                        result_excerpt,
                        self._v47_9_safe_json(payload),
                    ),
                )
                conn.commit()

            self.last_hypothesis_lineage_lines = [
                "LINHAGEM CONTEXTUAL DA HIPÓTESE v47.11",
                f"- linhagem: {lineage_id}",
                f"- hipótese: {hypothesis_id}",
                f"- tensão: {case.tension_id} ({case.source_pair})",
                f"- comparação-base: {comparison_id}",
                f"- influência-base: {influence_id}",
                f"- viés: {bias_label} | confiança={confidence:.3f}",
                "- efeito: hipótese vinculada à comparação e à influência contextual",
            ]
        except Exception as exc:
            self.last_hypothesis_lineage_lines = [
                "LINHAGEM CONTEXTUAL DA HIPÓTESE v47.11",
                f"- erro ao registrar linhagem: {exc}",
            ]

    def hypothesis_lineage_summary(self) -> str:
        import sqlite3

        lines = list(getattr(self, "last_hypothesis_lineage_lines", []))
        if lines:
            return chr(10).join(lines)

        db_path = self._v47_9_compare_db_path()
        if not db_path.exists():
            return chr(10).join(["LINHAGEM CONTEXTUAL DA HIPÓTESE v47.11", "- banco não encontrado"])

        self._v47_11_initialize_lineage_tables()
        active_id = getattr(self, "active_tension_id", None)

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            if active_id:
                row = conn.execute(
                    """
                    SELECT lineage_id, hypothesis_id, tension_id, source_pair, comparison_id,
                           influence_id, bias_label, confidence, timestamp, status
                    FROM tension_hypothesis_lineage
                    WHERE tension_id=?
                    ORDER BY id DESC
                    LIMIT 1
                    """
                    ,
                    (active_id,),
                ).fetchone()
            else:
                row = None

            if row is None:
                row = conn.execute(
                    """
                    SELECT lineage_id, hypothesis_id, tension_id, source_pair, comparison_id,
                           influence_id, bias_label, confidence, timestamp, status
                    FROM tension_hypothesis_lineage
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ).fetchone()

        if row is None:
            return chr(10).join(
                [
                    "LINHAGEM CONTEXTUAL DA HIPÓTESE v47.11",
                    "- nenhuma linhagem contextual registrada nesta sessão/banco",
                ]
            )

        return chr(10).join(
            [
                "LINHAGEM CONTEXTUAL DA HIPÓTESE v47.11",
                f"- linhagem: {row['lineage_id']}",
                f"- hipótese: {row['hypothesis_id']}",
                f"- tensão: {row['tension_id']} ({row['source_pair']})",
                f"- comparação-base: {row['comparison_id']}",
                f"- influência-base: {row['influence_id']}",
                f"- viés: {row['bias_label']} | confiança={float(row['confidence']):.3f}",
                f"- status: {row['status']}",
            ]
        )

    # --------------------------
    # relatório consolidado do ciclo cognitivo v47.12.1
    # --------------------------

    def _v47_12_initialize_cycle_report_tables(self) -> None:
        import sqlite3

        db_path = self._v47_9_compare_db_path()
        if not db_path.exists():
            return

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tension_cognitive_cycle_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_id TEXT NOT NULL,
                    tension_id TEXT NOT NULL,
                    source_pair TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    step INTEGER,
                    status_after TEXT NOT NULL DEFAULT '',
                    outcome_after TEXT NOT NULL DEFAULT '',
                    comparison_id TEXT NOT NULL DEFAULT '',
                    influence_id TEXT NOT NULL DEFAULT '',
                    lineage_id TEXT NOT NULL DEFAULT '',
                    hypothesis_id TEXT NOT NULL DEFAULT '',
                    validation_result TEXT NOT NULL DEFAULT '',
                    closure_assessment TEXT NOT NULL DEFAULT '',
                    narrative TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tension_cognitive_cycle_reports_tension
                ON tension_cognitive_cycle_reports(tension_id, id)
                """
            )
            conn.commit()

    def _v47_12_latest_row_dict(self, table: str, tension_id: str) -> dict:
        import sqlite3

        db_path = self._v47_9_compare_db_path()
        if not db_path.exists():
            return {}

        try:
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    f"SELECT * FROM {table} WHERE tension_id=? ORDER BY id DESC LIMIT 1",
                    (tension_id,),
                ).fetchone()
            if row is None:
                return {}
            return {key: row[key] for key in row.keys()}
        except Exception:
            return {}

    def _v47_12_find_case_for_plan(self, plan):
        lower = str(getattr(plan, "target_a", "") or "")
        upper = str(getattr(plan, "target_b", "") or "")
        active_id = getattr(self, "active_tension_id", None)
        case = getattr(self, "live_tension_cases", {}).get(active_id) if active_id else None

        if case is not None and getattr(case, "source_lower", None) == lower and getattr(case, "source_upper", None) == upper:
            return case

        for candidate in list(getattr(self, "live_tension_cases", {}).values()):
            if getattr(candidate, "source_lower", None) == lower and getattr(candidate, "source_upper", None) == upper:
                return candidate

        return case

    def _v47_12_case_status_text(self, case) -> tuple[str, str]:
        if case is None:
            return "", ""
        status = getattr(case, "status", "")
        outcome = getattr(case, "outcome", "")
        status_text = getattr(status, "value", str(status))
        outcome_text = getattr(outcome, "value", str(outcome))
        return status_text, outcome_text

    def _v47_12_closure_assessment(self, case, result_text: str) -> str:
        status_text, outcome_text = self._v47_12_case_status_text(case)
        result_lower = str(result_text or "").lower()

        if status_text in {"closed", "archived", "stale"}:
            return f"cycle_resolved_by_status:{status_text}"
        if "previsão confirmada" in result_lower or "validou" in result_lower:
            return "cycle_validated_by_observation"
        if "contradi" in result_lower or "falhou" in result_lower:
            return "cycle_remains_open_after_contradiction"
        if outcome_text:
            return f"cycle_outcome:{outcome_text}"
        return "cycle_state_uncertain"

    def _v47_12_build_cycle_narrative(self, case, comparison: dict, influence: dict, lineage: dict, result_text: str, closure: str) -> str:
        tension_id = getattr(case, "tension_id", "") if case is not None else ""
        source_pair = getattr(case, "source_pair", "") if case is not None else ""
        comparison_id = str(comparison.get("comparison_id", "") or "")
        influence_id = str(influence.get("influence_id", "") or "")
        lineage_id = str(lineage.get("lineage_id", "") or "")
        hypothesis_id = str(lineage.get("hypothesis_id", "") or "")
        bias = str(influence.get("bias_label", lineage.get("bias_label", "")) or "")
        confidence = float(influence.get("confidence", lineage.get("confidence", 0.0)) or 0.0)

        parts = [
            f"ciclo v47.12.1 para {tension_id} ({source_pair})",
            f"comparação={comparison_id or 'ausente'}",
            f"influência={influence_id or 'ausente'}",
            f"linhagem={lineage_id or 'ausente'}",
            f"hipótese={hypothesis_id or 'ausente'}",
            f"viés={bias or 'ausente'}",
            f"confiança={confidence:.3f}",
            f"fechamento={closure}",
        ]
        return "; ".join(parts)

    def _v47_12_report_already_recorded(self, tension_id: str, lineage_id: str, validation_result: str) -> bool:
        import sqlite3

        db_path = self._v47_9_compare_db_path()
        if not db_path.exists():
            return False

        self._v47_12_initialize_cycle_report_tables()
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM tension_cognitive_cycle_reports
                WHERE tension_id=? AND lineage_id=? AND validation_result=?
                """
                ,
                (tension_id, lineage_id, validation_result[:800]),
            ).fetchone()
        return bool(row and int(row[0]) > 0)

    def _v47_12_record_cycle_report_after_validate(self, plan, result_text: str) -> None:
        import sqlite3

        try:
            action_name = str(getattr(plan, "action_name", "") or "")
            bucket = str(getattr(plan, "curriculum_bucket", "") or "")
            if action_name != "validate":
                return
            if bucket != "routine_validate":
                return

            case = self._v47_12_find_case_for_plan(plan)
            if case is None:
                return

            tension_id = str(getattr(case, "tension_id", "") or "")
            source_pair = str(getattr(case, "source_pair", "") or "")
            if not tension_id:
                return

            comparison = self._v47_12_latest_row_dict("tension_context_comparisons", tension_id)
            influence = self._v47_12_latest_row_dict("tension_prediction_influences", tension_id)
            lineage = self._v47_12_latest_row_dict("tension_hypothesis_lineage", tension_id)

            comparison_id = str(comparison.get("comparison_id", "") or "")
            influence_id = str(influence.get("influence_id", "") or "")
            lineage_id = str(lineage.get("lineage_id", "") or "")
            hypothesis_id = str(lineage.get("hypothesis_id", "") or "")
            bias_label = str(influence.get("bias_label", lineage.get("bias_label", "")) or "")
            confidence = float(influence.get("confidence", lineage.get("confidence", 0.0)) or 0.0)

            validation_excerpt = str(result_text or "")[:800]
            if self._v47_12_report_already_recorded(tension_id, lineage_id, validation_excerpt):
                return

            self._v47_12_initialize_cycle_report_tables()
            db_path = self._v47_9_compare_db_path()
            if not db_path.exists():
                return

            status_after, outcome_after = self._v47_12_case_status_text(case)
            closure = self._v47_12_closure_assessment(case, result_text)
            step = self._current_step()
            report_id = f"CYCLE:{tension_id}:{step}"
            now = self._v47_9_now_iso()
            narrative = self._v47_12_build_cycle_narrative(case, comparison, influence, lineage, result_text, closure)

            payload = {
                "report_id": report_id,
                "tension_id": tension_id,
                "source_pair": source_pair,
                "status_after": status_after,
                "outcome_after": outcome_after,
                "comparison_id": comparison_id,
                "influence_id": influence_id,
                "lineage_id": lineage_id,
                "hypothesis_id": hypothesis_id,
                "bias_label": bias_label,
                "confidence": confidence,
                "closure_assessment": closure,
                "validation_result": validation_excerpt,
                "narrative": narrative,
                "effect": "full_cognitive_cycle_report_recorded",
            }

            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO tension_cognitive_cycle_reports (
                        report_id, tension_id, source_pair, timestamp, step,
                        status_after, outcome_after, comparison_id, influence_id, lineage_id,
                        hypothesis_id, validation_result, closure_assessment, narrative, payload_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    ,
                    (
                        report_id,
                        tension_id,
                        source_pair,
                        now,
                        step,
                        status_after,
                        outcome_after,
                        comparison_id,
                        influence_id,
                        lineage_id,
                        hypothesis_id,
                        validation_excerpt,
                        closure,
                        narrative,
                        self._v47_9_safe_json(payload),
                    ),
                )
                conn.commit()

            self.last_cycle_report_lines = [
                "RELATÓRIO CONSOLIDADO DO CICLO COGNITIVO v47.12.1",
                f"- relatório: {report_id}",
                f"- tensão: {tension_id} ({source_pair})",
                f"- estado final: {status_after} | desfecho={outcome_after}",
                f"- comparação: {comparison_id or 'ausente'}",
                f"- influência: {influence_id or 'ausente'}",
                f"- linhagem: {lineage_id or 'ausente'}",
                f"- hipótese: {hypothesis_id or 'ausente'}",
                f"- viés: {bias_label or 'ausente'} | confiança={confidence:.3f}",
                f"- fechamento: {closure}",
                f"- narrativa: {narrative}",
            ]
        except Exception as exc:
            self.last_cycle_report_lines = [
                "RELATÓRIO CONSOLIDADO DO CICLO COGNITIVO v47.12.1",
                f"- erro ao registrar relatório: {exc}",
            ]

    def cognitive_cycle_report_summary(self) -> str:
        import sqlite3

        lines = list(getattr(self, "last_cycle_report_lines", []))
        if lines:
            return chr(10).join(lines)

        db_path = self._v47_9_compare_db_path()
        if not db_path.exists():
            return chr(10).join(["RELATÓRIO CONSOLIDADO DO CICLO COGNITIVO v47.12.1", "- banco não encontrado"])

        self._v47_12_initialize_cycle_report_tables()
        active_id = getattr(self, "active_tension_id", None)

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            if active_id:
                row = conn.execute(
                    """
                    SELECT report_id, tension_id, source_pair, status_after, outcome_after,
                           comparison_id, influence_id, lineage_id, hypothesis_id,
                           closure_assessment, narrative
                    FROM tension_cognitive_cycle_reports
                    WHERE tension_id=?
                    ORDER BY id DESC
                    LIMIT 1
                    """
                    ,
                    (active_id,),
                ).fetchone()
            else:
                row = None

            if row is None:
                row = conn.execute(
                    """
                    SELECT report_id, tension_id, source_pair, status_after, outcome_after,
                           comparison_id, influence_id, lineage_id, hypothesis_id,
                           closure_assessment, narrative
                    FROM tension_cognitive_cycle_reports
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ).fetchone()

        if row is None:
            return chr(10).join(
                [
                    "RELATÓRIO CONSOLIDADO DO CICLO COGNITIVO v47.12.1",
                    "- nenhum ciclo consolidado registrado nesta sessão/banco",
                ]
            )

        return chr(10).join(
            [
                "RELATÓRIO CONSOLIDADO DO CICLO COGNITIVO v47.12.1",
                f"- relatório: {row['report_id']}",
                f"- tensão: {row['tension_id']} ({row['source_pair']})",
                f"- estado final: {row['status_after']} | desfecho={row['outcome_after']}",
                f"- comparação: {row['comparison_id']}",
                f"- influência: {row['influence_id']}",
                f"- linhagem: {row['lineage_id']}",
                f"- hipótese: {row['hypothesis_id']}",
                f"- fechamento: {row['closure_assessment']}",
                f"- narrativa: {row['narrative']}",
            ]
        )

    def execute_action(self, plan):
        result = self._execute_action_v47_10_base(plan)
        self._v47_11_record_hypothesis_lineage_after_predict(plan, result)
        self._v47_12_record_cycle_report_after_validate(plan, result)
        return result

    def _execute_action_v47_10_base(self, plan: ActionPlan) -> str:
        prev_sigma = self.sigma_now()

        if plan.action_name == "observe":
            result = self.env.observe(plan.target_a)
        elif plan.action_name == "touch":
            result = self.env.touch(plan.target_a)
        elif plan.action_name == "fit" and plan.target_b is not None:
            result = self.env.try_fit(plan.target_a, plan.target_b)
        elif plan.action_name == "stack" and plan.target_b is not None:
            result = self.env.try_stack(plan.target_a, plan.target_b)
        elif plan.action_name == "compare" and plan.target_b is not None:
            result = self.env.compare_objects(plan.target_a, plan.target_b)
        elif plan.action_name == "infer":
            result = self.infer_generalizations()
        elif plan.action_name == "predict" and plan.target_b is not None:
            result = self.propose_hypothesis(plan.target_a, plan.target_b)
        elif plan.action_name == "validate":
            result = self.validate_oldest_hypothesis()
        elif plan.action_name == "consolidate":
            result = self._consolidate()
        else:
            raise ValueError("Plano inválido.")

        effective_novelty = clamp(result.novelty * max(plan.novelty_residual, 0.05), 0.02, 1.0)
        task = self._task_for_action(effective_novelty, result.conflict, result.info_gain, result.utility)

        if plan.action_name == "consolidate":
            self.state.bandwidth = clamp(self.state.bandwidth + 0.35, 1.2, 5.0)
            self.state.energy = clamp(self.state.energy + 0.20, 0.0, 1.0)
            self.state.latency = clamp(self.state.latency - 0.08, 0.6, 2.5)
            self.state.info_external = clamp(self.state.info_external - 0.28, 0.0, 2.5)
            self.state.info_self = clamp(self.state.info_self - 0.08, 0.0, 2.5)
        else:
            self.state.bandwidth = clamp(self.state.bandwidth - task.energy_cost + (0.05 if result.success else 0.0), 1.2, 5.0)
            self.state.energy = clamp(self.state.energy - task.energy_cost + (0.06 if result.success else -0.02), 0.0, 1.0)
            self.state.latency = clamp(self.state.latency + task.latency_cost - (0.02 if result.success else 0.0), 0.6, 2.5)
            self.state.info_external = clamp(self.state.info_external + result.info_gain * 0.14, 0.0, 2.5)
            self.state.info_self = clamp(self.state.info_self + result.conflict * 0.10, 0.0, 2.5)

        sigma_final = self.sigma_now()
        repeated_error = (not result.success) and plan.novelty_residual < 0.35
        pain, wellbeing = compute_valence(prev_sigma, sigma_final, self.state.energy, repeated_error)

        if plan.action_name == "consolidate":
            pain = max(0.0, pain - 0.80)
            wellbeing = min(3.0, wellbeing + 0.55)
        elif result.success:
            pain = max(0.0, pain - (0.95 + 0.70 * result.info_gain))
            wellbeing = min(3.0, wellbeing + 0.45 + 0.80 * result.info_gain)
            if sigma_final < 0.95:
                pain = min(3.0, pain + 0.35)
                wellbeing = max(0.0, wellbeing - 0.20)
        else:
            pain = min(3.0, pain + 0.25 + 0.50 * result.conflict)
            wellbeing = max(0.0, wellbeing - 0.10)

        for item in result.learned:
            if "=" in item:
                key, value = item.split("=", 1)
            else:
                key, value = item, "true"
            boost = 0.14 if result.success else 0.08
            if plan.action_name == "consolidate":
                boost = 0.04
            if plan.action_name == "compare":
                boost = 0.12
            if plan.action_name == "infer":
                boost = 0.16
            if plan.action_name == "predict":
                boost = 0.11
            if plan.action_name == "validate":
                boost = 0.16
            self.memory.learn(key, value, confidence_boost=boost)
            self.home.upsert_semantic_memory(key=key, content=value, confidence=self.memory.nodes[key].confidence, source="nursery_v47")

        current_state = self.home.load_current_state()
        current_state.sigma = sigma_final
        current_state.energy = self.state.energy
        current_state.info_self = self.state.info_self
        current_state.info_external = self.state.info_external
        current_state.latency = self.state.latency
        current_state.pain_signal = pain
        current_state.wellbeing_signal = wellbeing
        self.home.save_current_state(current_state)

        context = f"nursery_v46 | action={plan.action_name} | target_a={plan.target_a} | target_b={plan.target_b}"
        action_taken = f"{plan.action_name}:{plan.target_a}" + (f":{plan.target_b}" if plan.target_b else "")
        self.home.add_episode(module="nursery_v47", context=context, action_taken=action_taken, outcome="success" if result.success else "friction", lesson=result.summary, sigma_before=prev_sigma, sigma_after=sigma_final)

        self.step_counter += 1
        self.last_episode_summary = f"step={self.step_counter} | ação={action_taken} | fase={plan.lesson_phase} | bucket={plan.curriculum_bucket} | sucesso={result.success} | sigma={sigma_final:.2f} | pain={pain:.2f} | wellbeing={wellbeing:.2f}"
        self.recent_action_buckets.append(plan.curriculum_bucket)
        self.recent_action_buckets = self.recent_action_buckets[-8:]
        self.recent_signatures.append(plan.signature)
        self.recent_signatures = self.recent_signatures[-10:]

        return (
            f"Ação escolhida      : {plan.action_name} ({plan.target_a}" + (f", {plan.target_b}" if plan.target_b else "") + ")\n"
            f"Fase pedagógica     : {plan.lesson_phase}\n"
            f"Bucket curricular   : {plan.curriculum_bucket}\n"
            f"Motivo              : {plan.explanation}\n"
            f"Novidade residual   : {plan.novelty_residual:.4f}\n"
            f"Resultado           : {result.summary}\n"
            f"Aprendizados        : {', '.join(result.learned) if result.learned else '(nenhum)'}\n"
            f"Sigma antes         : {prev_sigma:.4f}\n"
            f"Sigma depois        : {sigma_final:.4f}\n"
            f"Pain signal         : {pain:.4f}\n"
            f"Wellbeing signal    : {wellbeing:.4f}"
        )

    def show_state(self) -> str:
        persistent = self.home.load_current_state()
        buckets = ", ".join(self.recent_action_buckets[-6:]) if self.recent_action_buckets else "(nenhum)"
        queue_size = len(self.experiment_queue)
        plan_label = f"P{self.current_plan_id:03d}" if self.current_plan_id > 0 else "(nenhum)"
        return (
            "ESTADO DARWIN NURSERY\n"
            f"- sigma persistente  : {persistent.sigma:.4f}\n"
            f"- sigma local        : {self.sigma_now():.4f}\n"
            f"- energia            : {persistent.energy:.4f}\n"
            f"- info_self          : {persistent.info_self:.4f}\n"
            f"- info_external      : {persistent.info_external:.4f}\n"
            f"- latência           : {persistent.latency:.4f}\n"
            f"- pain               : {persistent.pain_signal:.4f}\n"
            f"- wellbeing          : {persistent.wellbeing_signal:.4f}\n"
            f"- buckets recentes   : {buckets}\n"
            f"- plano atual        : {plan_label}\n"
            f"- microplano ativo   : {queue_size} etapa(s) restante(s)\n"
            f"- erro planner       : {self.last_planner_error or '(nenhum)'}\n"
            f"- último episódio    : {self.last_episode_summary or '(nenhum)'}"
        )

    def show_concepts(self) -> str:
        return "CONCEITOS LOCAIS HIDRATADOS (TENSÃO VIVA PERSISTENTE + CAUSALIDADE REFINADA)\n" + self.memory.snapshot()

    def recent_history(self, limit: int = 24) -> str:
        episodes = self.home.recent_episodes(limit=limit * 4)
        relevant = [
            e for e in episodes
            if str(e.get("module", "")).startswith("nursery_v")
        ]
        if not relevant:
            return "HISTÓRICO NURSERY\n(nenhum episódio de nursery salvo ainda)"
        lines = ["HISTÓRICO NURSERY"]
        for ep in relevant[:limit]:
            lines.append(
                f"- id={ep['id']} | módulo={ep['module']} | outcome={ep['outcome']} | "
                f"sigma {ep['sigma_before']:.2f}->{ep['sigma_after']:.2f} | {ep['lesson']}"
            )
        return "\n".join(lines)

    def hypotheses_summary(self) -> str:
        lines = ["HIPÓTESES"]
        if not self.pending_hypotheses:
            lines.append("(nenhuma hipótese pendente)")
            return "\n".join(lines)
        for hyp in self.pending_hypotheses[:12]:
            lines.append(f"- {hyp.hypothesis_id}: {hyp.upper_id} sobre {hyp.lower_id} -> {hyp.predicted_outcome} | base={hyp.basis}")
        return "\n".join(lines)

    def rules_summary(self) -> str:
        lines = ["REGRAS GENERALIZADAS"]
        rules = []
        for key, node in sorted(self.memory.nodes.items()):
            if key.startswith("rule:") and node.confidence >= 0.30:
                rules.append(f"- {key} [conf={node.confidence:.2f}]")
        if not rules:
            lines.append("(nenhuma regra generalizada ainda)")
        else:
            lines.extend(rules[:24])
        return "\n".join(lines)

    def lab_status(self) -> str:
        lines = ["LABORATÓRIO DE HIPÓTESES"]
        lines.append("- foco 1: formular previsões antes do teste")
        lines.append("- foco 2: validar previsões no ambiente")
        lines.append("- foco 3: atribuir causa à base, ao topo ou ao par")
        lines.append("- foco 4: tratar previsão uncertain como refinável")
        lines.append("- foco 5: aprender regras condicionais por tipo de topo")
        lines.append("- foco 6: agregar contexto em saldos líquidos")
        lines.append("- foco 7: detectar contextos ambíguos e atacar esses casos")
        lines.append("- foco 8: escolher experimentos pelo ganho de informação")
        lines.append("- foco 9: exigir diversidade de pares e famílias de contexto")
        lines.append("- foco 10: sair de contexto dominante quando necessário")
        lines.append("- foco 11: usar resgate em famílias não bloqueadas antes de exceções")
        lines.append("- foco 12: voltar a contexto antigo só quando houver motivo novo")
        lines.append("- foco 13: abrir retorno controlado sob bloqueio quando houver ambiguidade suficiente")
        lines.append("- foco 14: limitar retorno a uma sonda por microplano")
        lines.append("- foco 15: escolher a sonda com maior valor estratégico antes de entrar")
        lines.append("- foco 16: desempatar sondas fortes pelo conteúdo semântico da ambiguidade")
        lines.append("- foco 17: sintetizar um juízo único antes da sonda")
        lines.append("- foco 18: justificar a sonda por ambiguidade, sentido e saída")
        lines.append("- foco 19: registrar a última sonda justificada como memória explícita")
        lines.append("- foco 20: alinhar painéis ao que foi realmente escolhido")
        lines.append("- foco 21: aplicar boot por famílias no começo da sessão")
        lines.append("- foco 22: frear loop precoce no mesmo contexto dominante")
        lines.append("- foco 23: exigir contraste inicial entre famílias contextuais")
        lines.append("- foco 24: puxar mais cedo famílias não-rolling quando disponíveis")
        lines.append("- foco 25: transformar contradição forte em gatilho de reparo local")
        lines.append("- foco 26: revisar a vizinhança relacional do erro antes de seguir")
        lines.append("- foco 27: registrar baseline local logo após a contradição")
        lines.append("- foco 28: comparar o mapa local antes e depois do reparo")
        lines.append("- foco 29: tornar o efeito do reparo legível em regras e saldos")
        lines.append("- foco 30: sintetizar o delta em interpretação semântica compacta")
        lines.append("- foco 31: dizer o que enfraqueceu, fortaleceu ou ficou mais ambíguo")
        lines.append("- foco 32: ligar a leitura do reparo à próxima sonda escolhida")
        lines.append("- foco 33: dizer quando a nova sonda continua ou fecha a tensão do reparo")
        lines.append("- foco 34: registrar o desfecho da tensão depois da validação da sonda")
        lines.append("- foco 35: distinguir fechamento, manutenção ou reabertura da tensão")
        lines.append("- foco 36: impedir que consolidação adie a sonda que fecha o caso")
        lines.append("- foco 37: priorizar validação de sonda justificada antes de esfriar o conflito")
        lines.append("- foco 38: permitir sonda justificada mesmo sem bloqueio contextual ativo")
        lines.append("- foco 39: acionar sonda quando contradição recente ainda carregar tensão viva")
        lines.append("- foco 40: distinguir tensão viva de ambiguidade comum do laboratório")
        lines.append("- foco 41: medir pressão viva por recência, continuidade e ambiguidade local")
        lines.append("- foco 42: baixar o limiar operacional da sonda viva quando o reparo ainda está quente")
        lines.append("- foco 43: permitir que a sonda viva dispute prioridade mesmo com gate contextual leve")
        lines.append("- foco 44: sair de novo do contexto reaberto logo após a sonda")
        lines.append("- foco 45: distinguir retorno oportuno de recaída repetitiva")
        lines.append("- foco 46: penalizar repetição excessiva do mesmo par")
        lines.append("- foco 47: expandir o plano para vizinhos informativos")
        lines.append("- foco 48: impedir loop de infer sem exploração")
        lines.append("- foco 49: manter o plano mesmo após consolidar")
        lines.append("- foco 50: abstrair categorias relacionais do contexto")
        lines.append("- foco 51: arbitrar regras conflitantes")
        return "\n".join(lines)

    def curriculum_and_panels(self) -> str:
        return self.curriculum_status() + "\n\n" + self.comparison_summary() + "\n\n" + self.rules_summary() + "\n\n" + self.contextual_rules_summary() + "\n\n" + self.contextual_abstractions_summary() + "\n\n" + self.recent_context_families_summary() + "\n\n" + self.session_boot_summary() + "\n\n" + self.rotation_gate_summary() + "\n\n" + self.contextual_return_summary() + "\n\n" + self.live_tension_probe_summary() + "\n\n" + self.controlled_return_probe_summary() + "\n\n" + self.strategic_probe_selector_summary() + "\n\n" + self.semantic_probe_tiebreak_summary() + "\n\n" + self.probe_justification_summary() + "\n\n" + self.last_justified_probe_summary() + "\n\n" + self.probe_continuity_summary() + "\n\n" + self.live_tension_market_summary() + "\n\n" + self.active_tension_summary() + "\n\n" + self.archived_tensions_summary() + "\n\n" + self.live_tension_state_summary() + "\n\n" + self.tension_outcome_summary() + "\n\n" + self.probe_closure_priority_summary() + "\n\n" + self.contradiction_repair_summary() + "\n\n" + self.contradiction_effect_summary() + "\n\n" + self.contradiction_semantic_summary() + "\n\n" + self.controlled_return_budget_summary() + "\n\n" + self.experimental_plan_summary() + "\n\n" + self.active_experiment_queue_summary() + "\n\n" + self.ambiguous_contexts_summary() + "\n\n" + self.hypotheses_summary() + "\n\n" + self.lab_status()

    def reset_local_world(self) -> str:
        self.env = NurseryEnvironment()
        self.state = CognitiveState()
        self.step_counter = 0
        self.last_episode_summary = ""
        self.recent_action_buckets = []
        self.recent_signatures = []
        self.pending_hypotheses = []
        self.hypothesis_counter = 0
        self.experiment_queue = []
        self.last_experiment_plan_summary = ""
        self.current_plan_id = 0
        self.current_plan_step_index = 0
        self.plan_recent_pairs = []
        self.plan_recent_context_labels = []
        self.plan_recent_primary_families = []
        self.current_plan_return_budget = 0
        self.last_justified_probe = None
        self.last_justified_probe_judgment = ""
        self.last_contradiction_case = None
        self.contradiction_repair_budget = 0
        self.last_contradiction_baseline = None
        self.last_contradiction_delta_lines = []
        self.last_contradiction_semantic_lines = []
        self.last_probe_continuity_lines = []
        self.last_tension_outcome_lines = []
        self.last_contradiction_step = -10**9
        self.active_contradiction_repair_plan_id = 0
        self.live_tension_counter = 0
        self.live_tension_record = None
        self.init_live_tension_v46()
        self.memory = ConceptMemory()
        self.hydrate_memory_from_home()
        return "Mundo local do berçário reiniciado. A memória persistente foi reidratada."


class DarwinNurserySession:
    def __init__(self) -> None:
        self.home = DarwinHome("darwin_home")
        self.home.bootstrap()
        self.agent = DarwinNurseryAgent(self.home)

    def intro(self) -> None:
        print("=" * 72)
        print("DARWIN v61 — Nursery v47 (memória executiva persistente de tensões)")
        print("=" * 72)
        print("\nObjetivo desta fase:")
        print("  • persistir casos de tensão viva no banco como memória executiva")
        print("  • acumular pressão por recência, continuidade, ambiguidade e déficit de fechamento")
        print("  • manter erro → reparo → sonda → desfecho como narrativa viva até realmente fechar")
        print("\nMundo inicial:")
        print(self.agent.env.describe_world())
        print("\nComandos disponíveis:")
        print("  1 - passo autônomo do Darwin")
        print("  2 - mostrar mundo")
        print("  3 - mostrar estado")
        print("  4 - mostrar conceitos locais")
        print("  5 - mostrar histórico persistente do nursery")
        print("  6 - mostrar currículo, comparações, regras e hipóteses")
        print("  7 - exportar snapshot")
        print("  8 - reiniciar mundo local (mantendo memória persistente)")
        print("  9 - sair")
        print(" 10 - mostrar memória executiva de tensões abertas")
        print("10a - mostrar todas as tensões persistidas")
        print("10r - mostrar relatório de reidratação executiva")
        print("10c - mostrar compromisso executivo atual")
        print("10m - mostrar micro-rotina de resolução")
        print("10p - mostrar seletor de política da micro-rotina")
        print("10x - mostrar última comparação contextual")
        print("10i - mostrar influência contextual na hipótese")
        print("10h - mostrar linhagem contextual da hipótese")
        print("10z - mostrar relatório consolidado do ciclo cognitivo")
        print("10y - mostrar revisão de ciclos passados")


    def show_tension_dashboard(self, include_closed: bool = False, event_limit: int = 8) -> str:
        """
        Painel executivo interno da v47.

        Lê diretamente as tabelas persistentes:
        - tension_cases
        - tension_events
        - tension_probes
        - tension_outcomes

        Não altera o banco.
        """
        import sqlite3
        from pathlib import Path

        db_path = Path("darwin_home") / "darwin.db"
        lines: List[str] = ["MEMÓRIA EXECUTIVA DE TENSÕES — v47"]

        if not db_path.exists():
            lines.append(f"(banco não encontrado: {db_path})")
            return "\n".join(lines)

        def fmt(value, digits: int = 3) -> str:
            if value is None:
                return "-"
            try:
                return f"{float(value):.{digits}f}"
            except Exception:
                return str(value)

        def short(value, limit: int = 120) -> str:
            text = "" if value is None else str(value)
            return text if len(text) <= limit else text[: limit - 1] + "…"

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row

            table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='tension_cases'"
            ).fetchone()
            if table is None:
                lines.append("(schema v47 de tensões ainda não existe)")
                return "\n".join(lines)

            def count_table(name: str, where: str = "1=1") -> int:
                exists = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (name,),
                ).fetchone()
                if exists is None:
                    return 0
                row = conn.execute(f"SELECT COUNT(*) AS n FROM {name} WHERE {where}").fetchone()
                return int(row["n"]) if row else 0

            total = count_table("tension_cases")
            opened = count_table("tension_cases", "status NOT IN ('closed', 'archived', 'stale')")
            closed = count_table("tension_cases", "status='closed'")
            events = count_table("tension_events")
            probes = count_table("tension_probes")
            outcomes = count_table("tension_outcomes")

            lines.append("- casos totais:    " + str(total))
            lines.append("- casos abertos:   " + str(opened))
            lines.append("- casos fechados:  " + str(closed))
            lines.append("- eventos:         " + str(events))
            lines.append("- sondas:          " + str(probes))
            lines.append("- desfechos:       " + str(outcomes))
            lines.append("")

            where = "1=1" if include_closed else "status NOT IN ('closed', 'archived', 'stale')"
            rows = conn.execute(
                f"""
                SELECT tension_id, source_pair, status, outcome,
                       live_pressure, economic_priority, closure_deficit,
                       saturation_cost, updated_at, semantic_summary
                FROM tension_cases
                WHERE {where}
                ORDER BY
                    CASE WHEN status IN ('open', 'probing', 'reopened') THEN 0 ELSE 1 END,
                    economic_priority DESC,
                    live_pressure DESC,
                    updated_at DESC
                LIMIT 12
                """
            ).fetchall()

            lines.append("CASOS")
            if not rows:
                lines.append("(nenhum caso executivo para mostrar)")
            for row in rows:
                lines.append(
                    f"- {row['tension_id']} | {row['source_pair']} | "
                    f"status={row['status']} | outcome={row['outcome']} | "
                    f"pressão={fmt(row['live_pressure'])} | "
                    f"prioridade={fmt(row['economic_priority'])} | "
                    f"déficit={fmt(row['closure_deficit'])} | "
                    f"sat={fmt(row['saturation_cost'])}"
                )
                if row["semantic_summary"]:
                    lines.append(f"  resumo={short(row['semantic_summary'])}")

            lines.append("")
            lines.append(f"ÚLTIMOS {event_limit} EVENTOS")
            exists_events = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='tension_events'"
            ).fetchone()
            if exists_events is None:
                lines.append("(tabela tension_events ausente)")
            else:
                ev_rows = conn.execute(
                    """
                    SELECT tension_id, timestamp, event_type, status_after,
                           pressure_after, note
                    FROM tension_events
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (max(1, int(event_limit)),),
                ).fetchall()
                if not ev_rows:
                    lines.append("(nenhum evento)")
                for ev in ev_rows:
                    lines.append(
                        f"- {ev['timestamp']} | {ev['tension_id']} | "
                        f"{ev['event_type']} | status={ev['status_after']} | "
                        f"pressão={fmt(ev['pressure_after'])}"
                    )
                    if ev["note"]:
                        lines.append(f"  nota={short(ev['note'])}")

        return "\n".join(lines)

    def menu(self) -> str:
        return input("\nEscolha: ").strip().lower()

    def run(self) -> None:
        self.intro()
        while True:
            choice = self.menu()
            if choice == "1":
                plan = self.agent.choose_autonomous_action()
                print("\n" + "=" * 72)
                print("PASSO AUTÔNOMO")
                print("=" * 72)
                print(self.agent.execute_action(plan))
            elif choice == "2":
                print("\n" + "=" * 72)
                print("MUNDO")
                print("=" * 72)
                print(self.agent.env.describe_world())
            elif choice == "3":
                print("\n" + "=" * 72)
                print(self.agent.show_state())
            elif choice == "4":
                print("\n" + "=" * 72)
                print(self.agent.show_concepts())
            elif choice == "5":
                print("\n" + "=" * 72)
                print(self.agent.recent_history(limit=24))
            elif choice == "6":
                print("\n" + "=" * 72)
                print(self.agent.curriculum_and_panels())
            elif choice == "7":
                snapshot = self.home.export_snapshot()
                print(f"\nSnapshot exportado em: {snapshot}")
            elif choice == "8":
                print("\n" + self.agent.reset_local_world())
            elif choice in {"10", "tensoes", "tensões", "tension"}:
                print("\n" + "=" * 72)
                print(self.show_tension_dashboard(include_closed=False))
            elif choice in {"10a", "tensoes all", "tensões all", "tension all"}:
                print("\n" + "=" * 72)
                print(self.show_tension_dashboard(include_closed=True))
            elif choice in {"10r", "rehydrate", "reidratar", "reidratacao", "reidratação"}:
                print("\n" + "=" * 72)
                print(self.agent.v47_rehydration_summary())
            elif choice in {"10c", "commitment", "compromisso"}:
                print("\n" + "=" * 72)
                print(self.agent.executive_commitment_summary())
            elif choice in {"10m", "micro", "rotina", "routine"}:
                print("\n" + "=" * 72)
                print(self.agent.tension_resolution_routine_summary())
            elif choice in {"10p", "policy", "politica", "política"}:
                print("\n" + "=" * 72)
                print(self.agent.tension_resolution_policy_summary())
            elif choice in {"10x", "context", "comparar", "compare"}:
                print("\n" + "=" * 72)
                print(self.agent.context_comparison_summary())
            elif choice in {"10i", "influence", "influencia", "influência"}:
                print("\n" + "=" * 72)
                print(self.agent.prediction_influence_summary())
            elif choice in {"10h", "lineage", "linhagem", "hypothesis_lineage"}:
                print("\n" + "=" * 72)
                print(self.agent.hypothesis_lineage_summary())
            elif choice in {"10z", "cycle", "ciclo", "relatorio", "relatório"}:
                print("\n" + "=" * 72)
                print(self.agent.cognitive_cycle_report_summary())
            elif choice in {"10y", "review", "revisao", "revisão", "memoria", "memória"}:
                print("\n" + "=" * 72)
                print(self.agent.cycle_memory_review_summary())
            elif choice in {"9", "sair", "exit", "quit"}:
                print("\nEncerrando Darwin Nursery v47.")
                self.home.close()
                break
            else:
                print("Comando inválido. Use 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10a, 10r, 10c, 10m, 10p, 10x, 10i, 10h, 10z ou 10y.")


if __name__ == "__main__":
    DarwinNurserySession().run()
