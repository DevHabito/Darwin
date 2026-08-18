# Experiment 061 - Gemma 3 270M consent-locked admission

Status: pre-registered and blocked before download. Written after the E060
failure was frozen and the rejected H-350M artifact was removed. The owner has
not yet attested acceptance of the Gemma terms, and no Hugging Face credential
is configured on this host.

## Purpose

Evaluate whether a small instruction-tuned multilingual candidate can satisfy
Darwin's edge resource constraints without treating a license-gated model as
if it were permissionless.

E061 is only a consent, artifact-identity, load, and raw-performance gate. It
does not send language input, construct a conversation backend, or promote a
model.

## Candidate selection

The selected family is Gemma 3 270M instruction-tuned QAT. Google's official
model card reports a 270M instruction-tuned variant, a 32K context limit for
that size, training data spanning more than 140 languages, and an IFEval score
of `51.2`. Those facts make it relevant to a mobile-oriented development
screen, but none of them proves Portuguese conversational quality.

The exact GGUF candidate is the llama.cpp organization's Q4_0 conversion of
Google's QAT checkpoint:

- source family: `google/gemma-3-270m-it`;
- QAT source checkpoint:
  `google/gemma-3-270m-it-qat-q4_0-unquantized`;
- GGUF repository: `ggml-org/gemma-3-270m-it-qat-GGUF`;
- frozen repository revision:
  `7dba9faa7cdb58c7dc44b238c7dbb00e391fbf65`;
- artifact: `gemma-3-270m-it-qat-Q4_0.gguf`;
- quantization: `Q4_0` from quantization-aware training;
- exact bytes: `241410624`;
- exact SHA-256:
  `3626e245220ca4a1c5911eb4010b3ecb7bdbf5bc53c79403c21355354d1e2dc6`;
- Xet object:
  `4d6b0c52459e62b41a96e0dd683203649e3d190f9e82d0296d350df29625cb5e`.

The official Qwen3 0.6B GGUF was not selected for this gate. Its publisher
offers only a 639 MB Q8 artifact, and its model card warns that greedy decoding
can degrade behavior. Changing Darwin's frozen deterministic transport and
accepting a substantially larger artifact would introduce two variables at
once.

Sources:

- [Google Gemma 3 270M instruction-tuned model card](https://huggingface.co/google/gemma-3-270m-it)
- [Google Gemma 3 model card and evaluation table](https://ai.google.dev/gemma/docs/core/model_card_3)
- [Google QAT source checkpoint](https://huggingface.co/google/gemma-3-270m-it-qat-q4_0-unquantized)
- [Frozen ggml-org Q4_0 artifact](https://huggingface.co/ggml-org/gemma-3-270m-it-qat-GGUF/blob/7dba9faa7cdb58c7dc44b238c7dbb00e391fbf65/gemma-3-270m-it-qat-Q4_0.gguf)
- [Official Qwen3 0.6B GGUF comparison candidate](https://huggingface.co/Qwen/Qwen3-0.6B-GGUF)

## Consent lock

Google requires a logged-in user to review and agree to its usage license
before accessing official Gemma files. E061 therefore requires an explicit
owner statement made after reviewing the linked terms. A generic instruction
to continue, a repository flag, an environment variable, or access to a public
conversion is not evidence that the owner reviewed and accepted those terms.

Until the owner provides that statement:

- no Gemma weight may be downloaded;
- no access token may be requested, read, stored, or inferred;
- the public conversion may not be used to bypass the upstream gate;
- no runner may claim consent; and
- E061 remains blocked before measurement.

The eventual runner must require a one-time command-line acknowledgement and
must fail before network access when it is absent. The acknowledgement is an
execution guard, not a legal record and not legal advice.

## Frozen runtime and thresholds

After consent is explicit, admit a dedicated runner with fake-process tests
before downloading anything. Reuse the frozen llama.cpp b10470 CPU binaries:

- llama.cpp commit: `34af94cd9ab277632e27caeec2d41de2fd091b31`;
- `llama-server.exe` SHA-256:
  `aa6b7907d3901f2e24892838e6f15243a47b22ad792eaccbdc0e2a4bccfd5283`;
- `llama-bench.exe` SHA-256:
  `23947ddff87fe418e2db0e49d6fb1b79f2f66c142cf7d5c614d0f4c870e05c4b`;
- CPU: Intel Core i5-8250U;
- four CPU threads and zero GPU layers.

The gate is sequential:

1. download the immutable revision to a new partial file;
2. require the exact byte count and SHA-256 before atomic promotion;
3. load with one 4,096-token slot, no Web UI, no warm-up, and an ephemeral
   loopback key;
4. require exact model/context probing;
5. stop the server and require no remaining listener;
6. only after load admission, run the offline raw benchmark; and
7. remove the artifact after a failure is recorded.

Frozen conjunction:

- ready within `30,000` milliseconds;
- load peak working set no greater than `800,000,000` bytes;
- benchmark peak working set no greater than `800,000,000` bytes;
- prompt processing mean at least `75.0` tokens per second;
- generation mean at least `25.0` tokens per second;
- two repetitions of 256 prompt tokens and 32 generated tokens;
- no conversation text, schema, provider, memory, goal, tool, or action;
- zero key leakage and zero listener after stop.

Do not lower a threshold or change the artifact after observing a result and
call it E061. A launcher or capture failure is invalid measurement, not model
evidence.

## Pass consequence

A pass permits only inspection and pre-registration of a Gemma-specific token
boundary. It does not permit conversation, voice activation, model promotion,
or any claim about Portuguese understanding.

## Interpretation ceiling

E061 can establish only that one licensed artifact loads and reaches frozen
raw-performance thresholds on one notebook. It cannot establish language
quality, mobile energy use, safety, learning, memory, emotion, consciousness,
or similarity to Diana from *Pragmata*.
