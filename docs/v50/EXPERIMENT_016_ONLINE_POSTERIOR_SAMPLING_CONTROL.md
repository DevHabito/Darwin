# Experiment 016 — online posterior-sampling control

Pre-registered: 2026-08-02\
Hypothesis: H50-L12\
Status: final evaluation complete; **refuted**

## Pre-run clarification

Recorded on 2026-08-02 before running any registered development or final
seed.

The original wording combined 32-action environment episodes with candidate
resampling lengths of 8, 16, 32, or 64 actions, while saying that every sampled
model was solved for 32 remaining steps. That left the 64-action candidate
undefined. The executable interpretation is fixed as follows:

- a planning block contains exactly the candidate resampling length in online
  interactions;
- the sampled model and its finite-horizon policy remain fixed for the whole
  planning block, even when a 64-action block crosses one environment reset;
- the dynamic program is undiscounted and has a time-to-go equal to the full
  planning-block length;
- an environment reset supplies a new registered initial history but does not
  reset the planning-block clock or expose hidden world state;
- certainty-equivalent, epsilon-greedy, and fixed-order-5 policies rebuild
  their planners on the same selected planning-block boundaries;
- explore-then-commit updates its posterior during the first 512 uniformly
  random actions, freezes that posterior at action 512, and then plans on the
  same selected block boundaries without further learning;
- the simultaneous-world metric is a strict total-reward win over each of the
  four registered learned baselines; ties are not wins;
- information gain is the sum, within each 32-action environment episode, of
  `KL(order posterior after the observation || order posterior before the
  observation)` in natural units. The reported value is the mean of those 40
  episode sums.

This clarification resolves an internal inconsistency; it does not change the
seed families, candidate set, environment, baselines, metrics, thresholds, or
decision rule.

## Gap

H50-L11 learned context order, transition probabilities, and reward from a
human-defined random collection phase. The learned model was then frozen before
the agent tried to earn reward. That separation avoided leakage, but it did not
test whether Darwin can explore and exploit in one continuous interaction.

H50-L12 asks:

> Can an online agent use posterior uncertainty to choose actions, learn only
> from their observed consequences, and reduce cumulative regret while its
> context order, dynamics, and reward model are still uncertain?

## Research basis

