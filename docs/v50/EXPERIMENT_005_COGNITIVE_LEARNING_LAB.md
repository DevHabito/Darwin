# Experiment 005 — transition learning and recombination

Date: 2026-07-27\
Hypothesis: H50-L1\
Status: passed in the local evaluator

## Question

Can a tabular model learned from controlled transitions support plans for
start-goal pairs that were not used as training tasks?

## Protocol

Twenty deterministic opaque graph worlds were generated from registered seeds.
The learner received state, chosen action, and resulting state. It did not
receive the world's transition table. Training exhaustively visited every
state-action pair; held-out evaluation changed the requested start-goal pairs,
not the underlying dynamics.

Registered criteria:

- model-based success at least `0.95`;
- advantage over a random policy at least `0.20`;
- untrained-planner success exactly `0.0`;
- accuracy on observed transition pairs exactly `1.0`.

Any failed criterion would refute H50-L1.

## Observed result

```json
{
  "world_count": 20,
  "training_transition_count": 540,
  "evaluation_episode_count": 480,
  "model_based_success_rate": 1.0,
  "random_success_rate": 0.18541666666666667,
  "untrained_success_rate": 0.0,
  "known_transition_accuracy": 1.0,
  "success_rate_delta": 0.8145833333333333
}
```

All registered criteria passed. A negative kernel test lowered the advantage
below its threshold and correctly left the goal incomplete.

## What this establishes

The learned table was causally necessary for the tested planner, and the
planner recombined known one-step transitions into new requested paths.

This is not generalization to unseen dynamics. Collection was exhaustive, the
world was deterministic and symbolic, and the evaluator lives in this
repository. Evidence level: `E1_LOCAL_AUTOMATED_EVALUATOR`.
