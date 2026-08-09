"""Read-only Windows isolation probes and runtime token evidence."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppContainerTokenEvidence:
    platform_supported: bool
    query_succeeded: bool
    is_appcontainer: bool
    windows_error: int | None = None


@dataclass(frozen=True, slots=True)
class WindowsIsolationAvailability:
    platform_supported: bool
    legacy_appcontainer_profile_api: bool
    security_capabilities_attribute_api: bool
    experimental_sandbox_api: bool
    current_token: AppContainerTokenEvidence
    errors: tuple[str, ...]

    @property
    def appcontainer_primitives_available(self) -> bool:
        return (
            self.legacy_appcontainer_profile_api
            and self.security_capabilities_attribute_api
        ) or self.experimental_sandbox_api


def _system_directory() -> Path:
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
    buffer = ctypes.create_unicode_buffer(32768)
    length = kernel32.GetSystemDirectoryW(buffer, len(buffer))
    if length == 0 or length >= len(buffer):
        raise OSError(ctypes.get_last_error(), "GetSystemDirectoryW failed")
    return Path(buffer.value).resolve(strict=True)


def _has_exports(path: Path, names: tuple[str, ...]) -> bool:
    import ctypes

    library = ctypes.WinDLL(str(path), use_last_error=True)
    return all(hasattr(library, name) for name in names)


def current_process_appcontainer_evidence() -> AppContainerTokenEvidence:
    if os.name != "nt":
        return AppContainerTokenEvidence(
            platform_supported=False,
            query_succeeded=False,
            is_appcontainer=False,
        )

    import ctypes
    from ctypes import wintypes

    TOKEN_QUERY = 0x0008
    TOKEN_IS_APPCONTAINER = 29

    kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
    advapi32 = ctypes.WinDLL("advapi32.dll", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    advapi32.OpenProcessToken.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    )
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    )
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL

    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(
        kernel32.GetCurrentProcess(),
        TOKEN_QUERY,
        ctypes.byref(token),
    ):
        return AppContainerTokenEvidence(
            platform_supported=True,
            query_succeeded=False,
            is_appcontainer=False,
            windows_error=ctypes.get_last_error(),
        )
    try:
        value = wintypes.DWORD()
        returned = wintypes.DWORD()
        if not advapi32.GetTokenInformation(
            token,
            TOKEN_IS_APPCONTAINER,
            ctypes.byref(value),
            ctypes.sizeof(value),
            ctypes.byref(returned),
        ):
            return AppContainerTokenEvidence(
                platform_supported=True,
                query_succeeded=False,
                is_appcontainer=False,
                windows_error=ctypes.get_last_error(),
            )
        return AppContainerTokenEvidence(
            platform_supported=True,
            query_succeeded=True,
            is_appcontainer=bool(value.value),
        )
    finally:
        kernel32.CloseHandle(token)


def probe_windows_isolation_availability() -> WindowsIsolationAvailability:
    token = current_process_appcontainer_evidence()
    if os.name != "nt":
        return WindowsIsolationAvailability(
            platform_supported=False,
            legacy_appcontainer_profile_api=False,
            security_capabilities_attribute_api=False,
            experimental_sandbox_api=False,
            current_token=token,
            errors=("platform_not_windows",),
        )

    errors: list[str] = []
    try:
        system = _system_directory()
    except OSError as exc:
        return WindowsIsolationAvailability(
            platform_supported=True,
            legacy_appcontainer_profile_api=False,
            security_capabilities_attribute_api=False,
            experimental_sandbox_api=False,
            current_token=token,
            errors=(f"system_directory_unavailable:{exc.errno}",),
        )

    try:
        legacy = _has_exports(
            system / "userenv.dll",
            (
                "CreateAppContainerProfile",
                "DeriveAppContainerSidFromAppContainerName",
            ),
        )
    except OSError as exc:
        legacy = False
        errors.append(f"legacy_appcontainer_api_unavailable:{exc.errno}")

    try:
        attributes = _has_exports(
            system / "kernel32.dll",
            (
                "InitializeProcThreadAttributeList",
                "UpdateProcThreadAttribute",
                "CreateProcessW",
            ),
        )
    except OSError as exc:
        attributes = False
        errors.append(f"security_attributes_api_unavailable:{exc.errno}")

    processmodel = system / "processmodel.dll"
    if not processmodel.is_file():
        experimental = False
        errors.append("experimental_sandbox_dll_absent")
    else:
        try:
            experimental = _has_exports(
                processmodel,
                ("Experimental_CreateProcessInSandbox",),
            )
            if not experimental:
                errors.append("experimental_sandbox_export_absent")
        except OSError as exc:
            experimental = False
            errors.append(f"experimental_sandbox_api_unavailable:{exc.errno}")

    return WindowsIsolationAvailability(
        platform_supported=True,
        legacy_appcontainer_profile_api=legacy,
        security_capabilities_attribute_api=attributes,
        experimental_sandbox_api=experimental,
        current_token=token,
        errors=tuple(errors),
    )
