# Experiment 037 — online action-alignment development

Status: pre-registered development protocol. No development seed has been run.

This experiment tests whether a causal online alignment update inside Darwin's
integrated cycle changes later actions and preserves performance across an
abrupt, recurrent, and newly encountered target mode. It has no capability
threshold and cannot register H50-L17.

## Frozen candidate

- the exact H50-L10 transition model learned from `486` exploration actions;
- no changes to that model during target control;
- a separate replay-checked `OnlineActionAlignmentTracker`;
- initial rotation estimate `0`;
- latest compatible chosen-action observation replaces the current estimate;
- replanning before every action with the current estimate;
- `24` external goals, each with at most `6` actions;
- one kernel dispatch, observation, and condition decision per action;
- explicit continuation after unsatisfied evidence;
- tracker state persists across goals and is checkpointed after each segment.

The evaluator never supplies a boundary or current rotation to the candidate.
The tracker updates only after observing the consequence of its dispatched
action.

## Frozen schedule

| Segment | Tasks | Hidden rotation |
| --- | ---: | ---: |
| Base | `1–6` | `0` |
| Shifted | `7–12` | `1` |
| Recurrent | `13–18` | `0` |
| Novel | `19–24` | `2` |

The words “hidden” and “novel” are relative to target control. The evaluator
knows the schedule, and all three rotations are registered hypotheses.

## Frozen controls

- frozen rotation `0`;
- cumulative mode counts with no change reset;
- latest observation with its inferred rotation shifted by `+1`;
- seeded random actions;
- evaluator-known rotation oracle;
- non-kernel candidate twin for exact integration parity.

All tracker controls receive the same chosen-action cues. No policy receives
counterfactual transitions.

## Data partition

- engineering seeds: `41900–41903`;
- development seeds: `42000–42031`;
- bootstrap seed: `42700`;
- bootstrap replicates: `2,000`;
- `32` development worlds and `768` target tasks.

The engineering family may be used to fix implementation errors and is
permanently ineligible as development, calibration, or final evidence. The
development family was not executed when this protocol was committed.

## Frozen outputs

- overall success for candidate, frozen, cumulative, shifted-evidence, random,
  and oracle policies;
- candidate and frozen success in each schedule segment;
- candidate and oracle mean action counts;
- mean number of post-boundary observations before the candidate estimate
  matches the environment;
- exact action and outcome parity between integrated and pure candidates;
- alignment-identification and post-observation alignment rates;
- tracker snapshot replay, kernel lineage, action-observation correlation,
  no-premature-success, archive-retention, and frozen-prior rates.

World-bootstrap intervals are reported for candidate success, candidate minus
frozen, candidate minus cumulative, candidate minus shifted evidence,
candidate minus oracle, recurrent candidate minus frozen, and boundary
adaptation delay.

## Interpretation fixed before the run

There is no numerical pass rule. The run asks whether:

1. the candidate adapts after each hidden change using only post-action data;
2. shifted and novel segments separate it from frozen and cumulative controls;
3. the recurrent segment retains successful access to the earlier mode;
4. shifted evidence breaks behavior, establishing a causal observation path;
5. integration does not alter the pure policy;
6. every causal and persistence invariant remains exact;
7. adaptation cost is visible in action count rather than hidden.

A favorable result may justify a new calibration family with frozen thresholds.
It cannot itself promote H50-L17.

## Evidence boundary

The three hypotheses are known, observations are deterministic and uniquely
identify a rotation, the transition prior is frozen, tasks and goals are
external, and the evaluator is unauthenticated E1. The result cannot be
described as general online world-model learning or open-ended adaptation.
