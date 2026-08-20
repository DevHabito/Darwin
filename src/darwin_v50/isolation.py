"""Truthful isolation labels for Darwin v50 execution mechanisms."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import os


class IsolationMechanism(StrEnum):
    SAME_USER_SUBPROCESS = "same_user_subprocess"
    WINDOWS_JOB_OBJECT = "windows_job_object"
    WINDOWS_RESTRICTED_TOKEN = "windows_restricted_token"
    WINDOWS_APPCONTAINER = "windows_appcontainer"
    HYPERVISOR_ISOLATED_CONTAINER = "hypervisor_isolated_container"


@dataclass(frozen=True, slots=True)
class IsolationAssessment:
    mechanism: IsolationMechanism
    platform: str
    separate_process: bool
    same_user_identity: bool
    security_boundary: bool
    filesystem_enforced_by_os: bool
    network_enforced_by_os: bool
    resource_limits_enforced_by_os: bool
    runtime_verified: bool
    limitations: tuple[str, ...]


class IsolationPolicyError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def same_user_subprocess_assessment() -> IsolationAssessment:
    """Describe the executor implemented today, without probing extra controls."""

    return IsolationAssessment(
        mechanism=IsolationMechanism.SAME_USER_SUBPROCESS,
        platform="windows" if os.name == "nt" else os.name,
        separate_process=True,
        same_user_identity=True,
        security_boundary=False,
        filesystem_enforced_by_os=False,
        network_enforced_by_os=False,
        resource_limits_enforced_by_os=False,
        runtime_verified=False,
        limitations=(
            "workspace restrictions are enforced by application code",
            "the child inherits the caller's operating-system identity",
            "another same-user process can inspect or modify accessible resources",
            "process separation alone does not confine hostile code",
        ),
    )


def require_os_security_boundary(assessment: IsolationAssessment) -> None:
    if not assessment.runtime_verified:
        raise IsolationPolicyError("isolation_not_runtime_verified")
    if not assessment.security_boundary:
        raise IsolationPolicyError("os_security_boundary_required")
