# Experiment 034 — integrated cognitive-cycle development

Status: pre-registered development protocol. No development seed has been run.

This experiment asks whether Darwin's existing kernel, learned history model,
planner, and checkpoint logic can operate as one persistent action-observation
cycle. It is an integration test in a deterministic synthetic world, not a
claim of autonomy, general intelligence, consciousness, or a Diana-like mind.

## Question

Given an externally supplied goal and a model learned during a separate
exploration phase, can Darwin repeatedly plan one action, record exactly one
correlated observation, continue after unsatisfied evidence, and reach the
goal without changing its model? After two actions, can the agent state and
kernel be restored without changing the remaining policy or outcome?

## Frozen implementation

The candidate is implemented by:

- `IntegratedPlanningCycle`, which binds one kernel goal to the frozen H50-L10
  model and replans from the observable history before every action;
- `DarwinKernelV50`, which records goal, dispatch, observation, condition, and
  explicit continuation events in SQLite;
- a replay-checked cycle snapshot containing the model, bindings, observable
  history, planner configuration, action-observation trace, and pending action;
- the deterministic order-four predictive world already used by H50-L10.

The learned model is frozen for every target episode. No target observation is
used for learning. A model mutation causes the cycle to fail closed.

## Data partition

- Engineering seeds: `38900–38903`.
- Development seeds: `39000–39031`.
- Bootstrap seed: `39700`.
- Bootstrap replicates: `2,000`.

These sets were fixed before running a development seed. The engineering
family may be used to find implementation errors and is permanently ineligible
as development or confirmatory evidence.

Each development world receives `486` exploration interactions, the H50-L10
budget selected before that line's confirmation. The resulting frozen model is
evaluated on all `24` four-step tasks generated for that world. A target
episode receives at most `6` actions.

## Candidate protocol

For each task:

1. Create and start one kernel goal whose exact success condition is
   `goal_reached == 1`.
2. Construct the cycle from the frozen exploration-model snapshot, external
   start history, and external goal history.
3. Replan from the current observable history.
4. Dispatch exactly one action through the kernel.
5. Apply that action once to the evaluator-owned world.
6. Give the returned cue to the cycle and record exactly one correlated kernel
   observation.
7. If the condition is unsatisfied, append `goal.continued` before planning the
   next action. If the action budget is exhausted, leave the goal waiting.
8. If the condition is satisfied, require one and only one `goal.succeeded`
   event and stop.

After the second unsatisfied target action, serialize the cycle, close the
kernel, reopen its SQLite database, restore the cycle by causal replay, and
continue. The evaluator world remains in memory.

## Frozen comparisons

- **Restart candidate:** the full protocol above.
- **Uninterrupted twin:** the same model, task, and policy without the forced
  restart.
- **Rotated-policy ablation:** the learned planner's action mapping is rotated
  by one while all other planning inputs remain fixed.
- **Seeded random policy:** a deterministic random action stream with no learned
  model.
- **Evaluator oracle:** the world's exact shortest-plan solver, used only as a
  ceiling and task-construction check.

The rotated and random controls test whether the benchmark rewards the learned
action semantics rather than merely accepting any four actions. The
uninterrupted twin tests restart invariance, not behavioral superiority.

## Frozen outputs

The development record reports pooled values across 32 worlds and equal-sized
task sets:

- candidate, uninterrupted, rotated, random, and oracle success rates;
- candidate success minus each non-oracle comparison;
- exact restart-versus-uninterrupted action and outcome agreement;
- prediction-match and frozen-model rates;
- checkpoint replay and kernel-reopen rates;
- complete linear kernel lineage rate;
- action-observation correlation rate;
- no-premature-success rate;
- mean candidate action count.

World-level percentile bootstrap intervals are reported for candidate success,
candidate-minus-rotated, candidate-minus-random,
candidate-minus-uninterrupted, and restart action exactness.

## Interpretation fixed before the run

This is a development experiment with no numerical pass threshold. It cannot
register H50-L16 or any other capability. The result will be used only to
answer three development questions:

1. Is the benchmark sensitive to the rotated and random controls?
2. Does the forced restart preserve the uninterrupted policy and outcome?
3. Do all causal-integrity checks remain exact?

A favorable result may justify a separate calibration family. Any future
eligibility thresholds must be selected on that new family and frozen before a
confirmatory run. A weak or contradictory result will be recorded as such;
this protocol will not be repaired after seeing development outcomes.

## Evidence boundary

The evaluator and evidence source are local and unauthenticated, so the maximum
evidence level is E1. The restart covers the kernel and agent checkpoint but
not the environment process. The world is deterministic, symbolic, fully
observable through fixed-length histories, and supplied with an external goal.

Therefore, even a clean result would not establish self-generated goals,
online lifelong learning, natural-language grounding, open-world robustness,
general computer autonomy, subjective experience, personhood, AGI, or a
Diana-like artificial mind.
