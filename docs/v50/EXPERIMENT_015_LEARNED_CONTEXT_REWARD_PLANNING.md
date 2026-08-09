# Experiment 015 — learned context order and reward

Pre-registered: 2026-07-30\
Hypothesis: H50-L11\
Status: refuted in the single official run

## Question

Using only executed actions, binary observations, and observed rewards, can
Darwin select a useful memory depth, estimate stochastic transitions and reward,
and plan for future return?

The implementation is related to fixed-order ideas behind
[context-tree weighting](https://research.tue.nl/en/publications/the-context-tree-weighting-method-basic-properties/),
[Bayesian context trees](https://arxiv.org/abs/2007.14900), and
[U-Tree](https://citeseerx.ist.psu.edu/document?doi=ce40952e1ac0591fb3cea05e0a22fda1a3bb6691&repid=rep1&type=pdf).
It implements none of those methods in full. It selects one global suffix order
from 1 through 5.

## Registered process

- development seeds: `19000–19031`;
- final seeds: `19100–19199`;
- true memory order: 2, 3, 4, or 5, hidden from every policy;
- binary observations and two opaque actions, `amber` and `violet`;
- context-dependent stochastic transitions with fidelity `0.85`;
- two rewarding contexts per world, with action-conditioned reward
  probabilities `0.75`, `0.10`, and background probability `0.02`;
- potential transition and reward uniforms sampled before action choice, while
  only the chosen action's outcome is revealed;
- one continuous uniform-random collection trace per world.

For each candidate order, the first 70% of the trace fits Beta-Bernoulli
transition and reward tables. The final 30% scores predictive log loss without
updates. Lowest loss wins, ties prefer the smaller order, and the selected order
is refit on the full trace.

The candidate uses exact value iteration with discount `0.95`. Baselines use
fixed order 1, fixed order 5, immediate reward only, rotated reward estimates,
random actions, and an evaluator-only oracle. Final worlds contain 32 paired
episodes of 20 steps. Models remain frozen during evaluation.

## Pre-official amendment

The initial budget grid was 768, 1,024, and 1,536. An external run using
development `20300–20331` and evaluation `20400–20499` failed two criteria:

- gain over fixed order 5 was `0.0453157112`, below `0.10`;
- simultaneous world win rate was `0.25`, below `0.70`.

Those seeds were contaminated. Diagnostics on `20700–20715` showed that fixed
order 5 was no longer a meaningful sample-efficiency ablation at the larger
budgets. Before any official seed was touched, the budget grid was changed to
256, 384, and 512.

One logical scoring defect was also corrected. When both the true order and the
candidate order are 5, the candidate and fixed-order-5 baseline are identical.
The simultaneous metric therefore accepts a tie with that baseline only in this
exact case; every other comparison remains strict. No numeric threshold was
lowered.

The amended design passed once on new external development `20800–20831` and
evaluation `20900–20999`, but simultaneous wins landed exactly at the `0.70`
threshold. That cohort was then retired.

## Registered thresholds

The final decision required all of the following:

- exact order recovery at least `0.70`;
- transition and reward probability MAE at most `0.08` each;
- candidate/oracle return ratio at least `0.80`;
- gains of `0.25`, `0.10`, `0.20`, `0.25`, and `0.40` over reactive,
  fixed-order-5, myopic, rotated-reward, and random policies;
- simultaneous ablation success in at least `0.70` of worlds;
- archive, snapshot, and frozen-model rates exactly `1.0`.

## Official result

Development selected budget 512. The 100 final worlds were unique and balanced
across true orders.

| Criterion | Observed | Threshold | Result |
| --- | ---: | ---: | --- |
| Exact order recovery | `0.96` | `>= 0.70` | Passed |
| Transition MAE | `0.0634895253` | `<= 0.08` | Passed |
| Reward MAE | `0.0558083811` | `<= 0.08` | Passed |
| Candidate/oracle return ratio | `0.9738612394` | `>= 0.80` | Passed |
| Gain vs. reactive | `1.4274205742` | `>= 0.25` | Passed |
| Gain vs. fixed order 5 | `0.1158498278` | `>= 0.10` | Passed |
| Gain vs. myopic | `1.3519623739` | `>= 0.20` | Passed |
| Gain vs. rotated reward | `2.6859669982` | `>= 0.25` | Passed |
| Gain vs. random | `2.3581822169` | `>= 0.40` | Passed |
| Simultaneous ablation success | `0.55` | `>= 0.70` | **Failed** |
| Archive / snapshot / frozen model | `1.0` | `1.0` | Passed |

Order confusion was limited to four worlds: one true-order-2 world selected 1,
one selected 3, and two true-order-3 worlds selected 2 and 4. Every order-4 and
order-5 world selected exactly.

## Decision

H50-L11 was refuted. Mean model quality and mean returns were strong, but the
candidate did not beat all relevant ablations consistently enough across
worlds. The conjunctive evaluator returned `false`; the official run was not
repeated and thresholds were not changed.

The model is still binary, tabular, trained separately per world, and collected
through a human-defined random policy. It does not learn a variable context
tree, a latent representation, perception, language, or a general world model.
Final seeds `19000–19031` and `19100–19199` are contaminated. Evidence level:
`E1_LOCAL_AUTOMATED_EVALUATOR`.
