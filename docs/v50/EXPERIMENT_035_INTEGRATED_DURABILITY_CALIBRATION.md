# Experiment 035 — integrated-cycle durability calibration

Status: completed calibration. H50-L16 remains unregistered.

Experiment 034 showed that Darwin's kernel, frozen history model, planner, and
cycle checkpoint can complete one deterministic four-action task family with a
fixed restart after two observations. That development result was perfect but
narrow. Repeating the same restart on more seeds would add volume without
testing a new failure boundary.

This calibration keeps the policy and learning budget unchanged while varying
where recovery occurs and reconstructing the evaluator environment from causal
action replay. It can only authorize a future confirmatory pre-registration;
it cannot register H50-L16.

## Frozen candidate

The candidate is the exact Experiment 034 control policy:

- H50-L10 order-four history model;
- `486` exploration interactions per world;
- frozen model during target control;
- external start and goal histories;
- replanning before every requested action;
- at most `6` target actions;
- one kernel dispatch and one correlated observation per environment action;
- explicit `goal.continued` after every unsatisfied action that is followed by
  another action.

No target observation updates the model. The calibration adds recovery
coverage, not a behavioral algorithm change.

## Recovery bundle

At a quiescent boundary, the bundle joins:

- the causal-replay cycle snapshot, including any pending decision;
- kernel goal identity, session, evidence source, version, status, and last
  event identifier;
- the environment seed, external task, action history, and observed cues;
- a canonical SHA-256 checksum.

Recovery closes and reopens the SQLite kernel, restores the cycle by causal
replay, constructs a new environment instance, resets it to the external task,
and replays every prior action. Every returned cue and the final observable
history must match before execution continues.

The checksum detects accidental or unrecomputed modification. It is not a
signature, MAC, or authenticated external trust anchor. Recomputed tampering is
also rejected when it disagrees with kernel binding, cycle replay, or
environment replay, but an attacker controlling every local input is outside
this E1 evaluator.

## Frozen recovery matrix

The `24` tasks in each world are assigned cyclically and evenly to four modes:

1. recover after the first unsatisfied observation;
2. recover after the second unsatisfied observation;
3. recover after the third unsatisfied observation;
4. plan the second action, recover before dispatch, then require the pending
   decision to remain exact.

Each mode receives exactly six tasks per world. Every candidate task must
perform exactly one recovery. Unlike Experiment 034, the original environment
object is discarded at recovery and replaced by the replayed instance.

## Controls

- **Uninterrupted policy twin:** the same frozen cycle and world without a
  restart; its action sequence and outcome must match the candidate exactly.
- **Rotated-policy ablation:** learned action queries are rotated by one.
- **Seeded random policy:** fixed random actions without the learned model.
- **Evaluator oracle:** exact shortest-plan verification for task construction.

The uninterrupted twin compares behavior and does not duplicate the
candidate's kernel log. Kernel correctness is assessed through the candidate's
lineage and correlation invariants.

## Fresh inputs

- engineering seeds: `39900–39903`;
- calibration seeds: `40000–40063`;
- bootstrap seed: `40700`;
- bootstrap replicates: `5,000`;
- `64` worlds, `24` tasks per world, `1,536` target tasks total.

The engineering family may be used to correct implementation errors and is
permanently ineligible as calibration or confirmation evidence. The
calibration family is disjoint from all earlier integrated-cycle families and
had not been executed when this protocol was committed.

World-level percentile bootstrap intervals are computed for candidate success,
candidate minus rotated, candidate minus random, candidate minus
uninterrupted, and exact restart action agreement.

## Frozen conjunctive decision

All 17 criteria must pass:

