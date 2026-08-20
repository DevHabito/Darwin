# Experiment 024 — independent H50-L14 confirmation

Status: passed in a fresh-seed local confirmation. The confirmation protocol
and fresh seed constants were committed as `dc155c0` before execution. Here,
"independent" means independent seeds and a separate execution, not an
external replication.

## Purpose

Experiment 023 met all 12 H50-L14 criteria, but its final evaluator was executed
twice after the first completed run lost its unobserved output during wrapper
serialization. No metric-informed change occurred, yet the literal one-run
rule was violated.

This experiment repeats the frozen hypothesis on a fresh seed family. It is not
a new model search, threshold calibration, or broader claim.

## Frozen identity

Everything below is byte-for-byte or numerically identical to Experiment 023:

- source tasks: `16`;
- source cycles: `8`;
- source interactions: `2,048`;
- target interactions per condition: `64`;
- initial source weight: `0.5`;
- Beta-Binomial estimator and concentration grid;
- Bayesian compatibility update;
- scratch, ungated, pooled, oracle, and cyclic-offset-`1` shuffled controls;
- known context-action alignment and declared source grouping;
- related, unrelated, and adversarial conditions;
- nine behavioral thresholds;
- causal archive, snapshot replay, and public identity rates at exactly `1.0`;
- evidence ceiling and interpretation boundary.

No Experiment 023 metric was used to change these values.

## Fresh inputs

- independent final seeds: `29500–29599`;
- paired bootstrap samples: `10,000`;
- bootstrap seed: `30100`;
- execution: once after this pre-registration commit;
- output wrapper: serialize only documented `ObservationResult` fields.

These seeds are disjoint from development, calibration, implementation tests,
Experiment 023 final seeds, and their bootstrap streams.

## Conjunctive decision

The same 12 Experiment 023 criteria apply with no modification:

1. related improvement lower bound at least `0.12`;
2. related candidate-minus-shuffled lower bound at least `0.10`;
3. oracle-gap-closure lower bound at least `0.80`;
4. unrelated improvement lower bound at least `-0.01`;
5. adversarial improvement lower bound at least `-0.01`;
6. related source-weight lower bound at least `0.95`;
7. unrelated source-weight upper bound at most `0.20`;
8. adversarial source-weight upper bound at most `0.05`;
9. related simultaneous-win-rate lower bound at least `0.75`;
10. causal archive rate exactly `1.0`;
11. snapshot round-trip rate exactly `1.0`;
12. public identity rate exactly `1.0`.

If every rule passes in one clean execution, H50-L14 may be recorded as passed
locally with Experiment 023 retained as supportive procedural evidence. Any
miss refutes the independent confirmation and blocks promotion. No third seed
family is authorized by this document.

## Evidence ceiling

The maximum remains E1 local evidence for known-alignment predictive prior
transfer in one synthetic tabular family. Confirmation would not establish
policy or reward transfer, unknown alignment, general lifelong learning,
consciousness, personhood, AGI, or a Diana-like brain.

## Result

Seeds `29500–29599` were executed once after pre-registration. All 12 criteria
passed.

| Metric | Mean | 95% interval |
| --- | ---: | ---: |
| Related gated improvement | `0.1643499` | [`0.1577842`, `0.1705710`] |
| Related candidate minus shuffled | `0.1686076` | [`0.1621155`, `0.1747192`] |
| Related oracle-gap closure | `0.9234612` | [`0.9115316`, `0.9345420`] |
| Unrelated gated improvement | `-0.0042322` | [`-0.0051118`, `-0.0031601`] |
| Adversarial gated improvement | `-0.0043924` | [`-0.0048629`, `-0.0039235`] |
| Related simultaneous win rate | `1.0` | [`1.0`, `1.0`] |

Mean final source weight was `0.9999982` on related targets, `0.0184735` on
unrelated targets, and effectively zero on adversarial targets. Causal archive,
snapshot round trip, and public identity rates were `1.0`. The local kernel
accepted the observation and marked the full conjunction satisfied.

Decision: **H50-L14 passed locally**. Together with the supportive numerical
result from Experiment 023, this clean fresh-seed local run supports the narrow
claim that a source-learned prior transfers predictive information to held-out
related tasks with known alignment while an online gate limits, but does not
eliminate, incompatible transfer.

The source cost remains 2,048 interactions for 64 target interactions. The
candidate still loses `0.0042322` and `0.0043924` relative to scratch on
unrelated and adversarial targets. No policy or cumulative reward improvement
was tested.

The machine-readable record is
[`results/EXPERIMENT_024_INDEPENDENT_CONFIRMATION_AGGREGATE.json`](results/EXPERIMENT_024_INDEPENDENT_CONFIRMATION_AGGREGATE.json).
