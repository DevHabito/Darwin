# Experiment 022 — frozen transfer calibration

Status: calibration eligibility passed. The protocol and evaluator were
committed as `ae6ee33` before the calibration run. This is not H50-L14 and does
not establish a capability.

## Purpose

Experiment 021 selected a source-learned prior and compatibility gate on
development worlds. This experiment asks whether that frozen configuration is
stable enough on independent calibration worlds to justify writing a
confirmatory H50-L14 protocol.

No model choice is permitted here. Failure means H50-L14 remains unregistered.

## Frozen candidate

- source tasks: `16`;
- balanced cycles per source task: `8`;
- source interactions: `2,048`;
- target interactions: `64`;
- initial source weight: `0.5`;
- Beta-Binomial concentration grid: unchanged from Experiment 021;
- compatibility update: joint transition-and-reward predictive likelihood;
- source-shuffled control: fixed cyclic cell-prior offset `1`;
- target conditions: related, unrelated, and adversarial.

The evaluator supplies known alignment and a family label but no family
parameters. Source and target public identities omit evaluator seeds.

## Frozen calibration inputs

- calibration seeds: `27500–27531`;
- test-only seeds: `27600–27607`;
- bootstrap seed: `28000`;
- paired bootstrap samples: `5,000`;
- final H50-L14 seeds: not allocated.

Test-only calibration outputs may be inspected for implementation debugging and
are contaminated. They cannot replace the registered calibration run.

## Metrics

All loss improvements are scratch log loss minus candidate log loss.

- related gated improvement;
- related candidate improvement minus source-shuffled improvement;
- related oracle-gap closure: gated improvement divided by oracle improvement;
- unrelated and adversarial gated improvement;
- mean final source weight in all three conditions;
- related simultaneous win rate over both scratch and shuffled control.

Intervals are deterministic 95% paired bootstrap intervals over target worlds.

## Conjunctive calibration eligibility

Every rule must pass:

1. related improvement interval lower bound at least `0.12`;
2. related candidate-minus-shuffled interval lower bound at least `0.10`;
3. oracle-gap closure interval lower bound at least `0.80`;
4. unrelated improvement interval lower bound at least `-0.01`;
5. adversarial improvement interval lower bound at least `-0.01`;
6. related final source-weight interval lower bound at least `0.95`;
7. unrelated final source-weight interval upper bound at most `0.20`;
8. adversarial final source-weight interval upper bound at most `0.05`;
9. related simultaneous-win-rate interval lower bound at least `0.75`.

The snapshot replay, prior-digest, strict-JSON, causal ordering, and identity
boundary tests must also remain green. They are engineering invariants rather
than bootstrap metrics.

These thresholds were chosen from Experiment 021 development behavior before
accessing calibration seeds. They are eligibility margins, not a capability
decision. A miss on any rule blocks H50-L14 registration; the rule cannot be
relaxed on the same calibration outputs.

## Interpretation boundary

Even if calibration passes, the strongest supported next action is to
pre-register a confirmatory known-alignment predictive-transfer hypothesis on
new seeds. Calibration cannot establish general transfer, representation
learning, control improvement, lifelong autonomy, consciousness, or
personhood.

## Result

Calibration seeds `27500–27531` were run once after pre-registration. Every
eligibility rule passed.

| Metric | Mean | 95% interval |
| --- | ---: | ---: |
| Related gated improvement | `0.1595617` | [`0.1434855`, `0.1752002`] |
| Related candidate minus shuffled | `0.1643268` | [`0.1484299`, `0.1798033`] |
| Related oracle-gap closure | `0.9456677` | [`0.9257626`, `0.9644836`] |
| Unrelated gated improvement | `-0.0060205` | [`-0.0077414`, `-0.0044656`] |
| Adversarial gated improvement | `-0.0050725` | [`-0.0059595`, `-0.0042155`] |
| Related simultaneous win rate | `1.0` | [`1.0`, `1.0`] |

Mean final source weight was `0.9999000` for related targets, `0.0035624` for
unrelated targets, and effectively zero for adversarial targets. All registered
weight intervals cleared their margins.

Decision: **eligible to pre-register H50-L14**. This means only that the frozen
candidate and decision thresholds may now be written down before new final
seeds are used. It is not a capability pass. The calibration seeds are
contaminated and retired from confirmatory use.

The gate did not eliminate negative transfer. Mean predictive loss remained
`0.0060205` worse than scratch on unrelated targets and `0.0050725` worse on
adversarial targets. Source training still cost 2,048 interactions per family,
32 times the 64-interaction target evaluation.

The machine-readable result is
[`results/EXPERIMENT_022_CALIBRATION_AGGREGATE.json`](results/EXPERIMENT_022_CALIBRATION_AGGREGATE.json).
