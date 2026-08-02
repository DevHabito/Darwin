# Experiment 013 — episodic memory for contextual actions

Pre-registered: 2026-07-30\
Hypothesis: H50-L9\
Status: refuted in the single official run

## Question

Can episodic memory recognize a partially observed context and reuse the
consequences of past actions that are unavailable to an episode-local learner?

The experiment combines four noisy cues, three actions, bandit feedback,
recurring episodes, and genuinely new contexts. It was informed by work on
[partially observable planning](https://www.sciencedirect.com/science/article/pii/S000437029800023X),
[model-free episodic control](https://arxiv.org/abs/1606.04460), and
[neural episodic control](https://proceedings.mlr.press/v70/pritzel17a.html).
Darwin's implementation is tabular and does not reproduce those systems.

## Protocol

- development seeds: `14000–14031`;
- final seeds: `14100–14199`;
- 18 episodes of 24 steps per world;
- only the reward of the executed action is revealed;
- actions 0, 1, and 2 are forced on the first three steps, with two later
  forced probes; other steps use Beta-Bernoulli means;
- a local baseline resets each episode;
- a global baseline shares action values but ignores cues;
- the episodic candidate stores complete chosen-action interactions, consolidates
  prototypes after each episode, retrieves only after enough cue evidence, and
  keeps that decision fixed for the rest of the episode.

Development selected `minimum_cues=4` and `match_tolerance=0.24`. Final
evaluation used 100 unique worlds, 25 from each registered family. Models were
not transferred between worlds.

## Registered decision

Every criterion was conjunctive. The main requirements included at least
`0.04` total reward gain over the local learner, wins in `0.75` of worlds,
family-specific gains, bounded novelty damage, retrieval quality, novelty
abstention, and exact archive and snapshot replay.

## Official result

| Criterion | Observed | Threshold | Result |
| --- | ---: | ---: | --- |
| Total gain vs. local | `0.031550925926` | `>= 0.04` | **Failed** |
| World win rate vs. local | `0.92` | `>= 0.75` | Passed |
| Total gain vs. global | `0.137824074074` | `>= 0.05` | Passed |
| Early recurrence gain | `0.050747126437` | `>= 0.06` | **Failed** |
| Exact recurrence gain | `0.061111111111` | `>= 0.08` | **Failed** |
| Cue-drift gain | `0.035333333333` | `>= 0.05` | **Failed** |
| Reward-drift gain | `0.061333333333` | `>= 0.05` | Passed |
| Novelty degradation | `0.0` | `<= 0.02` | Passed |
| Oracle gap | `0.018888888889` | `<= 0.15` | Passed |
| Correct recurrence coverage | `0.954482758621` | `>= 0.85` | Passed |
| Retrieval precision | `0.987865810136` | `>= 0.90` | Passed |
| Novelty abstention | `1.0` | `>= 0.80` | Passed |
| Novelty false reuse | `0.0` | `<= 0.10` | Passed |
| Archive / snapshot | `1.0` / `1.0` | `1.0` | Passed |

## Decision

H50-L9 was refuted. The memory identified recurring and novel contexts well,
but its reward improvement was not large or consistent enough in four
registered comparisons. Recognition is not the same as useful action transfer.

Final seeds `14100–14199` are contaminated. Evidence level:
`E1_LOCAL_AUTOMATED_EVALUATOR`.
