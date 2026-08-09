# Experiment 008 — temporal adaptation with an intact archive

Date: 2026-07-28\
Hypothesis: H50-L4\
Status: passed in the local evaluator

## Question

Can a bounded working memory detect one abrupt change, stop relying directly on
stale observations, and still retain a complete replayable archive?

Predictions are evaluated prequentially, following
[Dawid's prequential approach](https://academic.oup.com/jrsssa/article/147/2/278/7106293).
The hand-written detector is a two-window mean comparison; it is not CUSUM
([Page, 1954](https://academic.oup.com/biomet/article-abstract/41/1-2/100/456627))
or ADWIN
([Bifet and Gavaldà](https://www.cs.upc.edu/~gavalda/papers/adwin06.pdf)).

## Protocol

Twenty Bernoulli streams changed once from `p=0.85` to `p=0.15` at observation
1,001. Each world contained 2,000 observations. The detector compared two fixed
windows of 64 results with `false_alarm_delta=1e-6`; working memory was capped
at 512 results.

The adaptive model was compared with stationary memory, a fixed window, and an
oracle. Criteria required reliable detection, no material early alarms, delay
at most 128, Brier improvement over stationary memory, no pre-change damage,
and exact archive and snapshot retention.

## Observed result

| Metric | Observed |
| --- | ---: |
| Detection rate | `1.0` |
| False-alarm world rate | `0.0` |
| Mean / maximum delay | `45.05` / `57` |
| Stationary total Brier | `0.2504914805` |
| Adaptive total Brier | `0.1388606564` |
| Fixed-window total Brier | `0.1344193892` |
| Post-change gain vs. stationary | `0.2232548404` |
| Total gain vs. stationary | `0.1116308242` |
| Archive / snapshot rate | `1.0` / `1.0` |

All registered H50-L4 criteria passed. The fixed-window baseline was still
better than the adaptive detector after the change and overall.

## What this establishes

The programmed detector adapted to one large, known-form change while keeping a
complete logical archive. It was not the best tested method and did not cover
gradual, recurring, adversarial, or multidimensional drift. Snapshots were
structurally replayed but not cryptographically authenticated. Evidence level:
`E1_LOCAL_AUTOMATED_EVALUATOR`.
