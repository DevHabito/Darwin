# E065 — Correlated sensor failure audit: observed counterexample

**Status: adversarial counterexample observed in the registered synthetic development run.**
This is a negative result for the general applicability of the E064 iid-sensor
estimator, **not** a failure of E064's previously delimited iid experiment.

E065 was preregistered in commit `eb6c4d85c5b0039c3b29662c36fc835a45f7d80a`.
Its generator, runner, and five focused engineering tests were committed
unchanged in `23ff54deed3340f998fc6f0eba8a7f57c852a965`
before the registered E065 seeds were evaluated.

## Construction

The latent mode R switches symmetrically at h=0.08. A sensor-error offset
persists at each step with probability rho=0.60; otherwise the offset is
redrawn with probabilities 0.78, 0.11, 0.11. The cue is (R+offset) mod 3.
The marginal sensor correctness is therefore exactly 0.78, but errors
are conditionally correlated over time and violate E064's iid-emission model.

The estimator received only the cue sequences from 24 synthetic 4,096-step
training worlds (seeds 65000–65023). No true mode or offset was supplied.
Evaluation used 24 disjoint 256-step worlds (seeds 65100–65123). The
independent-error control used seeds 65200–65223.

## Frozen adversarial observation

| Measurement | Expected true value or criterion | Observed |
| --- | ---: | ---: |
| Sensor marginal correctness | 0.78 | E064 estimate **0.9797515986647012** |
| Mode-switch hazard | 0.08 | E064 estimate **0.1798950629929997** |
| Estimated q threshold | >= 0.93 | Passed |
| Lag-3 equality gap | <= 0.018 | **0.0146347179159494** — passed |
| Correlated fit status | FITTED | FITTED |
| Independent-error control q | 0.78 | 0.7783514348912774 |
| Independent-error control h | 0.08 | 0.07339604409848917 |

**All three preregistered counterexample conditions occurred.** The candidate
became substantially overconfident while the lag-3 diagnostic remained below
E064's previously frozen threshold. No threshold or candidate code was
adjusted to produce this outcome.

## Held-out prefix-causal multiclass Brier

| Scorer | Mean Brier (lower is better) |
| --- | ---: |
| E063 using correlated-data fitted E064 parameters | **0.41265518194806394** |
| E063 using true h and marginal q but incorrectly assuming iid errors | 0.35675453364251336 |
| Last observed cue with known marginal q=0.78 | 0.3665973958333321 |

The fitted model was worse than both imperfect controls. The
'true-parameter' control is **not a true correlated-noise oracle**; it also
uses a misspecified observation model. All comparisons are local, descriptive
development findings, not evidence for a general sensor architecture.

The preregistered analytic construction predicts q approximately 0.979295,
h approximately 0.179537, and lag-3 residual approximately 0.013841
at population scale. The finite-sample result is consistent with that
construction but does not prove universal failure under other error models.

The raw JSON result is
[EXPERIMENT_065_CORRELATED_SENSOR_AUDIT.json](results/EXPERIMENT_065_CORRELATED_SENSOR_AUDIT.json).
Reproduce with Python 3.11+ from the repo root:

```powershell
$env:PYTHONPATH = "src"
py -m unittest discover -s tests -p test_e065_audit.py -v
py research/e065/e065_audit.py --output e065_reproduction.json
```

## Interpretation and next gate

E065 is a deliberately selected failure family. Its exposed seeds are
development-only; they cannot become a held-out confirmation of a redesigned
filter. The existing E063 causal boundary and E064 estimator remain
unchanged. No actual Darwin kernel action ID, persistent database, real sensor,
voice model, tool, or live interaction was used.

The next scientific work should compare explicit sensor-offset inference
against sensor-naive baselines with a NEW preregistered protocol, and test
model selection and abstention on independent external worlds. In particular,
a three-lag residual cannot be treated as a certificate that correlated
measurement errors are absent.

No new H50-L capability has been registered.
