# Experiment 039 — H50-L17 online action-alignment confirmation

Status: pre-registered confirmation protocol. No final seed has been run.

Experiment 037 established development sensitivity and causal controls.
Experiment 038 then passed all 20 frozen calibration criteria across `64`
disjoint worlds. This protocol asks whether the exact result repeats once on a
fully fresh final family.

## Registered claim

The short claim is **deterministic online action-alignment inference with a
frozen transition prior**.

H50-L17 requires Darwin's integrated cycle to use the observation caused by a
chosen action to identify one of three known action rotations, update a
separate latent tracker only after that observation, and change later plans
while preserving a transition model learned before target control.

The claim is limited to:

- a synthetic symbolic order-four world;
- a known closed rotation set `{0, 1, 2}`;
- deterministic observations that uniquely distinguish the rotations;
- an evaluator-defined `0→1→0→2` segment schedule;
- evaluator-supplied start histories, goal histories, and boundaries;
- a transition prior frozen throughout all target tasks;
- local SQLite kernel records and exact tracker replay;
- unauthenticated E1 evidence produced by this repository's evaluator.

## Frozen method

No candidate, control, schedule, budget, metric, or threshold changes from
Experiment 038:

- `486` exploration interactions per world;
- `24` target tasks per world;
- four six-task segments: base, shifted, recurrent, and novel;
- hidden rotations `(0, 1, 0, 2)`;
- at most `6` actions per target task;
- replanning before every action;
- alignment updates only after the chosen action's observation;
- tracker replay at each segment boundary;
- frozen, cumulative, shifted-evidence, seeded-random, oracle, and pure
  candidate controls;
- one kernel dispatch and one correlated observation per environment action.

## Final inputs

- implementation-only confirmation seeds: `43900–43903`;
- final seeds: `44000–44063`;
- `64` final worlds and `1,536` target tasks;
- bootstrap seed: `44700`;
- bootstrap replicates: `10,000`.

All earlier engineering, development, calibration, and confirmation families
are excluded. Final seeds will be executed once after this protocol and its
evaluator are committed. An operational failure after a final seed begins, a
rerun, or any evaluator, threshold, candidate, control, schedule, or budget
change blocks registration and requires a new pre-registered final family.

## Frozen 20-criterion conjunction

The exact Experiment 038 conjunction is retained:

1. pooled candidate success equals `1.0`;
2. the candidate-success interval lower bound equals `1.0`;
3. every candidate segment in every world has success `1.0`;
4. pooled oracle success equals `1.0`;
5. pooled frozen success equals `0.5`;
6. every world's frozen segment pattern is exactly `(1.0, 0.0, 1.0, 0.0)`;
7. pooled cumulative success equals `0.5`;
8. pooled shifted-evidence success equals `0.0`;
9. the candidate-minus-frozen interval is exactly `[0.5, 0.5]`;
10. the candidate-minus-cumulative interval is exactly `[0.5, 0.5]`;
11. the candidate-minus-shifted-evidence interval is exactly `[1.0, 1.0]`;
12. the candidate-minus-random interval lower bound is at least `0.90`;
13. the candidate-minus-oracle interval is exactly `[0.0, 0.0]`;
14. the recurrent candidate-minus-frozen interval is exactly `[0.0, 0.0]`;
15. boundary adaptation delay and its interval equal one observation;
16. candidate action overhead and its interval equal `0.125` action per task;
17. all nine registered causal-integrity rates equal `1.0`;
18. world count equals `64`;
19. task count equals `1,536`;
20. segment order, rotations, tasks per segment, exploration budget, and target
    action budget remain exact.

Any miss refutes H50-L17. A favorable subset, average, or secondary metric
cannot compensate for a failed criterion.

## Causal registration

After evaluation, the local kernel receives one Boolean representing the full
frozen conjunction. It accepts the observation only from the exact registered
local source. If and only if all 20 criteria pass in the single final execution,
the kernel marks its confirmation goal `succeeded` and H50-L17 is registered
locally for the narrow claim above. Otherwise the hypothesis is refuted.

Kernel acceptance records causal handling of the local result. It does not
authenticate the evaluator, provide independent replication, or raise the
evidence above E1.

## Interpretation ceiling

Even a complete pass would not establish unknown-mode discovery, ambiguous or
noisy inference, online learning of the transition model, self-generated goals,
natural-language grounding, unrestricted computer autonomy, consciousness,
emotions, personhood, AGI, or a Diana-like artificial mind.
