# Experiment 046 - authenticated native completion repair

Status: pre-registered and unexecuted. This protocol was written after E045
failed and before the maintained transport, CLI, tests, or server configuration
were changed.

## Why this is a new experiment

E045's exact first live `UNDERSTAND` request failed before generation. The
frozen llama.cpp chat-completions path combined Qwen3's disabled-thinking
prefill with the JSON-schema grammar and returned HTTP 400:

```text
Failed to initialize samplers:
Unexpected empty grammar stack after accepting piece: <think>
```

E046 does not reinterpret or replace that result. It tests a prospective repair
to the integration boundary. E045 remains failed even if E046 later works.

## Starting point and immutable evidence

- Base commit: `c8cc8184fa823126ebb2b941661de16eeede38ab`
- Development branch: `codex/portable-local-language-seed`
- E045 implementation blob at the starting point:
  `368db6f2c1088f76cb007f6f75d41f6dc1c13d6c`
- E045 test blob at the starting point:
  `6af60d89755d96a2304784e477c2d0ec6e2c02a0`

The following evidence blobs must remain exact:

| File | Frozen blob |
| --- | --- |
| `docs/v50/EXPERIMENT_045_PORTABLE_LOCAL_LANGUAGE_SEED.md` | `e29124e0aa96a54f54d0a9c72815559492d2e708` |
| `docs/v50/results/EXPERIMENT_045_ENGINEERING_ADMISSION.json` | `7290fc85204e9261b5886392974830cc48b59a4b` |
| `docs/v50/results/EXPERIMENT_045_ARTIFACT_LOCK.json` | `a7b7e4e131d3691b192c4f680b1ebeb8c3ddc9dc` |
| `docs/v50/results/EXPERIMENT_045_LOAD_PROBE.json` | `0cdba53ad169c60815fa8a0c2784021bda57b2b8` |
| `docs/v50/results/EXPERIMENT_045_FIRST_LIVE_TURN.json` | `92ba5d709be4f1cfc9b75a3953d8a199a9483838` |

The E043 and E044 freezes continue to apply independently.

## Fixed artifacts

E046 keeps both E045 artifacts unchanged:

- model file: `Qwen_Qwen3-0.6B-Q4_K_M.gguf`;
- model SHA-256:
  `9acfc1e001311f34b4252001b626f2e466d592a42065f66571bff3790d4e1b14`;
- llama.cpp release: `b10470`;
- runtime commit: `34af94cd9ab277632e27caeec2d41de2fd091b31`;
- runtime archive SHA-256:
  `a31f1f317813ae7e044be183e0a20b90e78a80c0e97ee11a8b32a014eccd5043`.

A model, quantization, tokenizer, runtime build, context limit, or schema change
is outside E046 and cannot inherit its result.

## Registered repair

The llama.cpp-specific desktop transport will stop using
`/v1/chat/completions` for structured generation. It will instead:

1. call `/apply-template` with the exact system and user messages and thinking
   disabled;
2. accept exactly one bounded prompt string from that endpoint;
3. call the native `/completion` endpoint with that prompt and the same explicit
   operation JSON Schema;
4. reject partial, truncated, malformed, empty, or tool-bearing results; and
5. pass the parsed object through the existing Darwin language gateway again.

This is an endpoint repair, not a schema relaxation. A plain `json_object`
constraint, prompt-only JSON request, regex parser, response extraction
heuristic, or unconstrained generation is not an admitted substitute.

The portable `StructuredLocalTransport` boundary remains unchanged so a future
mobile in-process engine is not coupled to HTTP.

## Authenticated loopback rule

The E045 runtime log warned that wildcard CORS without an API key created a
same-host cross-origin risk. E046 therefore requires all of the following:

- the listener remains exactly `127.0.0.1`;
- llama.cpp receives a fresh, cryptographically random session API key;
- the key is never committed, printed, logged, included in a snapshot, or
  persisted as Darwin memory;
- every Darwin request sends the key only to the exact registered loopback
  origin;
- redirects remain disabled;
- the Web UI, model tools, MCP proxy, prompt cache, and external networking are
  not enabled by Darwin; and
- special tokens in user-originated input are escaped by the runtime before
  tokenization.

This local bearer key is not an OpenAI key, account credential, paid service,
or cloud dependency. It only protects the temporary process boundary on the
same machine.

## Frozen request limits

- context: exactly 4,096 tokens;
- parallel slots: exactly one;
- maximum structured output: 1,000 tokens;
- maximum combined instructions and payload: 14,000 characters;
- temperature: `0.0`, preserving the E045 request rather than tuning after the
  failed result;
- thinking: disabled;
- tools: absent;
- successful turn order: exactly `UNDERSTAND`, then `EXPRESS`.

No sampling parameter will be tuned on the first-turn result. Qwen's published
recommendation for non-thinking sampling differs from this fixed setting, so a
failure may reflect the registered deterministic constraint.

## Hermetic admission before a second live turn

Automated tests must establish:

1. every frozen E045 evidence blob remains exact;
2. the transport never calls `/v1/chat/completions`;
3. `/apply-template` precedes `/completion` exactly once per operation;
4. both calls use the exact authenticated loopback origin;
5. the authorization value cannot appear in exceptions, snapshots, or request
   records intended for evidence;
6. the native completion retains the explicit JSON Schema and frozen bounds;
7. missing prompt fields, malformed native responses, truncation, unexpected
   fields, and authority-bearing output fail closed;
8. a failed operation clears pending context and commits no transcript;
9. successful mock turns still report every authority counter as zero; and
10. the full repository suite passes.

Mocks cannot establish that the repair works with the frozen model.

## First live repair check

After hermetic admission, E046 will repeat the exact E045 sentence once:

> Oi, Darwin. Estou animado para conversar com você hoje. Como devemos começar?

The live repair check passes only if:

- `UNDERSTAND` returns one gateway-valid object;
- `EXPRESS` returns one gateway-valid object;
- the expression acknowledges every required Darwin fact id;
- the session records exactly one temporary user message and one temporary
  Darwin message;
- no external network request is needed;
- no credential appears in output or evidence; and
- every authority mutation counter remains zero.

Any retry after a failed live result belongs to another pre-registered repair.

## Interpretation ceiling

A passing E046 result would establish only that the fixed local model/runtime
pair can complete one authenticated, schema-constrained Darwin turn through the
native llama.cpp endpoint.

It would not establish calibrated Portuguese understanding, safe factual
knowledge, long-conversation quality, offline operation, mobile suitability,
learning, autonomous cognition, consciousness, or similarity to Diana.
