# Experiment 032 — compatibility-feedback failure audit

Status: registered failure audit; audit seeds have not been run.

This protocol, evaluator, criteria, implementation-only tests, and seed
constants must be committed before audit execution. The audit is diagnostic. It
cannot register a new capability or reverse either H50-L15 or Experiment 031.

## Question

Did the transition likelihood available to the H50-L15 gate materially improve
mismatch detection and target decisions relative to the reward-only gate that
failed development in Experiment 031?

Comparing the Experiment 030 and 031 aggregates cannot answer that question:
they used different seed families. Experiment 032 places both gates in the same
fresh source and target worlds with paired schedules and random streams.

## Selection history

Implementation-only seeds `36900–36903` test determinism, paired construction,
fixed-archive replay, snapshot replay, cost accounting, interval construction,
and failure of the conjunctive decision when a criterion is false. They are
contaminated and excluded from audit conclusions.

Audit seeds `37000–37063` are fresh and will be executed once after this
protocol and evaluator are committed. No aggregate from those seeds has been
inspected while writing this registration.

## Frozen candidates

Both candidates use the exact H50-L15 configuration:

- 16 source tasks and eight source cycles;
- 2,048 chosen-action source interactions;
- the same empirical-Bayes Beta-Binomial source prior;
- initial source weight `0.50`;
- 64 target interactions in eight balanced context cycles;
- epsilon-greedy action selection with epsilon `0.10`;
- known context and action alignment;
- reward-estimate action ranking.

The **dual-channel** gate updates its mixture weight from chosen-action
transition and reward likelihoods. The **reward-only** gate updates from the
chosen-action reward likelihood alone. No other algorithmic setting differs.

A scratch policy is included to preserve the absolute performance context. It
is not part of the paired feedback-mode causal contrast.

## Behavioral pairing

Within a seed and condition, both candidates receive identical:

- source family, source observations, and learned prior;
- target family and target world specification;
- context schedule;
- epsilon-greedy policy-randomness stream;
- chosen-action outcome-randomness stream;
- source and target interaction budgets.

The policies may choose different actions after their internal states diverge.
The behavioral contrast therefore estimates the total downstream effect of the
feedback-mode change, not a same-action forecast difference.

## Fixed-archive diagnostic

The evaluator also takes the reward-only policy's complete causal archive and
replays those exact contexts, actions, transitions, and rewards through fresh
copies of both gates. This holds experience fixed and measures only how the
transition likelihood changes final source weight.

The reward-only replay must exactly reproduce the original reward-only weight
and archive. Failure blocks the audit conclusion.

## Frozen inputs

- implementation-only seeds: `36900–36903`;
- audit seeds: `37000–37063`;
- target conditions: related, unrelated, and adversarial;
- 64 worlds per condition;
- bootstrap samples: `5,000`;
- bootstrap seed: `37700`;
- related no-material-cost tolerance: `-0.5` reward or pseudo-regret units;
- all Experiment 020–031 seed families are excluded.

Continuous paired means use percentile bootstrap intervals over worlds.

## Frozen audit metrics

For each condition, the evaluator reports:

- dual-channel minus reward-only realized reward;
- dual-channel minus reward-only pseudo-regret reduction;
- dual-channel minus reward-only preferred-action rate;
- reward-only minus dual-channel final source weight under behavioral runs;
- reward-only minus dual-channel final source weight under the fixed archive;
- each candidate's realized reward improvement over scratch.

It also reports causal archive, opaque public identity, both snapshot replay,
reward-only fixed replay, and cost checks.

## Frozen 15-criterion conjunction

A clean transition-feedback benefit is supported only if all criteria pass:

1. unrelated reward-benefit interval lower bound is above `0`;
2. unrelated pseudo-regret-benefit lower bound is above `0`;
3. adversarial reward-benefit lower bound is above `0`;
4. adversarial pseudo-regret-benefit lower bound is above `0`;
5. related reward-effect lower bound is at least `-0.5`;
6. related pseudo-regret-effect lower bound is at least `-0.5`;
7. unrelated fixed-archive reward-only-minus-dual weight lower bound is above
   `0`;
8. adversarial fixed-archive reward-only-minus-dual weight lower bound is above
   `0`;
9–13. all five integrity rates equal `1.0`;
14. source interactions equal `2,048`;
15. target interactions equal `64`.

Any miss records `clean_transition_feedback_benefit_not_supported`. Passing
records `transition_feedback_benefit_supported` for this registered synthetic
family only.

The `-0.5` related tolerance is half a realized reward over 64 interactions,
less than one percent of the target budget. It is fixed before audit execution
and prevents a mismatch benefit from hiding a material related-task cost.

## Interpretation ceiling

A pass would explain part of Experiment 031's failure: transition outcomes
would be causally useful side information for compatibility detection in this
synthetic family. It would not show that reward-only transfer is impossible,
that the current dual-channel gate is optimal, or that comparable transition
signals exist in real environments.

This remains known-alignment, synthetic, tabular, single-step contextual
transfer. The audit cannot establish learned alignment, multistep control,
open-world robustness, autonomous goals, consciousness, personhood, AGI, or a
Diana-like brain.

