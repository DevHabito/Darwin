# Experiment 044 - conversational development runtime

Status: automated development admission passed after pre-registration. The live
provider and 20-30 minute usability probes are unexecuted. No language-quality
or scientific capability claim is registered.

## Purpose

Build a deliberately separate development surface for open-ended conversation
without changing the E043 persistent desktop candidate or granting a language
model authority over Darwin's persistent state.

This is a usability and boundary experiment. It is not a calibration
experiment, a consciousness test, evidence of personhood, or evidence that
Darwin is more than a language model. A fluent result can establish only that a
configured model can operate behind the existing language boundary while the
development runtime preserves its stated restrictions.

## Frozen starting point

- Base commit: `2602c57f21dc930b6fbe4426610469b39357119f`
- Development branch: `codex/conversational-darwin-dev`
- E043 runtime SHA-256:
  `fd0d8aaf2bd1011addea581eaef172ce940157164dc013681d5326476d49f7e8`
- E043 protocol SHA-256:
  `beea70ce6bcfd177a18d36feca016f5f93ed0bed7743fc73c31152cc19eaefad`

The files covered by the two digests above must remain byte-identical in this
experiment:

- `src/darwin_v50/desktop_runtime.py`
- `docs/v50/EXPERIMENT_043_PERSISTENT_DESKTOP_RUNTIME.md`

E043 remains PURE and keeps its own incomplete 14-day admission campaign.
E044 cannot complete, revise, or add evidence to E043.

## Architecture under test

```text
explicit backend configuration
             |
             v
OpenAI backend / explicit local seam / no backend
             |
             v
DarwinLanguageGateway
    UNDERSTAND -> candidate observation
             |
             v
deterministic conversation policy
    candidate remains unverified
    no persistent mutation path
             |
             v
DarwinLanguageGateway
       EXPRESS -> natural-language rendering
```

The deterministic conversation policy is a narrow core-side policy for this
development surface. It does not claim to be the full Darwin cognitive kernel.
The present v50 kernel has no general conversational deliberation mechanism;
pretending otherwise would overstate the implementation.

## Pre-registered invariants

### Backend selection

1. `DARWIN_LLM_BACKEND` is the only backend selector.
2. The default is `none`.
3. Valid selections are `none`, `openai`, and `local`.
4. `openai` never falls back to `local`, and `local` never falls back to
   `openai`.
5. Missing configuration, a failed model probe, a network error, a refusal, or
   a malformed response makes the requested backend unavailable for that
   operation. It does not select another model or provider.
6. An unavailable runtime does not manufacture a conversational reply through
   a hidden fallback.
7. The local seam is usable only when a local backend is supplied explicitly.
   E044 will not discover, install, launch, or guess a local server.

### Model and transport

1. `DARWIN_LLM_MODEL` is required for every model-backed configuration.
2. No API model identifier is embedded as a default in source code.
3. OpenAI configuration additionally requires `OPENAI_API_KEY`.
4. The OpenAI adapter uses the Responses API.
5. Every Responses request contains `store: false`.
6. The adapter does not send `previous_response_id`, tools, function calls,
   web-search configuration, or computer-use configuration.
7. The model identifier is checked through the Models API before an interactive
   OpenAI session is admitted.
8. The adapter uses strict Structured Outputs for both operations and rejects
   refusals, incomplete output, missing output text, invalid JSON, unknown
   fields, and authority fields.
9. API keys must not appear in snapshots, errors, prompts, test fixtures, or
   logs.

`store: false` prevents E044 from relying on provider-side application state.
It is not documented or represented as a guarantee of zero provider retention;
provider abuse-monitoring and account data-control policies remain separate.

### Conversation flow

One successful user turn performs exactly this sequence:

1. create a bounded `UnderstandingRequest` from the current text and temporary
   session transcript;
2. invoke the configured model for `UNDERSTAND`;
3. parse the result as a candidate `LanguageObservation`;
4. pass that candidate to the deterministic conversation policy;
5. create an `ExpressionPlan` that preserves the candidate status and the
   no-authority boundary;
6. invoke the same explicitly selected model for `EXPRESS`;
7. append the user and Darwin text to the in-memory transcript only after both
   operations succeed.

An `EXPRESS` request without a successful immediately preceding `UNDERSTAND`
request is invalid. A partial or failed turn is not appended to the transcript.

### Temporary context

1. Context is held in memory for one process session only.
2. The transcript is bounded by count and per-message length.
3. The runtime manually resends the bounded transcript on each turn and does
   not depend on provider-side conversation state.
