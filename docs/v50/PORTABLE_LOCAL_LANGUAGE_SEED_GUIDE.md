# Portable local language seed guide

This guide describes the admitted E045 desktop harness. It does not install a
model, claim mobile readiness, or alter the frozen E043 and E044 experiments.

## Design

The maintained local path has no OpenAI key and no provider fallback:

```text
explicit local model and endpoint
              |
              v
llama.cpp on 127.0.0.1 (desktop harness only)
              |
              v
PortableLocalLanguageBackend
              |
              v
DarwinLanguageGateway
```

`PortableLocalLanguageBackend` depends on an injectable structured-inference
transport. A future mobile application can replace the loopback transport with
an in-process native implementation while retaining the language schemas and
authority boundary.

## Registered candidate

The first candidate is `Qwen/Qwen3-0.6B`, quantized as `Q4_K_M`, with a model
artifact no larger than 600 MiB. The exact GGUF source, digest, runtime build,
and license files must be recorded before a live run.

No download has been performed yet. Do not substitute another tag or model and
report it as E045.

## Desktop harness configuration

The future live harness must launch one `llama-server` slot with a 4,096-token
context and an explicit model alias. A representative command shape is:

```powershell
llama-server.exe `
  --model <frozen-model.gguf> `
  --alias <frozen-model-id> `
  --host 127.0.0.1 `
  --port 8080 `
  --ctx-size 4096 `
  --parallel 1 `
  --no-webui
```

The exact executable options must be checked against the frozen runtime build
before the live run. The server must not listen on a LAN address.

In a separate terminal:

```powershell
$env:DARWIN_LLM_BACKEND = "local"
$env:DARWIN_LLM_MODEL = "<exact frozen model alias>"
$env:DARWIN_LOCAL_ENDPOINT = "http://127.0.0.1:8080"
$env:DARWIN_LLM_TIMEOUT_SECONDS = "120"
darwin-local-conversation-dev
```

The endpoint parser accepts only an explicit `http://127.0.0.1:<port>` origin.
It rejects credentials, redirects, paths, queries, fragments, hostnames, LAN
addresses, and public hosts.

## Current status

```text
portable backend implementation   COMMITTED (34c4ee7)
hermetic admission                PASSED (16/16 focused; 489/489 repository)
model download                    VERIFIED (484,220,320 bytes; SHA-256 locked)
portable runtime                  VERIFIED (llama.cpp b10470; SHA-256 locked)
model load probe                  PASSED (loopback; 4,096 context; one slot)
first live UNDERSTAND             FAILED CLOSED (HTTP 400; grammar initialization)
live local inference              FAILED (zero model output; zero successful turns)
Portuguese development screen     UNEXECUTED
mobile benchmark                  UNEXECUTED
```

The repository run declared one unrelated platform skip: the existing Windows
symlink test could not create a symlink without the required OS privilege. The
machine-readable
[engineering admission record](results/EXPERIMENT_045_ENGINEERING_ADMISSION.json)
preserves the subject commit, implementation blobs, commands, counts, and
interpretation ceiling.

The separate
[artifact lock](results/EXPERIMENT_045_ARTIFACT_LOCK.json) records the exact
model quantization revision, model and runtime digests, licenses, runtime build,
and the fact that neither the model nor inference had been executed at the time
of registration.

The [load probe](results/EXPERIMENT_045_LOAD_PROBE.json) records the subsequently
observed runtime, model, tokenizer, chat-template, listener, readiness, and
desktop-memory values. It deliberately stops before the first generation
request.

The subsequent
[first-live-turn record](results/EXPERIMENT_045_FIRST_LIVE_TURN.json) preserves
the failed result. The exact E045 pairing returned HTTP 400 while llama.cpp was
initializing a JSON-schema grammar around Qwen3's disabled-thinking prefill.
No model output was received, `EXPRESS` was not attempted, and the service was
stopped. E045 is therefore not a working-conversation result.

Until those runs exist, the honest user-facing state is unavailable. A mock or
canned reply must not be presented as Darwin successfully understanding text.
