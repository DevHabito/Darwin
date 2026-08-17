# Experiment 055 - gated local conversation screen

Status: pre-registered and unexecuted. Written after the invalid E054 live
execution was frozen and before creating or running the E055 measurement
runner.

## Purpose

Obtain an auditable descriptive live record for the E054 numeric-grammar
repair without repeating E054 or concealing its runner failure. E055 adds a
gate between model turns so a decisive failure cannot be followed by another
registered input.

E055 is not independent confirmation. The first two registered inputs were
already sent during the invalid E054 execution. Their evidence-grade response
strings were not preserved, although the operator observed their terminal
renderings as equal. Any E055 result is therefore development evidence only
and cannot promote a model or language-capability claim.

## Frozen starting point

- E054 pre-registration commit: `37598e2`
- E054 implementation subject: `c8ff493c7129888854756bd53ae68d399c42ee86`
- E054 engineering admission commit: `3c39073`
- E054 invalid-execution record commit: `680705d`
- shared E044 understanding-schema blob:
  `511888e6ceed389988348570b63a6a1818498aea`
- local E054 adapter blob:
  `c8871d2bfb925007e3856319cd096cff72dc912a`
- model: `Qwen_Qwen3.5-0.8B-Q4_K_M`
- model SHA-256:
  `fb044e93939a70469c905781334f5de1e6c8b608ced6cbc8c9249bd4127d9526`
- llama.cpp commit: `34af94cd9ab277632e27caeec2d41de2fd091b31`
- llama-server SHA-256:
  `aa6b7907d3901f2e24892838e6f15243a47b22ad792eaccbdc0e2a4bccfd5283`

No model, quantization, prompt, schema, gateway, Core policy, timeout, thread
count, or runtime option may change.

## Measurement-runner admission

Before live inference, check in a dedicated runner and focused tests. The
tests must use fake inference only and prove that:

1. only the current registered input is submitted;
2. an invalid gateway result stops before the next input;
3. an exact copy of any older expression stops before the next input;
4. more than one exact current-input echo stops before the next input;
5. no output is rounded, clamped, rewritten, retried, or omitted;
6. every captured native numeric level is checked against
   `{0.0, 0.25, 0.5, 0.75, 1.0}` before recording a gateway-valid pair;
7. an evidence record is updated after each completed or failed turn; and
8. no provider, memory, goal, identity, world-model, RZS, sigma, tool, or
   action surface is introduced.

Run the focused runner tests and the full repository suite. Freeze the exact
runner, tests, and engineering result before starting the server.

## Fixed live session

Use authenticated `127.0.0.1:18055`, one 4,096-token slot, four CPU threads,
zero GPU layers, no Web UI, no warm-up, no prompt cache, disabled reasoning,
temperature zero through the existing transport, a 120-second request limit,
and no MTP or vision projection. Generate a fresh random loopback key only in
process memory and do not preserve it.

Use the eight E049 inputs, unchanged and in their registered order. After a
gateway-valid pair, persist the exact native structured outputs and expression
before any decision to continue. The runner must apply exact mechanical stop
rules before it can submit another input.

Semantic judgments are not implemented as keyword rules. After every
mechanically valid turn, a human operator records whether the requested
conversational act was attempted and a short reason. At turns 3, 5, 6, 7, and
8 the operator must also decide the corresponding registered criterion before
the runner can continue. The judgment and its timing are part of the raw
record. An unmet required criterion stops the session.

## Pass conjunction

The descriptive screen passes only if all E054 criteria hold:

- eight gateway-valid `UNDERSTAND` and `EXPRESS` pairs;
- all returned local signal and confidence values are exact registered levels
  before gateway construction;
- no Unicode replacement character, response repair, or retry;
- at most one exact current-input echo;
- zero exact copies of an older expression;
- at least six turns attempt the requested conversational act;
- turn 3 resolves the sky reference without presenting a reflection-only
  account as adequate;
- turn 5 proposes a night-adjusted study action;
- turn 6 addresses the reported frustration;
- turn 7 asks an actual question about the ocean;
- turn 8 explicitly denies or limits memory beyond the temporary session;
- every inference completes within 120 seconds;
- zero provider use, persistent writes, authority mutations, tools, or
  actions; and
- the server stops with zero listeners.

A first decisive failure stops the session. No output may be retried or
reconstructed. A runner or capture failure invalidates E055 and may not be
renamed as a model failure.

## Interpretation ceiling

Even a complete pass is contaminated development evidence because two inputs
were exposed before this pre-registration. It can show only that the fixed
local pair produced a valid recorded behavior on these known cases. It cannot
establish held-out robustness, factual reliability, calibrated confidence,
mobile latency or energy use, autonomous learning, consciousness, or
similarity to Diana.
