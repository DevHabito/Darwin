# Experiment 028 — source-learned contextual decision development

Status: pre-registered development. Development seeds had not been run when
this document, evaluator, and seed constants were committed. This experiment
has no pass rule and cannot register H50-L15.

## Question

Can the exact H50-L14 source-learned prior and compatibility gate produce a
measurable contextual decision signal under the benchmark validated by
Experiment 027?

H50-L14 established prequential prediction under evaluator-scheduled actions.
Experiment 027 established that an evaluator-only exact family prior can improve
chosen actions and reward. This development stage connects those two results
without assuming that the learned candidate will inherit the oracle effect.

## Selection history

Implementation-only seeds `32900–32903` were used by automated tests. Before
this registration, tests checked determinism, complete causal archives,
snapshot replay, explicit source cost, positive related pseudo-regret direction,
and positive candidate-minus-shuffled pseudo-regret direction. Their exact
aggregate metrics were not used to set a pass threshold. These seeds are
contaminated and excluded from all later decisions.

Development seeds `33000–33031` are fresh and will be executed once after this
protocol is committed.

## Frozen candidate

The candidate reuses the H50-L14 configuration without a new search:

- 16 source tasks;
- eight balanced source cycles;
- 2,048 chosen-action source interactions;
- empirical-Bayes Beta-Binomial prior fitted from source observations only;
- initial source-model mixture weight `0.50`;
- online Bayesian compatibility update;
- 64 target interactions over eight balanced exogenous-context cycles;
- epsilon-greedy target action selection with epsilon `0.10`;
- action choice based only on current reward estimates.

The target budget is 64 interactions, so source training costs 32 times the
target evaluation budget.

## Feedback boundary

The existing task schema returns a chosen action's binary transition outcome
and binary reward. The policy ranks actions using reward estimates only. The
frozen H50-L14 compatibility gate updates its source weight using both observed
channels.

This auxiliary transition feedback may help detect family mismatch. It is
available to the candidate and comes from the chosen action, not from an
evaluator secret or counterfactual. Nevertheless, any later claim must say
"contextual decisions with auxiliary transition feedback," not pure contextual
bandit transfer. A reward-only gate would be a separate algorithm and is not
silently introduced here.

## Comparison set

Every target policy receives the same context schedule, target budget, policy
randomness namespace, and outcome-randomness namespace.

- **scratch:** independent `Beta(1, 1)` priors;
- **candidate:** source-learned prior with the frozen compatibility gate;
- **ungated:** the same learned prior with full fixed influence;
- **shuffled:** gated prior with a fixed cyclic cell permutation;
- **pooled:** naive pooled source counts;
- **oracle:** evaluator-only exact source-family prior.

The shuffled model tests whether aligned source structure causes any decision
advantage. The ungated and pooled controls expose negative transfer. The oracle
is a ceiling, not a Darwin component.

## Frozen development inputs

- implementation-only seeds: `32900–32903`;
- development seeds: `33000–33031`;
- target conditions: related, unrelated, and adversarial;
- bootstrap samples: `2,000`;
- bootstrap seed: `33700`;
- all Experiment 020–027 source, test, validation, calibration, final, audit,
  and replication seeds are excluded.

## Reported metrics

For every condition and policy:

- realized reward improvement over scratch;
- evaluator-only pseudo-regret reduction versus scratch;
- family-preferred action-rate improvement;
- source and target interaction costs.

Paired development intervals additionally cover:

- candidate improvement over scratch;
- candidate minus shuffled reward and pseudo-regret;
- candidate minus ungated reward and pseudo-regret;
- final candidate source weight;
- related simultaneous reward-and-pseudo-regret win rate;
- causal archive, opaque identity, and snapshot replay rates.

Continuous means use paired percentile bootstrap intervals over worlds. The
related simultaneous-win rate uses a 95% Wilson interval.

## Decision boundary

There is no capability decision. Development outputs may support a later
calibration protocol only if they show a related candidate effect, a causal
advantage over the shuffled control, and tolerable mismatch behavior. Any
thresholds must be set on a separate calibration family before final seeds are
allocated.

A favorable development result does not register H50-L15. A failed or ambiguous
result must be recorded and audited; it cannot be repaired on these seeds.

## Interpretation ceiling

This remains a synthetic, known-alignment, tabular contextual decision task
with auxiliary feedback. It does not establish multistep control, autonomous
goal formation, general lifelong learning, consciousness, personhood, AGI, or
a Diana-like brain.

## Result

Not run at pre-registration time.
