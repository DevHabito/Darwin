# Experiment 009 — multiscale memory under concept drift

Date: 2026-07-29\
Hypothesis: H50-L5\
Status: refuted

## Question

Can a fixed-share mixture of memory scales beat the best fixed window across
abrupt changes, recurrence, and gradual drift?

The design was motivated by work on
[concept drift and hidden contexts](https://doi.org/10.1007/BF00116900)
and [tracking the best expert](https://doi.org/10.1023/A:1007424614876).
Darwin implements a small custom forecaster, not either paper's full method.

## Protocol

Each 3,000-step Bernoulli world contained five phases: high probability, an
abrupt switch low, a return high, a gradual high-to-low interpolation, and a
final low regime. Development and final seeds were disjoint. Development chose
the fixed-window baseline and the candidate's learning rate and share rate.

The primary registered threshold required at least `0.002` total Brier
improvement over the selected fixed window. Other criteria covered world win
rate, recurrence, gradual drift, abrupt recovery, stationary memory, archive
retention, and snapshot replay. Every criterion was conjunctive.

## Observed result

```json
{
  "final_world_count": 40,
  "selected_fixed_window": 32,
  "selected_eta": 2.0,
  "selected_share_rate": 0.005,
  "fixed_window_total_brier": 0.15241738027692667,
  "multiscale_total_brier": 0.15068814806223685,
  "total_brier_improvement_vs_fixed": 0.0017292322146898187,
  "world_win_rate_vs_fixed": 1.0,
  "total_brier_improvement_vs_stationary": 0.09970283560860521,
  "archive_retention_rate": 1.0,
  "snapshot_round_trip_rate": 1.0
}
```

## Decision

H50-L5 was refuted. The candidate won every final world and improved on
stationary memory, but its mean gain over the fixed window was `0.0017292`,
below the pre-registered `0.002`. The threshold was not lowered after the run.

The result is local E1 evidence about one synthetic univariate schedule. It
does not show general concept-drift adaptation.
