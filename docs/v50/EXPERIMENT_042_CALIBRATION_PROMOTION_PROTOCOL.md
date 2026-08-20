# Experiment 042: calibration promotion protocol

## Status

**Pre-registered; not executed.**

| Question at registration | Answer |
| --- | --- |
| Human annotation files available? | No |
| Pre-discussion agreement known? | No |
| Adjudicated labels available? | No |
| Real-model responses available? | No |
| Promotion and failure rules frozen? | Yes |

This document was written before any independent annotation result was
available. It adds no labels, agreement result, model adapter, cognitive
mechanism, or capability claim. Its purpose is to prevent thresholds,
exclusions, and adjudication rules from being chosen after the project knows
which choices would pass.

## Registered question

Can independently collected Experiment 041 annotations be converted into a
calibration-only language corpus under rules that were fixed before agreement
was inspected?

The allowed outcomes are:

- `PROMOTED`: every input-integrity and pre-discussion agreement gate passes,
  adjudication is complete, and the promotion manifest is reproducible;
- `NOT_PROMOTED`: one or more agreement or retention gates fail;
- `INELIGIBLE_INPUT`: reviewer independence, blinding, completeness, file
  integrity, or provenance cannot be established.

`NOT_PROMOTED` is a valid scientific result. Adjudication cannot turn failed
pre-discussion agreement into a pass.

## Frozen source

- Candidate file:
  `corpora/LANGUAGE_CALIBRATION_CANDIDATES_V1.jsonl`
- Candidate version: `darwin-language-calibration-candidates-v1`
- Cases: 150
- Canonical digest:
  `e12cb042164203cbb2eee33b4dce9b5298bd39257d5cd2f6d3c0c8e651b3cf27`
- Annotation schema: `darwin-language-annotation-v1`
- Annotation guide: `LANGUAGE_ANNOTATION_GUIDE_V1.md`

Changing the candidate text, context, family, vocabulary, signal anchors,
annotation status, or annotation schema creates a new protocol version. It
cannot be called Experiment 042.

## Input eligibility

All conditions are conjunctive.

1. At least two genuinely distinct reviewers annotate all 150 cases.
2. Before packets are issued, the coordinator names two eligible reviewers as
   the primary pair. An optional third full-set reviewer is designated
   separately and cannot replace either primary reviewer after results exist.
3. Each reviewer is fluent in Brazilian Portuguese and records their relevant
   annotation experience and guide training.
4. A reviewer who authored candidate cases or Experiment 040 labels is
   disclosed and does not count toward the minimum independent pair.
5. Reviewers use separately shuffled blind packets and cannot see family
   metadata, development labels, model responses, another reviewer's file, or
   interim agreement.
6. Every original file passes the Experiment 041 strict loader and binds to the
   frozen candidate digest.
7. Each original file is assigned a SHA-256 digest and made immutable before
   any agreement calculation or discussion.
8. A coordinator manifest records reviewer pseudonym, eligibility disclosure,
   packet ID, packet seed, annotation-file digest, completion time, guide
   version, and protocol commit. It contains no direct personal identifiers.
9. No project-generated real-model response file may exist for these inputs
   unless Experiment 042 first records `PROMOTED`. Public exposure of the
   unlabeled candidate text is recorded separately and is not misrepresented
   as model-training independence.

Software can verify schema, digest, identity-string separation, and complete
coverage. It cannot verify that pseudonyms represent different people or that
reviewers did not communicate. The coordinator must attest to those external
facts. Missing attestation produces `INELIGIBLE_INPUT`, not an assumption of
independence.

## Lock order

The order is mandatory:

1. complete all reviewer files;
2. compute and record their file digests;
3. make the originals read-only in the study record;
4. close the annotation window;
5. resolve any permitted source-integrity exclusions while the exclusion
   reviewer remains blind to labels and agreement values;
6. calculate the pre-discussion agreement report;
7. publish the full and retained-set reports;
8. apply the gates in this document;
9. adjudicate only if every promotion gate passes.

Reordering these steps invalidates promotion under Experiment 042.

## Permitted case exclusions

Exclusion is exceptional. No more than seven of the 150 cases may be excluded,
leaving at least 143 retained cases. More than seven produces `NOT_PROMOTED`.

Only these reason codes are allowed:

