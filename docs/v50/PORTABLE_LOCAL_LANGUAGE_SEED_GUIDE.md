# Portable local language seed guide

This guide describes the admitted E045 desktop harness. It does not install a
model, claim mobile readiness, or alter the frozen E043 and E044 experiments.

## Design

The maintained local path has no OpenAI key and no provider fallback. E046 adds
a fresh local-only bearer value to protect the temporary loopback process; it
is not a provider credential:

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

The first candidate is `Qwen/Qwen3-0.6B`, quantized as `Q4_K_M`. The frozen
GGUF is 484,220,320 bytes with SHA-256
`9acfc1e001311f34b4252001b626f2e466d592a42065f66571bff3790d4e1b14`.
It is stored under the ignored project runtime directory, not installed as a
system service. Its source revision, license, and the exact llama.cpp runtime
are preserved in the E045 artifact lock.

## Desktop harness configuration

The live desktop harness launches one `llama-server` slot with a 4,096-token
context and an explicit model alias. A representative command shape is:

```powershell
llama-server.exe `
  --model <frozen-model.gguf> `
  --alias <frozen-model-id> `
  --host 127.0.0.1 `
  --port 8080 `
  --ctx-size 4096 `
  --parallel 1 `
  --no-webui `
  --cache-ram 0 `
  --reasoning off `
  --reasoning-format none `
  --api-key <fresh-random-local-session-key>
```

The exact executable options must be checked against the frozen runtime build
before the live run. The server must not listen on a LAN address.

In a separate terminal:

```powershell
$env:DARWIN_LLM_BACKEND = "local"
$env:DARWIN_LLM_MODEL = "<exact frozen model alias>"
$env:DARWIN_LOCAL_ENDPOINT = "http://127.0.0.1:8080"
$env:DARWIN_LOCAL_API_KEY = "<same-fresh-random-local-session-key>"
$env:DARWIN_LLM_TIMEOUT_SECONDS = "120"
darwin-local-conversation-dev
```

The endpoint parser accepts only an explicit `http://127.0.0.1:<port>` origin.
It rejects credentials, redirects, paths, queries, fragments, hostnames, LAN
addresses, and public hosts.

E046 uses llama.cpp's native `/apply-template` and `/completion` endpoints after
E045 demonstrated that the chat-completions parser could not initialize the
Qwen3 JSON-schema grammar. The explicit schema and gateway validation remain in
place.

The frozen b10470 runtime does not expose E046's pre-registered
`--escape-special-in-input` option, so that experiment could not be launched.
E047 instead rejects the frozen model's exact control markers in every
user-originated, model-bound field before `/apply-template`. It does not reject
ordinary angle brackets and does not claim that the runtime performs escaping.
The
[engineering admission record](results/EXPERIMENT_046_ENGINEERING_ADMISSION.json)
therefore marks E046 failed before a live repair turn.

## Current status

```text
portable backend implementation   COMMITTED (34c4ee7)
current UTF-8 implementation      COMMITTED (cd23929)
current numeric repair            COMMITTED (c8ff493)
current gated runner              COMMITTED (009d9ac)
current repository admission      PASSED (504 pass + 1 declared skip)
0.6B model download               VERIFIED (484,220,320 bytes; SHA-256 locked)
0.8B model download               VERIFIED (579,615,840 bytes; SHA-256 locked)
portable runtime                  VERIFIED (llama.cpp b10470; SHA-256 locked)
model load probe                  PASSED (loopback; 4,096 context; one slot)
E045 first live turn              FAILED (chat grammar initialization)
E046 native repair                FAILED (unsupported registered runtime flag)
E047 authenticated live turn      FAILED (Windows Unicode input integrity)
E048 exact UTF-8 live turn        PASSED (UNDERSTAND + EXPRESS; authority zero)
E048 observed response quality    WEAK (valid but little substantive guidance)
E049 0.6B conversation screen     FAILED QUALITY (echoes and stale copies)
E051 1.5B comparison              FAILED PERFORMANCE (120-second timeout)
E053 0.8B screen                  FAILED GATEWAY (numeric range)
E054 numeric repair engineering   PASSED; FIRST LIVE RUN INVALIDATED
E055 gated 0.8B screen            FAILED QUALITY (stale copy at turn 2)
promoted local language model     NONE
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

The [E047 live record](results/EXPERIMENT_047_FIRST_LIVE_TURN.json) preserves
the later input-integrity failure rather than promoting the two otherwise valid
inference stages. The [E048 live record](results/EXPERIMENT_048_FIRST_LIVE_TURN.json)
then establishes exact UTF-8 input, one gateway-valid `UNDERSTAND` plus
`EXPRESS` turn, and a pre-inference control-token rejection. It used no paid
provider and changed no Darwin authority state.

The current local path is executable and remains free of provider charges, but
conversational usefulness has not passed a development screen. E055 confirms
that the numeric grammar repair can produce gateway-valid coarse levels on two
known inputs; it also confirms that the fixed 0.8B candidate can copy a stale
reply instead of answering the current question. A mock, canned reply, schema
pass, or two-turn transport success must not be presented as evidence of strong
understanding.
