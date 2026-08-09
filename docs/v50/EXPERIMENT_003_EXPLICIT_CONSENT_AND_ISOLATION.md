# Experiment 003 — explicit consent and honest isolation labels

Date: 2026-07-27\
Base commit: `6c51cbc5cb1efd61ffe096f3000f8346942be1f8`

## Questions

1. Can the kernel refuse a capability until an exact, signed, unexpired consent
   decision has been registered?
2. Can automated test consent be distinguished from interactive consent?
3. Can the executor describe process separation without calling it an
   operating-system sandbox?

## Protocol

A consent request fixes the session, goal, action, parameters, action digest,
executor, resource scope, risk, timestamps, issuer channel, and an eight-character
challenge. The interactive ceremony accepts only `APPROVE <challenge>` or
`DENY` through a TTY. Non-TTY input is refused by default.

The signed receipt records the decision and every correlation. The test signer
uses the `test_harness` channel; production policy accepts only
`interactive_tty`. A denied or expired request remains auditable but cannot
produce a capability. Consent lifetime also caps capability lifetime.

The required event order is:

```text
action.dispatched
  -> consent.requested
  -> consent.approved
  -> capability.registered
  -> capability.consumed
  -> effect
```

Adversarial tests covered missing consent, wrong challenges, forged receipts,
expiry, replay, cross-action and cross-scope use, unregistered decisions,
multiple grants, non-TTY input, and secret inheritance.

## Observed result

```text
Ran 47 tests in 7.179s
OK (skipped=1)
```

`compileall`, `git diff --check`, and the explicit schema migration passed. Two
integration defects were retained in the record: one test helper initially
reused a request incorrectly, and the registration API initially leaked a
`ConsentError` when no approved decision existed. The latter now returns the
registered capability error and rolls back the incomplete transaction.

## Decision

The result supports explicit, correlated, single-use consent at the application
layer. It does not prove operator identity, comprehension, freedom from coercion,
AppContainer isolation, restricted-token isolation, or protection from a
compromised signer.

Relevant Windows mechanisms remain external to this experiment:
[restricted tokens](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-createrestrictedtoken)
and [AppContainer isolation](https://learn.microsoft.com/en-us/windows/win32/secauthz/appcontainer-isolation).