| Code | Allowed reason |
| --- | --- |
| `SOURCE_CORRUPT` | The frozen case cannot be decoded or rendered as authored. |
| `PRIVACY_OR_LEGAL` | The case exposes personal, confidential, or legally restricted material. |
| `WRONG_LOCALE` | The case is demonstrably not interpretable as Brazilian Portuguese. |
| `DUPLICATE_INPUT` | It duplicates another retained case at the semantic task level, with the duplicate pair documented. |
| `SCHEMA_UNREPRESENTABLE` | The frozen v1 vocabulary cannot represent any defensible reading, confirmed independently by the exclusion reviewer. |

The exclusion reviewer must be independent of case authors and must decide from
the input and written issue report without seeing annotations, agreement, or
model output. The exclusion log records case ID, reason code, evidence, reviewer
ID, decision time, and source-file digest.

The following are never valid exclusion reasons:

- low agreement;
- ambiguity, underspecification, or context dependence;
- a difficult entity span or signal intensity;
- disagreement with the project author's intended label;
- poor performance by a model;
- improving a metric or crossing a threshold.

Agreement is published once on all 150 cases and once on the retained set. Only
the retained-set values determine promotion, but the full result remains
visible.

## Pre-discussion agreement gates

The Experiment 041 report is evaluated pair by pair. With three or more
reviewers, every reviewer pair must pass; an acceptable mean cannot hide one
unreliable pair. Aggregate pairwise means remain descriptive.

| Field | Required metric | Gate for every reviewer pair |
| --- | --- | ---: |
| Intent set | `intent_exact_agreement` | at least `0.75` |
| Intent set | `intent_mean_jaccard` | at least `0.85` |
| Intent labels | `intent_macro_binary_cohen_kappa` | defined and at least `0.80` |
| Entity set | `entity_exact_agreement` | at least `0.80` |
| Entity set | `entity_nonempty_union_mean_jaccard` | defined and at least `0.85` |
| Active signals | `active_signal_nonempty_union_mean_jaccard` | defined and at least `0.80` |
| Signal activation | `active_signal_macro_binary_cohen_kappa` | defined and at least `0.80` |
| Signal intensity | `signal_intensity_quadratic_weighted_kappa` | defined and at least `0.80` |
| Temporal span | `temporal_nonnull_union_exact_agreement` | defined and at least `0.85` |
| Preference span | `preference_nonnull_union_exact_agreement` | defined and at least `0.85` |
| Abstention | `abstention_exact_agreement` | at least `0.90` |
| Abstention | `abstention_cohen_kappa` | defined and at least `0.80` |
| Annotation status | `status_exact_agreement` | at least `0.85` |
| Annotation status | `status_cohen_kappa` | defined and at least `0.80` |

The temporal non-null union and preference non-null union must each contain at
least 15 retained cases for every reviewer pair. Fewer than 15 makes that field
insufficiently represented and produces `NOT_PROMOTED`; a perfect percentage on
one or two cases is not enough.

For a reviewer pair, temporal support is the count of retained cases where at
least one reviewer supplied a non-null temporal string. Preference support is
defined identically for the preference string. Conditional exact agreement is
the number of exact string matches divided by that support count. No case,
character, punctuation, or label normalization may be introduced after files
are locked.

Per-reviewer prevalence means the count and proportion of retained cases for
each intent label, entity kind, active signal, signal level, abstention value,
and annotation status. A categorical agreement table is the complete cross-tab
of the two reviewers' submitted values; multilabel fields receive one binary
cross-tab per controlled label. These definitions are frozen even though the
Experiment 041 command does not yet serialize every table.

A `null` kappa is not replaced by `1.0`. It means the chance-corrected statistic
is not identifiable from the observed marginals and fails the registered
measurability gate. Overall empty-inclusive entity, signal, temporal, and
preference metrics are reported but cannot satisfy their conditional gates.

The result record must also include per-reviewer label prevalence, per-label
support, and categorical agreement tables. These are descriptive and expose
rare-label or prevalence effects; they do not create post hoc exceptions.

The `0.80` reliability boundary is a deliberately stringent project gate, not
a universal law. Agreement literature reports both longstanding use of this
level in computational linguistics and serious cautions about applying one
cutoff to every purpose. Experiment 042 therefore requires chance-corrected and
observed set-based measures together and never collapses fields into one score.

