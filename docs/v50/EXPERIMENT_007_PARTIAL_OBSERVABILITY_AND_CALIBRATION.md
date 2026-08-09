# Experiment 007 — partial observability and calibrated action

Date: 2026-07-27\
Hypothesis: H50-L3\
Status: passed in the local evaluator

## Question

Can Darwin produce calibrated forecasts before observing a stochastic outcome,
then use uncertainty to decide when a costly inspection is worthwhile?

The experiment follows the distinction between belief and hidden state used in
[partially observable stochastic domains](https://cs.brown.edu/research/pubs/techreports/reports/CS-96-08.html).
Forecast quality uses the proper scoring rule introduced by
[Brier](https://journals.ametsoc.org/view/journals/mwre/78/1/1520-0493_1950_078_0001_vofeit_2_0_co_2.xml).

## Protocol

A hidden binary state produced ambiguous observations and stochastic outcomes.
A Beta-Bernoulli model was trained on 3,000 experiences. Calibration used 6,000
separate prequential records. Policy evaluation used 10,000 further episodes.
Training, calibration, and policy seeds were disjoint.

The selective policy could pay an inspection cost before choosing its final
action. It was compared with policies that never inspect and always inspect.

Registered criteria:

- Brier score at most `0.18`;
- improvement over `p=0.5` at least `0.07`;
- ten-bin expected calibration error at most `0.04`;
- inspection rate between `0.35` and `0.65`;
- utility advantage over never inspect at least `0.05`;
- utility advantage over always inspect at least `0.02`.

## Observed result

| Metric | Observed |
| --- | ---: |
| Brier score | `0.1468837134` |
| Improvement over `p=0.5` | `0.1031162866` |
| Expected calibration error | `0.0159365079` |
| Selective inspection rate | `0.505` |
| Selective utility | `0.8225` |
| Never-inspect utility | `0.7408` |
| Always-inspect utility | `0.7835` |
| Utility gain vs. never | `0.0817` |
| Utility gain vs. always | `0.0390` |

All criteria passed.

## What this establishes

The model produced useful probabilities and the registered policy used them to
trade information against cost. Hidden state, observation channels, costs, and
policy thresholds were all designed by hand. The world remained binary and
synthetic. Evidence level: `E1_LOCAL_AUTOMATED_EVALUATOR`.
