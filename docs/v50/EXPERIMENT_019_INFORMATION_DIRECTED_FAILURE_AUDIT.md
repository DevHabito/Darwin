# Experiment 019 — information-directed control failure audit

Pre-registered: 2026-08-02

Experiment class: diagnostic follow-up to H50-L13

Status: pre-registered; implementation and diagnostic run not started

## Why this audit exists

H50-L13 improved on same-cadence posterior sampling and epsilon-greedy, learned
the hidden tabular model, and approached oracle reward late in the run. It was
still refuted because it remained below certainty-equivalent control, missed
the registered posterior-sampling margin, and rarely beat all learned baselines
simultaneously.

Registering another controller immediately would allow an unconstrained
post-hoc explanation. This audit first separates three ways the H50-L13 action
can differ from current posterior-mean control:

1. the block-boundary posterior-mean policy can become stale as observations
   arrive within a 16-action block;
2. a finite posterior ensemble can prefer a different action from the
   block-boundary posterior-mean policy;
3. the information-directed mixture can execute a different action from the
   ensemble's minimum-regret action.

The audit does not retry H50-L13, tune its controller, or promote a capability.

## Research and provenance boundary

[Learning to Optimize via Information-Directed Sampling](https://arxiv.org/abs/1403.5556)
defines the information ratio in terms of expected regret and information about
the optimal action. H50-L13 approximated that target with 16 posterior models.
The present audit measures how that approximation and its randomized mixture
affect decisions; it does not implement a new IDS variant or claim the paper's
guarantees.

Experiment 017 contained an overly strict separation rule that was later
violated when its mechanism result informed H50-L13's design. This protocol uses
a more accurate boundary: Experiment 019 may identify a qualitative mechanism
that motivates a future pre-registration, but its seeds cannot estimate that
future controller's performance, select its numerical hyperparameters or
thresholds, or become development or final evidence.

## Frozen diagnostic setup

- diagnostic seeds: `25200–25231`;
- H50-L13 block length: the frozen value of 16 actions;
- posterior ensemble size: the frozen value of 16 models;
- interaction budget: 40 environment episodes of 32 actions, or 1,280 actions
  per policy and world;
- candidate: the unchanged final H50-L13 agent and random-stream masks;
- comparator: the unchanged same-cadence certainty-equivalent policy;
- time buckets: four consecutive quarters of 320 interactions;
- test-only seeds must be at or above `25300`, outside future registered
  families.

The first complete execution on `25200–25231` retires those seeds for this
audit. H50-L13 final seeds `24100–24199` will not be rerun or inspected at
world level.

## Frozen pre-outcome trace

Every diagnostic is computed after the H50-L13 agent has selected its action
but before the environment reveals the next observation or reward.

At a planning-block boundary, the evaluator creates a **block MAP-mean** planner
from the candidate's causal posterior at that boundary. It uses the same
16-action horizon and remains fixed for the block. At every interaction, the
evaluator also creates a **current MAP-mean** planner from the candidate's
posterior after all previously observed outcomes, using the candidate's current
history and time-to-go.

The H50-L13 decision already exposes the two actions' ensemble expected regret.
The action with lower expected regret is the **ensemble-greedy** action; ties
select `amber`. These four action definitions yield a sequential diagnostic:

- **staleness channel:** block MAP-mean action differs from current MAP-mean;
- **ensemble channel:** ensemble-greedy differs from block MAP-mean;
- **mixture channel:** executed H50-L13 action differs from ensemble-greedy;
- **total disagreement:** executed action differs from current MAP-mean.

The channels are neither mutually exclusive nor additive causal effects. Their
order is an explicit attribution convention, not a Shapley decomposition.

The current MAP-mean planner supplies the internal opportunity-cost proxy

`Q_current_MAP(current_MAP_action) - Q_current_MAP(executed_action)`.

It is non-negative by construction and is not observed counterfactual reward.
Shadow actions never reach the environment or causal archive.

## Frozen metrics

The evaluator reports world-level values and across-world means for the full
run and each quarter:

- candidate reward, separately executed certainty-equivalent reward, and their
  paired difference;
- total, staleness-channel, ensemble-channel, and mixture-channel disagreement
  rates;
- `mixture - ensemble`, `mixture - staleness`, and `ensemble - staleness`
  world-level disagreement differences;
- selected probability of executing the non-greedy ensemble action;
- realized non-greedy action rate and non-degenerate mixture rate;
- binary entropy of the selected action mixture in natural units;
- mean current-MAP Q opportunity cost, over all steps and conditional on total
  disagreement, with `0.0` used when a world has no disagreement;
- H50-L13 action-target information gain and finite information ratio;
- context-order posterior entropy;
- causal archive completeness and exact trace length.

## Uncertainty calculation

Every across-world mean receives a paired non-parametric percentile bootstrap
interval over the 32 worlds:

- 10,000 resamples of 32 worlds with replacement;
- fixed bootstrap seed `0xA19D19`;
- two-sided 95% interval;
- quantiles use sorted bootstrap means and linear interpolation at
  `p × (n - 1)`.

## Frozen interpretation rules

This audit has no pass/fail result and cannot promote a capability.

1. The H50-L13 reward deficit is **replicated diagnostically** only if the upper
   endpoint of candidate-minus-certainty reward is below zero. Otherwise the
   audit is inconclusive about replication; the original refutation remains.
2. Model-implied decision cost is **resolved above zero** only if the lower
   endpoint of mean current-MAP Q opportunity cost is above zero.
3. A channel is dominant only when both paired comparisons against the other
   channels exclude zero in its favor:
   - mixture: lower endpoints of `mixture - ensemble` and
     `mixture - staleness` are above zero;
   - ensemble: upper endpoint of `mixture - ensemble` is below zero and lower
     endpoint of `ensemble - staleness` is above zero;
   - staleness: upper endpoints of `mixture - staleness` and
     `ensemble - staleness` are below zero.
   Otherwise dominance is unresolved.
4. Quarter results may locate persistence but cannot override the full-run
   interpretation.
5. A future controller requires new development and final seeds and its own
   thresholds. Experiment 019 may motivate only its qualitative mechanism.

## Integrity requirements

- Candidate code, selected cadence, posterior sample count, and random masks
  remain unchanged.
- All shadow calculations precede the chosen outcome.
- The comparator learns only from its own observations.
- Hidden world parameters and unchosen outcomes never enter a policy or causal
  archive.
- Wrong trace lengths, duplicate seeds, non-finite metrics, invalid mixtures,
  altered candidate rewards, or counterfactual archive fields fail closed.

## Evidence ceiling

The maximum result is `E1_LOCAL_DIAGNOSTIC`.

This audit can localize a failure inside one synthetic tabular benchmark. It
cannot establish general exploration efficiency, open-world learning,
perception, language grounding, consciousness, personhood, AGI, or a Diana-like
mind.