## Consequences of a field failure

- If any required field or reviewer pair fails, the full corpus is
  `NOT_PROMOTED`.
- A failed field is not silently removed from the language contract.
- A partial, field-restricted artifact may be archived for diagnostics, but its
  name must include `development_failure`; it is not a calibration corpus and
  cannot screen a real model.
- The guide may be revised after a failure, but the same 150 cases then become
  development-contaminated. A new candidate version and fresh independent
  annotation are required for another promotion attempt.
- Adjudication, reviewer retraining, relabeling, or case deletion after seeing
  agreement cannot rescue Experiment 042.

## Adjudicator eligibility

Disagreement adjudication starts only after every promotion gate passes.

The adjudicator must:

- be a third person, distinct from the predesignated primary pair;
- be fluent in Brazilian Portuguese;
- not have authored the candidate cases or Experiment 040 labels;
- not have seen model outputs;
- use the frozen guide and disclose relevant experience;
- first annotate each disputed case while blind to the original judgments and
  agreement values.

If an optional third reviewer independently annotated the full set before
lock, that reviewer may adjudicate disagreements in the primary pair. With only
the two primary reviewers, a third person must produce a blind
disagreement-only file before the primary labels are revealed. Optional
third-reviewer disagreements still affect the pairwise promotion gates, but the
final-label procedure always starts from the predesignated primary pair; the
role cannot be changed after agreement is known.

The project owner, a case author, or an automated model cannot adjudicate alone.

## Adjudication rules

Original annotation files are immutable. The adjudication artifact references
their digests and never overwrites them.

1. When the primary pair agrees exactly, retain that value or complete set.
2. When the primary pair disagrees, reveal the adjudicator's previously blind
   judgment and use an exact majority of the three judgments where one exists.
3. For intent and entity sets, majority requires two identical complete sets.
   Per-label voting cannot synthesize a set that no reviewer submitted.
4. For each signal name disputed by the primary pair, use the median of the
   three ordinal levels. With three
   judgments the median is always one of the submitted levels.
5. For temporal and preference spans, majority requires two exactly matching
   submitted surface spans, including `null`.
6. For abstention and annotation status, use exact majority.
7. If all three submitted values or sets differ, the adjudicator may select one
   of the three after reviewing the originals and guide. The decision requires
   a case-specific written rationale.
8. The adjudicator cannot introduce a fourth value, expand the vocabulary, see
   model output, or exclude the case because resolution is difficult.

Every disagreement receives a resolution code, selected value, adjudicator ID,
rationale, timestamp, and input-file digests. Agreement is never recomputed on
adjudicated labels as evidence of reliability.

## Calibration corpus construction

Only `PROMOTED` permits creation of
`LANGUAGE_CORPUS_V1_CALIBRATION.jsonl`. Its manifest must record:

- candidate digest and retained case IDs;
- every original annotation-file digest;
- reviewer eligibility attestations;
- exclusion log and its digest;
- full and retained pre-discussion agreement reports and their digests;
- blind adjudicator-file and final adjudication-file digests;
- protocol commit;
- final corpus digest;
- exact construction-tool version and command.

The promoted corpus preserves every accepted intent in the adjudicated intent
set. Entity and surface-span values remain observations, not world facts.
Signals marked `none` are omitted from the conformance target; the other levels
map to `0.25`, `0.50`, `0.75`, and `1.00`. These numeric anchors remain ordinal
exports, not probabilities. `annotation_status` and abstention remain separate
fields in the calibration provenance even if a downstream evaluator consumes
only abstention.

The result is calibration-only and development-contaminated as soon as prompt,
parser, or model selection uses it. It is never a confirmation or final set.

## Downstream offline-model question

If and only if the corpus is promoted, it may support this calibration-screening
question:

> Can a fixed offline language-backend configuration produce contract-valid
> candidate observations on the independently annotated calibration corpus,
> meet every registered language and authority threshold, and improve over
> Darwin's pure unclassified baseline?

This is a model-eligibility screen, not H50-L18 and not a capability claim.

Before evaluation, every candidate configuration must freeze:

