# Experiment 028 — source-learned contextual decision development

Status: completed development. Development seeds had not been run when this
document, evaluator, and seed constants were committed as `e4fc269`. This
experiment has no pass rule and cannot register H50-L15.

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

Seeds `33000–33031` were executed once after pre-registration.

| Development metric | Mean | 95% interval |
| --- | ---: | ---: |
| Related candidate reward improvement | `1.90625` | [`1.28125`, `2.65625`] |
| Related candidate pseudo-regret reduction | `1.632724` | [`1.158490`, `2.180477`] |
| Related candidate preferred-action improvement | `0.121094` | [`0.092448`, `0.153646`] |
| Related candidate simultaneous-win rate | `0.78125` | [`0.612450`, `0.889762`] Wilson |
| Related candidate minus shuffled reward | `2.5` | [`1.75`, `3.375`] |
| Related candidate minus shuffled pseudo-regret | `1.933329` | [`1.454265`, `2.461097`] |
| Unrelated candidate reward improvement | `0.3125` | [`-0.28125`, `0.90625`] |
| Unrelated candidate pseudo-regret reduction | `0.341675` | [`-0.147454`, `0.818062`] |
| Adversarial candidate reward improvement | `-1.1875` | [`-1.78125`, `-0.625`] |
| Adversarial candidate pseudo-regret reduction | `-0.950096` | [`-1.394087`, `-0.602126`] |

The candidate gate retained almost all source weight on related targets
(`0.999987`), fell to `0.013319` on unrelated targets, and fell effectively to
zero on adversarial targets. All causal archive, opaque identity, and snapshot
replay rates were `1.0`.

The gate materially reduced mismatch damage relative to ungated transfer. On
unrelated targets, candidate-minus-ungated reward was `4.15625` [`2.65625`,
`5.65625`]; on adversarial targets it was `10.75` [`9.530469`, `11.9375`]. The
related gated and ungated policies earned identical realized reward, while
their pseudo-regret difference was centered near zero.

Development interpretation: the source-learned structure causes a related
decision advantage and the gate prevents most, but not all, negative transfer.
Adversarial performance remains significantly worse than scratch. The result
is therefore promising but not robust-transfer evidence.

A separate calibration may freeze a related-effect threshold and an explicit
negative-transfer tolerance no looser than two realized rewards and `1.5`
pseudo-regret units over 64 target interactions. Those are development-informed
candidate thresholds, not demonstrated capability margins. Calibration must
use new seeds before any H50-L15 final protocol can be considered.

The 2,048-to-64 source/target cost ratio remains `32`. The auxiliary transition
feedback limitation also remains.

The machine-readable record is
[`results/EXPERIMENT_028_DEVELOPMENT_AGGREGATE.json`](results/EXPERIMENT_028_DEVELOPMENT_AGGREGATE.json).
