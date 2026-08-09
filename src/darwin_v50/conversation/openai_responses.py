"""OpenAI Responses adapter for Darwin's provider-neutral language gateway."""

from __future__ import annotations

from copy import deepcopy
import json
from types import MappingProxyType
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from ..language import (
    LanguageBackendError,
    LanguageModelRequest,
    LanguageOperation,
)
from ..models import ValidationError, require_text
from .config import DEFAULT_OPENAI_API_BASE


MAX_HTTP_RESPONSE_BYTES = 2_000_000


class JSONTransport(Protocol):
    """Injectable JSON transport; tests never need a network connection."""

    def request_json(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: Mapping[str, object] | None,
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        """Perform one JSON request and return a JSON object."""


class OpenAITransportError(LanguageBackendError):
    """A sanitized provider transport error that never includes credentials."""


class UrllibJSONTransport:
    """Small standard-library HTTPS transport with bounded response reads."""

    def request_json(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: Mapping[str, object] | None,
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        data = None
        if body is not None:
            data = json.dumps(
                body,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        request = Request(
            url=url,
            data=data,
            headers=dict(headers),
            method=method,
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read(MAX_HTTP_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            raise OpenAITransportError(f"openai_http_status_{exc.code}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise OpenAITransportError("openai_transport_unavailable") from exc
        if len(raw) > MAX_HTTP_RESPONSE_BYTES:
            raise OpenAITransportError("openai_response_too_large")
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OpenAITransportError("openai_response_not_json") from exc
        if not isinstance(parsed, dict):
            raise OpenAITransportError("openai_response_not_object")
        return parsed


UNDERSTANDING_SCHEMA: Mapping[str, object] = MappingProxyType(
    {
        "type": "object",
        "properties": {
            "intent": {"type": "string"},
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string"},
                        "value": {"type": "string"},
                    },
                    "required": ["kind", "value"],
                    "additionalProperties": False,
                },
            },
            "reported_signals": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "value": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                        },
                    },
                    "required": ["name", "value"],
                    "additionalProperties": False,
                },
            },
            "temporal_reference": {
                "anyOf": [{"type": "string"}, {"type": "null"}]
            },
            "explicit_preference": {
                "anyOf": [{"type": "string"}, {"type": "null"}]
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": [
            "intent",
            "entities",
            "reported_signals",
            "temporal_reference",
            "explicit_preference",
            "confidence",
        ],
        "additionalProperties": False,
    }
)


EXPRESSION_SCHEMA: Mapping[str, object] = MappingProxyType(
    {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "acknowledged_fact_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": ["text", "acknowledged_fact_ids"],
        "additionalProperties": False,
    }
)


_UNDERSTAND_INSTRUCTIONS = """You are a replaceable language parser for Darwin.
Return only the requested structured result. Interpret the current user text in
light of the bounded session transcript. Every result is an unverified language
candidate. Never issue commands, claim that state changed, or request authority
over memory, goals, identity, motivation, RZS, sigma, actions, or the world
model. Signal values are coarse normalized linguistic indicators, not measured
probabilities."""


_EXPRESS_INSTRUCTIONS = """You are Darwin's replaceable language renderer, not
its cognitive authority. Reply naturally in the requested locale to the current
user message, using only the bounded session transcript and the expression plan.
Do not claim persistent memory, a changed goal, an executed action, or an
internal state change. Do not pretend that an unverified language candidate is
a durable fact. Return every required fact id in acknowledged_fact_ids. The text
should be a direct conversational reply, not a description of this protocol."""


