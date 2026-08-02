# Experiment 026 — contextual decision failure audit

Status: completed diagnostic. Audit seeds had not been run when this document
and evaluator were committed as `9e5c671`. This audit cannot reverse Experiment
025, authorize candidate development, or register H50-L15.

## Question

Why did Experiment 025's related simultaneous-win interval miss its frozen
lower bound even though its aggregate reward and pseudo-regret intervals were
positive?

Two explanations remain plausible:

1. the oracle often chooses actions with lower conditional expected reward;
2. the oracle usually chooses better actions, but 64 binary rewards do not
   reliably turn that expected advantage into a positive realized difference
   in each world.

This audit separates the signs of realized reward improvement and
evaluator-only expected reward improvement. In this benchmark, scratch
pseudo-regret minus oracle pseudo-regret equals the conditional expected reward
difference along the two policies' chosen action trajectories.

## Frozen method

The Experiment 025 environment and policies are unchanged:

- related targets only;
- 64 exogenous-context interactions;
- epsilon `0.10`;
- scratch versus exact source-family oracle;
- common context, policy, and outcome randomness;
- chosen-action observations only.

No horizon, prior, exploration rule, task distribution, or threshold changes.

## Fresh inputs

- diagnostic seeds: `31000–31127`;
- implementation-only audit seeds: `31150–31153`;
- bootstrap samples: `5,000`;
- bootstrap seed: `31700`;
- Experiment 025 validation seeds remain retired.

## Reported diagnostics

Paired bootstrap intervals over diagnostic worlds are reported for:

- realized reward improvement;
- expected reward improvement;
- realized minus expected improvement;
- realized reward win rate;
- expected reward win rate;
- simultaneous win rate;
- expected-win/realized-nonwin rate;
- expected-nonwin/realized-win rate;
- causal archive and opaque public identity rates.

## Interpretation boundary

This audit has no pass rule. If expected wins substantially exceed simultaneous
wins, reward noise is a plausible contributor. If expected wins are themselves
unstable, the policy benchmark is decision-unstable. Neither finding changes
the registered refutation.

Any revised benchmark must explain its metric or horizon change, allocate new
test and validation seeds, and be pre-registered separately. The audit data
cannot be reused for that decision.

## Result

Seeds `31000–31127` were executed once after pre-registration.

| Diagnostic | Mean | 95% interval |
| --- | ---: | ---: |
| Realized reward improvement | `2.226563` | [`1.984375`, `2.484375`] |
| Expected reward improvement | `2.055065` | [`1.858433`, `2.252992`] |
| Realized minus expected | `0.171498` | [`0.014916`, `0.319516`] |
| Realized reward win rate | `0.890625` | [`0.835938`, `0.9375`] |
| Expected reward win rate | `0.984375` | [`0.960938`, `1.0`] |
| Simultaneous win rate | `0.890625` | [`0.835938`, `0.9375`] |
| Expected win, realized non-win | `0.09375` | [`0.046875`, `0.148438`] |
| Expected non-win, realized win | `0.0` | [`0.0`, `0.0`] |

Causal archive and opaque-identity rates were `1.0`.

Interpretation: the oracle had positive conditional expected improvement in
126 of 128 diagnostic worlds, while realized reward improved in 114. Twelve
worlds had positive expected improvement but no positive realized difference.
This pattern is consistent with finite binary-reward variation contributing to
the Experiment 025 simultaneous-win miss. It does not prove that sampling noise
was the only cause.

The larger diagnostic cohort places the simultaneous-win interval above the
old `0.75` threshold, but the audit has no promotion rule. Experiment 025
remains refuted, its validation seeds remain retired, candidate development is
still blocked, and H50-L15 remains unregistered.

A revised benchmark may keep the policy, horizon, and threshold unchanged while
using a larger pre-registered validation cohort and an interval designed for a
Bernoulli rate. It must use entirely fresh seeds and cannot reuse this audit.

The machine-readable record is
[`results/EXPERIMENT_026_FAILURE_AUDIT_AGGREGATE.json`](results/EXPERIMENT_026_FAILURE_AUDIT_AGGREGATE.json).
