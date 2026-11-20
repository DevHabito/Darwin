# Experiment 068 — exact result and interpretation

**Decision:** PASS_EXACT_BOUNDARY on the pre-registered finite model. This is a mathematical model audit, not a new H50-L cognitive capability.

## Evidence chronology

1. Protocol committed first as `a788a3c`, fixing the source family, exact rational configurations, hypotheses, tests and decision rules.
2. The source module, 20 passing local unit tests, and separate evaluator were frozen together as `1596ddee` before the registered enumeration.
3. The frozen evaluator was then executed once on Python 3.13.5 with no stochastic seed. It enumerated 27 (R,Y1,Y2) assignments for each of four models and all nine visible pairs. Its report is `EXPERIMENT_068_SHARED_SENSOR_EXACT_AUDIT.json`.
4. **All 14 recorded exact checks passed.** The original named experimental claims, comparisons and thresholds were not revised after this result.

The evaluator and module use `fractions.Fraction` throughout. Checks include normalization, an independently summed generative likelihood for all visible pairs, full duplication and independence controls, and an exact proper-scoring identity.

## What the results actually show

Two distinct models have the **identical complete nine-outcome observable law**, not merely a similar agreement rate:

| Model | Sensor correctness q | Copy probability alpha | Observable agreement |
| --- | ---: | ---: | ---: |
| A: shared sensor errors | `4/5` | `3/4` | `183/200` |
| B: alternative latent explanation | `19/20` | `9/77` | `183/200` |

For both models each matching pair has probability `61/200`, each distinct ordered pair has probability `17/1200`, and the exact total-variation distance is **zero**. An unlimited sample of independent pair measurements from this model cannot distinguish A from B solely through the pair distribution.

Yet for the same observed pair `(0,0)`, the posterior probability of hidden state 0 is `152/183` (about 83.06%) under A and `13984/14091` (about 99.24%) under B. Thus the observational equivalence matters for what the agent can justifiably believe about an unobserved state.

The naive fusion rule, which knows the true marginal `q=4/5` but incorrectly assumes alpha=0, reports `32/33` (about **96.97%**) for that state under A. The correctly specified posterior is only `152/183` (about **83.06%**). This is double-counted evidence, not newly observed information.

The exact expected multiclass Brier scores under A are:

- correctly specified A: `131771/414800` (approximately 0.3177);
- naive conditional-independence fusion: `283231/822800` (approximately 0.3442);
- excess naive loss: `196/7381` (approximately 0.02655).

The excess loss agrees exactly with the posterior squared-distance identity for the Brier score. That identity is an established property of proper scoring, not a new mathematical theorem.

At the pre-registered 90% assertion threshold, the correctly specified A model **abstains on every pair**. This is not useful coverage and must not be described as successful source identification. The naive model asserts a source on `183/200` (91.5%) of observations, but its exact conditional accuracy on those assertions is `152/183` (83.06%), well below the asserted 90% confidence.

When alpha=1, the second sensor provides exactly the same evidence as the first and all different-valued pairs are impossible. When alpha=0, correct fusion agrees with independent Bayesian multiplication.

## Scientific limit

The candidate receives q and alpha *from the evaluator*. It has not learned sensor reliability, discovered shared dependence, or authenticated either sensor. The underlying hidden R is available to the evaluator for scoring only, never to the candidate posterior. None of this tests streaming decisions, an actual external sensor, a real Darwin action ID, a goal, persistent memory or the v50 kernel.

This boundary is consistent with the established literature on conditional dependence in latent-class inference and unknown-correlation fusion, including:

- Collins and Huynh (2014), https://pmc.ncbi.nlm.nih.gov/articles/PMC4199084/;
- *A cautionary note on the robustness of latent class models for estimating diagnostic error without a gold standard* (2004), https://pubmed.ncbi.nlm.nih.gov/15180668/;
- *Homogeneous functionals and Bayesian data fusion with unknown correlation* (2018), https://www.sciencedirect.com/science/article/abs/pii/S1566253517302890.

**Conclusion:** sensor agreement cannot certify its own independence. A truthful Darwin inference system needs information provenance, defensible correlation assumptions, or new independent evidence before multiplying redundant readings as separate proof.

## Next research gate

A new experiment must pre-register a source of additional information: a genuinely independently generated third signal, calibrated external labels, or an intervention with explicitly bounded error. It must include a corrupted or duplicated supposed reference. Neither the frozen E068 data nor prior E062–E067 seeds may be reused to claim independent confirmation.

The branch remains separate from `main`; original E039/H50-L17, E063–E067 and the SQLite user database remain unchanged. Full Windows CI must be checked at the exact result commit before claiming complete repository-wide admission.
