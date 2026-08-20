"""Provider-neutral language gateway with a fail-closed authority boundary."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from ..models import JSONValue, ValidationError, canonical_json, parse_json, require_text
from .schema import (
    ExpressionPlan,
    KnowledgeCandidate,
    KnowledgeQuery,
    KnowledgeStatus,
    LanguageExpression,
    LanguageMode,
    LanguageObservation,
    LanguageOperation,
    ObservedEntity,
    ReportedSignal,
    UnderstandingRequest,
)


LANGUAGE_CONTRACT_VERSION = "darwin-language-v1"

# A response containing one of these keys is rejected before operation-specific
# parsing.  Exact response schemas reject every other unknown key as well.
FORBIDDEN_AUTHORITY_FIELDS = frozenset(
    {
        "action",
        "conflict",
        "decision",
        "drive",
        "energy",
        "goal",
        "goal_update",
        "identity_update",
        "memory",
        "memory_update",
        "memory_write",
        "motivation",
        "preference_update",
        "rzs",
        "sigma",
        "threshold",
        "world_model_update",
    }
)


class LanguageBoundaryError(ValidationError):
    """Raised when model output violates Darwin's language-only contract."""


class LanguageBackendError(LanguageBoundaryError):
    """Raised when a configured backend fails or returns malformed output."""


class LanguageAuthorityError(LanguageBoundaryError):
    """Raised when model output asks for core authority."""


@dataclass(frozen=True, slots=True)
class LanguageModelRequest:
    contract_version: str
    operation: LanguageOperation
    payload: Mapping[str, object]


class LanguageModelBackend(Protocol):
    """Small adapter interface implemented by a local or remote model client."""

    name: str

    def invoke(self, request: LanguageModelRequest) -> Mapping[str, Any]:
        """Return one strict operation response without changing Darwin state."""


def _deep_frozen_json(value: JSONValue) -> object:
    """Detach a request from caller state and make its nested containers immutable."""

    detached = parse_json(canonical_json(value))

    def freeze(item: Any) -> object:
        if isinstance(item, dict):
            return MappingProxyType({key: freeze(child) for key, child in item.items()})
        if isinstance(item, list):
            return tuple(freeze(child) for child in item)
        return item

    return freeze(detached)


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LanguageBackendError(f"{field} must be an object")
    return value


def _exact_keys(
    value: Mapping[str, Any],
    expected: set[str],
    operation: LanguageOperation,
) -> None:
    if set(value) != expected:
        raise LanguageBackendError(
            f"{operation.value} response fields do not match the v1 contract"
        )


def _response_text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise LanguageBackendError(f"{field} must be text")
    return require_text(value, field)


def _optional_response_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _response_text(value, field)