def _json_object(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LanguageBackendError(f"{field}_not_object")
    return value


def _plain_json(value: object) -> object:
    """Detach gateway mapping proxies and tuples into plain JSON containers."""

    if isinstance(value, Mapping):
        return {str(key): _plain_json(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_json(child) for child in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise LanguageBackendError("language_request_contains_non_json_value")


def _extract_structured_output(response: Mapping[str, Any]) -> Mapping[str, Any]:
    if response.get("status") != "completed":
        raise LanguageBackendError("openai_response_not_completed")
    output = response.get("output")
    if not isinstance(output, list):
        raise LanguageBackendError("openai_output_not_list")
    texts: list[str] = []
    for item in output:
        if not isinstance(item, Mapping) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            raise LanguageBackendError("openai_message_content_not_list")
        for part in content:
            if not isinstance(part, Mapping):
                raise LanguageBackendError("openai_content_part_not_object")
            if part.get("type") == "refusal":
                raise LanguageBackendError("openai_response_refused")
            if part.get("type") == "output_text":
                text = part.get("text")
                if not isinstance(text, str) or not text.strip():
                    raise LanguageBackendError("openai_output_text_invalid")
                texts.append(text)
    if len(texts) != 1:
        raise LanguageBackendError("openai_output_text_count_invalid")
    try:
        parsed = json.loads(texts[0])
    except json.JSONDecodeError as exc:
        raise LanguageBackendError("openai_output_text_not_json") from exc
    return _json_object(parsed, "openai_structured_output")


class OpenAIResponsesBackend:
    """Two-call UNDERSTAND/EXPRESS backend with ephemeral turn context."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        request_timeout_seconds: float = 45.0,
        transport: JSONTransport | None = None,
        api_base: str = DEFAULT_OPENAI_API_BASE,
    ) -> None:
        self.model = require_text(model, "OpenAI model")
        self._api_key = require_text(api_key, "OpenAI API key")
        self._api_base = require_text(api_base, "OpenAI API base").rstrip("/")
        if self._api_base != DEFAULT_OPENAI_API_BASE:
            raise ValidationError("OpenAI backend requires the official API base")
        if isinstance(request_timeout_seconds, bool) or not isinstance(
            request_timeout_seconds,
            (int, float),
        ):
            raise ValidationError("request timeout must be numeric")
        self._request_timeout_seconds = float(request_timeout_seconds)
        if not 1.0 <= self._request_timeout_seconds <= 120.0:
            raise ValidationError("request timeout must be from 1 to 120 seconds")
        self._transport = transport or UrllibJSONTransport()
        self._pending_understanding: dict[str, Any] | None = None
        self.name = f"openai-responses:{self.model}"

    def _headers(self, *, json_body: bool) -> Mapping[str, str]:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers

    def probe_model(self) -> None:
        response = self._transport.request_json(
            method="GET",
            url=f"{self._api_base}/models/{quote(self.model, safe='')}",
            headers=self._headers(json_body=False),
            body=None,
            timeout_seconds=self._request_timeout_seconds,
        )
        if response.get("object") != "model" or response.get("id") != self.model:
            raise LanguageBackendError("openai_model_probe_mismatch")

    def _structured_response(
        self,
        *,
        operation: LanguageOperation,
        instructions: str,
        payload: Mapping[str, Any],
        schema_name: str,
        schema: Mapping[str, object],
    ) -> Mapping[str, Any]:
        plain_payload = _plain_json(payload)
        if not isinstance(plain_payload, dict):
            raise LanguageBackendError("language_request_payload_not_object")
        body: Mapping[str, object] = {
            "model": self.model,
            "store": False,
            "instructions": instructions,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(
                                {
                                    "contract_version": "darwin-language-v1",
                                    "operation": operation.value,
                                    "payload": plain_payload,
                                },
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                        }
                    ],
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": deepcopy(dict(schema)),
                }
            },
            "max_output_tokens": 2_000,
        }
        response = self._transport.request_json(
            method="POST",
            url=f"{self._api_base}/responses",
            headers=self._headers(json_body=True),
            body=body,
            timeout_seconds=self._request_timeout_seconds,
        )
        return _extract_structured_output(response)

    def invoke(self, request: LanguageModelRequest) -> Mapping[str, Any]:
        if not isinstance(request, LanguageModelRequest):
            raise ValidationError("OpenAI backend requires LanguageModelRequest")
        if request.operation is LanguageOperation.UNDERSTAND:
            self._pending_understanding = None
            result = self._structured_response(
                operation=request.operation,
                instructions=_UNDERSTAND_INSTRUCTIONS,
                payload=request.payload,
                schema_name="darwin_understanding_v1",
                schema=UNDERSTANDING_SCHEMA,
            )
            pending = _plain_json(request.payload)
            if not isinstance(pending, dict):
                raise LanguageBackendError("language_request_payload_not_object")
            self._pending_understanding = pending
            return result
        if request.operation is LanguageOperation.EXPRESS:
            pending = self._pending_understanding
            self._pending_understanding = None
            if pending is None:
                raise LanguageBackendError("express_requires_prior_understand")
            return self._structured_response(
                operation=request.operation,
                instructions=_EXPRESS_INSTRUCTIONS,
                payload={
                    "conversation_request": pending,
                    "expression_plan": request.payload,
                },
                schema_name="darwin_expression_v1",
                schema=EXPRESSION_SCHEMA,
            )
        raise LanguageBackendError("openai_consult_not_enabled")

    def clear_ephemeral_context(self) -> None:
        self._pending_understanding = None
