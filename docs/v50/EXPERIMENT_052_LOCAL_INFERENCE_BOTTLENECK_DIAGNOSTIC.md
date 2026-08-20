# Experiment 052 - local inference bottleneck diagnostic

Status: pre-registered and unexecuted. Written after the failed E051 result was
frozen and before running `llama-bench` with the E051 artifact.

## Purpose

Determine whether E051's observed generation rate is primarily consistent with
the model's raw CPU throughput on this computer or with overhead in Darwin's
schema-constrained language path. This diagnostic may select a thread count for
a later experiment. It cannot promote a model or establish language quality.

## Starting point

- Base commit: `50929559197fa695f44626a42d314cabc1338936`
- E051 failure-result blob:
  `c2d636590bb6e8ea9da49cebc0818d2697d4ea91`
- E051 observed final generation-rate report: `1.54` tokens per second
- E051 first required inference completed within 120 seconds: no

All earlier protocol and evidence freezes remain in force.

## Fixed artifact and runtime

- Model repository: `Qwen/Qwen2.5-1.5B-Instruct-GGUF`
- Model revision: `62a8d092b0a1047016f3edbd0fde387598727aa5`
- Model file: `qwen2.5-1.5b-instruct-q4_k_m.gguf`
- Model SHA-256:
  `6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e`
- Runtime: llama.cpp build 10470, commit `34af94cd9`
- `llama-bench.exe` SHA-256:
  `23947ddff87fe418e2db0e49d6fb1b79f2f66c142cf7d5c614d0f4c870e05c4b`
- `llama-bench-impl.dll` SHA-256:
  `11d460130758a4f024c78de341bcfc2b85302bd7d9bdbe830174183f0ec4205b`
- CPU backend selected by this runtime before registration:
  `ggml-cpu-haswell.dll`

Any identity mismatch aborts E052.

## Fixed benchmark

Run from the fixed runtime directory with networking disabled by the tool:

```text
llama-bench.exe
  --model <fixed local model path>
  --offline
  --n-gpu-layers 0
  --n-prompt 256
  --n-gen 32
  --threads 2,4,8
  --repetitions 2
  --delay 1
  --output json
```

Warm-up remains enabled. Process priority remains at the runtime default. No
user text, conversation transcript, JSON schema, server, provider, network, or
language output is used. The synthetic benchmark does perform local model
inference.

Record the raw JSON artifact, its digest, elapsed wall time, process exit code,
and peak working set. Do not discard repetitions or rerun a weak configuration.

## Interpretation rules

For generation throughput (`tg32`):

1. rank candidates by the arithmetic mean reported by `llama-bench`;
2. if a lower-thread candidate is within five percent of the highest mean,
   select the lower thread count;
3. if the selected raw mean is at most `2.0` tokens per second, classify raw
   model throughput as the immediate bottleneck on this computer;
4. if the selected raw mean is at least `4.0` tokens per second and at least
   twice E051's `1.54` final reported rate, classify the schema-constrained
   path as the immediate bottleneck hypothesis for a later registered test;
5. otherwise classify the result as inconclusive between those two causes.

Prompt-processing throughput is descriptive only and cannot override these
rules.

## Stop and authority conditions

- stop the benchmark process after the fixed matrix;
- do not start `llama-server`;
- make no conversational request;
- write no Darwin memory, goals, identity, world model, RZS, or sigma;
- execute no action;
- use no paid provider or provider credential; and
- make no model or runtime promotion from this diagnostic alone.

## Interpretation ceiling

E052 can localize a performance bottleneck under one synthetic benchmark on
this Windows laptop. It does not establish server latency, schema correctness,
conversational quality, mobile speed, energy use, thermal stability, held-out
generalization, autonomous learning, consciousness, or similarity to Diana.
