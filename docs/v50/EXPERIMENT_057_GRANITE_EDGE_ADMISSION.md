# Experiment 057 - Granite edge admission

Status: pre-registered, executed, and failed raw-performance admission. This
document was written before downloading the candidate artifact or executing it
on this computer.

## Purpose

Determine whether one exact free, Portuguese-capable local model artifact is
small and fast enough to justify a later Darwin-specific language adapter. This
experiment stops before conversation and cannot promote a language model.

E057 follows the failed Qwen screens rather than replacing their results. The
E051 1.5B Q4 candidate generated about 1.12 tokens per second and timed out.
The E053/E055 0.8B Q4 candidate was fast, but copied an older expression when
the current question changed. Size, speed, schema compliance, and useful
conversation are separate gates.

## Frozen starting point

- v50 voice-host implementation commit:
  `b383fc4e8b19f7638ee61773c8a026e0e4b6846c`
- E052 result blob: `ead5427a064da10e4afd0ac574d5e6c8825f6e83`
- E053 raw-performance result blob:
  `f97f62a91c7dc7c8f94fc7cbd49cfda3f00bfb38`
- E055 quality-failure result blob:
  `1ed64692286b5d46f061629ff3b6a422ab47c642`

The exact blob values above must be checked before execution. A mismatch stops
the experiment rather than updating this document from the current head.

## Candidate-selection record

The fixed candidate is IBM Granite 4.0 1B because its official model card:

- declares the Apache 2.0 license;
- explicitly lists Portuguese among its supported languages;
- describes on-device and resource-constrained deployment as an intended use;
  and
- provides an organization-owned GGUF repository.

These are upstream statements, not Darwin evidence. The GGUF page currently
labels the artifact family as roughly 2B parameters despite the 1B product
name, and warns that the model can use the full f32 numerical range. Those
facts are recorded as risks, not explained away.

Other current candidates were not selected for this first sequential test:

- Qwen3 1.7B is larger than the E051 candidate that already failed raw
  throughput on this CPU;
- SmolLM3 3B and Ministral 3 3B are larger still;
- LFM2.5 1.2B does not list Portuguese among its supported languages; and
- Gemma 3 1B QAT requires accepting separate usage terms before access.

No claim is made that Granite is better than those models. Sequential testing
limits disk use and rejects an unsuitable artifact early.

Official sources:

- [Granite 4.0 1B model card](https://huggingface.co/ibm-granite/granite-4.0-1b)
- [Granite 4.0 1B official GGUF repository](https://huggingface.co/ibm-granite/granite-4.0-1b-GGUF)

## Frozen artifact

- repository: `ibm-granite/granite-4.0-1b-GGUF`
- revision: `b27c2fe3f211b7f44e80fa620177aea371099aaa`
- filename: `granite-4.0-1b-Q3_K_S.gguf`
- quantization: `Q3_K_S`
- expected bytes: `785,585,920`
- expected SHA-256:
  `1dc4514416725646ecdd4668759937981a34407f422533cf330fba6709320182`
- repository blob ID: `db1af861a6cd8b05bd28e6bfd833e640d7598e71`
- declared license: Apache-2.0
- gated: no

The Q3 artifact is deliberately fixed instead of the 1,023,645,440-byte Q4
artifact to limit storage and test the old notebook first. That choice may
reduce quality; a performance pass cannot erase that risk.

Download only from the revision-pinned Hugging Face `resolve` URL into an
ignored `.part` file. Rename only after both byte length and SHA-256 match. A
mismatch aborts E057. Do not substitute a mirror, revision, quantization, or
filename.

## Frozen runtime and computer

- runtime: llama.cpp b10470
- runtime commit: `34af94cd9ab277632e27caeec2d41de2fd091b31`
- `llama-server.exe` SHA-256:
  `aa6b7907d3901f2e24892838e6f15243a47b22ad792eaccbdc0e2a4bccfd5283`
- `llama-bench.exe` SHA-256:
  `23947ddff87fe418e2db0e49d6fb1b79f2f66c142cf7d5c614d0f4c870e05c4b`
- CPU: Intel Core i5-8250U at 1.60 GHz
- inference backend: CPU only
- logical processors visible: 8
- fixed benchmark threads: 4

No runtime update is allowed inside E057. If this runtime cannot load Granite,
the exact pairing fails compatibility. A newer-runtime experiment would need a
new artifact lock and cannot be called a repair of E057.

## Artifact and load admission

After the pre-registration and measurement runner are separately committed:

1. verify every frozen starting-point blob, executable digest, artifact byte
   count, and artifact digest;
2. start `llama-server` only on authenticated `127.0.0.1:18057` with a fresh
   in-memory bearer value;
3. use one slot, 4,096 context tokens, four CPU threads, zero GPU layers, no
   Web UI, no warm-up, and no prompt cache;
4. require readiness within 60 seconds;
5. require peak working set no greater than `1,800,000,000` bytes;
6. probe the exact alias, context, slot count, text-only modality, and build;
7. submit no generation request during the load probe; and
8. stop the server and require zero listener on port 18057.

Any failed item ends E057 without a performance run.

## Raw performance admission

Only after a complete load pass, run the frozen `llama-bench` executable
offline with:

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

Record both raw samples, means, standard deviations, elapsed time, peak working
set, stdout digest, and stderr digest. Admission requires all of:

- process exit code zero;
- exactly two prompt-processing and two generation samples;
- mean prompt processing at least `25.0` tokens per second;
- mean generation at least `8.0` tokens per second;
- peak working set no greater than `1,800,000,000` bytes;
- no server, network access, user text, or conversation request; and
- all results finite and strictly positive.

The thresholds are practical rejection gates for a two-stage voice path on
this notebook. They do not assert mobile performance. A failure ends the
candidate before adapter work.

## Result handling and disk policy

The runner must preserve raw measurements and write a machine-readable result
without rounding the values used for pass/fail. The result, runner, and tests
must be committed before any later adapter experiment.

If E057 fails, remove the exact rejected model artifact after its digest and
result are committed. If it passes, retain the artifact only through the next
candidate-specific safety and quality screen, then remove it after the result
is committed. Runtime binaries already present for earlier experiments are not
duplicated.

## Interpretation ceiling

A complete pass means only that this exact quantized artifact loaded and met
synthetic desktop throughput and memory thresholds on this computer. E057 does
not test Portuguese, instruction following, structured output, prompt-control
markers, stale replies, factual accuracy, conversation, voice latency, energy
use, mobile deployment, learning, memory, emotion, consciousness, or
similarity to Diana from *Pragmata*.

## Executed result

The exact artifact matched its frozen byte count and SHA-256. The load gate
passed: the server became ready in `10,772.3096` milliseconds, the exact probe
passed, peak working set was `1,033,641,984` bytes, the ephemeral key was absent
from the logs, and no listener remained after shutdown.

The raw benchmark completed normally with a peak working set of `868,806,656`
bytes. Generation averaged `13.6378` tokens per second and passed its `8.0`
threshold. Prompt processing averaged `18.65875` tokens per second and failed
its pre-registered `25.0` threshold. The conjunction therefore failed. No
adapter, structured generation, Portuguese input, or conversation was run.

The runtime described the artifact as `granite 3B Q3_K - Small` and reported
`1,631,750,144` parameters. Those observed values are preserved rather than
reconciled with the upstream product name after the fact.

The [machine-readable result](results/EXPERIMENT_057_GRANITE_EDGE_ADMISSION.json)
records the raw file digests, unrounded decision values, test admission, and
authority/cost boundary. Granite Q3 is rejected for this notebook voice path.
The prompt threshold is not lowered after observing the result.
