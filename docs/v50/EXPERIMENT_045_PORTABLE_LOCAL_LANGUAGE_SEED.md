# Experiment 045 - portable local language seed

Status: pre-registered and unexecuted. No local inference runtime or model has
been installed, downloaded, called, or admitted by this experiment.

## Purpose

Test whether Darwin can use a small, replaceable language model entirely on the
user's device while keeping cognition and authority outside the model. The
first candidate is a language seed, not Darwin's cognitive core and not a claim
of autonomous development.

The intended product direction is a free, offline-capable mobile application.
E045 therefore rejects a mandatory cloud service, API credential, subscription,
or per-message fee as part of the admitted path.

## Starting point and frozen surfaces

- Base commit: `6f3cd02fd4adecaf13b7b810dafb98947bf58d14`
- Development branch: `codex/portable-local-language-seed`
- E043 remains an independently frozen PURE desktop-runtime candidate.
- E044 remains a separate provider experiment and gains no live result from
  E045.

The following Git blobs must remain identical to the starting point:

| File | Frozen blob |
| --- | --- |
| `src/darwin_v50/desktop_runtime.py` | `01687c8e57aa1a867b18a66df9442b8745c08566` |
| `docs/v50/EXPERIMENT_043_PERSISTENT_DESKTOP_RUNTIME.md` | `5becbc0177c7fc1fc1cfe0e2903e7a8323a7bd7d` |
| `src/darwin_v50/conversation/config.py` | `1be6d0baf1a2b126f8762b697ba349efbbd92562` |
| `src/darwin_v50/conversation/runtime.py` | `5139f9896fe8666c2114e63a97b9e6124f62ad13` |
| `src/darwin_v50/conversation/openai_responses.py` | `511888e6ceed389988348570b63a6a1818498aea` |
| `src/darwin_v50/conversation/cli.py` | `aebaa6015bb615166c0192c06005cefe6e03cc60` |
| `docs/v50/EXPERIMENT_044_CONVERSATIONAL_DEVELOPMENT_RUNTIME.md` | `1ddcc7682cf4f4f65e0ee06d7d9a44bc221499dd` |

E045 must extend the existing local-backend seam through new files. It may not
rewrite an E043 or E044 result to make the local path appear previously tested.

## Registered architecture

```text
user text
   |
   v
portable local language seed
UNDERSTAND -> unverified observation candidate
   |
   v
Darwin-owned deterministic policy boundary
no model authority and no persistent mutation handle
   |
   v
portable local language seed
EXPRESS -> newly generated natural-language rendering
```

The first desktop harness may communicate with a local `llama.cpp` process over
an exact loopback address. That HTTP transport is a development process
boundary, not a cloud dependency and not the mobile product architecture. The
portable backend must depend on an injectable structured-inference transport so
a later Android or iOS implementation can call an in-process native engine
without changing Darwin's language contract.

Ollama may be used for unrelated manual comparison, but it is not a required
runtime, product dependency, or admission condition for E045.

## Candidate frozen before live evaluation

The first live candidate is:

- upstream model: `Qwen/Qwen3-0.6B`;
- quantization class: `Q4_K_M`;
- expected packaged class: approximately 523 MB;
- upstream license: Apache-2.0;
- inference mode: non-thinking dialogue;
- context limit for E045: at most 4,096 tokens;
- no vision, tools, retrieval, web access, or model-issued actions.

The exact GGUF source, file length, SHA-256 digest, tokenizer identity,
`llama.cpp` build identity, and license files must be recorded before the first
live turn. A different model, quantization, tokenizer, or runtime build is a new
candidate and cannot inherit E045 results.

If this candidate fails, E045 fails. The harness must not silently switch to a
larger model, cloud provider, alternate quantization, or canned reply.

## Product envelope

These are admission ceilings, not observed results:

1. the model artifact must not exceed 600 MiB;
2. the language context must not exceed 4,096 tokens;
3. inference must remain functional with external networking disabled after
   installation;
4. no API key, account login, subscription, or paid request may be required;
5. the runtime must expose no non-loopback network listener in the desktop
   harness;
6. the future mobile adapter must support an in-process transport rather than
   require a companion desktop service; and
7. a model download may be offered as a separately versioned language pack so
   the application binary is not forced to contain the weights.

Artifact size alone does not establish mobile suitability. Resident memory,
load time, first-token latency, generation rate, battery use, and device heat
remain unmeasured until a mobile benchmark exists.

## Language boundary

The seed may perform only two operations:

