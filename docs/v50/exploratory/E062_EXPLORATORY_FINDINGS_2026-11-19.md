# Darwin v50 — E062 exploratory findings and failure analysis

**Date:** 19 November 2026  
**Status:** Completed independent exploratory simulator study. **Not pre-registered on GitHub, not an H50-L capability result, and not a Darwin kernel/runtime test.** The E062 identifier remains provisional.

## Verified starting point

The v50 `OnlineActionAlignmentTracker._compatible_rotation` requires exactly one compatible rotation. That is a justified invariant for H50-L17's uniquely identifying deterministic cues, but it does not produce a probability distribution over possible modes. The E039 report's `1,536/1,536` local tasks apply only to its documented environment with a known set of three rotations, deterministic observations, a frozen transition prior and externally supplied goals.

This exploration investigates finite-mode inference with noisy observations, the failure of conditional-independence assumptions under a persistently faulty sensor, and the ability of a model of that sensor to restore calibrated probabilities.

## Generative model and information boundary

Let the unobserved action rotation be `R_t` in `{0,1,2}`. Initial `R_0` is uniform. At every following step, the mode stays unchanged with probability `0.94`; with probability `0.06` it changes to one of the other two modes uniformly. The corresponding transition matrix has diagonal `0.94` and off-diagonal `0.03`.

A candidate receives only `Observation(sequence, action_id, cue)` after a named synthetic action. The evaluator holds `R_t` for scoring. The synthetic action does **not** affect the hidden mode, sensor or reward; rewards are not returned to the candidate. The script therefore tests **state estimation and elementary event correlation**, not actual planning or external-effect control. Data are simulated, not from the Darwin database.

Three scenarios were evaluated:

1. **Informative and conditionally independent:** cue equals the current mode with probability `0.8` and either other mode with probability `0.1` each; errors are independent conditioned on the mode sequence.
2. **Uninformative negative control:** cue is uniform over modes and independent of the actual mode.
3. **Persistent correlated-error stress:** the cue is `(R_t + E_t) mod 3`. The hidden sensor offset `E_t` persists with probability `0.85` or is redrawn from `(0.8,0.1,0.1)` with probability `0.15`. The initial offset has this distribution too. Marginal correctness is still `0.8` but sensor errors occur in correlated streaks.

All of these probabilities are hand-specified toy-world assumptions, not physical sensor measurements or Darwin-learned quantities.

## Reference policies

- **Markov:** exact three-state Bayesian filter with known `0.06` transition hazard, *assuming conditionally independent cue errors*.
- **Fresh:** latest cue only, with no accumulated evidence.
- **Cumulative:** posterior as if the hidden mode never changed.
- **Shifted:** deliberately corrupts the observed cue by `+1 mod 3`.
- **Uninformative:** uniform posterior, deliberately ignoring cues.
- **Misspecified:** assumes 80% sensor reliability even when reality provides uniform, uninformative cues.
- **Joint known sensor:** exact nine-state HMM over hidden mode and hidden sensor offset, with the true hand-specified error persistence. This is an **oracle-specified probabilistic reference**, not a model that learns the persistence.

The three-state update has the standard form:

```text
predicted[r] = sum(previous[q] * P(new_mode=r | old_mode=q) for q in modes)
posterior[r] ∝ P(cue | mode=r) * predicted[r]
```

The nine-state filter uses `P(R_t|R_{t-1}) × P(E_t|E_{t-1})`, then retains only joint states satisfying `cue = (R_t + E_t) mod 3`. The candidate APIs do not accept latent mode, sensor offset, future observations, evaluator seed or counterfactual cue.

## Execution and software validation

- Python `3.13.5`, standard-library only.
- `128` independent simulation seeds per condition (`62000–62127`), `256` observations each.
- `32,768` observations per condition, **98,304** across all three conditions.
- All **21** automated tests passed: exact rational reference probabilities, deterministic limiting cases, posterior normalization, strict action and sequence checks, no-future-prefix invariance, snapshot replay and tamper checks, equivalent i.i.d. predictions from the three-state and nine-state filters, numerical tie handling, and reproducibility.
- All simulated-world posterior archives reconstructed exactly. SHA-256 detects accidental changes; it is not authenticated integrity or tamper-proof evidence.
- A deterministic lowest-ID tie-break with a floating-point tolerance was added after a real control failure exposed how tiny rounding differences can select arbitrary modes. The corrected tests and complete exploration were rerun; earlier pilot outputs are superseded.
- A paired **whole-world bootstrap**, 2,048 resamples with seed `62026`, summarizes differences. Correlated steps within a world are never treated as independent bootstrap units.

## Main results

Each entry is **post-observation classification accuracy / multiclass Brier score**. Brier is the sum of squared class-probability errors; lower is better. A uniform three-class belief has Brier `0.6667`.

