# Experiment 041: annotation protocol and independent calibration corpus

## Status

**Infrastructure complete; human study incomplete. No calibration corpus has
been promoted.**

The repository now contains a frozen unlabeled candidate set and the machinery
needed to prepare blind packets, validate complete reviewer panels, and report
agreement by field. It contains no independent annotations, adjudicated labels,
model responses, or language-capability result.

## Research question

Can the project collect reproducible human judgments for the
`darwin-language-v1` observation fields without exposing reviewers to the
development labels, case-family metadata, model outputs, or one another's
work?

This experiment does not ask whether Darwin or any model understands
Portuguese. It tests annotation infrastructure and records the external work
still required before that question becomes eligible.

## Frozen input

- File: `corpora/LANGUAGE_CALIBRATION_CANDIDATES_V1.jsonl`
- Version: `darwin-language-calibration-candidates-v1`
- Locale: Brazilian Portuguese (`pt-BR`)
- Cases: 150
- Design strata: 30 cases in each of five development families
- SHA-256 canonical digest:
  `e12cb042164203cbb2eee33b4dce9b5298bd39257d5cd2f6d3c0c8e651b3cf27`

The 150 requests are exactly disjoint from the 100 Experiment 040 development
requests. Every current-message and context surface span is also unique inside
the candidate set and absent verbatim from the development set. String
disjointness does not prove semantic independence: both sets were written
inside the project and may share author assumptions. The family field is design
metadata and is removed from reviewer packets.

The candidate file has no intent, entity, signal, temporal, preference,
abstention, status, or annotator fields. Adding labels to that source file would
invalidate this version.

## Pre-registered collection procedure

The operational rules are frozen in
[`LANGUAGE_ANNOTATION_GUIDE_V1.md`](LANGUAGE_ANNOTATION_GUIDE_V1.md).

1. Recruit at least two distinct reviewers; three are preferred.
2. Record whether each reviewer authored any cases or development labels.
3. Give each reviewer the same guide and a separately seeded blind packet.
4. Prevent access to development labels, family metadata, backend responses,
   other reviewers' files, and interim agreement.
5. Require one complete annotation per candidate per reviewer.
6. Lock the original reviewer files before calculating agreement.
7. Measure agreement by field and retain every disagreement case ID.

Distinct pseudonymous IDs and full coverage are machine-checked. Reviewer
identity, independence, training conditions, and absence of side-channel
communication require coordinator records and cannot be established from JSON.

## Label contract

- Intents use a frozen controlled vocabulary. One label is normal; up to three
  are permitted for genuinely unresolved readings.
- Entities use frozen kinds and minimal surface spans.
- All eight reported signals receive one ordinal category: `none`, `low`,
  `moderate`, `high`, or `very_high`. The numeric exports are respectively
  `0`, `0.25`, `0.5`, `0.75`, and `1` and are not probabilities.
- Temporal and preference fields use exact minimal surface spans or `null`.
- `annotation_status` is one of `clear`, `ambiguous`, `underspecified`, or
  `context_dependent`.
- Abstention is a separate Boolean decision. It is not inferred automatically
  from status.

## Agreement analysis

Agreement is reported separately for intents, entities, active signals, signal
intensity, temporal span, preference span, abstention, and status. Empty-field
agreement is shown separately from conditional metrics so a large number of
`null` or empty values cannot silently create an impressive result.

For two reviewers, categorical fields use Cohen's kappa where defined;
multilabel fields also use Jaccard and macro per-label binary kappa. Signal
intensity uses quadratic-weighted kappa. With three or more reviewers, all
reviewer pairs are retained and their defined values are averaged. This is
descriptive pairwise analysis, not Fleiss' kappa.

No global agreement threshold is registered in Experiment 041. Choosing one
after inspecting these cases and then calling the same data confirmatory would
be circular. Consequently, even excellent agreement cannot make this
experiment declare a pass or promote a calibration corpus. A subsequent
protocol must define adjudication, eligibility thresholds, and the exact claim
before it consumes the collected labels.

## Required evidence still absent

- two or more genuinely independent complete annotation files;
- reviewer-independence and training records;
- a locked pre-discussion agreement report;
- a separate adjudication artifact that preserves original judgments;
- a pre-registered rule for promoting an adjudicated calibration partition;
- a separately collected confirmation set;
- any offline response file from a real language model.

Until those exist, “independent calibration corpus” names the intended gate,
not an achieved artifact.

## Model boundary and next gate

Do not connect a real LLM to the Darwin runtime. The first eligible model test
must use immutable offline response files generated for the frozen calibration
inputs. Prompt, parser, and model selection may use only the promoted
calibration partition.

A future confirmation set must be newly collected, semantically screened
against both earlier sets, frozen before final model responses are generated,
and unavailable during development. Confirmation responses must also be
offline. Live desktop access, memory writes, goal updates, identity changes,
and autonomous tool authority remain out of scope.

## Result interpretation

The implemented code can establish schema integrity, exact set coverage,
digest binding, deterministic blinding, and reproducible agreement arithmetic.
It cannot establish honest human independence or label validity. No such claim
is made here.
