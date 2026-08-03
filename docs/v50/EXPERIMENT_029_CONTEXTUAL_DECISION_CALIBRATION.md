# Experiment 029 — source-learned contextual decision calibration

Status: completed calibration. Calibration seeds had not been run when this
document, evaluator, thresholds, and seed constants were committed as
`5a02923`. This experiment cannot register H50-L15.

## Purpose

Experiment 028 found a related decision signal and a causal advantage over a
source-shuffled control. It also found significant residual adversarial loss.
This calibration asks whether the exact frozen candidate repeats both facts
within explicit bounds on fresh task families.

Every threshold below was chosen after Experiment 028 development and before
accessing calibration seeds. Passing calibration can only make a confirmatory
H50-L15 protocol eligible for pre-registration.

## Frozen candidate and controls

No algorithm or interaction budget changes:

- exact H50-L14 source estimator and compatibility gate;
- 16 source tasks, eight cycles, and 2,048 source interactions;
- initial source weight `0.50`;
- 64 target interactions and epsilon `0.10`;
- reward-based action ranking;
- transition-plus-reward compatibility feedback;
- scratch, candidate, ungated, shuffled, pooled, and oracle policies.

## Fresh inputs

- implementation-only calibration seeds: `33900–33903`;
- calibration seeds: `34000–34063`;
- three conditions, 64 worlds each;
- bootstrap samples: `5,000`;
- bootstrap seed: `34700`;
- related simultaneous-win interval: 95% Wilson score;
- all earlier source, development, validation, final, audit, replication, test,
  and calibration seeds are excluded.

## Development-informed tolerances

The related thresholds require a measurable operational and causal effect. The
mismatch thresholds are non-inferiority tolerances, not claims that negative
transfer disappears.

- unrelated lower bounds may lose at most one realized reward and one
  pseudo-regret unit over 64 target interactions;
- adversarial lower bounds may lose at most two realized rewards and `1.5`
  pseudo-regret units;
- the gate must also recover at least two unrelated and eight adversarial
  rewards relative to ungated transfer.

These tolerances are deliberately reported in raw target-budget units. A later
reader can therefore see that a pass still permits bounded negative transfer.

## Conjunctive calibration decision

All 21 criteria must pass:

1. related candidate reward-improvement lower bound `>= 1.0`;
2. related candidate pseudo-regret lower bound `>= 0.75`;
3. related preferred-action improvement lower bound `>= 0.05`;
4. related candidate-minus-shuffled reward lower bound `>= 1.0`;
5. related candidate-minus-shuffled pseudo-regret lower bound `>= 1.0`;
6. related simultaneous-win Wilson lower bound `>= 0.65`;
7. unrelated candidate reward lower bound `>= -1.0`;
8. unrelated candidate pseudo-regret lower bound `>= -1.0`;
9. adversarial candidate reward lower bound `>= -2.0`;
10. adversarial candidate pseudo-regret lower bound `>= -1.5`;
11. unrelated candidate-minus-ungated reward lower bound `>= 2.0`;
12. adversarial candidate-minus-ungated reward lower bound `>= 8.0`;
13. related source-weight lower bound `>= 0.95`;
14. unrelated source-weight upper bound `<= 0.10`;
15. adversarial source-weight upper bound `<= 0.01`;
16. causal archive rate equals `1.0`;
17. opaque public identity rate equals `1.0`;
18. candidate snapshot replay rate equals `1.0`;
19. shuffled snapshot replay rate equals `1.0`;
20. source interaction cost equals `2,048`;
21. target interaction cost equals `64`.

Any miss yields `calibration_failed`. A favorable subset cannot authorize final
pre-registration.

## Interpretation boundary

Calibration remains E1 local development evidence. Even a complete pass would
not establish H50-L15, pure bandit transfer, multistep control, open-world
learning, consciousness, personhood, AGI, or a Diana-like brain.

## Result

Seeds `34000–34063` were executed once after pre-registration. All 21 criteria
passed.

| Calibration metric | Mean | 95% interval |
| --- | ---: | ---: |
| Related reward improvement | `1.734375` | [`1.390625`, `2.09375`] |
| Related pseudo-regret reduction | `1.704343` | [`1.356669`, `2.073671`] |
| Related candidate minus shuffled reward | `1.875` | [`1.46875`, `2.296875`] |
| Related candidate minus shuffled pseudo-regret | `1.740866` | [`1.403615`, `2.106069`] |
| Related simultaneous-win rate | `0.78125` | [`0.665672`, `0.864977`] Wilson |
| Unrelated reward improvement | `0.125` | [`-0.421875`, `0.640625`] |
| Unrelated pseudo-regret reduction | `-0.067872` | [`-0.435850`, `0.287976`] |
| Adversarial reward improvement | `-0.859375` | [`-1.296875`, `-0.421875`] |
| Adversarial pseudo-regret reduction | `-0.946510` | [`-1.244819`, `-0.664120`] |

Related final source weight was `0.999964`, unrelated weight was `0.021513`,
and adversarial weight was effectively zero. The gate recovered `2.84375`
unrelated rewards and `9.984375` adversarial rewards relative to ungated
transfer. All four integrity rates were `1.0` and both interaction-cost checks
matched the frozen values.

Decision: **eligible for confirmatory pre-registration**. Calibration repeated
the related operational and causal effects and kept mismatch losses within the
declared non-inferiority tolerances.

This is not a robust no-harm result. The adversarial candidate remained
significantly worse than scratch. A final H50-L15 protocol must preserve that
fact in its claim and cannot describe the gate as eliminating negative
transfer. H50-L15 remains unregistered until a separate protocol is committed
before fresh final seeds are run.

The machine-readable record is
[`results/EXPERIMENT_029_CALIBRATION_AGGREGATE.json`](results/EXPERIMENT_029_CALIBRATION_AGGREGATE.json).
