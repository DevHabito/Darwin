# Experiment 018 — information-directed online control

Pre-registered: 2026-08-02

Hypothesis: H50-L13

Status: pre-registered; implementation and evaluation not started

## Gap

H50-L12 learned the hidden model but lost cumulative reward because sampled
transition and reward parameters continued to change its actions. The
pre-registered H50-L12 failure audit reproduced that deficit on fresh diagnostic
worlds. In its last two quarters, context-order mismatch and order-channel
action disagreement were zero, while parameter sampling still changed
`10.5078125%` and `8.06640625%` of actions.

H50-L13 asks:

> Can Darwin direct exploration toward information about the current optimal
> action, rather than execute every policy perturbation produced by one
> posterior sample, and thereby improve cumulative reward without preventing
> online model learning?

## Research basis and claim boundary

[Learning to Optimize via Information-Directed Sampling](https://arxiv.org/abs/1403.5556)
defines information-directed sampling (IDS) by balancing squared expected
single-period regret against mutual information about the optimal action.

[An Information-Theoretic Analysis of Thompson Sampling](https://jmlr.org/beta/papers/v17/14-087.html)
shows why the relationship between regret and acquired information is relevant
to posterior sampling. [Regret Bounds for Information-Directed Reinforcement
Learning](https://openreview.net/forum?id=1pHC-yZfaTK) extends the information
ratio analysis to reinforcement-learning targets and stresses that target
choice affects both computation and regret.

Darwin will implement a finite-sample, blockwise approximation in a small
tabular MDP. It is not the exact algorithm analyzed in any of these papers, and
their regret bounds do not transfer to this benchmark.

## Seeds

- development: `24000–24031`;
- final: `24100–24199`.

These families are disjoint from every earlier development, final, diagnostic,
and test set. The first run of `24100–24199` permanently retires those seeds for
changes to H50-L13.

Implementation tests and debugging must use seeds at or above `25000`, excluding
any later registered family.

## Environment and online model

The environment, causal schedule, priors, context-order posterior, transition
and reward tables, interaction budget, and chosen-action feedback are unchanged
from H50-L12:

- binary observations and opaque actions `amber` and `violet`;
- hidden true context order 2, 3, 4, or 5;
- 40 environment episodes of 32 actions, or 1,280 interactions per policy;
- exact `Beta(1,1)` transition and reward tables for candidate orders 1 through
  5;
- prequential model evidence and online updates after the chosen outcome;
- separate potential-outcome, posterior-sampling, and action-sampling streams.

No policy observes a non-chosen outcome or hidden world parameter.

## Candidate: blockwise Monte Carlo IDS

At each planning-block boundary, the candidate draws `K = 16` independent
models from its current posterior. Each draw includes context order, transition
probabilities, and reward probabilities. An exact undiscounted planner solves
each sampled model for the full block horizon. The ensemble remains fixed until
the block ends, while the causal Bayesian model continues to update after every
chosen outcome.

At a step with current history `h` and time-to-go `t`, each sampled model `m`
provides `Q_m(h, a)` for both actions. Ties identify `amber` as optimal. For
action `a`, the Monte Carlo expected regret is

`delta(a) = mean_m[max_b Q_m(h, b) - Q_m(h, a)]`.

The binary next observation and binary reward define four possible outcomes
`y`. Under the registered model, their probabilities are the product of the
sampled transition and reward Bernoulli probabilities. The ensemble estimates
the joint distribution

`P(A* = b, Y = y | a)`

where `A*` is the action optimal in a sampled model. The action information gain
`g(a)` is the mutual information `I(A*; Y | a)` in natural units, computed from
that joint distribution. This target differs from H50-L12's order-only
information diagnostic.

For a distribution that chooses `amber` with probability `p`, define

- `delta(p) = p delta(amber) + (1 - p) delta(violet)`;
- `g(p) = p g(amber) + (1 - p) g(violet)`;
- information ratio `delta(p)^2 / g(p)`.

The evaluator minimizes this ratio exactly over the two-action mixture by
checking both endpoints and every in-range stationary point of the linear-over-
linear objective. If `g(p) = 0`, its score is zero only when `delta(p) = 0` and
infinity otherwise. Ties prefer lower expected regret and then higher `amber`
probability. The action is drawn from the selected mixture using a stream that
is independent of posterior model draws and environment outcomes.

If every feasible mixture has an infinite ratio, the same tie rules select the
lowest-regret mixture, its ratio is recorded as `null`, and that decision counts
against the registered finite-diagnostic rate. Aggregate mean ratio excludes
`null` decisions and is `null` if none are finite. This fallback changes no
decision criterion: the final finite-diagnostic rate must still equal `1.0`.

This construction introduces no exploration bonus, oracle stopping rule, or
learned neural component. `K = 16` is a fixed computational approximation, not
a claimed optimal sample count.

## Development selection

The only candidate hyperparameter is planning-block length:

- 4, 8, or 16 actions.

Every candidate receives exactly 1,280 interactions. Development selects the
highest mean cumulative reward on `24000–24031`; ties prefer lower final
combined transition-plus-reward MAE and then the shorter block. The selected
length is frozen in the experiment record before any final seed is run.

## Baselines

All learned baselines receive the same selected planning cadence and learn only
from their own chosen outcomes:

- certainty-equivalent posterior-mean planning;
- H50-L12-style single-model posterior sampling;
- posterior-mean epsilon-greedy with fixed `epsilon = 0.10`;
- uniform random control;
- an oracle that knows the true tabular model and uses the same finite-horizon
  planner.

The original H50-L12 32-action result remains historical evidence and is not
rerun as a decision baseline.

## Metrics

- mean reward over all 1,280 interactions and over the final 320;
- paired Bayesian regret relative to the oracle;
- improvement over certainty-equivalent, posterior-sampling, epsilon-greedy,
  and uniform-random baselines;
- fraction of worlds with strict simultaneous reward wins over all three
  learned baselines;
- final exact order recovery and posterior mass on the true order;
- final transition and reward probability MAE;
- mean selected action-target information gain and information ratio;
- archive retention, exact snapshot replay, and causal-field completeness.

## H50-L13 decision

Every criterion must pass on `24100–24199`:

- candidate/oracle total reward ratio at least `0.80`;
- candidate/oracle final-quarter reward ratio at least `0.90`;
- mean reward improvement at least `0.005` over certainty-equivalent;
- improvement at least `0.010` over same-cadence posterior sampling;
- improvement at least `0.005` over epsilon-greedy;
- improvement at least `0.050` over uniform random;
- simultaneous learned-baseline win rate at least `0.60`;
- final exact MAP-order recovery at least `0.70`;
- mean posterior mass on true order at least `0.65`;
- transition MAE at most `0.08`;
- reward MAE at most `0.08`;
- finite diagnostic rate, archive retention, snapshot replay, and causal-field
  rates exactly `1.0`.

Any failed criterion refutes H50-L13. Learning the model cannot compensate for
poor reward, and beating posterior sampling cannot compensate for failing
certainty-equivalent control.

## Persistence and integrity requirements

Snapshots must retain the causal model, archive, both random-stream states,
planning-block clock, sampled ensemble, selected mixture diagnostics, and
pending-action state. Restoration must replay derived state and produce the
same next action under the same pending block.

Unknown fields, counterfactual outcomes, non-finite probabilities or
information ratios, invalid mixtures, inconsistent clocks, tampered counts,
and incomplete ensembles fail closed. Structural replay is not cryptographic
authentication.

## Evidence ceiling

The maximum result is `E1_LOCAL_AUTOMATED_EVALUATOR`.

Even a pass would establish only information-directed action selection in a
tiny stationary binary world. It would not establish neural representation
learning, transfer, open-world autonomy, physical perception, language
grounding, consciousness, personhood, AGI, or a Diana-like mind.
