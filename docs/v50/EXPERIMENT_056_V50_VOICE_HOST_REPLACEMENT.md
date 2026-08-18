# Experiment 056 - v50 voice-host replacement

Status: retrospective engineering record. The implementation existed before
this document was written. This is not a pre-registration and reports no live
model result.

## Why this replacement exists

On 2026-08-17 the legacy v49 voice companion was observed producing fixed
unknown-word prompts, threshold-derived affect wording, and hard-coded intent
responses. Those outputs were faithful to the old implementation, but they did
not demonstrate open language understanding, feeling, or a distinct cognitive
entity. Presenting that surface as the current Darwin experience was
misleading. The running legacy voice processes were therefore stopped before
this replacement was evaluated.

## Engineering claim

The new host provides a Windows microphone and speech-synthesis path around
the maintained v50 `ConversationRuntime`. It imports no v49 dialogue module and
contains no fallback response generator.

```text
default microphone
        |
        v
local wake-word filter -- sleeping noise is discarded
        |
        v
v50 ConversationRuntime -- UNDERSTAND then EXPRESS
        |
        v
exact expression text returned by the configured local model
        |
        v
Windows speech synthesis
```

The process starts hidden. A wake word may expose the window, but a wake word
alone creates no Darwin reply. While awake, only the text after the wake word
is submitted. A direct sleep command hides the window without calling the
model.

## Fail-closed boundaries

- startup requires `DARWIN_LLM_BACKEND=local`;
- a model alias, loopback endpoint, and ephemeral local bearer value must all
  be explicit;
- OpenAI configuration is rejected by this host;
- no backend substitution occurs;
- an unavailable backend prevents microphone capture from starting;
- a failed model turn produces no speech;
- any nonzero authority-mutation count produces no speech;
- listener output captured during inference or speech synthesis is discarded;
- only the exact v50 `EXPRESS` text is passed to synthesis;
- the GUI transcript is session-only and is erased on close; and
- the host exposes no memory write, goal change, tool, or action interface.

The local bearer value protects a temporary loopback process. It is not a paid
provider credential.

## Automated checks

The focused tests must establish:

1. Discord or room speech without a wake word creates zero model calls while
   sleeping;
2. a wake word alone creates zero model calls and zero spoken reply text;
3. a wake command submits only its command portion;
4. backend failure and authority mutation produce no expression text;
5. sleeping never invokes the model;
6. recognizer output is discarded while paused instead of queued;
7. the voice modules contain no legacy dialogue imports or known v49 phrases;
8. provider configuration cannot start this local-only host; and
9. the exact explicit local configuration is probed before the runtime is
   admitted.

## Executed result

The maintained-surface checker passed. The focused voice-host run executed 20
tests and all 20 passed. The complete repository run executed 528 tests: 527
passed and one existing Windows symlink test was skipped because the current
account lacks the operating-system privilege required to create its fixture.
There were zero test failures.

These results establish the tested routing and isolation properties, not
language quality. No local inference was executed for E056.

## Explicit non-claims

This change does not provide a promoted local model. It does not establish that
Darwin understands unrestricted Portuguese, has feelings, possesses
consciousness, learns autonomously, remembers across sessions, or resembles
Diana from *Pragmata*. Until a free local model passes a separately frozen
screen, the honest v50 voice-host state is unavailable and silent.
