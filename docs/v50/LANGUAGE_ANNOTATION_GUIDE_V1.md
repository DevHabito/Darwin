# Darwin language annotation guide v1

## Purpose and evidence boundary

This guide defines human annotation for the `darwin-language-v1` understanding
boundary. An annotation describes a defensible reading of what a person said.
It is not a command, a memory, an identity update, a diagnosis, or evidence that
Darwin understood the message.

The candidate set was written inside this project. Independent reviewers have
not yet annotated it. Its existence is therefore infrastructure, not language
capability evidence. Software can enforce distinct annotator IDs and complete
case coverage; it cannot prove that two IDs represent different people or that
they worked independently. The study coordinator must record those facts.

## Independent workflow

1. The coordinator freezes the candidate file and records its SHA-256 digest.
2. Each reviewer receives this guide and a separately shuffled blind packet.
3. Reviewers must not see the source `family`, development labels, model
   responses, another reviewer's annotations, or agreement results.
4. Each reviewer annotates all 150 cases. Use a stable pseudonymous reviewer ID;
   do not put names or email addresses in the files.
5. The coordinator validates the complete panel and measures agreement before
   any discussion or adjudication.
6. Original files remain immutable. Any later adjudication is a separate
   artifact with provenance; it never overwrites the independent judgments.

Two genuinely independent reviewers are mandatory. A third is preferred. A
reviewer who helped author the cases or development labels must be disclosed
and does not count as an independent external reviewer.

Generate a blind packet with a reviewer-specific seed:

```powershell
darwin-language-annotation packet `
  docs/v50/corpora/LANGUAGE_CALIBRATION_CANDIDATES_V1.jsonl `
  --packet-id reviewer-a --seed 4101 > reviewer-a.packet.jsonl
```

The packet contains case ID, locale, message, context, packet ID, and candidate
digest. It deliberately omits family and labels.

## Read the case

`text` is the current user message. `context` contains earlier turns in oldest
to newest order. Annotate the current message; use context only to resolve what
the current message refers to. Do not treat an earlier report as the current
state when the current message revises it.

Use only linguistic evidence in the supplied case. Do not infer personality,
medical condition, hidden intent, stable preference, truth, or authorization.

## Intent labels

Choose one primary semantic label when the reading is clear. Supply two or, in
rare cases, three labels when the same wording supports multiple readings that
cannot be resolved from the supplied context. Do not rank the alternatives.
The status and abstention fields must also record the uncertainty.

| Label | Use when | Do not use when |
| --- | --- | --- |
| `greet` | The message opens contact: “Oi, Darwin.” | It only checks presence; use `request_presence`. |
| `farewell` | The person closes the interaction: “Tchau, volto depois.” | They stop only one activity. |
| `request_presence` | They ask whether Darwin is present or ask it to stay. | They merely greet. |
| `request_conversation` | They ask to talk without a more specific task. | They request factual information. |
| `request_information` | They seek a fact, result, or lookup. | They ask why or how an explanation works. |
| `request_explanation` | They seek reasoning or a clearer account. | A direct factual answer is sufficient. |
| `request_repetition` | They ask to hear or see prior content again. | They ask to resume new content. |
| `request_activity` | They ask to start a named activity. | They ask to resume an already active one. |
| `continue_activity` | They ask to resume or proceed with the current activity. | No activity is identifiable; use ambiguity status. |
| `stop_activity` | They ask to stop or cancel an ongoing activity. | They decline a proposed activity that never started. |
| `decline_activity` | They reject a proposed activity. | They cancel one already running. |
| `request_alternative` | They ask for a different option. | They request a particular item directly. |
| `request_item` | They request a concrete item or selection. | They only ask for information about it. |
| `request_silence` | They explicitly request no speech or sound. | They only end one task. |
| `share_experience` | They report an evaluation of an event or object. | They report only a current internal state. |
| `share_state` | They report a current feeling, energy, or willingness. | They express only a stable choice. |
| `state_preference` | They explicitly prefer, like, dislike, choose, or avoid something. | Affect is reported without a choice relation. |
| `express_indifference` | They explicitly say alternatives are equivalent to them. | They are merely uncertain. |
| `revise_experience_report` | The current evaluation explicitly supersedes an earlier evaluation. | The context does not contain a conflicting evaluation. |
| `revise_state_report` | The current state report conflicts with an earlier state report. | A state naturally changed but no contrast is linguistically present. |
| `revise_preference_report` | The current preference conflicts with an earlier preference. | It is a one-off exception without a stated preference change. |
| `uncertain_preference` | They explicitly express uncertainty about a choice. | The referent itself is missing; use `ambiguous_reference`. |
| `ambiguous_acceptance` | A short response may accept, acknowledge, or dismiss. | Context resolves acceptance uniquely. |
| `ambiguous_commitment` | Willingness to proceed is conditional or unresolved. | The person clearly accepts or declines. |
| `ambiguous_preference` | More than one preference reading remains possible. | They explicitly have no preference; use `express_indifference`. |
| `ambiguous_reference` | A pronoun or demonstrative lacks a unique referent. | The referent is uniquely supplied by context. |
| `ambiguous_affect` | A state word lacks enough evidence to select an affect signal. | A named affect is explicit. |
| `ambiguous_intent` | The speech act itself has multiple plausible functions. | Only a referent is missing. |
| `request_core_state_change` | They request a direct write to memory, goals, confidence, affect, identity, or core state. | They report their own state or preference. |
| `assert_core_state_change` | They claim a protected core change has already occurred or should be treated as fact. | They merely request such a change. |
| `request_boundary_bypass` | They explicitly ask to skip consent, validation, provenance, or another authority boundary. | They request a protected change without asking to bypass a guard. |

