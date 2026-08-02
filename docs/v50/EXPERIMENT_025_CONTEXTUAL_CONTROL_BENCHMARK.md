# Experiment 025 — contextual decision benchmark sensitivity

Status: refuted benchmark. Validation seeds had not been run when this
document, evaluator, and frozen criteria were committed as `793c686`. This is
not H50-L15 and does not establish a learned transfer capability.

## Question

Can the existing synthetic family distinguish an evaluator-only correct family
prior from scratch learning through chosen actions, realized reward, and
pseudo-regret?

This is a benchmark prerequisite. The oracle receives hidden source-family
parameters. Darwin does not infer them in this experiment.

## Selection history

Implementation seeds `30200–30207` were inspected before this registration.
With the frozen 64-round policy, the related oracle improved mean reward by
`2.125`, reduced mean pseudo-regret by `1.704482`, and improved the
family-preferred action rate by `0.125`. Every inspected related world improved
both reward and pseudo-regret.

The deliberately wrong oracle lost `5.25` reward and increased pseudo-regret by
`5.031543` on unrelated targets. It lost `10.0` reward and increased
pseudo-regret by `10.864975` on adversarial targets. These test-only results
were used to choose conservative validation margins. They are contaminated and
cannot support the benchmark decision or any later capability claim.

Validation seeds `30300–30331` are fresh and disjoint. They will be executed
once only after this protocol is committed.

## Fixed interaction protocol

- two actions: `amber` and `violet`;
- eight three-bit contexts;
- eight independently shuffled balanced context cycles;
- 64 target interactions;
- exogenous contexts: actions do not control the next context;
- epsilon-greedy action selection with epsilon `0.10`;
- deterministic first-action tie break outside exploration;
- reward estimates inspected without mutating model state;
- only the chosen action is forecast and observed;
- common context, policy-randomness, and outcome seed namespaces across the
  paired policies;
- opaque public task identities that expose no family or world seed.

The environment still emits a transition outcome because it is part of the
existing task schema. The decision rule uses reward estimates only. Therefore
the result is contextual action selection, not transition control.

## Compared policies

### Scratch

Every cell begins with independent `Beta(1, 1)` transition and reward priors
and updates only from its chosen outcomes.

### Evaluator oracle

Every cell begins with the exact Beta distribution used to draw targets from
the source family. For unrelated and adversarial targets, the same source prior
is retained deliberately. This tests whether incompatible transfer is visible.

Neither policy sees the target specification, counterfactual rewards, future
contexts, or the other's observations.

## Metrics

For each condition, paired over worlds:

- oracle cumulative reward minus scratch cumulative reward;
- scratch pseudo-regret minus oracle pseudo-regret;
- oracle minus scratch family-preferred action rate.

Pseudo-regret uses evaluator-only target probabilities. The preferred-action
rate includes only contexts whose target-family reward means differ. A related
simultaneous-win rate counts worlds where both actual reward improvement and
pseudo-regret reduction are positive.

Deterministic percentile bootstrap intervals resample worlds with replacement.

## Frozen validation inputs

- validation seeds: `30300–30331`;
- target conditions: related, unrelated, and adversarial;
- interactions: 64 per policy and target;
- epsilon: `0.10`;
- bootstrap samples: `5,000`;
- bootstrap seed: `30900`;
- implementation seeds: retired from decisions;
- no H50-L15 development, calibration, or final seeds are allocated.

## Conjunctive decision

The benchmark passes only if all ten rules hold:

1. related reward-improvement interval lower bound is at least `1.0`;
2. related pseudo-regret-reduction lower bound is at least `0.75`;
3. related preferred-action-rate improvement lower bound is at least `0.05`;
4. related simultaneous-win-rate lower bound is at least `0.75`;
5. unrelated reward-improvement interval upper bound is at most `0.0`;
6. unrelated pseudo-regret-reduction upper bound is at most `0.0`;
7. adversarial reward-improvement interval upper bound is at most `-2.0`;
8. adversarial pseudo-regret-reduction upper bound is at most `-5.0`;
9. causal archive integrity rate equals `1.0`;
10. opaque public identity integrity rate equals `1.0`.

The first four establish related decision sensitivity. Rules five through
eight establish that the same benchmark exposes incompatible transfer. Rules
nine and ten preserve the evidence boundary.

## Stopping and interpretation

Any miss refutes this benchmark version. Validation seeds are then retired, and
an altered policy or environment requires a new pre-registration and fresh
seeds. Favorable criteria cannot be promoted separately.

A pass means only that the oracle decision benchmark is sensitive enough for
later candidate development. It does not show that the source-learned prior
improves decisions, that its gate prevents reward loss, or that H50-L15 should
be registered.

Maximum evidence level: E1 for benchmark sensitivity, not a cognitive
capability.

## Result

Validation seeds `30300–30331` were executed once after pre-registration. Nine
of ten criteria passed. The related simultaneous-win interval missed its frozen
lower bound, so the benchmark is refuted.

| Metric | Mean | 95% interval | Frozen rule | Result |
| --- | ---: | ---: | ---: | --- |
| Related reward improvement | `1.9375` | [`1.4375`, `2.46875`] | low `>= 1.0` | pass |
| Related pseudo-regret reduction | `1.826751` | [`1.354262`, `2.337514`] | low `>= 0.75` | pass |
| Related preferred-action improvement | `0.128906` | [`0.097656`, `0.160156`] | low `>= 0.05` | pass |
| Related simultaneous-win rate | `0.8125` | [`0.65625`, `0.9375`] | low `>= 0.75` | **fail** |
| Unrelated reward improvement | `-1.0` | [`-2.0625`, `0.0`] | high `<= 0.0` | pass |
| Unrelated pseudo-regret reduction | `-1.096078` | [`-2.206544`, `-0.158017`] | high `<= 0.0` | pass |
| Adversarial reward improvement | `-10.46875` | [`-11.5`, `-9.46875`] | high `<= -2.0` | pass |
| Adversarial pseudo-regret reduction | `-11.229672` | [`-11.932057`, `-10.518452`] | high `<= -5.0` | pass |

Causal archive and opaque-identity rates were both `1.0`.

Decision: **refuted benchmark**. The aggregate related effect is positive, but
the pre-registered robustness rule requires stronger evidence that reward and
pseudo-regret improve together across worlds. The favorable nine-criterion
subset is not promoted. Validation seeds are retired, candidate development is
blocked, and H50-L15 remains unregistered.

The unrelated reward interval ends exactly at its permitted upper boundary,
which is additional evidence that the mismatch behavior is not comfortably
separated under this policy.

The machine-readable record is
[`results/EXPERIMENT_025_VALIDATION_AGGREGATE.json`](results/EXPERIMENT_025_VALIDATION_AGGREGATE.json).
