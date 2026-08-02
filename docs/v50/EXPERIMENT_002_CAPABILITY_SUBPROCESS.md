# Experiment 002 — single-use capability and subprocess

Date: 2026-07-27\
Base commit: `6c51cbc5cb1efd61ffe096f3000f8346942be1f8`

## Question

Can Darwin execute the fixed workspace effect in another process only after a
signed, registered, scoped, single-use capability has been issued?

## Protocol

A capability binds the session, goal, action, action digest, adapter, workspace
hash, issuer, issue time, and expiry. The event store registers at most one
capability per action and consumes it transactionally before the effect.

The worker starts through the fixed `darwin_v50.worker` entry point with
`shell=False`. It receives the capability and the observation key, but not the
approval secret. A crash after consumption does not trigger an automatic retry.

Tests attempted expired and forged grants, wrong scopes, unregistered grants,
cross-action substitution, duplicate registration, reuse after consumption,
and parent-secret inheritance.

## Observed result

```text
Ran 34 tests in 3.843s
OK (skipped=1)
```

The effect process had a different PID from the test process. Invalid grants
were rejected before the effect. `compileall` and `git diff --check` passed. The
symlink case was skipped for the same Windows privilege limitation recorded in
Experiment 001.

Two earlier `compileall` invocations used paths relative to the wrong working
directory and produced `Can't list`; they were discarded and repeated from the
repository root.

## Decision

The result supports single-use application-level authorization and real process
separation for the registered operation. It does not make the second process a
Windows security boundary: both processes still run as the same user.
