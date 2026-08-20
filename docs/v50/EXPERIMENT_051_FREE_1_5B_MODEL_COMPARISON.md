# Experiment 051 - free 1.5B model comparison

Status: pre-registered and unexecuted. Written after the failed E050 result was
frozen and before the baseline prompt was restored or the candidate artifact
was downloaded.

## Purpose

Test whether a still-small, free, instruction-tuned local model can satisfy the
same language boundary more reliably than the E049 0.6B candidate. The E050
long-prompt variant failed and is not used as the comparison baseline.

E051 is a model-development comparison, not a mobile or language-capability
confirmation.

## Starting point

- Base commit: `19dd5678d1a1337c3b1487fb4509c9978c098b72`
- E050 failure-result blob:
  `cac08761b9a328c5c57ff9516f4c0faae8d3d822`
- E049 baseline local-transport blob to restore:
  `557f18fc727d87dfc3c34c2994a4f3f98140ff96`
- E050 failed local-transport blob:
  `792137b3bc99ef6b79138c5bad8ffe6402a21c92`

All earlier protocol and evidence freezes remain in force.

## Fixed candidate artifact

- Repository: `Qwen/Qwen2.5-1.5B-Instruct-GGUF`
- Revision: `62a8d092b0a1047016f3edbd0fde387598727aa5`
- File: `qwen2.5-1.5b-instruct-q4_k_m.gguf`
- Quantization: `Q4_K_M`
- Expected bytes: `1,117,320,736`
- Expected SHA-256:
  `6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e`
- Declared license: Apache-2.0

These values came from the repository owner's revision-specific model API
metadata before download. A mismatch aborts E051. No mirror, alternative
quantization, newer revision, or automatic substitute is permitted.

The candidate is selected because its owner documents instruction tuning,
Portuguese among more than 29 supported languages, improved structured/JSON
output, and official llama.cpp GGUF usage. Those are upstream descriptions,
not Darwin evidence.

## Clean comparison boundary

Restore the exact E049 local transport blob, including its shorter `EXPRESS`
instructions, before engineering admission. The E051 maintained transport must
therefore have Git blob
`557f18fc727d87dfc3c34c2994a4f3f98140ff96` exactly.

Keep the E048 strict UTF-8 CLI, E047 control-marker guard, native authenticated
transport, schemas, 4,096-token context, one slot, 1,000-token ceiling,
temperature zero, disabled reasoning, temporary transcript, and authority-zero
boundary unchanged.

The only experimental difference from E049 is the explicitly configured model
artifact and alias.

## Artifact and load admission

Before language inference:

1. file length and SHA-256 must match this protocol;
2. the Apache-2.0 license source and fixed revision must be recorded;
3. the unchanged b10470 runtime must load the exact alias on authenticated
   `127.0.0.1` with one 4,096-token slot and no Web UI;
4. readiness must occur within 60 seconds;
5. peak desktop working set during the load probe must not exceed
   2,750,000,000 bytes;
6. the server must be stopped after the load probe; and
7. no model inference may occur during the load probe.

Passing this desktop ceiling does not establish a mobile memory budget.

## Engineering admission

The focused suite must freeze every earlier result, confirm the exact restored
E049 transport blob, and preserve authentication, schemas, UTF-8, input guard,
no response table, no provider fallback, and authority-zero behavior. The full
repository suite must pass before the live screen.

## Development comparison

Repeat the eight E049 inputs, unchanged and in one temporary session. The E051
candidate passes this development comparison only if all of these hold:

- eight gateway-valid `UNDERSTAND` and `EXPRESS` pairs;
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
- every inference request completes within the existing 120-second ceiling;
- zero provider use, persistent writes, authority mutations, or actions; and
- the server is stopped after the screen.

No output may be retried, repaired, or selectively omitted.

## Interpretation ceiling

A pass would establish improvement over the disclosed E049 development cases
with a larger free model under the same prompt and authority boundary. It would
not establish held-out generalization, calibrated factual reliability,
long-session quality, mobile performance, autonomous learning, consciousness,
or similarity to Diana.

