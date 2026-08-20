# Experiment 038 — online action-alignment calibration

Status: completed calibration. H50-L17 remains unregistered.

Experiment 037 showed that a replay-checked latent tracker can update Darwin's
next action after an observed alignment change while the learned transition
model remains frozen. The result covered `32` development worlds and separated
the candidate from frozen, cumulative, and evidence-shifted controls.

This experiment asks whether the exact result repeats on a larger, disjoint
family under a frozen conjunctive decision. It can authorize a later
confirmatory pre-registration. It cannot register H50-L17.

## Frozen candidate

The candidate is unchanged from Experiment 037:

- an H50-L10 order-four predictive-history model learned from `486`
  exploration interactions per world;
- a transition model frozen before all target tasks;
- a separate three-hypothesis action-alignment tracker;
- tracker updates only after the chosen action produces an observation;
- the most recent uniquely compatible rotation controls the next plan;
- an external start history and goal history for every task;
- replanning before every action and at most `6` target actions;
- one kernel dispatch and one correlated observation for each environment
  action;
- exact causal replay of the tracker at every segment boundary.

The environment applies a hidden rotation to the requested action. Rotation
`r` maps action index `i` to `(i + r) mod 3`. The tracker receives only the cue
caused by the action that was actually requested. It does not receive the
rotation label.

## Frozen schedule

Each world contains `24` tasks in four consecutive six-task segments:

1. base, rotation `0`;
2. shifted, rotation `1`;
3. recurrent, rotation `0`;
4. novel, rotation `2`.

There are three alignment boundaries. Because observations are deterministic
and the registered action predictions are distinct, the first action after a
boundary supplies enough evidence to identify the new rotation. The candidate
must use that rotation only on its next plan, never retroactively.

## Controls

- **Frozen rotation:** always uses rotation `0`.
- **Cumulative evidence:** retains unbounded counts across modes and chooses
  the largest total rather than the latest compatible rotation.
- **Shifted evidence:** gives the candidate the observation from the following
  action instead of the chosen action.
- **Seeded random:** requests uniformly sampled actions from a fixed stream.
- **Oracle:** knows the active rotation before acting.
- **Pure candidate twin:** runs the same tracker and planner without the
  integrated SQLite kernel and must match the integrated candidate exactly.

The shifted-evidence control tests the causal link from chosen action to
observation to alignment to the next action. The cumulative control tests
whether merely retaining evidence, without an appropriate change policy, is
enough for this schedule.

## Fresh inputs

- implementation-only seeds: `42900–42903`;
- calibration seeds: `43000–43063`;
- bootstrap seed: `43700`;
- bootstrap replicates: `5,000`;
- `64` worlds and `1,536` target tasks.

The implementation-only and calibration families are disjoint from the
engineering and development inputs of Experiment 037. Implementation-only
seeds may be rerun while correcting evaluator defects and are permanently
ineligible as calibration or confirmation evidence. Calibration seeds will be
executed once after this protocol and its evaluator are committed.

If execution stops after a calibration seed begins, if any calibration seed is
rerun, or if the evaluator, thresholds, candidate, controls, or budgets change,
the calibration is invalid and requires a new pre-registered seed family.

## World-bootstrap metrics

The evaluator resamples complete worlds and reports 95% percentile intervals
for:

- candidate success;
- candidate minus frozen, cumulative, shifted-evidence, random, and oracle
  success;
- recurrent candidate minus recurrent frozen success;
- boundary adaptation delay;
- candidate action-count overhead over the oracle.

Worlds, not tasks, are the resampling unit because the `24` tasks in one world
share a learned model and tracker history.

## Frozen 20-criterion conjunction

All criteria must pass:

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
15. boundary adaptation delay is exactly one observation, including its
    interval;
16. candidate action overhead is exactly `0.125` action per task, including
    its interval;
17. every registered causal-integrity rate equals `1.0`;
18. world count equals `64`;
19. task count equals `1,536`;
20. segment order, hidden rotations, six tasks per segment, `486` exploration
    interactions, and the six-action target budget remain exact.

