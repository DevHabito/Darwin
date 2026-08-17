"""Portable, provider-free language seed behind Darwin's language boundary."""

from __future__ import annotations

from copy import deepcopy
import json
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ..language import (
    LANGUAGE_CONTRACT_VERSION,
    LanguageBackendError,
    LanguageModelRequest,
    LanguageOperation,
)
from ..models import ValidationError, require_text
from .openai_responses import EXPRESSION_SCHEMA, UNDERSTANDING_SCHEMA


LOCAL_SEED_CONTRACT = "darwin-local-seed-v1"
MAX_LOCAL_RESPONSE_BYTES = 2_000_000
MAX_LOCAL_PROMPT_CHARACTERS = 14_000
MAX_LOCAL_TEMPLATE_CHARACTERS = 18_000
MAX_LOCAL_OUTPUT_TOKENS = 1_000
REGISTERED_CONTEXT_TOKENS = 4_096
LOCAL_NUMERIC_LEVELS = tuple((0.0, 0.25, 0.5, 0.75, 1.0))
LOCAL_CONTROL_MARKERS = frozenset(
    (
        "<|endoftext|>",
        "<|im_start|>",
        "<|im_end|>",
        "<think>",
        "</think>",
        "<tool_call>",
        "</tool_call>",
        "<tool_response>",
        "</tool_response>",
    )
)


_UNDERSTAND_INSTRUCTIONS = """You are Darwin's small, replaceable local
language parser. Interpret the current Brazilian Portuguese user text using the
bounded temporary transcript. Return only the requested JSON object. The result
is an unverified language candidate, not a command or accepted memory. Never
request or claim authority over memory, goals, identity, motivation, RZS,
sigma, actions, or Darwin's world model. Do not include reasoning text."""


_EXPRESS_INSTRUCTIONS = """You are Darwin's small, replaceable local language
renderer, not Darwin's cognitive authority. Reply naturally in the requested
locale using only the current conversation request and Darwin's expression
plan. Return only the requested JSON object. Do not claim persistent memory,
goal changes, actions, or internal state changes. Acknowledge every required
fact id. Do not describe this protocol unless the user asks. Do not include
reasoning text."""


class StructuredLocalTransport(Protocol):
    """Runtime-neutral constrained inference used by desktop and mobile hosts."""

    def probe(self, *, model: str, context_tokens: int) -> None:
        """Fail unless the exact local model and context are available."""

    def generate_structured(
        self,
        *,
        model: str,
        instructions: str,
        payload: Mapping[str, object],
        schema_name: str,
        schema: Mapping[str, object],
        max_output_tokens: int,
    ) -> Mapping[str, Any]:
        """Generate one schema-constrained object without external authority."""


class LocalSeedTransportError(LanguageBackendError):
    """Sanitized local inference transport failure."""


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        return None


