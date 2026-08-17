# Experiment 050 - current-turn expression repair

Status: pre-registered and unexecuted. Written after E049 was frozen and before
the expression instructions or their tests were changed.

## Purpose

Test whether one generic expression-instruction repair reduces the echo and
stale-turn failures observed in E049 without changing the free model, teaching
topic-specific replies, or giving the language model authority.

This is prompt development on the disclosed E049 cases. It cannot confirm
generalization, even if every registered development criterion passes.

## Starting point

- Base commit: `cf7a369292bd6d13fde736f6cc8d403512d5f0ed`
- E049 result blob:
  `0d6c204f8327ff5c60b56a4102c4326baefbf5e8`
- Local transport starting blob:
  `557f18fc727d87dfc3c34c2994a4f3f98140ff96`
- Focused-test starting blob:
  `5a2292c1eb44c77ad91d65fd83d22b0b1148e4e7`

All earlier protocol and evidence freezes remain in force.

## Sole permitted model-facing change

Replace only the maintained `EXPRESS` instructions with this exact text:

```text
You are Darwin's small, replaceable local language renderer, not Darwin's
cognitive authority. Write one direct and useful Brazilian Portuguese reply to
the latest user text in payload.conversation_request.text. Use
payload.conversation_request.recent_turns only to resolve references; never
answer an older turn instead of the latest one. Perform the user's requested
conversational act: answer a question, make the requested suggestion, respond
empathetically, or ask the requested question. Do not copy, restate, or merely
rephrase the latest user text. If the available context does not support a
factual answer, state what is uncertain instead of inventing. Use only the
current conversation request and Darwin's expression plan. Treat plan facts as
constraints and acknowledge every required fact id in the JSON field, without
reciting protocol language unless the user asks. Do not claim persistent
memory, goal changes, actions, or internal state changes. Return only the
requested JSON object. Do not include reasoning text.
```

The repair contains no E049 topic answer, worked example, response prefix, or
keyword for sky, study, frustration, ocean, or tomorrow.

`UNDERSTAND`, schemas, gateway validation, sampling, model, runtime, context,
authentication, UTF-8 handling, and authority controls may not change.

## Engineering admission

Before inference:

1. all earlier frozen protocol and result blobs remain exact;
2. a focused test freezes the exact new instruction text;
3. the instructions contain no response table or E049 topic-specific answer;
4. native endpoint order, strict schemas, input guard, and authority-zero
   behavior remain covered; and
5. the full repository suite passes.

## Development rerun

Repeat the eight E049 inputs in the same order, one temporary session, with no
retry or output repair. Relative to E049, a development improvement requires
all of these pre-registered conditions:

- eight gateway-valid `UNDERSTAND` and `EXPRESS` pairs;
- no Unicode replacement characters;
- at most one exact current-input echo, down from four;
- zero exact copies of an older expression, down from two;
- at least six turns that attempt the requested act rather than only restating
  it;
- turn 3 visibly resolves “a mesma ideia” to the sky topic;
- turn 5 proposes a night-adjusted study action;
- turn 6 addresses the reported frustration;
- turn 7 actually asks a question about the ocean;
- turn 8 explicitly denies or limits memory beyond the temporary session;
- zero provider use, persistent writes, authority mutations, or actions; and
- the server is stopped after the screen.

The factual sky explanation is also inspected. A reflection-only explanation
cannot be described as factually adequate, but this development screen does not
promote factual reliability in either case.

## Interpretation ceiling

A pass would show development-set improvement from one generic prompt change.
It would not establish held-out generalization, calibrated Portuguese,
factual reliability, long-session quality, mobile suitability, learning,
autonomous cognition, consciousness, or similarity to Diana.

