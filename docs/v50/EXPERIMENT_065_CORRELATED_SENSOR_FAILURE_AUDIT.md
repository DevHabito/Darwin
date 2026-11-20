# Experiment 065 — correlated sensor failure audit of E064

**Status: preregistered adversarial audit.** No E064 revision is allowed, no new H50-L result is registered, and no correlated-sensor results have yet been generated on the registered E065 seeds.

## Why the next gate must be adversarial

E064 succeeded only for an iid-emission, stationary three-mode hidden Markov world. Its estimator fits mode-switch hazard h and cue reliability q from equality rates at lags 1 and 2. Its lag-3 residual was a diagnostic, not proof of model correctness. E062 previously found a correlated-noise failure in a separate development simulator.

Construct an explicitly out-of-model sensor: the latent rotation R_t switches symmetrically with h=0.08. An independent additive error offset O_t in {0,1,2} persists from the previous step with probability rho=0.60; otherwise it redraws from {0:0.78, 1:0.11, 2:0.11}. The observed cue is (R_t+O_t) mod 3. Start R uniformly and O in its redraw stationary distribution. Only the evaluator sees R and O; the unchanged E064 estimator sees Y only.

The marginal sensor correctness P(O_t=0) remains 0.78. But errors are temporally correlated, violating E064's conditional iid-emission assumption.

## Pre-experiment analytic counterexample

Write a=1-3h/2, b=(3q-1)/2 and rho=0.60. For lag k,
c_k = (3*P(Y_t=Y_(t+k))-1)/2
= a^k * [b^2 + (1-b^2)*rho^k].
In contrast, the E064 model assumes c_k = a^k*b^2. Applying the E064 two-lag inversion to this misspecified *population* yields approximately h=0.179537 and q=0.979295 (true h=0.08, marginal q=0.78). The absolute population lag-3 equality residual is approximately 0.013841, **below E064's frozen 0.018 diagnostic**.

This deliberately constructed theoretical example was analyzed before the E065 protocol and is NOT independent evidence. Its value is a falsifiable risk: a model can give very confident but badly biased parameters while the third-lag check appears acceptable. The equality formula was independently cross-checked by explicit nine-state Markov transition enumeration before this preregistration.

## Frozen finite-sample audit

Use the unchanged committed E064 estimator and E063 observer. Freeze the new adversarial world generator, its tests and the evaluation runner in a separate commit before sampling any registered E065 seed.

- Correlated training: 24 independent stationary 4,096-cue sequences with seeds 65000–65023; true h=0.08, marginal q=0.78, offset persistence rho=0.60.
- Correlated held-out: 24 independent 256-cue sequences with seeds 65100–65123, same parameters; report prefix-causal E063 multiclass Brier for E064-fitted parameters if a fit exists, the oracle **iid-assumption** model h=0.08/q=0.78 (not a true correlated-sensor oracle), and a last-cue classifier with q=0.78.
- Independent-error control: 24 independent 4,096-cue sequences with seeds 65200–65223, same h and q but rho=0; report fitted parameters and lag-3 gap.
- Within-sequence lag-1 through lag-3 rates only, no cross-world pairs. Do not pass hidden rotations, offset states, future cues or true parameters to the estimator.
- Record all fit/abstention outcomes and numeric diagnostics; no retry, parameter adjustments, seed substitution or thresholds changes.

The preregistered **adversarial counterexample observation** is the conjunction:
(1) E064 returns FITTED, (2) q_estimated >= 0.93, and
(3) the observed lag-3 equality gap <= 0.018.
If it holds, the finite-sample E064 third-lag gate has failed to detect material misspecification. If not, report the exact miss without rescuing the hypothesis. The analytic population counterexample stands independently of the finite realization.

The engineering audit passes only when all new tests pass, the control and correlated outputs are reported, no replay/kernel changes occur, every posterior is finite and normalized, and all original E064 protocol thresholds and code remain unchanged. Engineering completion does NOT promote E064 to general sensor reliability.

## Interpretation ceiling

This is an adversarial model-misspecification test, using a *deliberately chosen* failure family and project-owned synthetic evaluator. It cannot establish robust detector quality, independently calibrated sensor confidence, real-world reliability, consciousness, autonomous goals, or language understanding. An independent externally controlled evaluator and a sensor-error-state-aware model would require new protocols.
