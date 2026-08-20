# Experiment 054 - local numeric grammar repair

Status: pre-registered and unexecuted. Written after the failed E053 result was
frozen and before changing the local schema adapter or rerunning language.

## Purpose

Repair a demonstrated semantic gap between Darwin's numeric language contract
and llama.cpp's JSON-Schema-to-grammar subset without weakening the Core,
changing the shared E044 schema, coercing output, or retrying a failed model
response.

## Starting point

- Base commit: `acc6e782872901aaa20d2dd4f670e82b6cd6aa00`
- E053 failure-result blob:
  `f24a935b6b6c988add826647d1a130e7a6a16e97`
- E053 failed field: `reported_signals[].value`
- E053 gateway error:
  `reported signal value must be a number from 0 to 1`
- E053 native server completed the JSON response before the gateway rejected
  its semantic value.

All earlier protocol and evidence freezes remain in force.

## External runtime fact recorded before implementation

The llama.cpp grammar documentation states that it converts only a subset of
JSON Schema, skips unsupported features silently, and currently supports
`minimum`, `exclusiveMinimum`, `maximum`, and `exclusiveMaximum` for
`"type": "integer"`, not `"type": "number"`.

Primary source:

`https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md`

Darwin's shared understanding schema uses `type: number`, `minimum: 0`, and
`maximum: 1` for both `reported_signals[].value` and `confidence`. Therefore
the native grammar guarantees JSON number syntax but does not guarantee those
two semantic ranges. E053 is consistent with this documented limitation. This
is a causal implementation hypothesis, not proof of the exact rejected value,
which was not logged and will not be reconstructed or retried.

## Fixed repair

Leave `conversation.openai_responses.UNDERSTANDING_SCHEMA` byte-for-byte and
semantically unchanged. It belongs to the earlier shared boundary.

Add one local-only understanding schema derived from that shared schema. Change
only these two local schema nodes:

```text
reported_signals[].value
confidence
```

For each node, replace the unsupported continuous range keywords with:

```json
{
  "type": "number",
  "enum": [0.0, 0.25, 0.5, 0.75, 1.0]
}
```

Use that derived schema only for local `UNDERSTAND`. Keep local `EXPRESS` and
all gateway/Core validation unchanged.

The levels are coarse linguistic indicators. They are not probabilities or
measurements. Applying them to local `confidence` narrows an uncalibrated model
field; it does not create calibrated confidence.

## Forbidden repairs

- no clamping, rounding, parsing, or coercion after generation;
- no retry or repair call after invalid output;
- no prompt-specific examples or topic words;
- no change to the shared E044 schema;
- no change to the gateway's finite `0..1` validation;
- no acceptance of out-of-range values;
- no response table or scripted topic answer;
- no provider fallback, persistent history, memory write, authority mutation,
  tool, or action; and
- no MTP activation or model/runtime substitution.

## Engineering admission

The focused suite must prove:

- the shared schema still has the original continuous number bounds;
- the local schema has exactly the five fixed enum values at both nodes;
- local `UNDERSTAND` sends the local schema;
- local `EXPRESS` still sends the unchanged expression schema;
- no post-generation coercion or retry is introduced;
- every earlier local freeze, authentication, UTF-8, control-marker, endpoint,
  authority, and no-response-table test still passes; and
- the full repository suite passes with only the already declared Windows
  symlink privilege skip permitted.

Freeze the implementation and engineering records before live inference.

## Live development rerun

After engineering admission, use the exact E053 artifact, alias, b10470 runtime,
four threads, authenticated loopback configuration, and eight E049 inputs.
Send one input at a time only after a valid preceding expression.

The candidate passes only if all of these hold:

- eight gateway-valid `UNDERSTAND` and `EXPRESS` pairs;
- every returned local signal and confidence belongs to the fixed five-level
  set before gateway construction;
- no Unicode replacement character or retry;
- at most one exact current-input echo;
- zero exact copies of an older expression;
- at least six turns attempt the requested conversational act;
- turn 3 resolves the sky reference;
- turn 5 proposes a night-adjusted study action;
- turn 6 addresses the reported frustration;
- turn 7 asks an actual question about the ocean;
- turn 8 explicitly denies or limits memory beyond the temporary session;
- no reflection-only sky explanation is described as factually adequate;
- every inference request completes within 120 seconds;
- zero provider use, persistent writes, authority mutations, or actions; and
- the server is stopped after the screen.

No output may be retried, repaired, or selectively omitted. A required failure
stops the screen before the next registered input.

## Interpretation ceiling

A pass can show that the local grammar adapter closed the disclosed numeric
range gap and that the fixed candidate passed the disclosed development cases.
It cannot establish held-out robustness, calibrated confidence, factual
reliability, long-session quality, mobile speed or energy use, autonomous
learning, consciousness, or similarity to Diana.
