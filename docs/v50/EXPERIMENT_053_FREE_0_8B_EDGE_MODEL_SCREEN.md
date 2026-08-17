# Experiment 053 - free 0.8B edge-model screen

Status: pre-registered and unexecuted. Written after E052 was frozen and before
downloading or executing the candidate artifact.

## Purpose

Test a smaller, newer, free local model after E052 localized the Qwen2.5 1.5B
failure to raw CPU throughput on this computer. E053 admits performance before
language and uses the unchanged Darwin language boundary.

This is a development candidate screen, not a model promotion, mobile claim, or
general language evaluation.

## Starting point

- Base commit: `e87dcc4e7a40782d0fdbc5bbd6a70200d6ee34dc`
- E052 result blob: `ead5427a064da10e4afd0ac574d5e6c8825f6e83`
- E049/E051 baseline local-transport blob:
  `557f18fc727d87dfc3c34c2994a4f3f98140ff96`
- Portable local focused-test blob:
  `d9d7337bf2de5e91add39a5c46eb016280974a6f`

All earlier protocol and evidence freezes remain in force.

## Fixed candidate

Official upstream:

- Repository: `Qwen/Qwen3.5-0.8B`
- Revision: `2fc06364715b967f1860aea9cf38778875588b17`
- Declared license: Apache-2.0
- Gated: no
- Upstream description: a post-trained 0.8B model intended for prototyping,
  task-specific fine-tuning, and research or development

Converted artifact:

- Repository: `bartowski/Qwen_Qwen3.5-0.8B-GGUF`
- Revision: `f36b1ea49a332ede8fe5f389bbf5b3575ef71f48`
- File: `Qwen_Qwen3.5-0.8B-Q4_K_M.gguf`
- Quantization: `Q4_K_M`
- Expected bytes: `579,615,840`
- Expected SHA-256:
  `fb044e93939a70469c905781334f5de1e6c8b608ced6cbc8c9249bd4127d9526`
- Repository blob ID: `12a018f92b0cc4b7a82447bfad8d76468b807506`
- Xet hash:
  `2fe2572a6d762e51d88c6a90c1b77c0636d04122460c62e8b6e27894ff2bee70`
- Converter-declared quantization runtime: llama.cpp b9222

The model developer and GGUF converter are different parties. The artifact is
not described as an official Qwen GGUF. The upstream claim of 201 supported
languages is candidate-selection context, not Darwin evidence that this
quantization handles Portuguese well.

Any identity mismatch aborts E053. No mirror, different quantization, newer
revision, automatic substitute, authentication, or provider inference is
permitted.

## Unchanged language boundary

Keep the exact E049 transport and prompts. Keep E048 strict UTF-8, E047 control
marker rejection, native authenticated loopback transport, the two frozen JSON
schemas, 4,096-token context, one slot, 1,000-token ceiling, temperature zero,
disabled thinking, temporary transcript, and authority-zero boundary.

Do not download or enable a vision projection. The server's probed vision
modality must be false. The candidate changes the language model and its fixed
alias only.

## Artifact and load admission

1. download to an ignored `.part` path and rename only after exact byte and
   SHA-256 matches;
2. record the upstream and converter identities and Apache-2.0 source;
3. load with the unchanged b10470 runtime on authenticated `127.0.0.1`, one
   4,096-token slot, four CPU threads, no Web UI, and no warm-up;
4. require readiness within 60 seconds;
5. require peak working set at most `2,250,000,000` bytes;
6. require exact alias, context, slot, text-only modality, and build probes;
7. perform no inference during the load probe; and
8. stop the server and require zero listeners afterward.

Passing is desktop load admission only.

## Raw performance admission

After a passing load probe, run exactly:

```text
llama-bench.exe
  --model <fixed local model path>
  --offline
  --n-gpu-layers 0
  --n-prompt 256
  --n-gen 32
  --threads 4
  --repetitions 2
  --delay 1
  --output json
```

Record both samples, mean, raw output digest, elapsed time, exit code, and peak
working set. The candidate reaches language admission only if generation mean
is at least `4.0` tokens per second. Prompt throughput is descriptive. No weak
sample may be discarded or rerun.

## Engineering admission

Before live language use:

- the exact E049 transport and focused-test blobs must still match;
- `git diff` from the E051 admitted subject through `src/` and `tests/` must be
  empty;
- the focused portable-local suite must pass; and
- no provider fallback, response table, authority handle, persistent history,
  or automatic memory may be added.

The full repository suite is not repeated if and only if the admitted `src/`
and `tests/` trees are byte-identical. The existing E051 full-suite record then
remains the applicable code admission; this condition must be recorded.

## Development language screen

If every earlier E053 gate passes, repeat the eight E049 inputs, unchanged and
in one temporary session. Send the next input only after the preceding turn
returns a valid expression. Do not pre-queue later inputs.

The candidate passes only if all of these hold:

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
- every inference request completes within 120 seconds;
- zero provider use, persistent writes, authority mutations, or actions; and
- the server is stopped after the screen.

No output may be retried, repaired, or selectively omitted. If a required
inference fails or misses its deadline, stop before sending the next registered
input because the conjunction is already impossible. Record the incomplete
screen and do not evaluate unobserved quality criteria.

## Interpretation ceiling

A pass would establish improvement on the disclosed E049 development cases at
zero provider cost with this exact candidate system. It would not establish
held-out generalization, calibrated factual reliability, long-session quality,
mobile speed or energy use, autonomous learning, consciousness, or similarity
to Diana.