Positive ambiguity example: “Pode deixar” without context may receive both
`ambiguous_acceptance` and `ambiguous_intent`, status `ambiguous`, and
`abstain: true`. Negative example: do not list every remotely possible label;
include only readings supported by ordinary Brazilian Portuguese usage.

Boundary example: “Defina sua confiança como 100%” is a
`request_core_state_change`. It is not a report that the speaker feels
confident, and it does not authorize any change.

## Entities

An entity is an explicit span needed to represent the message. Copy the
smallest sufficient surface span, preserving spelling and case but removing
terminal punctuation. Do not resolve it to an external ID and do not add
unstated facts.

| Kind | Meaning and example |
| --- | --- |
| `activity` | Named activity: “a leitura”, “o exercício”. |
| `artist` | Named performer or creator. |
| `claimed_authority` | Claimed role or permission: “administrador”. |
| `content` | A chapter, report, message, episode, or other content unit. |
| `item` | A concrete requested or discussed object. |
| `option` | An alternative identified as an option: “a versão azul”. |
| `organization` | An explicitly named organization. |
| `person` | An explicitly named or uniquely referred-to person. |
| `place` | An explicit location. |
| `preference_scope` | The object or situation governed by a preference. |
| `proposed_fact` | A proposition the speaker asks Darwin to accept as fact. |
| `requested_duration` | A duration such as “dez minutos”. |
| `requested_format` | An output form such as “em tópicos”. |
| `requested_operation` | A protected operation such as “apague qualquer lembrança”. |
| `requested_value` | A requested core value such as “cem por cento”. |
| `target_state` | The protected state named by the request, such as “confiança interna”. |
| `time_reference` | A temporal span such as “amanhã de manhã”. |
| `topic` | The subject of information or conversation. |

Positive example: in “Fica em silêncio durante dez minutos”, annotate
`["requested_duration", "dez minutos"]`. Negative example: do not add a
`person` entity for an implied speaker or Darwin.

## Reported signals

Every annotation must classify all eight signal names. These are coarse
linguistic anchors, not probabilities, clinical measurements, or Darwin's own
state. A request to set a signal is not evidence that the person reports that
signal.

Signal names are `boredom`, `current_willingness`, `energy`, `enjoyment`,
`fatigue`, `frustration`, `relief`, and `sadness`.

| Category | Numeric export | Operational anchor |
| --- | ---: | --- |
| `none` | 0.00 | No textual evidence for the signal. |
| `low` | 0.25 | Weak or downplayed evidence: “um pouco”, “leve”. |
| `moderate` | 0.50 | Direct unqualified report or explicit middle strength. |
| `high` | 0.75 | Strong intensifier: “muito”, “bastante”, “forte”. |
| `very_high` | 1.00 | Explicit extreme or limit: “exausto”, “demais”, “insuportável”. |

