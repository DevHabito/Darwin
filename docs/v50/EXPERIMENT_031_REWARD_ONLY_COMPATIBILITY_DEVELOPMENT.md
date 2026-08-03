# Experiment 031 — reward-only compatibility development

Status: completed development; not eligible for calibration.

This protocol, evaluator, implementation-only tests, and seed constants must be
committed before development execution. The experiment has no pass rule and
cannot register a new capability hypothesis.

## Question

Can the H50-L15 source-learned prior retain a related contextual decision
advantage when its compatibility gate learns from chosen-action rewards alone?

H50-L15 used both transition and reward likelihoods to update the source-model
weight. That result therefore did not establish a pure reward-feedback
contextual transfer mechanism. Experiment 031 removes the transition
likelihood from the gate without changing the source learner, action policy,
budget, target family, or comparison priors.

## Selection history

Implementation-only seeds `35900–35903` check determinism, causal archives,
snapshot replay, transition blindness, cost accounting, and test-only metric
direction. They are contaminated and excluded from every later decision.

Development seeds `36000–36031` are fresh. They will be executed once after
this protocol and its evaluator are committed. No aggregate from those seeds
has been inspected while writing this registration.

## Frozen candidate

The candidate retains the exact H50-L15 configuration:

- 16 source tasks;
- eight balanced source cycles;
- 2,048 chosen-action source interactions;
- the same empirical-Bayes Beta-Binomial source prior;
- initial source weight `0.50`;
- 64 balanced target interactions;
- epsilon-greedy action selection with epsilon `0.10`;
- action ranking from current reward estimates;
- known context and action alignment.

The only algorithmic change is the compatibility likelihood. After a chosen
action, the gate updates source versus scratch weight from the observed reward
probability. It does not include the observed transition probability.

The common task schema still returns and archives a binary transition outcome.
The source and scratch submodels update their transition posteriors for schema
and replay compatibility. Those transition posteriors do not enter reward
forecasts, action ranking, or reward-only gate weights.

## Counterfactual boundary check

For every candidate and shuffled archive, the evaluator performs a second
causal replay with every transition outcome inverted while preserving contexts,
actions, and rewards. At every step it requires exact equality of:

- all reward forecasts;
- the current source weight;
- the complete source-weight history.

Any difference marks transition blindness as false. This check establishes a
software-level causal exclusion in the registered model; it does not establish
that a real-world agent could avoid observing correlated side information.

## Comparison set

All policies receive the same context schedule, target budget, policy-randomness
namespace, and outcome-randomness namespace.

- **scratch:** independent `Beta(1, 1)` priors;
- **candidate:** learned prior with the reward-only compatibility gate;
- **ungated:** the learned prior with full fixed influence;
- **shuffled:** cyclically permuted learned prior with the reward-only gate;
- **pooled:** naive pooled source counts;
- **oracle:** evaluator-only exact source-family prior.

The shuffled policy remains the causal alignment control. Ungated transfer
exposes mismatch damage. The oracle is a ceiling and is not a Darwin component.

This development does not include the earlier dual-channel gate as a same-seed
competitor. Cross-experiment numerical differences cannot be interpreted as a
causal comparison between feedback modes. A direct comparison would require a
separate registered evaluator.

## Frozen inputs

- implementation-only seeds: `35900–35903`;
- development seeds: `36000–36031`;
- target conditions: related, unrelated, and adversarial;
- target interactions per world: `64`;
- bootstrap samples: `2,000`;
- bootstrap seed: `36700`;
- all Experiment 020–030 seed families are excluded.

## Reported metrics

The evaluator reports the same development metrics as Experiment 028:

- candidate reward, pseudo-regret, and preferred-action improvement over
  scratch;
- candidate-minus-shuffled reward and pseudo-regret;
- candidate-minus-ungated reward and pseudo-regret;
- final candidate source weight;
- related simultaneous reward-and-pseudo-regret win rate;
- causal archive, opaque identity, snapshot replay, and counterfactual
  transition-blindness rates;
- source and target interaction costs.

Continuous means use paired percentile bootstrap intervals over worlds. The
related simultaneous-win rate uses a 95% Wilson interval.

## Decision boundary

There is no capability decision and no frozen performance threshold. A later
calibration may be considered only if development shows all of the following:

- a positive related decision signal;
- a causal advantage over the shuffled prior;
- complete integrity and transition-blindness checks;
- mismatch behavior that can be bounded without hiding negative transfer.

This list is a screening boundary, not a capability conjunction. Any numerical
threshold must be chosen and tested on a separate calibration seed family.
Failure or ambiguity will be recorded; the algorithm will not be repaired on
these development seeds.

## Interpretation ceiling

Even a favorable result would remain known-alignment, synthetic, tabular,
single-step contextual transfer. It would not establish learned alignment,
multistep control, open-world robustness, autonomous goals, consciousness,
personhood, AGI, or a Diana-like brain.

## Result

Seeds `36000–36031` were executed once after pre-registration in commit
`fa30e8c`. No threshold or algorithm was changed before execution.

| Development metric | Mean | 95% interval |
| --- | ---: | ---: |
| Related reward improvement | `1.625` | [`1.03125`, `2.28125`] |
| Related pseudo-regret reduction | `1.587954` | [`1.169672`, `2.032954`] |
| Related candidate minus shuffled reward | `3.65625` | [`2.46875`, `5.03125`] |
| Related candidate minus shuffled pseudo-regret | `3.631124` | [`2.631003`, `4.759096`] |
| Related simultaneous-win rate | `0.8125` | [`0.646908`, `0.911105`] Wilson |
| Unrelated reward improvement | `-1.5625` | [`-2.46875`, `-0.84375`] |
| Unrelated pseudo-regret reduction | `-1.418548` | [`-2.152930`, `-0.723438`] |
| Adversarial reward improvement | `-6.46875` | [`-7.875`, `-5.0`] |
| Adversarial pseudo-regret reduction | `-6.570846` | [`-7.877974`, `-5.235853`] |

All archive, identity, snapshot, and counterfactual transition-blindness rates
were exactly `1.0`. The software boundary therefore worked: inverting every
transition left gate weights and reward forecasts unchanged.

The reward-only candidate retained a strong related signal and beat the
shuffled alignment control. It also reduced mismatch damage relative to
ungated transfer by `2.59375` rewards on unrelated targets and `4.34375` on
adversarial targets. That reduction was insufficient. Mean source weight only
fell to `0.116127` on unrelated targets and remained `0.375972` on adversarial
targets, compared with `0.999399` on related targets.

Decision: **do not advance this candidate to calibration**. Both mismatch
conditions were significantly worse than scratch, and adversarial loss was
large. Choosing a confirmatory tolerance around this result would preserve a
positive related headline by accepting substantial negative transfer. That
would not be a defensible robustness claim.

The first emitted summary also contained the inherited field
`h50_l15_registered: false` from the Experiment 028 report class. That metadata
was stale: H50-L15 had already passed locally in Experiment 030. The field was
removed and replaced with `baseline_h50_l15_status: passed_locally` after this
single run. No seed was rerun, and no numerical value was recomputed for that
correction.

This development demonstrates that the registered implementation can exclude
transition outcomes causally, but it refutes the current reward-only gate as a
robust transfer candidate. It does not reverse H50-L15, whose narrower claim
explicitly includes transition feedback.

The machine-readable record is
[`results/EXPERIMENT_031_DEVELOPMENT_AGGREGATE.json`](results/EXPERIMENT_031_DEVELOPMENT_AGGREGATE.json).
