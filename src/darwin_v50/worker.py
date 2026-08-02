"""Fixed subprocess entrypoint for one authorized workspace action."""

from __future__ import annotations

import argparse
import base64
import binascii
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

from .capabilities import (
    CapabilityError,
    CapabilityGrant,
    workspace_scope,
)
from .evidence import ActionRequest, HMACObservationSigner
from .executor import CapabilityWorkspaceExecutor
from .ipc import OBSERVATION_SECRET_ENV
from .models import CausalEvent, GoalStatus, ValidationError, canonical_json
from .store import SQLiteEventStore
from .windows_isolation import current_process_appcontainer_evidence


MAX_INPUT_BYTES = 256 * 1024


def _secret_from_environment(name: str) -> bytes:
    encoded = os.environ.get(name)
    if not encoded:
        raise CapabilityError("worker_secret_missing")
    try:
        return base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise CapabilityError("worker_secret_invalid") from exc


def _read_input() -> tuple[ActionRequest, CapabilityGrant]:
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise CapabilityError("worker_input_too_large")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CapabilityError("worker_input_invalid") from exc
    if not isinstance(payload, dict):
        raise CapabilityError("worker_input_invalid")
    request_payload = payload.get("request")
    grant_payload = payload.get("grant")
    if not isinstance(request_payload, dict) or not isinstance(grant_payload, dict):
        raise CapabilityError("worker_input_invalid")
    return (
        ActionRequest.from_dict(request_payload),
        CapabilityGrant.from_dict(grant_payload),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--database", required=True)
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--adapter-source", required=True)
    parser.add_argument("--require-appcontainer", action="store_true")
    return parser


def run_worker(args: argparse.Namespace) -> dict:
    request, grant = _read_input()
    unexpected_internal_environment = {
        name
        for name in os.environ
        if name.upper().startswith("DARWIN_V50_")
        and name != OBSERVATION_SECRET_ENV
    }
    if unexpected_internal_environment:
        raise CapabilityError("worker_environment_not_sanitized")
    token_evidence = current_process_appcontainer_evidence()
    if args.require_appcontainer and not (
        token_evidence.query_succeeded and token_evidence.is_appcontainer
    ):
        raise CapabilityError("appcontainer_required")
    observation_secret = _secret_from_environment(OBSERVATION_SECRET_ENV)
    scope = workspace_scope(Path(args.workspace_root))

    if not grant.correlates(
        request,
        adapter_source=args.adapter_source,
        resource_scope=scope,
    ):
        raise CapabilityError("capability_correlation_mismatch")

    now = datetime.now(timezone.utc)
    with SQLiteEventStore(args.database) as store:
        with store.transaction() as connection:
            goal = store.get_goal(request.goal_id, connection=connection)
            if goal.status is not GoalStatus.WAITING_OBSERVATION:
                raise CapabilityError("goal_not_waiting_for_action")
            if (
                goal.session_id != request.session_id
                or goal.expected_action_id != request.action_id
                or goal.expected_action_event_id is None
            ):
                raise CapabilityError("action_request_not_pending")
            action_event = store.get_event(
                goal.expected_action_event_id,
                connection=connection,
            )
            if action_event.payload.get("action_digest") != request.action_digest:
                raise CapabilityError("action_digest_not_pending")
            registration_event_id = store.capability_registration_event_id(
                grant.grant_id,
                connection=connection,
            )
            consumed_event = CausalEvent.create(
                session_id=request.session_id,
                kind="capability.consumed",
                goal_id=request.goal_id,
                action_id=request.action_id,
                parent_event_id=registration_event_id,
                payload={
                    "grant_id": grant.grant_id,
                    "issuer": grant.issuer,
                    "adapter_source": grant.adapter_source,
                    "resource_scope": grant.resource_scope,
                    "action_digest": grant.action_digest,
                    "consent_id": grant.consent_id,
                    "consent_receipt_digest": grant.consent_receipt_digest,
                    "consumed_before_execution": True,
                },
            )
            store.consume_capability(
                grant,
                request,
                adapter_source=args.adapter_source,
                resource_scope=scope,
                consumed_event=consumed_event,
                now=now,
                connection=connection,
            )

    signer = HMACObservationSigner(
        source=args.adapter_source,
        secret=observation_secret,
    )
    executor = CapabilityWorkspaceExecutor(
        root=args.workspace_root,
        signer=signer,
    )
    metrics = executor.perform(request)
    metrics.update(
        {
            "worker_pid": os.getpid(),
            "separate_process": True,
            "capability_grant_id": grant.grant_id,
            "appcontainer_query_succeeded": token_evidence.query_succeeded,
            "appcontainer_token": token_evidence.is_appcontainer,
        }
    )
    envelope = signer.attest(request, metrics)
    return {"ok": True, "envelope": envelope.to_dict()}


def main() -> int:
    try:
        args = _parser().parse_args()
        result = run_worker(args)
    except CapabilityError as exc:
        result = {"ok": False, "error_code": exc.code}
    except ValidationError:
        result = {"ok": False, "error_code": "worker_validation_failed"}
    except Exception:
        result = {"ok": False, "error_code": "worker_internal_error"}
    sys.stdout.write(canonical_json(result) + "\n")
    return 0 if result.get("ok") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
