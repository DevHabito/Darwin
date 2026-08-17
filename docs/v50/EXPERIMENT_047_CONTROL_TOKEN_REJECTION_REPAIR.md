# Experiment 047 - control-token rejection repair

Status: pre-registered and unexecuted. Written after E046 failed admission and
before the maintained input guard or its tests were implemented.

## Purpose

Test the authenticated native-completion transport from E046 using a security
control that llama.cpp b10470 can actually support. E047 rejects model control
markers in model-bound language fields before `/apply-template`; it does not
claim that b10470 escapes those tokens internally.

E045 remains failed at its first live turn. E046 remains failed at engineering
admission. Neither result can be promoted by E047.

## Starting point

- Base commit: `ffe3f5acbb3ee2e9d543e730b4a4863de9bd75d7`
- E046 protocol blob:
  `1bdfb670fbe36974c4da1811b5eedb81f180e6a6`
- E046 failure-record blob:
  `e16f9b140f986493fc29c3a49d8cd095911d2733`
- Native transport starting blob:
  `be5868fdca072c863bd8385fd00bd7d6e2222251`
- Focused-test starting blob:
  `1f70edfff80b1ba712d56971644fd68a2bc24e2f`

The E043, E044, E045, and E046 protocol and result freezes remain in force.

## Fixed artifacts and limits

E047 retains the exact E045 model and runtime hashes, the 4,096-token context,
one slot, 1,000-token output ceiling, 14,000-character request ceiling,
temperature `0.0`, disabled thinking, explicit operation schemas, and
`UNDERSTAND` then `EXPRESS` ordering.

It may not switch model, quantization, runtime, endpoint family, schema, or
sampling parameters.

## Registered input guard

Before any template request, every string in the model-bound payload must be
checked for these exact, case-sensitive substrings observed in the frozen GGUF
metadata and chat template:

```text
<|endoftext|>
<|im_start|>
<|im_end|>
<think>
</think>
<tool_call>
</tool_call>
<tool_response>
</tool_response>
```

If any marker appears in current user text, temporary transcript, or other
model-bound payload, the entire turn fails before `/apply-template`. The error
may name the class `local_control_token_rejected` but may not echo the input or
the marker. The guard is a security rejection, not a conversational response
rule and not a model-quality result.

System instructions are source-controlled and outside this user-originated
guard. Generated output still passes through strict JSON parsing, the operation
schema, and Darwin's authority boundary.

## Authenticated runtime

The server must bind exactly to `127.0.0.1`, use a fresh unlogged session API
key, disable the Web UI, prompt cache, tools, and reasoning, and expose one
4,096-token slot. E047 does not pass the unsupported E046 flag.

The model file and runtime must already match their frozen SHA-256 values before
launch. External networking is disabled for the live turn after the local
process is ready.

## Admission

Before live inference, tests must prove:

1. every earlier frozen evidence blob remains exact;
2. every registered control marker is rejected at every payload depth;
3. rejection occurs before either native endpoint is called;
4. ordinary Portuguese containing angle brackets but no registered marker is
   not rejected by the guard;
5. authenticated `/apply-template` then `/completion` ordering remains exact;
6. JSON Schema and the existing Darwin gateway remain mandatory;
7. credentials remain absent from exceptions and snapshots;
8. failed turns commit no transcript or authority mutation; and
9. the full repository suite passes.

## First live turn

After admission, repeat exactly once:

> Oi, Darwin. Estou animado para conversar com você hoje. Como devemos começar?

Pass requires gateway-valid `UNDERSTAND` and `EXPRESS`, two temporary transcript
messages, zero external requests during the turn, no credential disclosure,
and every authority mutation counter equal to zero.

One additional adversarial turn containing `<|im_start|>` must be rejected
before inference and cannot count as a language failure or successful turn.

## Interpretation ceiling

A pass would establish one authenticated local turn and one control-token
rejection with the frozen desktop pair. It would not establish calibrated
Portuguese, factual reliability, long-session quality, offline installation,
mobile performance, learning, autonomous cognition, or similarity to Diana.
