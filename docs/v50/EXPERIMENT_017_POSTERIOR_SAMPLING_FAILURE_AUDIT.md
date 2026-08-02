# Experiment 017 — posterior-sampling failure audit

Pre-registered: 2026-08-02

Experiment class: diagnostic follow-up to H50-L12

Status: pre-registered; implementation and diagnostic run not started

## Why this audit exists

H50-L12 was refuted because posterior-sampling control earned less cumulative
reward than certainty-equivalent control, despite recovering the hidden context
order and learning accurate transition and reward tables. Changing the
controller immediately would make it too easy to explain the result after the
fact. This audit therefore freezes a new diagnostic before inspecting any new
worlds.

The audit does not retry H50-L12, select a new controller, or provide evidence
for H50-L13. Its seeds are diagnostic and cannot later become development or
final seeds.

## Research basis

[Posterior Sampling for Reinforcement Learning](https://papers.nips.cc/paper_files/paper/2013/hash/6a5889bb0190d0211a991f47bb19a777-Abstract.html)
samples an MDP from the posterior at an episode boundary and follows the policy
that is optimal for that sample. H50-L12 used this structure and still lost to
its posterior-mean control in Darwin's small stationary benchmark.

[Learning to Optimize via Information-Directed Sampling](https://arxiv.org/abs/1403.5556)
frames exploration as a balance between expected immediate regret and expected
information gain. It motivates measuring decision cost and information
separately. This audit does not implement IDS and does not claim its guarantees.

[An Information-Theoretic Analysis of Thompson Sampling](https://jmlr.org/beta/papers/v17/14-087.html)
connects Thompson-sampling regret to information acquisition. The analysis does
not imply that every posterior sample is useful in this environment.

The later [Regret Bounds for Information-Directed Reinforcement Learning](https://openreview.net/forum?id=1pHC-yZfaTK)
also emphasizes that the learning target matters. Darwin's order information
gain is only information about context order; it is not information about the
optimal policy or the entire environment.

## Frozen diagnostic setup

- seeds: `23200–23231`;
- planning-block length: the H50-L12 frozen value of 32 actions;
- interaction budget: 40 environment episodes of 32 actions, or 1,280 actions
  per policy and world;
- candidate: the unchanged H50-L12 posterior-sampling agent;
- comparator: the unchanged certainty-equivalent policy;
- time buckets: four consecutive quarters of 320 interactions;
- test-only seeds must be at or above `23300` and outside future registered
  families.

The first execution on all seeds `23200–23231` retires them for this audit.
They will not be used to choose H50-L13's algorithm, hyperparameters,
thresholds, development seeds, or final seeds.

## Frozen shadow-policy trace

At each 32-action planning-block boundary, after the candidate samples its
model but before the environment reveals either outcome, the evaluator creates
two shadow planners from the candidate's posterior at that boundary. The
sampled and shadow models remain fixed for the same block. At every interaction
in that block, all three planners are evaluated on the candidate's current
causal history and time-to-go:

1. **sampled policy:** the unchanged action selected by H50-L12's sampled
   model;
2. **sampled-order mean policy:** an exact planner using posterior-mean
   transition and reward probabilities conditional on the candidate's sampled
   order;
3. **MAP mean policy:** an exact planner using posterior-mean probabilities at
   the block-boundary MAP order, which is the candidate-state shadow of the
   certainty-equivalent controller.

All three use the candidate's current time-to-go. Shadow actions are never sent
to the environment and no unchosen outcome is read or stored.

The MAP-mean planner also supplies the model-implied opportunity-cost proxy

`Q_MAP_mean(MAP_mean_action) - Q_MAP_mean(sampled_action)`.

This quantity is non-negative by construction. It is an internal diagnostic,
not observed counterfactual regret and not a causal estimate of the reward that
an unchosen action would have produced.

If a world contains no sampled/MAP action disagreement, its conditional
opportunity-cost value is recorded as `0.0`, and the disagreement rate makes
that convention explicit.

## Frozen metrics

The evaluator reports world-level values and across-world means for the full
run and every quarter:

- posterior-sampling reward and separately executed certainty-equivalent
  reward;
- paired reward difference, candidate minus certainty-equivalent;
- sampled-policy versus MAP-mean action disagreement rate;
- sampled-order-mean versus MAP-mean disagreement rate, called the **order
  channel**;
- sampled-policy versus sampled-order-mean disagreement rate, called the
  **parameter channel**;
- sampled-order versus MAP-order mismatch rate;
- mean MAP-mean opportunity-cost proxy, both over all steps and conditional on
  sampled/MAP action disagreement;
- Shannon entropy of the order posterior in natural units;
- order information gain already emitted by the unchanged Bayesian model;
- causal archive completeness.

The order and parameter channels are a sequential diagnostic, not an additive
or unique causal decomposition. Both can change the same final action.

## Uncertainty calculation

Every reported across-world mean receives a paired, non-parametric percentile
bootstrap interval over the 32 worlds:

- 10,000 resamples of 32 worlds with replacement;
- fixed bootstrap seed `0xA17D17`;
- two-sided 95% interval;
- quantiles use sorted bootstrap means and linear interpolation at
  `p × (n - 1)`.

The bootstrap describes variation across this diagnostic world generator. It
does not turn the audit into independent confirmation.

## Frozen interpretation rules

The audit has no pass/fail outcome and cannot promote a capability claim.
Interpretation is limited to these pre-declared statements:

1. The H50-L12 reward deficit is **replicated diagnostically** only if the
   upper endpoint of the total paired reward-difference interval is below zero.
   Otherwise the fresh audit is inconclusive about replication, while the
   original registered refutation remains unchanged.
2. A model-implied sampling cost is **resolved above zero** only if the lower
   endpoint of the mean opportunity-cost interval is above zero. This remains
   a statement about the learned model, not true counterfactual reward.
3. The parameter channel is descriptively dominant only if the 95% interval
   for world-level `parameter disagreement - order disagreement` lies entirely
   above zero. The order channel is dominant only if that interval lies entirely
   below zero. Otherwise channel dominance is unresolved.
4. Quarter-level results may locate when loss or disagreement occurs, but no
   quarter may override the total-run interpretation.
5. No controller for H50-L13 will be named until the audit is complete. Any
   later hypothesis must receive disjoint development and final seed families
   and its own pre-registration.

## Integrity checks

- The candidate implementation and random streams remain unchanged.
- Diagnostic calculations occur before the chosen outcome is observed.
- The comparator learns only from its own actions and observations.
- Hidden true probabilities may be used only for evaluator summaries, never by
  either policy.
- Shadow actions and Q values stay outside the causal experience archive.
- Non-finite values, incomplete traces, seed duplication, wrong trace lengths,
  or counterfactual fields fail closed.

## Evidence ceiling

The maximum result is `E1_LOCAL_DIAGNOSTIC`.

This audit can identify a narrow failure mechanism in a tiny stationary binary
world. It cannot establish general exploration efficiency, representation
learning, continual adaptation, perception, language grounding, consciousness,
personhood, AGI, or a Diana-like mind.
