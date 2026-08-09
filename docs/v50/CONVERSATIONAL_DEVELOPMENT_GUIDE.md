# Conversational development guide

This guide starts the isolated E044 terminal session. It does not modify or
replace the E043 desktop runtime.

## What this surface does

Each successful turn makes two model calls through `DarwinLanguageGateway`:

```text
free text -> UNDERSTAND -> unverified observation
          -> deterministic conversation policy
          -> EXPRESS -> new natural-language reply
```

The transcript is kept only in process memory, is bounded to 60 messages, and
is cleared when the command exits. The runtime has no event-store, goal,
executor, consent, capability, RZS, sigma, identity, or autobiographical-memory
handle.

This is still a development adapter around a language model. The current
conversation policy preserves the authority boundary, but it is not a general
cognitive deliberation mechanism.

## OpenAI configuration

Install the project, then set all three values explicitly in the same terminal:

```powershell
py -m pip install -e .
$env:DARWIN_LLM_BACKEND = "openai"
$env:DARWIN_LLM_MODEL = "<model id available to your API account>"
$env:OPENAI_API_KEY = "<your API key>"
darwin-conversation-dev
```

You can also run:

```powershell
py -m darwin_v50.conversation.cli
```

There is no default model. The command checks the exact configured identifier
through `GET /v1/models/{model}` before admitting the session. A missing key,
missing model, rejected probe, malformed result, or provider error never causes
a switch to a local model.

Every model request uses the Responses API with `store: false`, strict
Structured Outputs, no `previous_response_id`, and no tools. The transcript is
manually resent as bounded input. `store: false` means the runtime does not rely
on provider-side application state; it does not override the provider's
separate abuse-monitoring retention or account data-control policy.

Relevant official references:

- <https://developers.openai.com/api/reference/resources/models>
- <https://developers.openai.com/api/docs/guides/structured-outputs>
- <https://developers.openai.com/api/docs/guides/your-data#default-usage-policies-by-endpoint>

## No backend and local development

The default is:

```powershell
$env:DARWIN_LLM_BACKEND = "none"
```

In that state the conversational command reports `backend_not_requested` and
exits. It does not generate a canned conversation.

`DARWIN_LLM_BACKEND=local` is an explicit code-level integration seam. E044
does not install, discover, start, or assume compatibility with Ollama, LM
Studio, or any other local server. A local adapter must be supplied explicitly,
declare the exact `DARWIN_LLM_MODEL` it serves, implement the frozen gateway
contract, and clear its pending context on close. No local adapter has been
validated by E044 yet.

## Ending a session

Use `/exit`, `/quit`, Ctrl+C, or close the terminal. The runtime clears its
temporary transcript in all normal exit paths. It writes no conversation log.

Do not paste secrets into the conversation. Model inputs are still sent to the
explicitly selected provider, subject to that provider's data controls.