4. Closing the runtime clears the transcript and any pending backend context.
5. E044 does not write conversation text or extracted candidates to SQLite,
   files, autobiographical memory, a vector store, or a provider conversation.
6. No automatic memory-candidate feature is in scope.

### Authority

The language model receives no callable path that can:

- write persistent or autobiographical memory;
- create, start, cancel, or modify a goal;
- change RZS, sigma, motivation, preference, identity, or world-model state;
- dispatch or execute an action;
- issue consent or capability grants;
- write directly to the Darwin event store.

The model output remains subject to the existing exact response schemas and
forbidden-authority-field check in `DarwinLanguageGateway`.

## Acceptance checks

The implementation can be admitted as E044 development infrastructure only if:

1. the two frozen E043 file digests remain unchanged;
2. automated tests prove all backend-selection branches and the absence of
   cross-provider fallback;
3. captured OpenAI requests prove that the configured model is used and that
   every request has `store: false`;
4. captured requests contain no tools or provider-side continuation identifier;
5. a model-backed successful turn makes one `UNDERSTAND` call followed by one
   `EXPRESS` call;
6. strict response parsing rejects malformed and authority-bearing results;
7. failed and partial turns do not enter session context;
8. closing a session erases its temporary transcript;
9. the full existing automated suite still passes; and
10. no live result is reported unless a real configured provider was actually
    called and the raw run metadata was recorded without secrets.

## Live usability gate

The intended later live probe is a 20-30 minute conversation in Brazilian
Portuguese that includes unplanned subjects, at least two topic changes, and at
least one return to an earlier topic. No response sentence may come from a
registered response library.

The probe must separately record:

- successful and failed turns;
- end-to-end latency per operation;
- whether topic returns were handled correctly;
- human-noted contradictions or fabricated memories;
- model and backend identifiers;
- confirmation that persistent-authority mutation counts remained zero; and
- confirmation that the transcript disappeared when the session closed.

Automated mocks cannot pass this live usability gate. If no API credential or
explicit local backend is available, the correct result is `UNEXECUTED`, not a
simulated success.

## Claims explicitly excluded

E044 cannot establish:

- calibrated natural-language understanding;
- semantic fidelity of generated replies;
- long-term memory or autobiographical continuity;
- autonomous goal formation;
- general reasoning by the Darwin kernel;
- consciousness, sentience, personhood, AGI, or similarity to Diana beyond a
  superficial conversational impression; or
- that Darwin is more than an LLM-centered conversational system.

The last exclusion matters. Until durable cognition, learning, self-model,
goal, and evidence mechanisms causally shape conversation under independent
tests, a successful E044 result is still best described as an LLM conversation
adapter behind a strict authority boundary.

## Observed implementation result

The protocol above was committed as `61d6f97` before any E044 implementation
or test was added.

The admitted implementation adds:

- explicit environment parsing with `none` as the default backend;
- an OpenAI Responses adapter built on an injectable, bounded JSON transport;
- mandatory exact-model probing through the Models API;
- strict `UNDERSTAND` and `EXPRESS` JSON schemas;
- a deterministic policy that marks the interpretation as an unverified
  candidate and creates no persistent mutation handle;
- a bounded 60-message in-memory session;
- an explicit local-backend seam with model matching and mandatory ephemeral
  context cleanup; and
- a terminal command that starts only when invoked.

Automated observations on the local Windows machine:

- 24 of 24 focused E044 tests passed;
- the full suite discovered 472 tests;
- 471 tests executed and passed;
- one pre-existing workspace-executor test was skipped because Windows symlink
  creation was unavailable;
- zero tests failed;
- both frozen E043 SHA-256 digests remained exact;
- captured OpenAI request fixtures used the configured model, `store: false`,
  strict Structured Outputs, and no tools or `previous_response_id`; and
- the no-backend terminal check reported `backend_not_requested` and made no
  conversational reply.

These are hermetic implementation checks. The provider responses were test
fixtures, not OpenAI responses. No `OPENAI_API_KEY` was configured on the test
machine, no explicit local backend was installed or validated, and no billable
API request was made. Therefore:

```text
live OpenAI model probe        UNEXECUTED
live UNDERSTAND call           UNEXECUTED
live EXPRESS call              UNEXECUTED
20-30 minute usability probe   UNEXECUTED
language quality               UNKNOWN
topic-return quality           UNKNOWN
```

Automated development admission does not pass the live usability gate and does
not alter the independent E041/E042 human-annotation block.
