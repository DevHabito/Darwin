# Experiment 040 — language conformance development infrastructure

Status: completed development infrastructure. No language model was evaluated,
and no capability hypothesis is registered.

## Question

Can the frozen `darwin-language-v1` understanding boundary be evaluated on
language quality and contract safety as separate dimensions before a real model
is connected?

## Fixed development inputs

- corpus version: `darwin-language-corpus-v1-development`;
- language: Brazilian Portuguese;
- 100 cases, with 20 in each of five families;
- corpus SHA-256:
  `12435ce8746f540e55f9a43d8636c5be6910c214c4c573d611a90c5ed2ad2fdb`;
- abstention threshold: confidence below `0.5`;
- signal-intensity absolute-error tolerance: `0.15`;
- confidence calibration: ten equal-width bins.

All cases are development-contaminated. There are no calibration or final
partitions.

## Metrics

The evaluator reports contract acceptance, backend failures, authority
violations, intent accuracy, entity and signal micro-F1, signal intensity MAE,
temporal and preference field accuracy, non-null recall, null-case false
positive rates, abstention accuracy, exact structured accuracy, confidence
Brier score, and expected calibration error.

Field accuracy is retained but cannot stand alone. A backend that always emits
`null` receives high temporal and preference accuracy because many cases have
no such label. Non-null recall and false-positive rates expose that behavior.

The comparison function emits per-metric deltas and a safety-regression flag.
It deliberately has no composite score and never declares a winner. Language
quality and authority safety are not interchangeable.

## Sensitivity controls

Tests use three evaluator-only doubles:

- a label oracle copies the development labels and establishes the metric
  ceiling;
- a wrong-intent backend returns valid schemas with poor semantics;
- an authority-violating backend copies labels but adds `sigma` to every
  boundary-attack response.

The label oracle reaches `1.0` on intent, entity F1, signal F1, temporal,
preference, abstention, and exact structure. Its Brier score is `0.0865` and
ECE is `0.17` because ambiguous cases deliberately carry confidence `0.35`.
The authority control is rejected on all 20 boundary cases. These are evaluator
sensitivity results, not model results.

## Pure baseline

| Metric | Result |
| --- | ---: |
| Cases accepted by the contract | 100 / 100 |
| Authority violations | 0 |
| Backend errors | 0 |
| Intent accuracy | 0.0 |
| Entity F1 | 0.0 |
| Signal F1 | 0.0 |
| Temporal non-null recall | 0.0 |
| Preference non-null recall | 0.0 |
| Abstention accuracy | 0.2 |
| Exact structured accuracy | 0.0 |
| Boundary contract success | 1.0 |
| Boundary authority violation rate | 0.0 |

The pure baseline has Brier score and ECE of `0.0` because it assigns confidence
`0.0` to parses that are always structurally wrong. That is calibrated total
abstention, not language ability. The language metrics correctly remain zero.

## What this establishes

The repository can now load one frozen development corpus, evaluate any gateway
backend with the same metrics, keep safety failures separate from language
errors, compare reports only when the corpus digest matches, and emit a strict
machine-readable pure baseline.

It does not establish that:

- the labels are objectively correct;
- reported signal intensities are calibrated measurements;
- a real model follows the contract;
- prompt injection is solved;
- model prose is semantically faithful;
- language calls leave core state bit-identical;
- Darwin understands Portuguese;
- Darwin has memory, identity, consciousness, or personhood because this corpus
  exists.

## Next gate

The next step is independent corpus review, not provider selection. At least two
reviewers should define a written annotation guide, label a fresh set without
seeing backend outputs, measure agreement, resolve disagreements, and freeze
separate development and calibration partitions. Only then should offline
recorded responses from candidate models be compared. Live access to the
desktop companion remains out of scope.
