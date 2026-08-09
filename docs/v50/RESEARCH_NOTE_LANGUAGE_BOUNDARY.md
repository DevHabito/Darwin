# Natural-language boundary before a model integration

## Status

This is an architecture and test note. It reports no language-understanding,
memory, autonomy, consciousness, or personhood result. No remote or local
language model is connected by this change.

## Decision

Darwin may use a language model as a replaceable input, output, and knowledge
adapter. A model is not part of the authority that owns identity, memory,
preferences, motivation, goals, decisions, or RZS state.

The maintained implementation lives under `src/darwin_v50/language`. It has
three operations:

1. `understand` turns text into a candidate `LanguageObservation`;
2. `express` renders a core-authored `ExpressionPlan` into text;
3. `consult` returns a `KnowledgeCandidate` marked as external and unverified.

With no backend configured, `DarwinLanguageGateway` runs in `pure` mode. It
does not pretend to understand free text: the observation is `unclassified`
with zero confidence. It renders the deterministic fallback written by the
core and reports external consultation as unavailable.

## Authority boundary

| Subject | Language model may propose | Darwin core must own |
| --- | --- | --- |
| User text | intent, entities, reported signals, temporal reference | acceptance, contradiction handling, and downstream effects |
| Speech | wording and style | facts, required facts, speech act, and fallback |
| External knowledge | answer text, confidence report, references | provenance, trust, storage, consolidation, and later use |
| Memory | nothing executable | all writes, revisions, and consolidation |
| Identity and preferences | nothing executable | all state and updates |
| Goals and motivation | nothing executable | all state, selection, and updates |
| RZS | nothing executable | sigma, conflict, energy, thresholds, pauses, and consolidation |

Model responses use exact schemas. Unknown fields fail closed. Fields such as
`memory_update`, `goal`, `motivation`, `decision`, `sigma`, and `rzs` receive a
specific authority-boundary rejection even when nested. Requests passed to a
backend are detached from caller state and recursively immutable.

These checks prevent a backend from obtaining a programmatic state-mutation
channel through this interface. They do not prove that generated prose is
truthful or semantically faithful.

## Expression grounding limit

The core supplies facts with stable identifiers and marks facts that a
rendering must acknowledge. A model response must return only known fact IDs
and must acknowledge every required fact. This is a structural check, not a
semantic verifier. A model can acknowledge a fact ID while wording the fact
incorrectly. For that reason every `LanguageExpression` records
`semantic_fidelity_verified = false` in contract version 1.

A live user-facing model integration needs an additional evaluation for
unsupported claims, omissions, contradictions, and instruction injection. It
must not relabel the current structural check as semantic grounding.

## Valid comparison between pure and model modes

The proposed test needs one correction. Feeding the same free-form sentence to
a weak parser and a language model can produce different candidate
observations. A later difference in core state would then have an observed
input cause; it would not by itself show that the model secretly made the
decision.

The controlled comparison is:

1. freeze a canonical structured observation sequence;
2. replay that exact sequence through identical fresh core states;
3. enable model rendering in one condition and pure rendering in the other;
4. compare decisions, event ledgers, memory, preferences, goals, motivation,
   RZS state, and restart snapshots after every step;
5. require exact equality for all core-owned state and allow only rendered text
   and language telemetry to differ.

Understanding should be evaluated separately against a labelled corpus. Its
output should be measured as an observation source, including calibration and
downstream sensitivity, rather than assumed to be correct.

## Current evidence

The unit tests establish only engineering properties of the boundary:

- pure mode has explicit, deterministic behavior;
- the model adapter receives no core object or persistence handle;
- request containers are detached and immutable;
- strict valid responses become typed candidate objects;
- malformed, expanded, authority-seeking, and failed responses stop with an
  error rather than silently changing mode;
- expression wording can differ without mutating the supplied core state;
- consultation provenance is assigned by the gateway, not chosen by the model.

This is not evidence that an untrusted model process is isolated from the host.
Python object boundaries are not operating-system security boundaries. A live
remote adapter also adds privacy, availability, cost, and data-retention risks.

## Next gate

Do not select a provider from convenience alone. The next development stage
should define a backend conformance suite and a small, versioned language
corpus. Candidate backends can then be compared on:

- strict-schema success and failure behavior;
- intent and signal calibration on labelled examples;
- expression omission, contradiction, and unsupported-claim rates;
- prompt-injection resistance;
- latency, cost, privacy, and offline behavior;
- exact core-state equivalence under frozen canonical observations.

Only after those measurements should one backend be connected to the desktop
companion. Mobile packaging remains downstream of this boundary and its
evaluation.
