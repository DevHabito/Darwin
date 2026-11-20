# E067 capture incident 01 — output-directory permission

**Classification:** operational recording failure, not a mathematical gate failure.

The preregistered candidate, tests and evaluator were frozen at `59c0baef4733d1b334321b9fac8519d3d5937d38`. After that commit, the first invocation of the registered exact evaluator completed the finite calculations, reached the output-write step and raised `PermissionError: [Errno 13] Permission denied` for `/mnt/data/darwin_e067_work/docs/v50/results/EXPERIMENT_067_ANCHOR_SOURCE_AUDIT.json`.

The failed process did not create the evidence JSON. Its computed values were not captured and cannot be treated as preserved evidence.

The unchanged evaluator was then run with an output path writable by the invoking process. The second invocation completed with exit code zero, recorded `PASS_EXACT_FINITE_ANCHOR_BOUNDARY`, and its exact JSON has SHA-256 `44a6563fb6bd1b903725bafd34beac5ab45f0f44a7a43ea5939c5d4e06d2628b`. All 24 focused tests also passed locally after the recorded run.

No implementation, threshold, source hypothesis, anchor reliability, enumeration domain or evidence gate changed between invocations. This protocol did not register a one-run-only restriction; the evaluator uses exhaustive exact rational arithmetic and no sampling. The retry is disclosed because output failures and repeated evaluation must not be silently represented as a clean first run.

This remains project-owned mathematical evidence. The run says nothing about the durability or causal authority of a real Darwin process or sensor.
