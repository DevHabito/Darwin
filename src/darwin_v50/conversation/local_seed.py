"""Portable, provider-free language seed behind Darwin's language boundary."""

from __future__ import annotations

from copy import deepcopy
import json
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
MAX_LOCAL_OUTPUT_TOKENS = 1_000
REGISTERED_CONTEXT_TOKENS = 4_096


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


def _object(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LocalSeedTransportError(f"{field}_not_object")
    return value


def _array(value: object, field: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise LocalSeedTransportError(f"{field}_not_array")
    return value


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
    ) -> Mapping[str, Any]:
        parsed = urlsplit(url)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1":
            raise LocalSeedTransportError("local_transport_non_loopback_url")
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(
                body,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(url=url, data=data, headers=headers, method=method)
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
        timeout_seconds: float = 120.0,
        json_transport: LoopbackJSONTransport | None = None,
    ) -> None:
        self.endpoint = _registered_loopback_origin(endpoint)
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
        user_text = json.dumps(
            plain_payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if len(system_text) + len(user_text) > MAX_LOCAL_PROMPT_CHARACTERS:
            raise LanguageBackendError("local_prompt_exceeds_registered_limit")
        body: Mapping[str, object] = {
            "model": configured_model,
            "messages": [
                {"role": "system", "content": system_text},
                {"role": "user", "content": user_text},
            ],
            "stream": False,
            "temperature": 0.0,
            "max_tokens": max_output_tokens,
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_id,
                    "strict": True,
                    "schema": deepcopy(dict(schema)),
                },
            },
        }
        response = self._request(
            method="POST",
            path="/v1/chat/completions",
            body=body,
        )
        choices = _array(response.get("choices"), "local_choices")
        if len(choices) != 1:
            raise LocalSeedTransportError("local_choice_count_invalid")
        choice = _object(choices[0], "local_choice")
        if choice.get("finish_reason") != "stop":
            raise LocalSeedTransportError("local_completion_not_finished")
        message = _object(choice.get("message"), "local_message")
        if message.get("tool_calls") or message.get("function_call"):
            raise LocalSeedTransportError("local_completion_requested_tool")
        content = message.get("content")
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
                schema=UNDERSTANDING_SCHEMA,
            )
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
