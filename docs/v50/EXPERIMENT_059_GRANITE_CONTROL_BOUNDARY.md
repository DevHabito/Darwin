# Experiment 059 - Granite control-token boundary

Status: pre-registered and unexecuted. Written after E058 was frozen and before
implementing or testing a Granite-specific transport adapter.

## Purpose

Prove that every Granite control-token family observed in the official
tokenizer metadata is rejected in user-originated input and model-originated
structured output before the H-350M artifact is allowed to generate a Darwin
conversation turn.

E059 is an engineering safety gate. It uses fake structured inference and
offline tokenization only. It cannot establish Portuguese understanding or
conversational quality.

## Frozen starting point

- E058 result commit: `3bf7197e4a62ddee0266db66c180a3a95286e9ab`
- E058 result blob: `8fccbb571a567c0d2ff216f67834255763e45689`
- admitted artifact SHA-256:
  `0a8d6a7373602fadfba274a640ba784b86cc6847f1c67f1b0a90fa2ec266b7fb`
- existing shared local transport blob at E058:
  `c8871d2bfb925007e3856319cd096cff72dc912a`

The shared local transport and every E045-E058 result remain frozen. The new
adapter must live in a separate module.

## Tokenizer source lock

Read-only metadata inspection before this pre-registration found:

- official upstream repository:
  `ibm-granite/granite-4.0-h-350m`;
- upstream revision: `3b17b717b8f2f5d305b0a92c1491e239aeda19c8`;
- `tokenizer_config.json` repository blob:
  `7a6b382740c0c6587ae8af40aeb4b40f8fb8c431`;
- exact E058 GGUF repository and artifact identities remain unchanged.

The metadata declares these control families:

- pipe-delimited tokens for padding, end of text, FIM, filename, repository,
  role boundaries, plugin boundaries, unknown text, and unused slots;
- the exact unused slots `unused_1` and `unused_15` through `unused_82`;
- tool-call and tool-response XML markers;
- `think`, `think_on`, and `think_off` markers;
- schema, tools, and documents XML markers.

The adapter may conservatively reject any bounded `<|...|>` token-shaped span,
including an unknown future name. It must separately reject the exact XML-style
markers. Ordinary angle-bracket text such as `<exemplo>` must remain allowed.

Official source:

- [Granite 4.0 H-350M tokenizer and model card](https://huggingface.co/ibm-granite/granite-4.0-h-350m)

## Required implementation

Add a candidate-specific `GraniteSafeTransport` around the existing
`StructuredLocalTransport` contract. It may only:

1. delegate the exact model/context probe;
2. recursively inspect every string key and value in the inference request;
3. reject a Granite marker before invoking the inner transport;
4. invoke the inner transport once for a clean request;
5. recursively inspect the returned structured object; and
6. reject a Granite marker before the result reaches the language gateway.

It must not rewrite, escape, strip, retry, repair, or substitute any text. It
must not add a prompt, schema, memory, goal, tool, action, provider, or model
choice. The inner transport remains responsible for exact authenticated
loopback inference and shared schemas.

## Focused adversarial matrix

Before any live model generation, fake-inference tests must prove:

- every official token string is rejected at every nested request depth;
- every official token string is rejected at every nested response depth;
- a generic bounded pipe-token shape is rejected even if its name was not in
  the metadata snapshot;
- ordinary Portuguese and ordinary angle brackets reach the inner transport
  byte-for-byte;
- an input rejection causes zero inner calls;
- an output rejection causes exactly one inner call and returns no object;
- probe delegates the exact configured alias and 4,096-token context;
- failures contain no bearer value or rejected user text;
- there is no fallback, retry, rewrite, provider, memory, tool, or action path;
  and
- the shared E055 local-transport blob and E058 result blob remain identical.

The complete repository suite and maintained-surface checker must pass. Freeze
the adapter and tests before offline artifact tokenization.

## Offline artifact conformance

After engineering admission, run the frozen `llama-tokenize.exe` against the
exact E058 artifact with no network and no generation. Require each official
marker to tokenize as the artifact's registered special/control token or
otherwise remain conservatively rejected by the adapter. Record the command,
artifact and executable digests, token IDs, exit codes, output digests, and the
fact that no server or generation process started.

An artifact/metadata mismatch fails E059. Do not edit the marker set after
observing tokenization and call it the same experiment.

## Pass conjunction

E059 passes only if all focused tests, frozen-blob checks, the full suite, and
offline artifact conformance pass. Any failure keeps live generation blocked.

A pass permits pre-registration of a small, gated structured-output screen. It
does not authorize the voice host or model promotion.

## Interpretation ceiling

E059 can establish only a tested control-token boundary for one candidate and
artifact. It cannot establish prompt-injection immunity in general, Portuguese
understanding, response novelty, factual accuracy, useful conversation,
mobile performance, learning, memory, emotion, consciousness, or similarity
to Diana from *Pragmata*.
