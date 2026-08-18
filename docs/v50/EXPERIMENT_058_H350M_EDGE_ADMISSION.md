# Experiment 058 - Granite H-350M edge admission

Status: pre-registered and unexecuted. Written before downloading or executing
the fixed candidate artifact.

## Purpose

Test whether an official 350M-class multilingual instruct model is fast and
small enough to justify a later Darwin-specific safety adapter. E058 performs
no language generation and cannot promote a conversational model.

E057 rejected Granite 4.0 1B Q3 because prompt processing averaged
`18.65875` tokens per second against its frozen `25.0` threshold, even though
generation passed. E058 changes the model family member and quantization and is
therefore a new experiment, not a repair or threshold change.

## Frozen starting point

- E057 result commit: `69cdadc2b20c212cbd1306876fb368311d2c357e`
- E057 result blob: `3b7743c541666fd367a9b1e66595e0911dad0c63`
- v50 voice-host commit: `b383fc4e8b19f7638ee61773c8a026e0e4b6846c`
- E057 rejected-model artifact is absent from local storage.

## Candidate record

The IBM model card describes Granite 4.0 H-350M as a lightweight instruct
model for edge and on-device use. It declares Apache 2.0, lists Portuguese,
and reports 340M active parameters. The card also says multilingual quality
may differ from English and recommends task-specific safety testing. Those are
upstream statements and limitations, not Darwin evidence.

The H-350M card reports better average instruction-following scores than the
non-H 350M sibling, while using four attention and 28 Mamba2 layers. This is
candidate-selection context only; E058 does not reproduce those benchmarks.

Official sources:

- [Granite 4.0 H-350M model card](https://huggingface.co/ibm-granite/granite-4.0-h-350m)
- [Granite 4.0 H-350M GGUF repository](https://huggingface.co/ibm-granite/granite-4.0-h-350m-GGUF)

## Frozen artifact

- repository: `ibm-granite/granite-4.0-h-350m-GGUF`
- revision: `a864f823cce6e6048b5752e2816fe7a23987d790`
- filename: `granite-4.0-h-350m-Q4_K_M.gguf`
- quantization: `Q4_K_M`
- expected bytes: `222,662,560`
- expected SHA-256:
  `0a8d6a7373602fadfba274a640ba784b86cc6847f1c67f1b0a90fa2ec266b7fb`
- repository blob ID: `f49c4bb0e598ac8fddc357b4f6a3e092136068ec`
- declared license: Apache-2.0
- gated: no

Download only from the revision-pinned official `resolve` URL into an ignored
`.part` file. Promote the file only after exact byte and SHA-256 verification.
No mirror, alternative quantization, or automatic substitute is permitted.

## Frozen runtime

Reuse the E057 runtime without modification:

- llama.cpp b10470;
- commit `34af94cd9ab277632e27caeec2d41de2fd091b31`;
- `llama-server.exe` SHA-256
  `aa6b7907d3901f2e24892838e6f15243a47b22ad792eaccbdc0e2a4bccfd5283`;
- `llama-bench.exe` SHA-256
  `23947ddff87fe418e2db0e49d6fb1b79f2f66c142cf7d5c614d0f4c870e05c4b`;
- Intel Core i5-8250U CPU, four fixed threads, zero GPU layers.

A load failure is a compatibility failure for this exact pairing. No runtime
upgrade is allowed inside E058.

## Load admission

After the pre-registration and measurement runner are separately committed:

1. verify every frozen commit, blob, executable, and artifact identity;
2. start an authenticated server only on `127.0.0.1:18058` with a fresh
   in-memory bearer value;
3. use one slot, 4,096 context tokens, four CPU threads, zero GPU layers, no
   Web UI, no warm-up, and no prompt cache;
4. require readiness within 30 seconds;
5. require peak working set no greater than `1,000,000,000` bytes;
6. require exact alias, context, slot, text-only modality, and build probes;
7. submit no generation request; and
8. require the bearer value absent from logs and zero listener after shutdown.

Any failure stops before the raw benchmark.

## Raw performance admission

Only after a complete load pass, run the same offline synthetic shape used in
E057:

```text
--model <verified artifact>
--offline
--n-gpu-layers 0
--n-prompt 256
--n-gen 32
--threads 4
--repetitions 2
--delay 1
--output json
```

Admission requires all of:

- exit code zero and exactly two finite positive samples per test;
- mean prompt processing at least `50.0` tokens per second;
- mean generation at least `20.0` tokens per second;
- peak working set no greater than `1,000,000,000` bytes;
- no server, network access, user text, or conversation request; and
- raw values and file digests preserved before interpretation.

These stricter thresholds reflect why a 350M candidate is being tested: it
must offer a material latency margin for a future two-stage voice path, not
merely be smaller on disk.

## Result handling and disk policy

The measurement code must have focused failure tests and pass the complete
repository suite before model download. Record a single execution. Do not
rerun a failed sample, average a second run into the result, change a threshold,
or upgrade the runtime after observation.

If E058 fails, commit the result and remove the exact model file. If it passes,
retain the file only through a separately pre-registered Granite control-token
and structured-output adapter gate. Passing E058 alone does not authorize the
v50 voice host.

## Interpretation ceiling

A pass would establish only desktop load, memory, and synthetic throughput for
this exact artifact. It would not establish Portuguese understanding,
structured output, resistance to Granite control-token injection, factual
accuracy, useful conversation, mobile latency or energy use, learning, memory,
emotion, consciousness, or similarity to Diana from *Pragmata*.
