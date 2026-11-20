# E064 — Label-free reliability development result

**Status: development gate passed, not independently confirmed.**
The experimental protocol was frozen in commit `a4bbf6946165c7898e0c8a25eb9466c66c36791b`.
The estimator and tests were committed in `af11989a0ebbe25fda75dcb9e40e44d1b4a706a2`.
The evaluation runner was committed in `3635dfdd50ca6e352974d5b872f736097388b483`
**before** any E064 registered seeds were evaluated. The source used for
the local measurement matched those three frozen development commits.

## Question and result

In a **stationary, symmetric three-state hidden Markov model**, can an
estimator infer both its environment's state-switch probability and a fixed
sensor's correctness probability using only the observed cue sequence?

Yes, within this narrowly specified local synthetic development experiment.
The model parameters used to generate the worlds were
`h = 0.08` and `q = 0.78`. The observation-only fit returned:

| Parameter | True value (evaluator only) | Fitted value |
| --- | ---: | ---: |
| Mode-switch hazard h | 0.08 | 0.08334435426771059 |
| Sensor correctness q | 0.78 | 0.7828464886092023 |

The estimator pooled cue-equality pairs inside 24 independent 4,096-step
training sequences (seeds 64000–64023); it received no hidden state labels.
The fitted model was then scored after each prefix observation in 24 fresh
256-step synthetic worlds (seeds 64100–64123), for **6,144** observed steps.

## Prefix-causal held-out Brier scores

| Model | Mean Brier |
| --- | ---: |
| Observation-only fitted parameters | 0.21130316953441375 |
| Oracle supplied true parameters | 0.2111951553974064 |
| Frozen misspecified parameters (h=0.25,q=0.55) | 0.2836221882832914 |

Paired world bootstrap (2,000 resamples, fixed seed 64990):

- Misspecified minus fitted: `0.07231901874887767`; nominal 95% percentile interval `[0.06722781835718648, 0.07710576785145483]`.
- Fitted minus oracle: `0.0001080141370073268`; interval `[-0.0002816936076362603, 0.00048383570310706406]`.

The fitted model outperformed the deliberately poor baseline, but there is
**no evidence that it outperforms the true-parameter oracle**, and that
baseline is not a representative benchmark for all alternative models.

## Negative controls, identification and diagnostics

- Sensor emits no information, `q=1/3` (seeds 64200–64223):
  `UNIDENTIFIABLE`, no fitted parameters invented.
- Hidden modes are memoryless, `h=2/3` (seeds 64300–64323):
  `UNIDENTIFIABLE`.
- A global permutation of the cue labels left both fitted parameters unchanged.
- Empirical lag-equality rates: 0.5985347985347985, 0.5653802312326982,
  0.538602492059614 for lags 1, 2 and 3.
- Predicted lag-3 equality from the first two moments:
  0.5363705329348263, absolute residual approximately 0.002232.
- Pair counts: 98,280, 98,256 and 98,232.
- All **10 frozen conjunctive criteria passed**.
- All **12 E064 focused engineering tests** passed in the local run.

Exact raw output:
[EXPERIMENT_064_LABEL_FREE_RELIABILITY_DEVELOPMENT.json](results/EXPERIMENT_064_LABEL_FREE_RELIABILITY_DEVELOPMENT.json).

Reproduction from the repository root on Python 3.11+:

```powershell
$env:PYTHONPATH = "src"
py -m unittest discover -s tests -p test_v50_reliability_identifiability_lab.py -v
py research/e064/e064_evaluate.py --output e064_reproduction.json
```

## Evidence boundary

This is local E1 **development** evidence from a project-owned synthetic
generator, not external validation or a new H50-L capability. The estimator
uses fixed stationary symmetric Markov assumptions and conditionally
independent sensor errors. It was trained once on a substantial pool of
observations; it does not estimate an unknown real sensor online. Both the
generator and evaluator are project-controlled, so structural similarities
may favor the candidate. A device with correlated observation errors,
drifting parameters, multiple sensors or unknown cue coding may defeat the
fit. E062 already found such a risk in a separate developmental setup.

The E063 causal wrapper is exercised with **synthetic caller-supplied action
IDs**, not authenticated Darwin kernel actions. The E039 deterministic tracker,
actual v50 kernel, SQLite state, PR #1–3, and main remain untouched.
No language model, licensed weights, provider, or external effect was used.

**Next step:** a separately frozen E065 model-misspecification audit to test
whether this fitting method becomes overconfident under correlated errors,
and whether lag-3 residuals are sufficient to reject that misspecification.
No threshold may be changed after viewing E065 outcomes.
