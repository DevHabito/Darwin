# Research note — minimum integrated cognitive cycle

Status: engineering contract. No integrated capability is registered.

## Motivation

Darwin v50 has separately tested goal evidence, learned transition models,
bounded memory, planning, persistence, and scoped effects. Those results do not
show that the parts form one continuing agent. Calling the repository an
integrated cognitive architecture before testing their composition would be a
category error.

The next research line asks a smaller question: can one externally supplied
goal remain causally grounded while a learned model repeatedly plans, requests
one action, receives one observation, updates its observable state, survives an
agent restart, and continues until the exact condition is observed?

This note defines the minimum contract. It does not claim self-generated goals,
online lifelong learning, open-world autonomy, or consciousness.

## Interface audit

| Component | Existing property | Integration boundary |
| --- | --- | --- |
| Causal kernel | Persistent goals, action correlation, evidence evaluation | Before this note it had no explicit transition from accepted unsatisfied evidence to a new action |
| SQLite event store | Immutable event lineage and optimistic goal versions | Persists kernel state, not a learned-model checkpoint |
| H50-L10 history model | Chosen-action archive and replay-checked snapshot | A model cannot mix traces; target evaluation therefore uses a frozen exploration model |
| H50-L10 planner | Multistep search over learned modal transitions | Requires externally supplied start and goal histories |
| Predictive world | One cue after each chosen action | Environment state has no restart snapshot and remains evaluator-owned |
| Workspace executor | Scoped, consent-bound real file effect | Excluded from the first synthetic integration benchmark |
| Temporal and transfer labs | Independently tested state estimators | Their schemas are not yet compatible with the predictive history model |

The audit found one concrete kernel gap. After an accepted observation failed a
goal condition, the goal remained in `waiting_observation`. The kernel permitted
another observation for the same action, but could not explicitly close that
action and dispatch a new one.

The new `continue_goal` operation is allowed only when the latest event is a
correlated `goal.condition_unsatisfied` decision. It records
`goal.continued`, clears the completed action correlation, and returns the goal
to `active`. Rejected evidence, an unobserved action, and terminal goals cannot
continue. The event store enforces the same transition if a caller bypasses the
kernel.

This is an engineering prerequisite, not behavioral evidence.

## Minimum cycle contract

The first integrated cycle must satisfy all of the following:

1. The goal is supplied by the evaluator and recorded before action.
2. The policy receives only the observable history, learned-model snapshot,
   external goal, and its own prior action-observation history.
3. Planning occurs before each action request.
4. Every environment action has exactly one kernel dispatch and one accepted
   correlated observation.
5. An unsatisfied observation cannot mark success and requires an explicit
   continuation event before another action.
6. A satisfied observation marks success exactly once and must correspond to
   the environment's terminal reward.
7. A checkpoint must restore learned model, observable state, pending state,
   action history, and planner configuration exactly.
8. Closing and reopening the kernel plus restoring the checkpoint must preserve
   future action choice and final outcome relative to an uninterrupted twin.
9. The learned model remains frozen during target evaluation; any later online
   learning claim requires a different experiment.
10. Snapshot tampering, action mismatch, observation replay, or causal-lineage
    mismatch fails closed.

## First benchmark boundary

The first benchmark should reuse the deterministic order-four world from
H50-L10 because its observability and planning limits are already known. It
should use fresh worlds and four-step held-out tasks, with the frozen `486`
interaction exploration budget selected before H50-L10 confirmation.

Required comparisons are:

- an integrated learned-model cycle with a forced agent restart after two
  target actions;
- an uninterrupted twin using the same model and task;
- an action-rotated learned-model ablation;
- a seeded random policy;
- the evaluator oracle as a ceiling.

The restart candidate and uninterrupted twin must choose exactly the same
actions and produce the same outcome. Behavioral success alone is insufficient:
kernel lineage, observation correlation, checkpoint replay, frozen-model, and
no-premature-success checks must all be reported.

The first experiment is benchmark and development infrastructure. It cannot
register H50-L16. Numerical eligibility criteria, if justified, must be frozen
on a separate calibration family before a final integrated-cycle claim.

## Persistence boundary

The first benchmark restarts the agent state, not the synthetic environment.
The kernel is closed and reopened from SQLite, while the cycle is restored from
its replay-checked checkpoint. The evaluator-owned world continues in memory.

This does not demonstrate full process recovery, distributed transactions, or
environment recovery after a crash. A later durability experiment would need
an environment adapter with its own authenticated checkpoint and a committed
cross-component checkpoint protocol.

## Evidence ceiling

Even a favorable integrated result would show only that several existing
mechanisms compose in one deterministic synthetic loop. It would not establish:

- self-generated or intrinsically meaningful goals;
- natural-language understanding independent of an LLM;
- online learning during control;
- learned representation alignment;
- stochastic or open-world planning;
- unrestricted computer use;
- consciousness, emotions, personhood, AGI, or a Diana-like mind.