| Policy | Informative i.i.d. | Persistent errors | Uninformative |
|---|---:|---:|---:|
| Joint, known persistence | 88.519% / 0.1708 | 80.566% / 0.3044 | 31.686% / 0.6667 |
| Three-state Markov | 88.519% / 0.1708 | 77.103% / 0.3814 | 31.686% / 0.6667 |
| Fresh cue | 79.813% / 0.3426 | 80.566% / 0.3321 | 31.686% / 0.6667 |
| Cumulative, no reset | 47.534% / 1.0250 | 47.235% / 1.0390 | 31.686% / 0.6667 |
| Shifted-evidence control | 5.664% / 1.6599 | 11.777% / 1.6554 | 31.686% / 0.6667 |
| Uniform-belief control | 32.068% / 0.6667 | 33.334% / 0.6667 | 31.686% / 0.6667 |
| Model falsely assuming 80% reliability | 88.519% / 0.1708 | 77.103% / 0.3814 | 33.044% / 0.9817 |

**Paired, whole-world exploratory bootstrap comparisons:**

- Informative i.i.d.: Markov minus fresh = **+8.707 percentage points**, interval `[+8.173,+9.216]` points.
- Correlated errors: Markov minus fresh = **−3.464 points**, interval `[−3.775,−3.146]` points. The sign reverses: naive evidence accumulation can hurt classification.
- Correlated errors: joint-known-sensor minus Markov = **+3.464 points**, interval `[+3.143,+3.775]` points.
- Correlated errors: joint-known-sensor and fresh make the **same classifications on this development set** (80.566% accuracy), but the joint posterior has lower Brier (`0.3044` versus `0.3321`). Better calibrated probabilities do not automatically improve top-class decisions.
- Uninformative cues: the correctly informed filters return uniform Brier `0.6667` and log loss `ln(3) ≈ 1.0986`, while the falsely confident 80%-reliability filter has Brier `0.9817` and log loss `1.9303`. Its confidence is not grounded.

The uninformative-sensor classification accuracy (`31.686%`) is one finite-sample result around theoretical chance (`33.333%`), not evidence of learning. Multiple filters share identical deterministic tie-breaking.

## Interpretation ceiling and contamination

The simulator demonstrates that its **declared** conditional-independence assumption becomes misleading when the error process is correlated. This is an established inference issue, not a novel theorem.

The nine-state reference was introduced *after* the correlated-error failure was observed, and the same seeds were reused while debugging. **These results are developmental, not held-out confirmation, and all reported world seeds are contaminated.** Bootstrap intervals describe within-simulator variability, not independent replication or evidence against post-selection.

The nine-state reference knows the true `0.06` regime-change hazard, `0.8` marginal sensor accuracy and `0.85` persistence. It does not learn them. The conditional independence of the simulated sensor resets, mode and seed schedule are imposed by the evaluator. A shared-process Python interface is not a security boundary; the causal API, despite rejecting duplicates and wrong action IDs, is not the maintained Darwin kernel.

No Darwin cognitive claim, no H50-L hypothesis, no independence-level E3 result, no real-world control, no robust Portuguese conversation and no subjectivity/consciousness conclusion follows.

## Next falsifiable gate — before any new capability claim

**Engineering:** Build a separate evaluator-owned stochastic observation bridge for maintained v50. Leave E039 and the existing deterministic tracker unchanged. Force observations to match real dispatched actions, preserve goal isolation, reject duplicate/out-of-order events, prevent future mode or hidden sensor state from entering the candidate, and require exact replay after restart.

**Research:** Specify an estimator that can **learn or explicitly remain uncertain about sensor-error persistence without receiving hidden offsets or true modes**. Evaluate its identifiability first. Compare against fresh evidence, correctly specified oracle filtering, misspecified accumulation, shuffled or deliberately shifted cues, and the uniform negative control. Keep calibration, false-change alarms and action costs separate from classification accuracy. A reasonable outcome is that the sensor and latent mode cannot be disentangled with the information currently available.

**Confirmatory evidence:** Freeze separate implementation, controls, thresholds, seed families, stop rules and acceptance criteria *before* any final run. Do not reuse seeds `62000–62127` for validation or confirmation; do not rebrand this exploratory artifact as preregistered. The true E061 Gemma license gate remains blocked and unchanged.

## Reproduction on Windows

Keep these three Python files together: `darwin_noisy_alignment_exact_reference.py`, `e062_exploratory_benchmark.py`, `test_e062_exploratory_benchmark.py`. Python 3.11+ suffices; no dependencies, model weights or Darwin installation are needed for these standalone tests.

```powershell
py -m unittest discover -s . -p 'test_e062_exploratory_benchmark.py' -v
py .\e062_exploratory_benchmark.py --output .\e062_exploratory_results_local.json
```

`RUN_E062_WINDOWS.ps1` runs both from its own directory and writes an output beside the scripts. No GitHub commits, code modifications, memory-database changes, network requests or persistent model inference occur.

## Established literature

- Adams, R. P.; MacKay, D. J. C. (2007). *Bayesian Online Changepoint Detection*. https://arxiv.org/abs/0710.3742
- Choi, S. P.-M.; Zhang, N. L.; Yeung, D.-Y. (2001). *Solving Hidden-Mode Markov Decision Problems*. https://proceedings.mlr.press/r3/choi01a.html
- Ross, S.; Pineau, J.; Paquet, S.; Chaib-draa, B. (2008). *Online Planning Algorithms for POMDPs*. https://pmc.ncbi.nlm.nih.gov/articles/PMC2748358/

**Repository provenance:** `DevHabito/Darwin` branch `codex/v50-kernel-foundation` (v50 source and E039) and `codex/portable-local-language-seed` (E060/E061). No repository changes were made by this exploration.
