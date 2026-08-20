# Experiment 010 — Bayesian run-length tracking

Date: 2026-07-29\
Hypothesis: H50-L6\
Status: passed in the local evaluator

## Question

Can a pruned Beta-Bernoulli run-length posterior improve on the best fixed
window when regime lengths and probabilities vary between worlds?

The implementation is a bounded custom variant informed by
[Bayesian Online Changepoint Detection](https://arxiv.org/abs/0710.3742)
and [online inference for multiple changepoints](https://eprints.lancs.ac.uk/id/eprint/745/).
It is not an exact reproduction of either method.

## Protocol

Development seeds `9300–9319` selected the fixed window, expected duration, and
maximum posterior hypothesis count. Final seeds `9400–9459` contained sixty
unique schedules. Forecasts preceded outcomes, learned state was not shared
between worlds, and final seeds were not used for selection.

Registered criteria required at least `0.002` total Brier improvement over the
fixed window, wins in at least `0.65` of worlds, no average loss in abrupt or
recurrent regions, gradual degradation at most `0.003`, at least `0.05`
improvement over stationary memory, and exact archive and snapshot rates.

## Observed result

| Metric | Observed | Threshold | Result |
| --- | ---: | ---: | --- |
| Total gain vs. fixed window | `0.0034053` | `>= 0.002` | Passed |
| World win rate | `1.0` | `>= 0.65` | Passed |
| Abrupt-region gain | `0.0206452` | `>= 0.0` | Passed |
| Recurrence gain | `0.0074865` | `>= 0.0` | Passed |
| Gradual degradation | `0.0019344` | `<= 0.003` | Passed |
| Gain vs. stationary | `0.0907653` | `>= 0.05` | Passed |
| Archive / snapshot | `1.0` / `1.0` | `1.0` | Passed |

The selected expected duration was 400 and the posterior was capped at 64
hypotheses; the mean active count was `63.349`, close to the cap.

## Decision

H50-L6 passed locally. The gain was small and the pruning cap was active, so the
result does not establish a generally calibrated changepoint posterior or
unbounded temporal reasoning. Evidence level: `E1_LOCAL_AUTOMATED_EVALUATOR`.