[Posterior Sampling for Reinforcement Learning](https://papers.nips.cc/paper_files/paper/2013/hash/6a5889bb0190d0211a991f47bb19a777-Abstract.html)
updates a posterior over MDPs, samples one model at the start of an episode, and
follows that sample's optimal policy for the episode. H50-L12 implements this
small episodic idea with exact tabular Beta posteriors. It does not claim the
paper's regret bound because Darwin also infers context order and its benchmark
does not match the theorem's assumptions.

[VIME](https://papers.nips.cc/paper_files/paper/2016/hash/abd815286ba1007abfbb8415b83ae2cf-Abstract.html)
uses information gain to drive exploration in learned dynamics. It motivates an
information-gain diagnostic here, but Darwin will not implement VIME, a neural
network, or variational inference.

## Seeds

- development: `22000–22031`;
- final: `22100–22199`.

These families are disjoint from every earlier development and final set. The
first run of `22100–22199` permanently contaminates those seeds for changes to
H50-L12.

Implementation debugging must use seeds at or above `23000`, excluding any
later registered family.

## Environment

The environment retains the registered H50-L11 structure:

- binary observations;
- opaque actions `amber` and `violet`;
- hidden true context order 2, 3, 4, or 5;
- context-dependent stochastic transitions with fidelity `0.85`;
- two rewarding contexts per world;
- reward probabilities `0.75` for the designated action, `0.10` for the other
  action in a rewarding context, and `0.02` elsewhere.

Each policy receives 40 episodes of 32 actions, for 1,280 online interactions.
The world structure stays fixed across a policy's episodes. Initial five-bit
histories and action-indexed potential outcomes are precomputed from separate
streams. Policies receive the same initial histories and the same potential
outcome for any action they both choose at the same step.

The agent sees only the initial history, its executed action, the next bit, and
the reward of that action. It never receives true order, true probabilities,
rewarding contexts, non-chosen outcomes, or oracle values.

## Bayesian model

The learner maintains one Beta-Bernoulli transition and reward table for each
candidate order 1 through 5. Priors are `Beta(1,1)`. Before incorporating each
chosen outcome, every order assigns its sequential posterior-predictive
probability to the observed next bit and reward. Log model evidence accumulates
from those pre-update probabilities.

Order posterior starts uniform and is the normalized exponentiation of the five
log evidences. Counts and order evidence update only after the chosen outcome is
observed.

## Candidate policy

At the start of each planning episode, the candidate:

1. samples an order from the current order posterior;
2. samples transition and reward probabilities from that order's Beta tables;
3. solves the sampled finite-horizon MDP exactly for the registered planning
   block length;
4. follows the sampled policy for the episode;
5. archives and learns from each executed action, without changing the sampled
   policy until the next episode.

Sampling uses a policy-only random stream. Potential world outcomes use separate
streams. The candidate receives no exploration bonus and no oracle termination
signal.

## Development selection

The only candidate hyperparameter is posterior-resampling episode length:

- 8, 16, 32, or 64 actions.

All candidates receive the same 1,280 interactions. Development selects the
highest mean cumulative reward on `22000–22031`; ties prefer lower final combined
model error and then shorter episode length. No learned state transfers between
worlds.

### Frozen development result

The registered development seeds `22000–22031` were first run after the
implementation and all structural tests passed. Results were:

| Resampling length | Mean reward | Mean combined model error |
| ---: | ---: | ---: |
| 8 | `0.2671875` | `0.09659293601408378` |
| 16 | `0.2697265625` | `0.09625653330267775` |
| 32 | `0.2720703125` | `0.10287408714901367` |
| 64 | `0.264501953125` | `0.0956723466880944` |

The frozen resampling length is therefore **32 actions**. Selection followed
the registered primary ranking by mean reward; the lower model error of another
candidate cannot override that ranking. Final seeds `22100–22199` had not been
run when this choice was recorded.

## Baselines and ablations

- **certainty-equivalent:** plans from posterior-mean probabilities at the MAP
  order, without posterior sampling;
- **epsilon-greedy:** the same certainty-equivalent planner with fixed
  `epsilon=0.10` and a separate action stream;
- **explore then commit:** uniform random actions for the first 512 interactions,
  followed by a frozen posterior-mean planner;
- **fixed order 5 posterior sampling:** removes order inference while preserving
  posterior sampling and reward learning;
- **uniform random:** chooses each action with probability `0.5`;
- **oracle:** knows true order and probabilities and uses the same finite-horizon
  dynamic program.

Every policy has the same interaction count. Candidate and baselines learn only
from their own chosen outcomes.

## Metrics

- mean reward per online interaction over all 1,280 steps;
- reward in the final 320 interactions;
- Bayesian regret relative to the paired oracle;
- mean information gain about order per episode;
- final MAP-order recovery and mean posterior mass on true order;
- final transition and reward probability MAE;
- improvement over every baseline;
- fraction of worlds with simultaneous wins over certainty-equivalent,
  epsilon-greedy, explore-then-commit, and fixed-order-5 posterior sampling;
- complete causal archive, exact snapshot replay, and no counterfactual fields.

## H50-L12 decision

Every criterion must pass on `22100–22199`:

- candidate/oracle total reward ratio at least `0.75`;
- candidate/oracle final-quarter reward ratio at least `0.85`;
- mean reward improvement at least `0.010` over certainty-equivalent;
- improvement at least `0.005` over epsilon-greedy;
- improvement at least `0.015` over explore-then-commit;
- improvement at least `0.010` over fixed-order-5 posterior sampling;
- improvement at least `0.050` over uniform random;
- simultaneous win rate at least `0.60`;
- final MAP-order recovery at least `0.70`;
- mean posterior mass on true order at least `0.65`;
- transition MAE at most `0.08`;
- reward MAE at most `0.08`;
- archive retention, snapshot replay, and causal-field rates exactly `1.0`.

Any failed criterion refutes H50-L12. A good final model does not compensate for
poor cumulative reward, and high reward does not compensate for failure to learn
the hidden model.

## Final evaluation

The final seeds `22100–22199` were run once with the frozen 32-action
resampling length. H50-L12 is **refuted**. Twelve of fifteen registered checks
passed; three failed.

| Criterion | Required | Observed | Result |
| --- | ---: | ---: | --- |
| Candidate/oracle total reward ratio | `>= 0.75` | `0.8620182634` | Pass |
| Candidate/oracle final-quarter ratio | `>= 0.85` | `0.9564634272` | Pass |
| Improvement over certainty-equivalent | `>= 0.010` | `-0.0164218750` | **Fail** |
| Improvement over epsilon-greedy | `>= 0.005` | `0.0033671875` | **Fail** |
| Improvement over explore-then-commit | `>= 0.015` | `0.0384140625` | Pass |
| Improvement over fixed order 5 | `>= 0.010` | `0.0282031250` | Pass |
| Improvement over uniform random | `>= 0.050` | `0.1463125000` | Pass |
| Simultaneous learned-baseline win rate | `>= 0.60` | `0.04` | **Fail** |
| Exact MAP-order recovery | `>= 0.70` | `0.96` | Pass |
| Mean posterior mass on true order | `>= 0.65` | `0.9590054404` | Pass |
| Transition MAE | `<= 0.08` | `0.0555320000` | Pass |
| Reward MAE | `<= 0.08` | `0.0412705321` | Pass |
| Archive retention | `1.0` | `1.0` | Pass |
| Snapshot replay | `1.0` | `1.0` | Pass |
| Causal-field rate | `1.0` | `1.0` | Pass |

The candidate learned the hidden model accurately and approached the oracle in
the final quarter, but posterior sampling paid too much cumulative exploration
cost in this stationary benchmark. Certainty-equivalent control earned mean
reward `0.2774921875`, above the candidate's `0.2610703125`. The candidate beat
all four learned baselines simultaneously in only four of 100 worlds.

The generator produced 99 unique latent world structures. Seeds `22104` and
`22192` had the same latent structure, although their episode schedules and
exogenous outcome streams remained seed-specific. Structural uniqueness was
not a registered criterion, but the collision is retained as a limitation.

The machine-readable aggregate is stored in
[`results/EXPERIMENT_016_FINAL_AGGREGATE.json`](results/EXPERIMENT_016_FINAL_AGGREGATE.json).
The final seed family is retired for H50-L12 and will not be reused to promote
an altered version of this hypothesis.

## Persistence and tamper checks

The snapshot must contain configuration, all five order models, log evidence,
the causal archive, current episode state, sampled model, and policy RNG state.
Restoration replays the archive, reconstructs derived counts and evidence, and
must produce the same next action under the same pending episode.

Skipped indices, discontinuous histories, unknown actions, non-boolean outcomes,
non-finite evidence, posterior values that do not normalize, derived counts that
disagree with replay, and counterfactual outcome fields must be rejected.
Snapshots remain structurally checked, not cryptographically authenticated.

## Evidence ceiling

The maximum result is `E1_LOCAL_AUTOMATED_EVALUATOR`.

Even a pass would show online Bayesian control only in a tiny stationary binary
world. It would not establish neural representation learning, continual
adaptation across changing worlds, physical perception, language grounding,
consciousness, personhood, AGI, or a Diana-like mind.