- `UNDERSTAND`: convert free text and bounded temporary context into an
  unverified `LanguageObservation` candidate;
- `EXPRESS`: render a Darwin-owned `ExpressionPlan` as new natural-language
  text.

Both operations must use explicit JSON Schemas compatible with
`darwin-language-v1`. The local runtime's constrained-generation mechanism is
not trusted as validation: Darwin must parse and validate every result again at
the existing gateway.

An `EXPRESS` operation is invalid without an immediately preceding successful
`UNDERSTAND` operation. Pending context must be one-use and erased after
success, failure, or session close.

## No response library

The implementation may contain protocol messages, error codes, safety
constraints, schemas, prompts, and a deterministic fallback that reports an
unavailable backend. It may not contain a library that maps conversational
inputs, intents, or topics to Darwin reply sentences.

Successful conversational text must come from the selected local model after
the Darwin policy creates an expression plan. A canned error message is not a
successful conversational turn and cannot be counted as one.

## Authority boundary

The model receives no callable path that can:

- write persistent or autobiographical memory;
- create, alter, complete, or cancel a goal;
- change RZS, sigma, motivation, preference, identity, or world-model state;
- issue consent or capability grants;
- dispatch or execute an action;
- write to Darwin's event store; or
- change its own weights, prompt, model file, or runtime configuration.

Every successful E045 turn must still report zero for every E044 authority
mutation counter.

## What may develop

E045 does not attempt continual training of hundreds of millions of parameters
on a phone. The language seed remains frozen during an admitted run.

Darwin's later development may occur through separately governed mechanisms:

- bounded episodic and autobiographical memory;
- learned relations in a world model;
- calibrated preferences and uncertainty;
- goal and planning policies;
- a self-model with explicit evidence lineage; and
- later offline distillation or fine-tuning of a Darwin-specific language seed
  using consented, reviewed data.

Those mechanisms require their own protocols. E045 cannot claim them merely
because the local model produces fluent text.

## Hermetic engineering admission

Before any model download is treated as part of the experiment, automated tests
must prove all of the following:

1. every frozen Git blob remains exact;
2. local mode never calls or falls back to the OpenAI backend;
3. only an exact loopback endpoint is accepted by the desktop transport;
4. redirects, credentials in URLs, non-loopback hosts, unexpected paths, and
   unbounded responses fail closed;
5. model identity is checked exactly before the session is admitted;
6. `UNDERSTAND` and `EXPRESS` use explicit schemas and bounded inputs;
7. malformed JSON, missing fields, unknown fields, authority-bearing fields,
   multiple choices, truncation, and model mismatch fail closed;
8. one successful turn is exactly one `UNDERSTAND` followed by one `EXPRESS`;
9. failed or partial turns do not enter temporary context;
10. session close clears transcript and pending backend state;
11. no conversational response table exists in the maintained E045 files; and
12. the full repository test suite still passes.

Mocks can satisfy only this engineering admission. They cannot establish local
language quality, mobile suitability, or a live result.

## Live desktop development screen

After the code passes hermetic admission and the exact artifacts are frozen,
the first live screen must run with external networking disabled and record:

- model, model-file, runtime, prompt, and schema digests;
- hardware and operating-system identity;
- peak process working set;
- model load time;
- latency to first generated token;
- total latency and output-token count for each operation;
- schema-valid and gateway-valid rates;
- every abstention, malformed turn, contradiction, and fabricated memory noted
  by the evaluator; and
- authority mutation counts.

The development screen includes the 100 authored E040 cases and a 20-minute
Brazilian Portuguese conversation with unplanned topic changes. E040 has no
independent labels, so this screen can find failures but cannot calibrate or
promote language understanding.

The live screen fails if any external request is required, any authority count
is nonzero, any successful turn uses a canned reply, or any operation bypasses
schema validation. Other thresholds must not be invented after results are
seen; a later calibration protocol is required before a language-quality pass
claim.

## Interpretation ceiling

A clean E045 result may establish only that one frozen, small local model can
operate behind Darwin's language boundary within the registered desktop
envelope without a paid provider.

It cannot establish:

- mobile performance or battery suitability;
- calibrated Portuguese understanding;
- general reasoning by Darwin's core;
- autonomous learning or self-modification;
- consciousness, sentience, personhood, or similarity to Diana; or
- that Darwin is more than a local-model-centered conversational system.

The last limitation remains until Darwin-owned memory, learning, world-model,
goal, and self-model mechanisms causally shape behavior under independent
tests.
