# Experiment 064 — Label-free sensor reliability and identifiability

**Status:** Preregistered DEVELOPMENT study; no H50-L capability registered. This protocol was committed before implementation, evaluation, or inspection of E064 synthetic outputs.

## Question and model

Can an estimator infer the fixed reliability of a three-symbol sensor and a latent mode-switch probability **only from the cue sequence**, without access to hidden modes or labels? Can it refuse to report a fit when the data cannot identify the parameters?

Latent R_t is stationary uniform in {0,1,2}. It switches with probability h to one of the other two modes, each with probability h/2. Emission Y_t equals R_t with probability q, otherwise one of the other two symbols with probability (1-q)/2. Emissions are conditionally independent given R, with fixed h and q. The supported identifiable regime is q > 1/3 and 0 <= h < 2/3.

Set a=1-3h/2, b=(3q-1)/2 and m_k=P(Y_t=Y_(t+k)). Symmetry gives m_k=1/3+(2/3)*b^2*a^k. Thus with c_k=(3m_k-1)/2, c1=b^2*a, c2=b^2*a^2, and (when positive) a=c2/c1, b=sqrt(c1^2/c2), h=2(1-a)/3, q=(1+2b)/3. The predicted lag-3 equality is 1/3+(2/3)*b^2*a^3. This is a specialized method-of-moments identity, not a novel HMM theorem. Related work: Hsu, Kakade, Zhang (2012), https://arxiv.org/abs/0811.4413 ; Mattila et al., https://www.mdpi.com/2673-9984/5/1/10 .

When q=1/3 or h=2/3, all positive-lag correlations vanish, so this estimator must abstain instead of inventing an estimate. Other sensor-error processes, nonstationary parameters, cue-to-mode ambiguity, and asymmetric dynamics are not identified by this protocol.

## Frozen engineering specification

Add an isolated standard-library-only module `darwin_v50.reliability_identifiability_lab`. Its input is only sequences of exact integer cues 0, 1, 2, each of length at least 4. Pool within-sequence equality pairs at lags 1, 2 and 3; never join independent sequences. Reject malformed input before counting. Use strict c1 > 0.04 and c2 > 0.04; if not, return an explicit `UNIDENTIFIABLE` outcome. Reject out-of-domain inverted parameters, nonfinite results, and impossible moment ratios without clipping, fallback, or use of hidden labels. Report measured and predicted lag-3 equality, pair counts, and estimates.

Freeze implementation, tests, synthetic data generator, scoring, and all engineering controls in a separate commit BEFORE running the registered synthetic study. Tests must include exact model identity checks, permutation invariance, no-information abstention, boundary and invalid input handling, causal prefix-only belief updates, and unchanged E063 behavior. A later source change requires a new experiment ID; do not rerun E064 to rescue the result.

## Registered development evaluation

Positive training data: 24 independent 4,096-cue worlds, seeds 64000–64023, true h=0.08 and q=0.78. Fit once from cues only, never hidden rotations. Held-out scoring: 24 fresh 256-cue worlds, seeds 64100–64123, same true parameters. Score 6,144 prefix-causal posteriors through the existing E063 observer with synthetic unique action IDs. Compare the fitted estimate against oracle h=0.08, q=0.78 and a deliberately misspecified fixed baseline h=0.25, q=0.55. Hidden rotations are evaluator-only and may be inspected solely AFTER each posterior has been produced.

Negative training controls: (a) q=1/3, h=0.08 with seeds 64200–64223, 4,096 cues each; (b) h=2/3, q=0.78 with seeds 64300–64323, 4,096 cues each. Both MUST return `UNIDENTIFIABLE`. Global permutation of all cue labels must produce numerically identical h and q within 1e-12.

**All ten pass conditions (conjunctive):**
1. E064 new-module tests pass unchanged.
2. Estimator takes only cues; no hidden label, future observation, or oracle parameters.
3. |estimated h - 0.08| <= 0.035 and |estimated q - 0.78| <= 0.035.
4. Absolute lag-3 equality-rate residual <= 0.018.
5. Both negative controls abstain.
6. Global cue permutation leaves fitted estimates within 1e-12.
7. Mean held-out Brier improves on the misspecified baseline by >= 0.010.
8. Mean fitted Brier exceeds oracle Brier by <= 0.010.
9. All prefix-scored E063 posteriors remain normalized, finite and causal.
10. No kernel changes, external actions, provider calls, model downloads, or Darwin database access.

Report exact measurements and all criteria even if one fails. E062 seeds 62000–62127 are contaminated and excluded. Once E064 runs, its seeds are also development-only.

## Interpretation

Even a pass is a narrow, locally evaluated synthetic E1 *development result*, NOT independent confirmation or a new H50-L capability. It does not infer sensor error persistence, locate unknown modes, learn continuously, authenticate kernel dispatches, affect real goals, understand language, or establish autonomous cognition. E063 and H50-L17 must remain unchanged. An out-of-model correlated-noise audit requires a separately named follow-up.