1. pooled candidate success equals `1.0`;
2. candidate-success interval lower bound equals `1.0`;
3. every recovery mode succeeds on every world;
4. pooled uninterrupted success equals `1.0`;
5. pooled oracle success equals `1.0`;
6. candidate-minus-rotated interval lower bound is at least `0.95`;
7. candidate-minus-random interval lower bound is at least `0.90`;
8. restart action and outcome exactness equals `1.0`;
9. restart-exactness interval lower bound equals `1.0`;
10. candidate-minus-uninterrupted interval is exactly `[0.0, 0.0]`;
11. every integrity rate listed below equals `1.0`;
12. mean candidate action count equals `4.0`;
13. every world assigns exactly six tasks to each recovery mode;
14. world count equals `64`;
15. task count equals `1,536`;
16. exploration budget equals `486` per world;
17. target action budget equals `6`.

The conjunctive integrity criterion covers prediction agreement, frozen model,
recovery execution, cycle-checkpoint exactness, kernel reopen exactness,
environment replay exactness, pending-decision preservation, kernel-cycle
binding, linear kernel lineage, action-observation correlation, absence of
premature success, and restart action agreement.

Any miss yields `calibration_failed`. Passing all criteria yields only
`eligible_for_confirmatory_preregistration`.

## Threshold rationale

Perfect candidate, restart, and integrity thresholds are appropriate because
the registered world and recovery mechanism are deterministic. A tolerance
would hide an implementation failure rather than model statistical noise.

Experiment 034's world-bootstrap lower bounds were `1.0` for the rotated gap
and `0.942708` for the random gap. Calibration freezes lower bounds of `0.95`
and `0.90`, respectively. The random tolerance permits ordinary variation in
accidental four-action successes while still requiring a large operational
separation. No calibration result was inspected when selecting these values.

## Evidence boundary

This remains a local, unauthenticated, deterministic E1 evaluator. Environment
reconstruction is replay from evaluator-known inputs, not recovery of an
independent external process or a distributed transaction. Goals remain
externally supplied and the model remains frozen during control.

Even a complete pass would not establish online adaptation, self-generated
goals, stochastic robustness, natural-language grounding, unrestricted
computer autonomy, consciousness, personhood, AGI, or a Diana-like mind.

## Result

Seeds `40000–40063` were executed once on 2026-08-03 after this protocol and
its evaluator were committed as `51d3e13`. All 17 criteria passed.

| Calibration output | Result | World-bootstrap 95% interval |
| --- | ---: | ---: |
| Restart candidate success | `1.000000` (`1,536/1,536`) | `[1.000000, 1.000000]` |
| Uninterrupted success | `1.000000` (`1,536/1,536`) | not registered |
| Rotated-policy success | `0.000000` (`0/1,536`) | not registered |
| Seeded-random success | `0.028646` (`44/1,536`) | not registered |
| Candidate minus rotated | `1.000000` | `[1.000000, 1.000000]` |
| Candidate minus random | `0.971354` | `[0.962240, 0.979167]` |
| Candidate minus uninterrupted | `0.000000` | `[0.000000, 0.000000]` |
| Restart action exactness | `1.000000` | `[1.000000, 1.000000]` |
| Mean candidate actions | `4.000000` | not registered |

Every recovery mode succeeded on `384/384` assigned tasks. Prediction
agreement, frozen model, recovery execution, cycle replay, kernel reopen,
environment replay, pending-decision preservation, kernel-cycle binding,
linear event lineage, action-observation correlation, absence of premature
success, and restart action agreement were all exactly `1.000000`.

Decision: **eligible for confirmatory pre-registration**. The result supports
the narrow claim that the frozen integrated cycle survives these four local
deterministic recovery boundaries without changing its policy or outcome.

The perfect recovery rates do not establish an authenticated crash-consistent
transaction. The evaluator owns the seed and task and reconstructs the world
by deterministic replay. A malicious party controlling all local artifacts, a
stochastic external environment, or a remote side effect remains outside the
tested boundary. H50-L16 is not registered by calibration.

The machine-readable aggregate is
[`results/EXPERIMENT_035_CALIBRATION_AGGREGATE.json`](results/EXPERIMENT_035_CALIBRATION_AGGREGATE.json).