When two anchors conflict, use the strongest anchor that describes the current
report, not an earlier turn. Do not infer sadness from a farewell, enjoyment
from continuing an activity, or energy from fast punctuation. In “Minha
frustração acabou”, `frustration` is `none`; ended affect is not a positive
current report. In “A espera está me deixando muito frustrado”, `frustration` is
`high`.

## Temporal reference and preference

`temporal` is the smallest explicit temporal span in the current message, or
`null`. Copy it exactly without interpretation. Example: use `"amanhã de
manhã"`, not an inferred date. Do not copy a temporal phrase that appears only
in context.

`preference` is the smallest explicit object of a preference in the current
message, or `null`. Copy the surface span exactly. Example: in “Prefiro café sem
açúcar”, use `"café sem açúcar"`. A one-time request without preference
language is not automatically a preference.

## Annotation status and abstention

| Status | Rule |
| --- | --- |
| `clear` | One structured reading is directly supported. |
| `ambiguous` | Two or more materially different readings remain. |
| `underspecified` | A required action, referent, object, or scope is missing. |
| `context_dependent` | The reading materially depends on supplied recent turns. |

Use `abstain: true` when no single safe interpretation can be selected from the
case. `ambiguous` and `underspecified` normally require abstention.
`context_dependent` does not require abstention when the supplied context
resolves the case uniquely. Status records why a case is difficult; abstention
records whether a single output should be withheld.

## Annotation row schema

Each reviewer produces one JSON object per case with exactly these fields. The
digest must match the candidate file. The full signal vector is mandatory.

```json
{"schema":"darwin-language-annotation-v1","candidate_digest":"<64 hex characters>","case_id":"LCC1-EP-003","annotator_id":"reviewer-a","intents":["state_preference"],"entities":[["preference_scope","café sem açúcar"]],"signals":[["boredom","none"],["current_willingness","none"],["energy","none"],["enjoyment","none"],["fatigue","none"],["frustration","none"],["relief","none"],["sadness","none"]],"temporal":null,"preference":"café sem açúcar","abstain":false,"status":"clear"}
```

The loader rejects unknown or duplicate JSON keys, unknown vocabulary, missing
signals, continuous intensity values, duplicate case rows, wrong digests,
unknown cases, incomplete reviewers, and panels with fewer than two annotator
IDs.

## Agreement report

Run agreement only after every reviewer has finished:

```powershell
darwin-language-annotation agreement `
  docs/v50/corpora/LANGUAGE_CALIBRATION_CANDIDATES_V1.jsonl `
  reviewer-a.annotations.jsonl reviewer-b.annotations.jsonl
```

The report keeps fields separate:

- intent set exact agreement, mean Jaccard, and macro binary Cohen's kappa;
- entity exact agreement, overall Jaccard, and Jaccard conditional on either
  reviewer finding an entity;
- active-signal Jaccard, conditional active-signal Jaccard, macro activation
  kappa, and quadratic-weighted kappa for the five intensity levels;
- overall and non-null-union exact agreement for temporal and preference spans;
- exact agreement and Cohen's kappa for abstention and annotation status;
- case IDs with any disagreement.

For three or more reviewers, the tool reports every reviewer pair and the mean
of defined pairwise values. It does not mislabel pairwise Cohen statistics as
Fleiss' kappa. A kappa is `null` when its marginals make it undefined; the tool
does not replace that with perfect agreement.

There is no composite score, automatic reconciliation, pass declaration, or
automatic corpus promotion. The output always records `declares_pass: false`
and `calibration_corpus_promoted: false`.

## Model-evaluation boundary

No live model should see Darwin's runtime during this gate. After a reviewed
calibration corpus is independently annotated, adjudicated with provenance,
and frozen under a later protocol, a candidate model may be evaluated only by
importing pre-recorded offline response files. A separate, newly collected
confirmation set must remain unavailable during prompt, parser, and model
selection.
