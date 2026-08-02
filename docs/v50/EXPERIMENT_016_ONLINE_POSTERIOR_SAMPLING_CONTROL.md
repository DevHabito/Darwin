# Experiment 016 — online posterior-sampling control

Pre-registered: 2026-08-02\
Hypothesis: H50-L12\
Status: pre-registered; no development or final seed has been run

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
3. solves the sampled finite-horizon MDP exactly for the remaining 32 steps;
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
