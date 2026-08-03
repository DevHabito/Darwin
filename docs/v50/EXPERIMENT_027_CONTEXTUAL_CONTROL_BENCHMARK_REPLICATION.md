# Experiment 027 — contextual decision benchmark replication

Status: passed benchmark replication locally. Validation seeds had not been run
when this document, seed constants, and evaluator were committed as `338ab18`.
This experiment cannot reverse Experiment 025 or register H50-L15.

## Purpose

Experiment 025 was refuted because the lower interval bound for its related
simultaneous-win rate was `0.65625`, below the frozen `0.75` threshold. The
fresh-seed Experiment 026 audit found expected reward wins in `126/128` worlds
and simultaneous wins in `114/128`, with a `0.835938` bootstrap lower bound.
That pattern is consistent with the original 32-world validation cohort being
too imprecise for a per-world binary robustness rate.

The audit cannot promote the old benchmark. This experiment performs a new
validation with fresh seeds and a method chosen before those seeds are run.

## What remains unchanged

- the synthetic task-family generator;
- related, unrelated, and adversarial conditions;
- exact source-family oracle versus `Beta(1, 1)` scratch;
- 64 exogenous-context interactions per policy and target;
- eight balanced context cycles;
- epsilon-greedy action selection with epsilon `0.10`;
- deterministic first-action tie break;
- common policy and outcome randomness for paired policies;
- chosen-action evidence only;
- the ten Experiment 025 thresholds.

No policy, horizon, reward distribution, prior, mismatch construction, or pass
margin changed after the refutation.

## Statistical correction

Experiment 025 used a nonparametric percentile bootstrap for every metric. For
a Bernoulli rate, that interval can collapse to `[1, 1]` when a small observed
sample contains only successes, as happened on the eight implementation seeds.
It then became much wider when the 32 validation worlds contained six
non-wins.

Experiment 027 retains paired percentile bootstrap intervals for continuous
world-level means. It uses a two-sided 95% Wilson score interval for the
related simultaneous-win proportion. Wilson intervals remain non-degenerate
at zero or complete observed success.

The validation cohort increases from 32 to 128 worlds per condition. This
changes precision, not the 64-interaction target horizon.

## Frozen inputs

- implementation-only seeds: `31800–31803`;
- validation seeds: `32000–32127`;
- three conditions, 128 worlds each;
- bootstrap samples: `5,000`;
- bootstrap seed: `32700`;
- Wilson `z`: `1.959963984540054`;
- all Experiment 020–026 decision, final, validation, audit, and test seeds are
  excluded.

## Unchanged conjunctive decision

All ten rules must pass:

1. related reward-improvement lower bound is at least `1.0`;
2. related pseudo-regret-reduction lower bound is at least `0.75`;
3. related preferred-action improvement lower bound is at least `0.05`;
4. related simultaneous-win Wilson lower bound is at least `0.75`;
5. unrelated reward-improvement upper bound is at most `0.0`;
6. unrelated pseudo-regret-reduction upper bound is at most `0.0`;
7. adversarial reward-improvement upper bound is at most `-2.0`;
8. adversarial pseudo-regret-reduction upper bound is at most `-5.0`;
9. causal archive integrity rate equals `1.0`;
10. opaque public identity rate equals `1.0`.

Any miss refutes this replication. No favorable subset may authorize candidate
development.

## Interpretation boundary

A pass would show only that a correctly specified evaluator oracle can improve
contextual decisions in this synthetic family while the same prior exposes
negative transfer under mismatch. It would authorize development of a
source-learned candidate on new seeds. It would not show that Darwin has already
learned reward transfer, and H50-L15 would remain unregistered.

Experiment 025 remains historically refuted under its own protocol regardless
of this result.

## Result

Seeds `32000–32127` were executed once after pre-registration. All ten frozen
criteria passed.

| Metric | Mean | 95% interval | Frozen rule |
| --- | ---: | ---: | ---: |
| Related reward improvement | `1.851563` | [`1.617188`, `2.101563`] | low `>= 1.0` |
| Related pseudo-regret reduction | `2.028021` | [`1.803848`, `2.271262`] | low `>= 0.75` |
| Related preferred-action improvement | `0.149089` | [`0.130208`, `0.168294`] | low `>= 0.05` |
| Related simultaneous-win rate | `0.875` | [`0.806574`, `0.921574`] Wilson | low `>= 0.75` |
| Unrelated reward improvement | `-1.726563` | [`-2.265625`, `-1.203125`] | high `<= 0.0` |
| Unrelated pseudo-regret reduction | `-1.701070` | [`-2.177292`, `-1.213446`] | high `<= 0.0` |
| Adversarial reward improvement | `-11.109375` | [`-11.75`, `-10.484375`] | high `<= -2.0` |
| Adversarial pseudo-regret reduction | `-10.933234` | [`-11.328913`, `-10.515643`] | high `<= -5.0` |

Causal archive and opaque-identity rates were both `1.0`.

Decision: **passed benchmark sensitivity locally**. The exact source-family
oracle improves related contextual decisions and the same prior produces clear
negative transfer under mismatch. The benchmark is now eligible for
source-learned candidate development on new seed families.

This does not reverse Experiment 025, whose registered decision remains
refuted. It does not show that Darwin's learned prior improves reward, and it
does not register H50-L15.

The machine-readable record is
[`results/EXPERIMENT_027_VALIDATION_AGGREGATE.json`](results/EXPERIMENT_027_VALIDATION_AGGREGATE.json).