The integrity conjunction covers integrated/pure-candidate parity, alignment
identification, post-observation updating, tracker snapshot replay, linear
kernel lineage, action-observation correlation, absence of premature success,
archive retention, and a frozen transition prior.

Any miss yields `calibration_failed`. A complete pass yields only
`eligible_for_confirmatory_preregistration`.

## Threshold rationale

Perfect and exact thresholds are appropriate for the registered candidate,
controls, and causal checks because the environment and observation mapping are
deterministic. A tolerance would hide an implementation or causal-ordering
failure.

Experiment 037 observed candidate-minus-random success of `0.964844`. The
calibration lower bound of `0.90` allows ordinary variation in accidental
random solutions while retaining a large operational separation. This value
was frozen before any calibration result was inspected.

The recurrent gap is required to be zero because the frozen control is already
correct when rotation `0` returns. Recurrence tests retained access to the base
alignment; it is not a place where the candidate should outperform that
control.

## Evidence boundary

This remains an unauthenticated local E1 evaluator over a synthetic symbolic
world. The three possible rotations, segment boundaries, deterministic
observations, tasks, and goals all come from the evaluator. The transition
model does not learn during target control.

Even a complete pass would not establish unknown-mode discovery, ambiguous or
noisy inference, transition-model learning during control, endogenous goals,
natural-language grounding, unrestricted autonomy, consciousness, personhood,
AGI, or a Diana-like artificial mind.

## Result

Calibration seeds `43000–43063` were executed once on 2026-08-03 after this
protocol and its evaluator were committed as `0aca36f`. All 20 frozen criteria
passed.

| Calibration output | Result | World-bootstrap 95% interval |
| --- | ---: | ---: |
| Candidate success | `1.000000` (`1,536/1,536`) | `[1.000000, 1.000000]` |
| Frozen success | `0.500000` (`768/1,536`) | not registered |
| Cumulative success | `0.500000` (`768/1,536`) | not registered |
| Shifted-evidence success | `0.000000` (`0/1,536`) | not registered |
| Seeded-random success | `0.039714` (`61/1,536`) | not registered |
| Oracle success | `1.000000` (`1,536/1,536`) | not registered |
| Candidate minus frozen | `0.500000` | `[0.500000, 0.500000]` |
| Candidate minus cumulative | `0.500000` | `[0.500000, 0.500000]` |
| Candidate minus shifted evidence | `1.000000` | `[1.000000, 1.000000]` |
| Candidate minus random | `0.960286` | `[0.951172, 0.968750]` |
| Candidate minus oracle | `0.000000` | `[0.000000, 0.000000]` |
| Recurrent candidate minus frozen | `0.000000` | `[0.000000, 0.000000]` |
| Boundary adaptation delay | `1.000000` observation | `[1.000000, 1.000000]` |
| Candidate action overhead | `0.125000` action/task | `[0.125000, 0.125000]` |

Candidate success was `1.000000` in every segment. The frozen pattern was
exactly `(1.0, 0.0, 1.0, 0.0)` in every world. Integrated/pure-candidate
parity, alignment identification, post-observation updating, tracker snapshot
replay, kernel lineage, action-observation correlation, absence of premature
success, archive retention, and frozen-prior integrity were all `1.000000`.

The candidate averaged `4.125` actions per task versus the oracle's `4.000`.
Each alignment boundary cost one observation and therefore one additional
action, for three extra actions across each 24-task world.

Decision: **eligible for confirmatory pre-registration**. The result supports
the narrow claim that, in this registered deterministic three-rotation family,
an observation causally updates a separate alignment tracker and changes later
actions without changing the transition prior.

Calibration does not register H50-L17. The rotation set is closed and known,
observations uniquely identify the active rotation, segment boundaries are
evaluator-defined, and all goals are external. No broader learning or mind-like
claim follows from this result.

The machine-readable aggregate is
[`results/EXPERIMENT_038_CALIBRATION_AGGREGATE.json`](results/EXPERIMENT_038_CALIBRATION_AGGREGATE.json).
