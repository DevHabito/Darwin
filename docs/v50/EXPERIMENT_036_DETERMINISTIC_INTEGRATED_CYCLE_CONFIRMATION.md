# Experiment 036 — H50-L16 deterministic integrated-cycle confirmation

Status: passed locally. H50-L16 is registered at E1 for the narrow claim below.

Experiment 034 established development sensitivity and fixed-restart behavior.
Experiment 035 then passed all 17 calibration criteria across four balanced
recovery boundaries, including reconstruction of a new deterministic
environment instance by causal action replay. This protocol asks whether the
exact frozen result repeats once on a fully fresh final family.

## Registered claim

The short claim is **deterministic externally-goaled integrated planning with
local replay-based recovery**.

H50-L16 requires Darwin to preserve one externally supplied goal while its
frozen learned model replans before each action, its kernel records every
dispatch and observation, and its agent, kernel, and deterministic environment
state are reconstructed at one of four registered recovery boundaries without
changing the remaining action sequence or outcome.

The claim is explicitly limited to:

- a synthetic symbolic order-four world;
- a model learned before target control and frozen during every target task;
- evaluator-supplied start and goal histories;
- local SQLite persistence;
- evaluator-known environment seed and task;
- deterministic environment reconstruction by replay;
- E1 evidence from this repository's unauthenticated local evaluator.

## Frozen method

No candidate, control, budget, recovery mode, metric, or threshold changes from
Experiment 035:

- `486` exploration interactions per world;
- `24` four-action target tasks per world;
- at most `6` target actions;
- replanning before every action;
- one dispatch and one correlated observation for each environment action;
- explicit continuation after unsatisfied evidence;
- six tasks per world for each of four restart modes;
- uninterrupted, rotated, random, and oracle controls;
- causal cycle replay, SQLite reopen, and deterministic environment replay.

The four modes remain recovery after observations one, two, and three, plus
recovery after planning but before dispatching the second action.

## Final inputs

- implementation-only confirmation seeds: `40900–40903`;
- final seeds: `41000–41063`;
- `64` final worlds and `1,536` target tasks;
- bootstrap seed: `41700`;
- bootstrap replicates: `10,000`.

All earlier engineering, development, calibration, audit, and final seed
families are excluded. Final seeds will be executed once. An operational
failure after a final seed begins, a rerun, or any evaluator or threshold
change blocks promotion and requires a new pre-registered seed family.

## Frozen 17-criterion conjunction

The exact Experiment 035 conjunction is retained:

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
11. all registered recovery and causal-integrity rates equal `1.0`;
12. mean candidate action count equals `4.0`;
13. every world assigns exactly six tasks to each recovery mode;
14. world count equals `64`;
15. task count equals `1,536`;
16. exploration budget equals `486` per world;
17. target action budget equals `6`.

Any miss refutes H50-L16. A favorable subset, average, or secondary metric
cannot compensate for a failure.

## Causal registration

After evaluation, the local kernel receives a single Boolean representing the
complete frozen conjunction. The observation is accepted only from the exact
registered local source. Kernel success records causal acceptance of that
local evaluator result; it does not authenticate the evaluator or raise the
evidence above E1.

If and only if all criteria pass in the single final execution, H50-L16 will be
registered locally for the claim above. Otherwise the hypothesis is refuted.

## Interpretation ceiling

Even a complete pass would not show online learning during control, endogenous
goals, recovery of an independent stochastic service, authenticated distributed
transactions, natural-language grounding, unrestricted computer autonomy,
consciousness, emotions, personhood, AGI, or a Diana-like artificial mind.

## Result

Final seeds `41000–41063` were executed once on 2026-08-03 after the protocol
was committed as `ad304f6`. All 17 frozen criteria passed, and the local causal
kernel accepted the complete conjunction and marked its goal `succeeded`.

| Final output | Result | World-bootstrap 95% interval |
| --- | ---: | ---: |
| Restart candidate success | `1.000000` (`1,536/1,536`) | `[1.000000, 1.000000]` |
| Uninterrupted success | `1.000000` (`1,536/1,536`) | not registered |
| Rotated-policy success | `0.000000` (`0/1,536`) | not registered |
| Seeded-random success | `0.039714` (`61/1,536`) | not registered |
| Candidate minus rotated | `1.000000` | `[1.000000, 1.000000]` |
| Candidate minus random | `0.960286` | `[0.951172, 0.968750]` |
| Candidate minus uninterrupted | `0.000000` | `[0.000000, 0.000000]` |
| Restart action exactness | `1.000000` | `[1.000000, 1.000000]` |
| Mean candidate actions | `4.000000` | not registered |

Each of the four recovery modes succeeded on `384/384` assigned tasks. All 12
reported recovery and causal-integrity rates were exactly `1.000000`.

Decision: **H50-L16 passed locally** for deterministic externally-goaled
integrated planning with local replay-based recovery.

This is the first registered Darwin result in which a persisted goal, learned
model, multistep planner, per-action evidence loop, agent checkpoint, kernel
reopen, and reconstructed environment operate in one continuing task. The
model remains frozen during target control, and both goal and world recipe are
supplied by the evaluator. The result does not support a broader claim.

The machine-readable record is
[`results/EXPERIMENT_036_FINAL_AGGREGATE.json`](results/EXPERIMENT_036_FINAL_AGGREGATE.json).
