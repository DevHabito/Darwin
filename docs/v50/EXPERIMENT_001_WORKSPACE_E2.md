# Experiment 001 — scoped workspace effect

Date: 2026-07-27\
Base commit: `6c51cbc5cb1efd61ffe096f3000f8346942be1f8`

## Question

Can the v50 kernel authorize a small external effect, observe the result, and
keep the effect inside a declared workspace root?

## Scope

The executor exposes two fixed operations:

- create a new UTF-8 text file;
- inspect file metadata.

It does not expose a shell, network access, deletion, overwrite, arbitrary
directory creation, or a caller-selected Python module. Absolute paths, `..`,
missing parents, symbolic-link escapes, Windows reserved names, and alternate
data streams are rejected.

The observation is correlated with the exact session, goal, action, action
digest, source, nonce, and measured file metadata. A signed observation with a
wrong correlation cannot complete the goal.

## Observed result

```text
Ran 25 tests in 0.670s
OK (skipped=1)
```

The real symlink test was skipped because this Windows session returned
`WinError 1314`, meaning it could not create the adversarial link. The separate
`../escape.txt` traversal test passed and created nothing outside the root.

An intermediate run found one classification bug: a Windows reserved-name path
was blocked, but reported as a generic path error rather than the registered
reserved-name reason. Production validation order was fixed; the test threshold
was not relaxed.

## Decision

This is restricted E2 evidence for one low-risk filesystem effect. It shows
that the tested adapter created and inspected a file within a temporary root and
that the kernel correlated the resulting observation.

It does not establish a general sandbox, safe arbitrary code execution,
operating-system isolation, autonomy, or cognition.
