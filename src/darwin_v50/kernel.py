"""Causal goal kernel for the Darwin v50 foundation."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import hashlib
from pathlib import Path
from typing import Collection, Mapping

from .capabilities import (
    CapabilityApprovalVerifier,
    CapabilityError,
    CapabilityGrant,
)
from .consent import (
    ED25519_CONSENT_SCHEME,
    INTERACTIVE_TTY_CHANNEL,
    ConsentError,
    ConsentReceipt,
    ConsentVerifier,
    ConsentRequest,
    ConsentRisk,
)
from .evidence import (
    ActionRequest,
    ObservationEnvelope,
    ObservationVerifier,
    compute_action_digest,
)
from .models import (
    CausalEvent,
    Clock,
    ComparisonCondition,
    Goal,
    GoalStateError,
    GoalStatus,
    IdFactory,
    JSONValue,
    ObservationResult,
    ValidationError,
    new_id,
    require_text,
    utc_now,
)
from .store import SQLiteEventStore


class DarwinKernelV50:
    """A minimal kernel that records claims and verifies goal completion.

    Dispatching an action does not execute it.  A capability adapter may perform
    it and report a signed observation.  Sources without a registered verifier
    remain explicitly unauthenticated E1 inputs.
    """

    def __init__(
        self,
        store: SQLiteEventStore,
        *,
        clock: Clock = utc_now,
        id_factory: IdFactory = new_id,
        evidence_verifiers: Mapping[str, ObservationVerifier] | None = None,
        capability_verifiers: Mapping[str, CapabilityApprovalVerifier] | None = None,
        consent_verifiers: Mapping[str, ConsentVerifier] | None = None,
        accepted_consent_channels: Collection[str] = (INTERACTIVE_TTY_CHANNEL,),
        accepted_consent_schemes: Collection[str] = (ED25519_CONSENT_SCHEME,),
    ) -> None:
        self.store = store
        self._clock = clock
        self._id_factory = id_factory
        self._evidence_verifiers = dict(evidence_verifiers or {})
        self._capability_verifiers = dict(capability_verifiers or {})
        self._consent_verifiers = dict(consent_verifiers or {})
        self._accepted_consent_channels = frozenset(
            require_text(channel, "accepted_consent_channel")
            for channel in accepted_consent_channels
        )
        if not self._accepted_consent_channels:
            raise ValidationError("at least one consent channel must be accepted")
        self._accepted_consent_schemes = frozenset(
            require_text(scheme, "accepted_consent_scheme")
            for scheme in accepted_consent_schemes
        )
        if not self._accepted_consent_schemes:
            raise ValidationError("at least one consent scheme must be accepted")
        for source, verifier in self._evidence_verifiers.items():
            if source != verifier.source:
                raise ValidationError(
                    f"evidence verifier key does not match source: {source}"
                )
        for issuer, verifier in self._capability_verifiers.items():
            if issuer != verifier.issuer:
                raise ValidationError(
                    f"capability verifier key does not match issuer: {issuer}"
                )
        for issuer, verifier in self._consent_verifiers.items():
            if issuer != verifier.issuer:
                raise ValidationError(
                    f"consent verifier key does not match issuer: {issuer}"
                )

    @classmethod
    def open(
        cls,
        database: str | Path,
        *,
        clock: Clock = utc_now,
        id_factory: IdFactory = new_id,
        evidence_verifiers: Mapping[str, ObservationVerifier] | None = None,
        capability_verifiers: Mapping[str, CapabilityApprovalVerifier] | None = None,
        consent_verifiers: Mapping[str, ConsentVerifier] | None = None,
        accepted_consent_channels: Collection[str] = (INTERACTIVE_TTY_CHANNEL,),
        accepted_consent_schemes: Collection[str] = (ED25519_CONSENT_SCHEME,),
    ) -> "DarwinKernelV50":
        return cls(
            SQLiteEventStore(database),
            clock=clock,
            id_factory=id_factory,
            evidence_verifiers=evidence_verifiers,
            capability_verifiers=capability_verifiers,
            consent_verifiers=consent_verifiers,
            accepted_consent_channels=accepted_consent_channels,
            accepted_consent_schemes=accepted_consent_schemes,
        )

    def close(self) -> None:
        self.store.close()

    def __enter__(self) -> "DarwinKernelV50":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _new_id(self, kind: str) -> str:
        return f"{kind}:{self._id_factory()}"

    def _event(
        self,
        *,
        session_id: str,
        kind: str,
        payload: Mapping[str, JSONValue],
        parent_event_id: str | None = None,
        goal_id: str | None = None,
        action_id: str | None = None,
        observation_id: str | None = None,
    ) -> CausalEvent:
        return CausalEvent.create(
            session_id=session_id,
            kind=kind,
            payload=payload,
            parent_event_id=parent_event_id,
            goal_id=goal_id,
            action_id=action_id,
            observation_id=observation_id,
            clock=self._clock,
            id_factory=lambda: self._new_id("event"),
        )

    def create_goal(
        self,
        *,
        session_id: str,
        description: str,
        evidence_source: str,
        condition: ComparisonCondition,
    ) -> Goal:
        session_id = require_text(session_id, "session_id")
        description = require_text(description, "description")
        evidence_source = require_text(evidence_source, "evidence_source")
        goal_id = self._new_id("goal")
        event = self._event(
            session_id=session_id,
            kind="goal.created",
            goal_id=goal_id,
            payload={
                "description": description,
                "evidence_source": evidence_source,
                "condition": condition.to_dict(),
            },
        )
        goal = Goal(
            goal_id=goal_id,
            session_id=session_id,
            description=description,
            evidence_source=evidence_source,
            condition=condition,
            status=GoalStatus.PLANNED,
            created_event_id=event.event_id,
            last_event_id=event.event_id,
        )
        with self.store.transaction() as connection:
            self.store.append_event(event, connection=connection)
            self.store.insert_goal(goal, connection=connection)
        return goal

    def start_goal(self, goal_id: str) -> Goal:
        with self.store.transaction() as connection:
            goal = self.store.get_goal(goal_id, connection=connection)
            if goal.status is not GoalStatus.PLANNED:
                raise GoalStateError(
                    f"goal {goal.goal_id} cannot start from {goal.status.value}"
                )
            event = self._event(
                session_id=goal.session_id,
                kind="goal.started",
                goal_id=goal.goal_id,
                parent_event_id=goal.last_event_id,
                payload={"from_status": goal.status.value},
            )
            self.store.append_event(event, connection=connection)
            updated = replace(
                goal,
                status=GoalStatus.ACTIVE,
                last_event_id=event.event_id,
            )
            return self.store.update_goal(
                updated,
                expected_version=goal.version,
                connection=connection,
            )

    def dispatch_action(
        self,
        goal_id: str,
        *,
        action_name: str,
        parameters: Mapping[str, JSONValue] | None = None,
    ) -> Goal:
        """Record a requested action without pretending that it executed."""

        action_name = require_text(action_name, "action_name")
        parameters = dict(parameters or {})
        action_digest = compute_action_digest(action_name, parameters)
        with self.store.transaction() as connection:
            goal = self.store.get_goal(goal_id, connection=connection)
            if goal.status is not GoalStatus.ACTIVE:
                raise GoalStateError(
                    f"goal {goal.goal_id} cannot dispatch from {goal.status.value}"
                )
            action_id = self._new_id("action")
            event = self._event(
                session_id=goal.session_id,
                kind="action.dispatched",
                goal_id=goal.goal_id,
                action_id=action_id,
                parent_event_id=goal.last_event_id,
                payload={
                    "action_name": action_name,
                    "parameters": parameters,
                    "action_digest": action_digest,
                    "execution_claimed": False,
                },
            )
            self.store.append_event(event, connection=connection)
            updated = replace(
                goal,
                status=GoalStatus.WAITING_OBSERVATION,
                last_event_id=event.event_id,
                expected_action_id=action_id,
                expected_action_event_id=event.event_id,
            )
            return self.store.update_goal(
                updated,
                expected_version=goal.version,
                connection=connection,
            )

    def pending_action(self, goal_id: str) -> ActionRequest:
        goal = self.store.get_goal(goal_id)
        return self._action_request(goal)

    def _action_request(
        self,
        goal: Goal,
        *,
        connection=None,
    ) -> ActionRequest:
        if goal.status is not GoalStatus.WAITING_OBSERVATION:
            raise GoalStateError(
                f"goal {goal.goal_id} has no pending action in {goal.status.value}"
            )
        if (
            goal.expected_action_id is None
            or goal.expected_action_event_id is None
        ):
            raise GoalStateError("waiting goal has no correlated action")
        event = self.store.get_event(
            goal.expected_action_event_id,
            connection=connection,
        )
        action_name = event.payload.get("action_name")
        parameters = event.payload.get("parameters")
        action_digest = event.payload.get("action_digest")
        if (
            not isinstance(action_name, str)
            or not isinstance(parameters, dict)
            or not isinstance(action_digest, str)
        ):
            raise GoalStateError("persisted action request is incomplete")
        return ActionRequest(
            session_id=goal.session_id,
            goal_id=goal.goal_id,
            action_id=goal.expected_action_id,
            action_name=action_name,
            parameters=parameters,
            action_digest=action_digest,
        )

    def request_consent(
        self,
        goal_id: str,
        *,
        consent_issuer: str,
        expected_resource_scope: str,
        risk: ConsentRisk,
        ttl: timedelta = timedelta(minutes=5),
    ) -> ConsentRequest:
        expected_resource_scope = require_text(
            expected_resource_scope,
            "expected_resource_scope",
        )
        if ttl <= timedelta(0):
            raise ValidationError("consent ttl must be positive")
        consent_issuer = require_text(consent_issuer, "consent_issuer")
        authority = self._consent_verifiers.get(consent_issuer)
        if authority is None:
            raise ConsentError("consent_verifier_not_registered")
        if authority.scheme not in self._accepted_consent_schemes:
            raise ConsentError("consent_scheme_not_accepted")
        created_at = self._clock()
        challenge_seed = self._new_id("challenge")
        challenge = hashlib.sha256(challenge_seed.encode("utf-8")).hexdigest()[
            :8
        ].upper()

        with self.store.transaction() as connection:
            goal = self.store.get_goal(goal_id, connection=connection)
            action = self._action_request(goal, connection=connection)
            request = ConsentRequest(
                consent_id=self._new_id("consent"),
                authority_issuer=authority.issuer,
                authority_scheme=authority.scheme,
                authority_fingerprint=authority.fingerprint,
                adapter_source=goal.evidence_source,
                session_id=action.session_id,
                goal_id=action.goal_id,
                action_id=action.action_id,
                action_name=action.action_name,
                parameters=dict(action.parameters),
                action_digest=action.action_digest,
                resource_scope=expected_resource_scope,
                risk=risk,
                created_at=created_at,
                expires_at=created_at + ttl,
                challenge=challenge,
            )
            event = self._event(
                session_id=goal.session_id,
                kind="consent.requested",
                goal_id=goal.goal_id,
                action_id=action.action_id,
                parent_event_id=goal.expected_action_event_id,
                payload={
                    "consent_id": request.consent_id,
                    "authority_issuer": request.authority_issuer,
                    "authority_scheme": request.authority_scheme,
                    "authority_fingerprint": request.authority_fingerprint,
                    "request_digest": request.request_digest,
                    "adapter_source": request.adapter_source,
                    "action_name": request.action_name,
                    "parameters": request.parameters,
                    "action_digest": request.action_digest,
                    "resource_scope": request.resource_scope,
                    "risk": request.risk.value,
                    "created_at": request.created_at.isoformat(),
                    "expires_at": request.expires_at.isoformat(),
                    "challenge": request.challenge,
                },
            )
            self.store.append_event(event, connection=connection)
            self.store.insert_consent_request(
                request,
                requested_event_id=event.event_id,
                connection=connection,
            )
        return request

    def register_consent_receipt(
        self,
        receipt: ConsentReceipt,
    ) -> ConsentReceipt:
        verifier = self._consent_verifiers.get(receipt.issuer)
        if verifier is None:
            raise ConsentError("consent_verifier_not_registered")

        with self.store.transaction() as connection:
            request = self.store.get_consent_request(
                receipt.consent_id,
                connection=connection,
            )
            verification = verifier.verify(receipt, request)
            if not verification.valid:
                raise ConsentError(verification.reason)
            if receipt.channel not in self._accepted_consent_channels:
                raise ConsentError("consent_channel_not_accepted")
            if receipt.scheme not in self._accepted_consent_schemes:
                raise ConsentError("consent_scheme_not_accepted")
            parent_event_id = self.store.consent_event_id(
                receipt.consent_id,
                decision=False,
                connection=connection,
            )
            event = self._event(
                session_id=request.session_id,
                kind="consent.approved" if receipt.approved else "consent.denied",
                goal_id=request.goal_id,
                action_id=request.action_id,
                parent_event_id=parent_event_id,
                payload={
                    "receipt_id": receipt.receipt_id,
                    "issuer": receipt.issuer,
                    "consent_id": receipt.consent_id,
                    "request_digest": receipt.request_digest,
                    "receipt_digest": receipt.receipt_digest,
                    "approved": receipt.approved,
                    "channel": receipt.channel,
                    "decision_reason": receipt.decision_reason,
                    "decided_at": receipt.decided_at.isoformat(),
                    "signature_verified": True,
                },
            )
            self.store.append_event(event, connection=connection)
            self.store.register_consent_receipt(
                request,
                receipt,
                decision_event_id=event.event_id,
                connection=connection,
            )
        return receipt

    def register_capability_grant(
        self,
        grant: CapabilityGrant,
        *,
        expected_resource_scope: str,
    ) -> CapabilityGrant:
        expected_resource_scope = require_text(
            expected_resource_scope,
            "expected_resource_scope",
        )
        verifier = self._capability_verifiers.get(grant.issuer)
        if verifier is None:
            raise CapabilityError("capability_verifier_not_registered")
        verification = verifier.verify(grant)
        if not verification.valid:
            raise CapabilityError(verification.reason)

        with self.store.transaction() as connection:
            goal = self.store.get_goal(grant.goal_id, connection=connection)
            request = self._action_request(goal, connection=connection)
            if not grant.correlates(
                request,
                adapter_source=goal.evidence_source,
                resource_scope=expected_resource_scope,
            ):
                raise CapabilityError("capability_correlation_mismatch")
            try:
                parent_event_id = self.store.consent_event_id(
                    grant.consent_id,
                    decision=True,
                    connection=connection,
                )
            except ConsentError as exc:
                if exc.code == "consent_decision_not_registered":
                    raise CapabilityError(
                        "approved_consent_not_registered"
                    ) from exc
                raise
            event = self._event(
                session_id=goal.session_id,
                kind="capability.registered",
                goal_id=goal.goal_id,
                action_id=request.action_id,
                parent_event_id=parent_event_id,
                payload={
                    "grant_id": grant.grant_id,
                    "issuer": grant.issuer,
                    "adapter_source": grant.adapter_source,
                    "action_digest": grant.action_digest,
                    "resource_scope": grant.resource_scope,
                    "consent_id": grant.consent_id,
                    "consent_receipt_digest": grant.consent_receipt_digest,
                    "expires_at": grant.expires_at.isoformat(),
                    "max_uses": grant.max_uses,
                    "signature_verified": True,
                },
            )
            self.store.append_event(event, connection=connection)
            self.store.register_capability(
                grant,
                registered_event_id=event.event_id,
                connection=connection,
            )
        return grant

    def record_observation(
        self,
        goal_id: str,
        *,
        action_id: str,
        source: str,
        metrics: Mapping[str, JSONValue],
    ) -> ObservationResult:
        """Evaluate externally supplied evidence against one exact goal.

        A mismatched action or source is recorded as rejected evidence and
        cannot affect the persisted stop condition.
        """

        return self._record_observation(
            goal_id,
            action_id=action_id,
            source=source,
            metrics=metrics,
            attestation=None,
        )

    def record_attested_observation(
        self,
        envelope: ObservationEnvelope,
    ) -> ObservationResult:
        return self._record_observation(
            envelope.goal_id,
            action_id=envelope.action_id,
            source=envelope.source,
            metrics=envelope.metrics,
            attestation=envelope,
        )

    def _record_observation(
        self,
        goal_id: str,
        *,
        action_id: str,
        source: str,
        metrics: Mapping[str, JSONValue],
        attestation: ObservationEnvelope | None,
    ) -> ObservationResult:
        action_id = require_text(action_id, "action_id")
        source = require_text(source, "source")
        metrics = dict(metrics)
        observation_id = self._new_id("observation")

        with self.store.transaction() as connection:
            goal = self.store.get_goal(goal_id, connection=connection)
            if goal.status is not GoalStatus.WAITING_OBSERVATION:
                raise GoalStateError(
                    f"goal {goal.goal_id} cannot observe from {goal.status.value}"
                )
            if (
                goal.expected_action_id is None
                or goal.expected_action_event_id is None
            ):
                raise GoalStateError("waiting goal has no correlated action")

            rejection_reason: str | None = None
            authenticated = False
            expected_action_digest: str | None = None
            if action_id != goal.expected_action_id:
                rejection_reason = "action_mismatch"
            elif source != goal.evidence_source:
                rejection_reason = "evidence_source_mismatch"
            else:
                action_event = self.store.get_event(
                    goal.expected_action_event_id,
                    connection=connection,
                )
                persisted_digest = action_event.payload.get("action_digest")
                if isinstance(persisted_digest, str):
                    expected_action_digest = persisted_digest

                verifier = self._evidence_verifiers.get(source)
                if verifier is not None and attestation is None:
                    rejection_reason = "authentication_required"
                elif verifier is None and attestation is not None:
                    rejection_reason = "verifier_not_registered"
                elif verifier is not None and attestation is not None:
                    if (
                        attestation.session_id != goal.session_id
                        or attestation.goal_id != goal.goal_id
                        or attestation.action_id != goal.expected_action_id
                        or expected_action_digest is None
                        or attestation.action_digest != expected_action_digest
                    ):
                        rejection_reason = "attestation_correlation_mismatch"
                    else:
                        verification = verifier.verify(attestation)
                        if not verification.valid:
                            rejection_reason = verification.reason
                        elif self.store.evidence_nonce_claimed(
                            source=source,
                            nonce=attestation.nonce,
                            connection=connection,
                        ):
                            rejection_reason = "attestation_replay"
                        else:
                            authenticated = True

            if rejection_reason is not None:
                rejected = self._event(
                    session_id=goal.session_id,
                    kind="observation.rejected",
                    goal_id=goal.goal_id,
                    action_id=action_id,
                    observation_id=observation_id,
                    parent_event_id=goal.last_event_id,
                    payload={
                        "reason": rejection_reason,
                        "source": source,
                        "expected_source": goal.evidence_source,
                        "expected_action_id": goal.expected_action_id,
                        "expected_action_digest": expected_action_digest,
                        "attestation_scheme": (
                            attestation.scheme if attestation is not None else None
                        ),
                        "attestation_nonce": (
                            attestation.nonce if attestation is not None else None
                        ),
                        "authenticated": False,
                        "metrics": metrics,
                    },
                )
                self.store.append_event(rejected, connection=connection)
                updated = self.store.update_goal(
                    replace(goal, last_event_id=rejected.event_id),
                    expected_version=goal.version,
                    connection=connection,
                )
                return ObservationResult(
                    goal=updated,
                    accepted=False,
                    condition_satisfied=False,
                    reason=rejection_reason,
                    observation_event_id=rejected.event_id,
                    decision_event_id=rejected.event_id,
                )

            observation = self._event(
                session_id=goal.session_id,
                kind="observation.recorded",
                goal_id=goal.goal_id,
                action_id=action_id,
                observation_id=observation_id,
                parent_event_id=goal.expected_action_event_id,
                payload={
                    "source": source,
                    "metrics": metrics,
                    "authenticated": authenticated,
                    "attestation_scheme": (
                        attestation.scheme if attestation is not None else None
                    ),
                    "attestation_nonce": (
                        attestation.nonce if attestation is not None else None
                    ),
                    "action_digest": expected_action_digest,
                },
            )
            self.store.append_event(observation, connection=connection)
            if authenticated and attestation is not None:
                self.store.claim_evidence_nonce(
                    source=source,
                    nonce=attestation.nonce,
                    goal_id=goal.goal_id,
                    action_id=action_id,
                    observation_event_id=observation.event_id,
                    claimed_at=self._clock(),
                    connection=connection,
                )
            evaluation = goal.condition.evaluate(metrics)
            succeeded = evaluation.satisfied
            decision = self._event(
                session_id=goal.session_id,
                kind=(
                    "goal.succeeded"
                    if succeeded
                    else "goal.condition_unsatisfied"
                ),
                goal_id=goal.goal_id,
                action_id=action_id,
                observation_id=observation_id,
                parent_event_id=observation.event_id,
                payload={
                    "satisfied": succeeded,
                    "evaluation_reason": evaluation.reason,
                    "actual": evaluation.actual,
                    "condition": goal.condition.to_dict(),
                    "evidence_source": source,
                    "evidence_authenticated": authenticated,
                },
            )
            self.store.append_event(decision, connection=connection)
            updated = self.store.update_goal(
                replace(
                    goal,
                    status=(
                        GoalStatus.SUCCEEDED
                        if succeeded
                        else GoalStatus.WAITING_OBSERVATION
                    ),
                    last_event_id=decision.event_id,
                ),
                expected_version=goal.version,
                connection=connection,
            )
            return ObservationResult(
                goal=updated,
                accepted=True,
                condition_satisfied=succeeded,
                reason=(
                    "condition_satisfied"
                    if succeeded
                    else "condition_unsatisfied"
                ),
                observation_event_id=observation.event_id,
                decision_event_id=decision.event_id,
            )

    def cancel_goal(self, goal_id: str, *, reason: str) -> Goal:
        reason = require_text(reason, "reason")
        with self.store.transaction() as connection:
            goal = self.store.get_goal(goal_id, connection=connection)
            if goal.status.terminal:
                raise GoalStateError(
                    f"goal {goal.goal_id} is already {goal.status.value}"
                )
            event = self._event(
                session_id=goal.session_id,
                kind="goal.cancelled",
                goal_id=goal.goal_id,
                action_id=goal.expected_action_id,
                parent_event_id=goal.last_event_id,
                payload={"reason": reason, "from_status": goal.status.value},
            )
            self.store.append_event(event, connection=connection)
            updated = replace(
                goal,
                status=GoalStatus.CANCELLED,
                last_event_id=event.event_id,
            )
            return self.store.update_goal(
                updated,
                expected_version=goal.version,
                connection=connection,
            )

    def continue_goal(self, goal_id: str) -> Goal:
        """Resume a goal after accepted evidence did not satisfy it.

        Continuation is explicit so a new action cannot be silently attached to
        rejected evidence, an unobserved action, or a terminal goal.
        """

        with self.store.transaction() as connection:
            goal = self.store.get_goal(goal_id, connection=connection)
            if goal.status is not GoalStatus.WAITING_OBSERVATION:
                raise GoalStateError(
                    f"goal {goal.goal_id} cannot continue from "
                    f"{goal.status.value}"
                )
            latest = self.store.get_event(
                goal.last_event_id,
                connection=connection,
            )
            if latest.kind != "goal.condition_unsatisfied":
                raise GoalStateError(
                    "goal can continue only after accepted unsatisfied evidence"
                )
            if (
                goal.expected_action_id is None
                or latest.action_id != goal.expected_action_id
            ):
                raise GoalStateError(
                    "unsatisfied decision is not correlated to the pending action"
                )
            event = self._event(
                session_id=goal.session_id,
                kind="goal.continued",
                goal_id=goal.goal_id,
                action_id=goal.expected_action_id,
                parent_event_id=goal.last_event_id,
                payload={
                    "from_status": goal.status.value,
                    "completed_action_id": goal.expected_action_id,
                    "condition_remains_unsatisfied": True,
                },
            )
            self.store.append_event(event, connection=connection)
            updated = replace(
                goal,
                status=GoalStatus.ACTIVE,
                last_event_id=event.event_id,
                expected_action_id=None,
                expected_action_event_id=None,
            )
            return self.store.update_goal(
                updated,
                expected_version=goal.version,
                connection=connection,
            )

    def get_goal(self, goal_id: str) -> Goal:
        return self.store.get_goal(goal_id)

    def goal_events(self, goal_id: str) -> list[CausalEvent]:
        return self.store.events_for_goal(goal_id)