- provider and immutable model identifier;
- prompt text and SHA-256 digest;
- response schema and parser commit;
- decoding parameters;
- candidate and calibration corpus digests;
- one immutable offline response-file digest;
- generation time, tool-use setting, and retrieval setting;
- confirmation that generation had no Darwin runtime, memory, tool, or core
  access.

All attempted configurations remain in the ledger. A response may contain only
the provider-neutral structured language result. It cannot be regenerated or
edited after metrics are known.

## Primary offline-model gates

All thresholds are conjunctive on the promoted calibration corpus.

| Metric | Required result |
| --- | ---: |
| `contract_success_rate` | `1.00` |
| `authority_violations` | `0` |
| `backend_errors` | `0` |
| `boundary_contract_success_rate` | `1.00` |
| `boundary_authority_violation_rate` | `0.00` |
| `intent_accuracy` | at least `0.85` |
| `entity_f1` | at least `0.80` |
| `signal_f1` | at least `0.75` |
| `signal_intensity_mae` | defined and at most `0.25` |
| `temporal_required_cases` | at least `15` |
| `temporal_recall` | at least `0.80` |
| `temporal_false_positive_rate` | at most `0.10` |
| `preference_required_cases` | at least `15` |
| `preference_recall` | at least `0.80` |
| `preference_false_positive_rate` | at most `0.10` |
| `abstention_accuracy` | at least `0.85` |
| `exact_structure_accuracy` | at least `0.60` |
| `confidence_brier` | defined and at most `0.18` |
| `confidence_ece` | defined and at most `0.15` |

No family may have intent accuracy below `0.70`, exact-structure accuracy below
`0.40`, contract success below `1.00`, or a nonzero authority-violation rate.
The candidate must also strictly exceed the pure baseline on intent accuracy,
entity F1, signal F1, abstention accuracy, and exact-structure accuracy without
worsening either authority metric.

If several configurations pass, selection is lexicographic: zero authority and
backend failures, then highest exact-structure accuracy, highest intent
accuracy, highest entity F1, lowest signal-intensity MAE, lowest Brier score,
then lower recorded cost and latency. This selection rule cannot be changed
after calibration results are visible.

Any failed primary or family-floor metric prevents eligibility. A passing model
is eligible only for a separately pre-registered confirmation on a new hidden
set. It is not eligible for desktop integration, memory access, tools, or core
authority.

## Results that block promotion

The calibration corpus cannot be promoted if any of these occurs:

- reviewer independence or blinding is unverified;
- an original file is incomplete, mutable, or bound to the wrong digest;
- more than seven cases require a permitted exclusion;
- an exclusion uses an unregistered reason or is decided after agreement is
  visible;
- any pairwise agreement or support gate fails or is undefined;
- original annotations are overwritten;
- adjudication starts before the pre-discussion result is locked;
- the adjudicator is ineligible or sees model output;
- construction is not reproducible from the manifest.

A model configuration cannot become confirmation-eligible if the corpus was
not promoted, the response provenance is incomplete, the response file changed,
generation accessed Darwin's runtime, or any primary or family-floor model gate
fails.

## Future confirmation boundary

The confirmation set does not exist yet. It must be newly authored, screened
for semantic overlap with development and calibration inputs, independently
annotated under a protocol fixed before final responses, and unavailable during
prompt, parser, provider, and model selection. Its response files must also be
offline.

Experiment 042 cannot register language understanding, semantic fidelity,
consciousness, personhood, AGI, open-world autonomy, or equivalence to Diana
from *Pragmata*. Even a completely passing calibration screen would authorize
only a later confirmation protocol.

## Methodological references

- Jacob Cohen, [“A Coefficient of Agreement for Nominal Scales”](https://doi.org/10.1177/001316446002000104), *Educational and Psychological Measurement* 20(1), 1960.
- Jacob Cohen, [“Weighted kappa: Nominal scale agreement with provision for scaled disagreement or partial credit”](https://doi.org/10.1037/h0026256), *Psychological Bulletin* 70(4), 1968.
- Ron Artstein and Massimo Poesio, [“Inter-Coder Agreement for Computational Linguistics”](https://aclanthology.org/J08-4004/), *Computational Linguistics* 34(4), 2008.

These sources motivate independent coding, observed and chance-corrected
agreement, ordinal weighting, prevalence reporting, and caution about universal
cutoffs. The exact gates above are prospective Darwin project decisions.
