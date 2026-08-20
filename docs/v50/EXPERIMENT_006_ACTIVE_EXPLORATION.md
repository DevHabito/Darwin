# Experiment 006 — active exploration under a fixed budget

Date: 2026-07-27\
Hypothesis: H50-L2\
Status: passed in the local evaluator

## Question

Can an exploration policy choose more informative actions than uniform random
exploration when both receive the same number of interactions?

## Protocol

The learner did not receive the list of world states or the transition table.
For each of twenty deterministic graph worlds, an active frontier policy and a
uniform random policy each received thirty actions. Their learned models were
then evaluated on the same held-out planning tasks.

Registered criteria:

- active state-action coverage at least `0.95`;
- coverage advantage over random at least `0.20`;
- active held-out task success at least `0.95`;
- task-success advantage over random exploration at least `0.20`.

## Observed result

```json
{
  "world_count": 20,
  "budget_per_world": 30,
  "active_coverage": 0.9962962962962963,
  "random_coverage": 0.6648148148148147,
  "coverage_delta": 0.3314814814814816,
  "active_task_success_rate": 0.9979166666666667,
  "random_exploration_task_success_rate": 0.70625,
  "task_success_delta": 0.29166666666666663
}
```

All criteria passed. A deliberately insufficient success delta did not produce
a kernel success event.

## What this establishes

The hand-written frontier rule used its interaction budget more effectively
than uniform random exploration in these graph worlds. The experiment did not
learn the exploration strategy itself, handle stochastic dynamics, or discover
useful representations. Evidence level: `E1_LOCAL_AUTOMATED_EVALUATOR`.