def _plain_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _plain_json(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_json(child) for child in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise LanguageBackendError("local_request_contains_non_json_value")


def _reject_control_markers(value: object) -> None:
    if isinstance(value, str):
        if any(marker in value for marker in LOCAL_CONTROL_MARKERS):
            raise LanguageBackendError("local_control_token_rejected")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            _reject_control_markers(key)
            _reject_control_markers(child)
        return
    if isinstance(value, (list, tuple)):
        for child in value:
            _reject_control_markers(child)


def _object(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LocalSeedTransportError(f"{field}_not_object")
    return value


def _array(value: object, field: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise LocalSeedTransportError(f"{field}_not_array")
    return value


def _schema_object(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RuntimeError(f"shared understanding schema changed at {field}")
    return value


def _build_local_understanding_schema() -> Mapping[str, object]:
    schema = deepcopy(dict(UNDERSTANDING_SCHEMA))
    properties = _schema_object(schema.get("properties"), "properties")
    reported = _schema_object(
        properties.get("reported_signals"),
        "reported_signals",
    )
    reported_items = _schema_object(
        reported.get("items"),
        "reported_signals.items",
    )
    reported_properties = _schema_object(
        reported_items.get("properties"),
        "reported_signals.items.properties",
    )
    value_schema = _schema_object(
        reported_properties.get("value"),
        "reported_signals.items.properties.value",
    )
    confidence_schema = _schema_object(
        properties.get("confidence"),
        "confidence",
    )
    expected_continuous_node = {
        "type": "number",
        "minimum": 0,
        "maximum": 1,
    }
    for field, node in (
        ("reported_signals.items.properties.value", value_schema),
        ("confidence", confidence_schema),
    ):
        if node != expected_continuous_node:
            raise RuntimeError(f"shared understanding schema changed at {field}")
        node.clear()
        node.update(
            {
                "type": "number",
                "enum": list(LOCAL_NUMERIC_LEVELS),
            }
        )
    return MappingProxyType(schema)


LOCAL_UNDERSTANDING_SCHEMA = _build_local_understanding_schema()


def _is_local_numeric_level(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and value in LOCAL_NUMERIC_LEVELS
    )


def _reject_unregistered_local_numeric_levels(result: Mapping[str, Any]) -> None:
    confidence = result.get("confidence")
    if confidence is not None and not _is_local_numeric_level(confidence):
        raise LanguageBackendError("local_numeric_level_invalid")
    signals = result.get("reported_signals")
    if not isinstance(signals, list):
        return
    for signal in signals:
        if not isinstance(signal, Mapping) or "value" not in signal:
            continue
        if not _is_local_numeric_level(signal["value"]):
            raise LanguageBackendError("local_numeric_level_invalid")


def _registered_loopback_origin(endpoint: str) -> str:
    value = require_text(endpoint, "local inference endpoint")
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValidationError("local inference endpoint port is invalid") from exc
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or port is None
        or not 1_024 <= port <= 65_535
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.netloc != f"127.0.0.1:{port}"
    ):
        raise ValidationError(
            "local inference endpoint must be exact http://127.0.0.1:<port>"
        )
    return f"http://127.0.0.1:{port}"


class LoopbackJSONTransport:
    """Bounded JSON transport that refuses redirects away from loopback."""

    def __init__(self) -> None:
        self._opener = build_opener(_RejectRedirects())

    def request_json(
        self,
        *,
        method: str,
        url: str,
        body: Mapping[str, object] | None,
        timeout_seconds: float,
        headers: Mapping[str, str] | None = None,
    ) -> Mapping[str, Any]:
        parsed = urlsplit(url)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1":
            raise LocalSeedTransportError("local_transport_non_loopback_url")
        data = None
        request_headers = {"Accept": "application/json"}
        if headers is not None:
            for name, value in headers.items():
                if not isinstance(name, str) or not isinstance(value, str):
                    raise ValidationError("local transport headers must be text")
                request_headers[name] = value
        if body is not None:
            data = json.dumps(
                body,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request = Request(url=url, data=data, headers=request_headers, method=method)
        try:
            with self._opener.open(request, timeout=timeout_seconds) as response:
                if response.geturl() != url:
                    raise LocalSeedTransportError("local_transport_redirect_rejected")
                raw = response.read(MAX_LOCAL_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            if 300 <= exc.code < 400:
                raise LocalSeedTransportError(
                    "local_transport_redirect_rejected"
                ) from exc
            raise LocalSeedTransportError(f"local_http_status_{exc.code}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise LocalSeedTransportError("local_transport_unavailable") from exc
        if len(raw) > MAX_LOCAL_RESPONSE_BYTES:
            raise LocalSeedTransportError("local_response_too_large")
        try:
            parsed_body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LocalSeedTransportError("local_response_not_json") from exc
        return _object(parsed_body, "local_response")


class LlamaCppServerTransport:
    """Desktop harness for one explicitly launched loopback llama.cpp server."""

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        timeout_seconds: float = 120.0,
        json_transport: LoopbackJSONTransport | None = None,
    ) -> None:
        self.endpoint = _registered_loopback_origin(endpoint)
        self._api_key = require_text(api_key, "local API key")
        if not 32 <= len(self._api_key) <= 512:
            raise ValidationError("local API key must contain 32 to 512 characters")
        if isinstance(timeout_seconds, bool) or not isinstance(
            timeout_seconds,
            (int, float),
        ):
            raise ValidationError("local request timeout must be numeric")
        self.timeout_seconds = float(timeout_seconds)
        if not 1.0 <= self.timeout_seconds <= 300.0:
            raise ValidationError("local request timeout must be from 1 to 300 seconds")
        self._json_transport = json_transport or LoopbackJSONTransport()

    def _request(
        self,
        *,
        method: str,
        path: str,
        body: Mapping[str, object] | None = None,
    ) -> Mapping[str, Any]:
        if not path.startswith("/") or "//" in path or "?" in path or "#" in path:
            raise ValidationError("local inference path is invalid")
        return self._json_transport.request_json(
            method=method,
            url=self.endpoint + path,
            body=body,
            timeout_seconds=self.timeout_seconds,
            headers={"Authorization": f"Bearer {self._api_key}"},
        )

    def probe(self, *, model: str, context_tokens: int) -> None:
        configured_model = require_text(model, "local model")
        if context_tokens != REGISTERED_CONTEXT_TOKENS:
            raise ValidationError("local context must equal the registered 4096 tokens")
        models = self._request(method="GET", path="/v1/models")
        entries = _array(models.get("data"), "local_models_data")
        identities = []
        for entry in entries:
            mapped = _object(entry, "local_model_entry")
            identity = mapped.get("id")
            if isinstance(identity, str):
                identities.append(identity)
        if identities != [configured_model]:
            raise LocalSeedTransportError("local_model_probe_mismatch")

        props = self._request(method="GET", path="/props")
        defaults = _object(
            props.get("default_generation_settings"),
            "local_default_generation_settings",
        )
        if defaults.get("n_ctx") != context_tokens:
            raise LocalSeedTransportError("local_context_probe_mismatch")
        if props.get("total_slots") != 1:
            raise LocalSeedTransportError("local_parallel_slots_not_one")
        modalities = _object(props.get("modalities"), "local_modalities")
        if modalities.get("vision") is not False:
            raise LocalSeedTransportError("local_vision_must_be_disabled")
        build_info = props.get("build_info")
        if not isinstance(build_info, str) or not build_info.strip():
            raise LocalSeedTransportError("local_build_identity_missing")

    def generate_structured(
        self,
        *,
        model: str,
        instructions: str,
        payload: Mapping[str, object],
        schema_name: str,
        schema: Mapping[str, object],
        max_output_tokens: int,
    ) -> Mapping[str, Any]:
        configured_model = require_text(model, "local model")
        system_text = require_text(instructions, "local model instructions")
        schema_id = require_text(schema_name, "local schema name")
        if max_output_tokens != MAX_LOCAL_OUTPUT_TOKENS:
            raise ValidationError("local output limit differs from registered limit")
        plain_payload = _plain_json(payload)
        if not isinstance(plain_payload, dict):
            raise LanguageBackendError("local_request_payload_not_object")
        _reject_control_markers(plain_payload)
        user_text = json.dumps(
            plain_payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if len(system_text) + len(user_text) > MAX_LOCAL_PROMPT_CHARACTERS:
            raise LanguageBackendError("local_prompt_exceeds_registered_limit")
        template_body: Mapping[str, object] = {
            "messages": [
                {"role": "system", "content": system_text},
                {"role": "user", "content": user_text},
            ],
            "add_generation_prompt": True,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        template_response = self._request(
            method="POST",
            path="/apply-template",
            body=template_body,
        )
        prompt = template_response.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise LocalSeedTransportError("local_template_prompt_invalid")
        if len(prompt) > MAX_LOCAL_TEMPLATE_CHARACTERS:
            raise LocalSeedTransportError("local_template_prompt_too_large")

        body: Mapping[str, object] = {
            "prompt": prompt,
            "stream": False,
            "temperature": 0.0,
            "n_predict": max_output_tokens,
            "json_schema": deepcopy(dict(schema)),
        }
        response = self._request(
            method="POST",
            path="/completion",
            body=body,
        )
        if response.get("stop") is not True:
            raise LocalSeedTransportError("local_completion_not_finished")
        if response.get("truncated") is True or response.get("stopped_limit") is True:
            raise LocalSeedTransportError("local_completion_truncated")
        predicted = response.get("tokens_predicted")
        if (
            isinstance(predicted, bool)
            or not isinstance(predicted, int)
            or not 0 <= predicted <= max_output_tokens
        ):
            raise LocalSeedTransportError("local_completion_token_count_invalid")
        content = response.get("content")
        if not isinstance(content, str) or not content.strip():
            raise LocalSeedTransportError("local_completion_content_invalid")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LocalSeedTransportError("local_completion_not_json") from exc
        return _object(parsed, "local_structured_output")


class PortableLocalLanguageBackend:
    """Two-stage language backend with no provider, memory, or action handle."""

    def __init__(
        self,
        *,
        model: str,
        transport: StructuredLocalTransport,
        context_tokens: int = REGISTERED_CONTEXT_TOKENS,
    ) -> None:
        self.model = require_text(model, "local model")
        if context_tokens != REGISTERED_CONTEXT_TOKENS:
            raise ValidationError("local context must equal the registered 4096 tokens")
        if not callable(getattr(transport, "probe", None)) or not callable(
            getattr(transport, "generate_structured", None)
        ):
            raise ValidationError("local structured transport is invalid")
        self._transport = transport
        self._context_tokens = context_tokens
        self._pending_understanding: dict[str, Any] | None = None
        self.name = f"portable-local-seed:{self.model}"

    def probe_model(self) -> None:
        self._transport.probe(
            model=self.model,
            context_tokens=self._context_tokens,
        )

    def _generate(
        self,
        *,
        operation: LanguageOperation,
        instructions: str,
        payload: Mapping[str, object],
        schema_name: str,
        schema: Mapping[str, object],
    ) -> Mapping[str, Any]:
        request_payload = {
            "seed_contract": LOCAL_SEED_CONTRACT,
            "language_contract": LANGUAGE_CONTRACT_VERSION,
            "operation": operation.value,
            "payload": _plain_json(payload),
        }
        return self._transport.generate_structured(
            model=self.model,
            instructions=instructions,
            payload=request_payload,
            schema_name=schema_name,
            schema=schema,
            max_output_tokens=MAX_LOCAL_OUTPUT_TOKENS,
        )

    def invoke(self, request: LanguageModelRequest) -> Mapping[str, Any]:
        if not isinstance(request, LanguageModelRequest):
            raise ValidationError("local backend requires LanguageModelRequest")
        if request.contract_version != LANGUAGE_CONTRACT_VERSION:
            raise LanguageBackendError("local_language_contract_mismatch")
        if request.operation is LanguageOperation.UNDERSTAND:
            self._pending_understanding = None
            result = self._generate(
                operation=request.operation,
                instructions=_UNDERSTAND_INSTRUCTIONS,
                payload=request.payload,
                schema_name="darwin_understanding_v1",
                schema=LOCAL_UNDERSTANDING_SCHEMA,
            )
            _reject_unregistered_local_numeric_levels(result)
            pending = _plain_json(request.payload)
            if not isinstance(pending, dict):
                raise LanguageBackendError("local_request_payload_not_object")
            self._pending_understanding = pending
            return result
        if request.operation is LanguageOperation.EXPRESS:
            pending = self._pending_understanding
            self._pending_understanding = None
            if pending is None:
                raise LanguageBackendError("express_requires_prior_understand")
            return self._generate(
                operation=request.operation,
                instructions=_EXPRESS_INSTRUCTIONS,
                payload={
                    "conversation_request": pending,
                    "expression_plan": request.payload,
                },
                schema_name="darwin_expression_v1",
                schema=EXPRESSION_SCHEMA,
            )
        raise LanguageBackendError("local_consult_not_enabled")

    def clear_ephemeral_context(self) -> None:
        self._pending_understanding = None