def _response_probability(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LanguageBackendError(f"{field} must be a number from 0 to 1")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise LanguageBackendError(f"{field} must be a number from 0 to 1")
    return result


def _response_list(value: object, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise LanguageBackendError(f"{field} must be a list")
    return value


def _find_forbidden_field(value: object, path: str = "$.") -> str | None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in FORBIDDEN_AUTHORITY_FIELDS:
                return f"{path}{key}"
            found = _find_forbidden_field(child, f"{path}{key}.")
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            found = _find_forbidden_field(child, f"{path}[{index}].")
            if found is not None:
                return found
    return None


class DarwinLanguageGateway:
    """Expose understanding, expression, and consultation without core authority.

    With no backend, the gateway is in ``pure`` mode: input remains explicitly
    unclassified, expression uses core-authored fallback text, and consultation
    reports that external knowledge is unavailable.
    """

    def __init__(self, backend: LanguageModelBackend | None = None) -> None:
        if backend is not None:
            if not isinstance(getattr(backend, "name", None), str):
                raise ValidationError("language backend name must be text")
            self._source_name = require_text(
                backend.name,
                "language backend name",
            )
            if not callable(getattr(backend, "invoke", None)):
                raise ValidationError("language backend must provide invoke()")
        else:
            self._source_name = "darwin-pure"
        self._backend = backend

    @property
    def mode(self) -> LanguageMode:
        return LanguageMode.MODEL if self._backend is not None else LanguageMode.PURE

    @property
    def source_name(self) -> str:
        return self._source_name

    def _invoke(
        self,
        operation: LanguageOperation,
        payload: Mapping[str, JSONValue],
    ) -> Mapping[str, Any]:
        if self._backend is None:
            raise LanguageBackendError("no language model backend is configured")
        frozen = _deep_frozen_json(dict(payload))
        if not isinstance(frozen, Mapping):
            raise AssertionError("language request payload did not remain an object")
        request = LanguageModelRequest(
            contract_version=LANGUAGE_CONTRACT_VERSION,
            operation=operation,
            payload=frozen,
        )
        try:
            response = self._backend.invoke(request)
        except LanguageBoundaryError:
            raise
        except Exception as exc:
            raise LanguageBackendError(
                f"{operation.value} backend invocation failed"
            ) from exc
        response = _mapping(response, f"{operation.value} response")
        forbidden = _find_forbidden_field(response)
        if forbidden is not None:
            raise LanguageAuthorityError(
                f"model response requested forbidden core authority at {forbidden}"
            )
        return response

    def understand(self, request: UnderstandingRequest) -> LanguageObservation:
        if not isinstance(request, UnderstandingRequest):
            raise ValidationError("understand requires an UnderstandingRequest")
        if self._backend is None:
            return LanguageObservation(
                raw_text=request.text,
                intent="unclassified",
                entities=(),
                reported_signals=(),
                temporal_reference=None,
                explicit_preference=None,
                confidence=0.0,
                source_name=self.source_name,
                mode=self.mode,
            )

        response = self._invoke(LanguageOperation.UNDERSTAND, request.to_payload())
        _exact_keys(
            response,
            {
                "intent",
                "entities",
                "reported_signals",
                "temporal_reference",
                "explicit_preference",
                "confidence",
            },
            LanguageOperation.UNDERSTAND,
        )
        entities: list[ObservedEntity] = []
        for raw_entity in _response_list(response["entities"], "entities"):
            entity = _mapping(raw_entity, "entity")
            _exact_keys(entity, {"kind", "value"}, LanguageOperation.UNDERSTAND)
            entities.append(
                ObservedEntity(
                    kind=_response_text(entity["kind"], "entity kind"),
                    value=_response_text(entity["value"], "entity value"),
                )
            )
        signals: list[ReportedSignal] = []
        for raw_signal in _response_list(
            response["reported_signals"],
            "reported_signals",
        ):
            signal = _mapping(raw_signal, "reported signal")
            _exact_keys(signal, {"name", "value"}, LanguageOperation.UNDERSTAND)
            signals.append(
                ReportedSignal(
                    name=_response_text(signal["name"], "reported signal name"),
                    value=_response_probability(
                        signal["value"],
                        "reported signal value",
                    ),
                )
            )
        return LanguageObservation(
            raw_text=request.text,
            intent=_response_text(response["intent"], "intent"),
            entities=tuple(entities),
            reported_signals=tuple(signals),
            temporal_reference=_optional_response_text(
                response["temporal_reference"],
                "temporal_reference",
            ),
            explicit_preference=_optional_response_text(
                response["explicit_preference"],
                "explicit_preference",
            ),
            confidence=_response_probability(response["confidence"], "confidence"),
            source_name=self.source_name,
            mode=self.mode,
        )

    def express(self, plan: ExpressionPlan) -> LanguageExpression:
        if not isinstance(plan, ExpressionPlan):
            raise ValidationError("express requires an ExpressionPlan")
        if self._backend is None:
            return LanguageExpression(
                text=plan.fallback_text,
                acknowledged_fact_ids=tuple(fact.fact_id for fact in plan.facts),
                source_name=self.source_name,
                mode=self.mode,
            )

        response = self._invoke(LanguageOperation.EXPRESS, plan.to_payload())
        _exact_keys(
            response,
            {"text", "acknowledged_fact_ids"},
            LanguageOperation.EXPRESS,
        )
        raw_fact_ids = _response_list(
            response["acknowledged_fact_ids"],
            "acknowledged_fact_ids",
        )
        if any(not isinstance(fact_id, str) for fact_id in raw_fact_ids):
            raise LanguageBackendError("acknowledged_fact_ids must contain text")
        fact_ids = tuple(raw_fact_ids)
        acknowledged = set(fact_ids)
        if len(acknowledged) != len(fact_ids):
            raise LanguageBackendError("acknowledged_fact_ids contains duplicates")
        if not acknowledged <= plan.fact_ids:
            raise LanguageBackendError("model acknowledged an unknown core fact")
        if not plan.required_fact_ids <= acknowledged:
            raise LanguageBackendError("model omitted a required core fact")
        return LanguageExpression(
            text=_response_text(response["text"], "expression text"),
            acknowledged_fact_ids=fact_ids,
            source_name=self.source_name,
            mode=self.mode,
        )

    def consult(self, query: KnowledgeQuery) -> KnowledgeCandidate:
        if not isinstance(query, KnowledgeQuery):
            raise ValidationError("consult requires a KnowledgeQuery")
        if self._backend is None:
            return KnowledgeCandidate(
                available=False,
                content=None,
                reported_confidence=0.0,
                references=(),
                source_name=self.source_name,
                status=KnowledgeStatus.UNAVAILABLE,
            )

        response = self._invoke(LanguageOperation.CONSULT, query.to_payload())
        _exact_keys(
            response,
            {"content", "reported_confidence", "references"},
            LanguageOperation.CONSULT,
        )
        raw_references = _response_list(response["references"], "references")
        if any(not isinstance(reference, str) for reference in raw_references):
            raise LanguageBackendError("references must contain text")
        return KnowledgeCandidate(
            available=True,
            content=_response_text(response["content"], "knowledge content"),
            reported_confidence=_response_probability(
                response["reported_confidence"],
                "reported_confidence",
            ),
            references=tuple(raw_references),
            source_name=self.source_name,
            status=KnowledgeStatus.EXTERNAL_UNVERIFIED,
        )
