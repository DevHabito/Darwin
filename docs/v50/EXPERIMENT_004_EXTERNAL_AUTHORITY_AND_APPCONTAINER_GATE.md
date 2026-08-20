# Experiment 004 — external consent authority and AppContainer gate

Date: 2026-07-27\
Base commit: `6c51cbc5cb1efd61ffe096f3000f8346942be1f8`\
Observed runtime: Python 3.12.13 on Windows

## Questions

1. Can the kernel verify production consent without holding a signing key?
2. Does the request prevent issuer or key substitution after display?
3. Does an AppContainer requirement fail before capability consumption when the
   worker token is not an AppContainer token?

## External authority

Production consent uses Ed25519. The broker owns the encrypted private key; the
kernel stores only the public key. The request fixes the issuer, scheme, and
public-key fingerprint. Replacing the authority after request creation is
rejected. HMAC remains available only when explicitly enabled for legacy tests.

The offline handoff uses canonical UTF-8 JSON files that are never overwritten.
It rejects duplicate JSON keys and files larger than 256 KiB. Private keys use
encrypted PKCS8 PEM and require a passphrase of at least 16 bytes. The
passphrase is read from a TTY, not a command line or environment variable.

The implementation follows the `cryptography` Ed25519 API:
[Ed25519 signing](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/).

## AppContainer gate

Before opening the capability ledger, a worker started with
`--require-appcontainer` checks `TokenIsAppContainer`. The normal executor does
not create an AppContainer. On this machine the current token was not an
AppContainer token, so the worker returned `appcontainer_required` before
consuming the grant or touching the filesystem. The same grant remained usable
by the non-isolated executor, confirming the ordering.

Observed platform probe:

```json
{
  "current_token_is_appcontainer": false,
  "experimental_sandbox_api": false,
  "legacy_appcontainer_profile_api": true,
  "security_capabilities_attribute_api": true
}
```

Microsoft documents the token query in
[`TOKEN_INFORMATION_CLASS`](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ne-winnt-token_information_class)
and the classic launch path in
[Launch an AppContainer](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer).

## Observed result

```text
Ran 59 tests in 10.878s
OK (skipped=1)
```

The broker CLI, compilation, whitespace checks, key substitution, malformed
handoff, weak passphrase, signature, migration, and fail-closed runtime cases
passed. No real private key was created inside the repository.

## Decision

The kernel can verify consent with public material only, and the AppContainer
policy fails before use when the worker does not have the required token. The
experiment did not launch an AppContainer, validate its ACLs or capabilities,
test network denial, or establish resistance to sandbox escape.
