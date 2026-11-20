# Experiment 066 — Structural identifiability of world change and sensor drift

**Status:** Pre-registered mathematical and engineering audit. No E1 Darwin learning capability is registered. This protocol is committed before implementing or evaluating E066.

## Research question

Can a decoder that receives only an observed, action-associated cue always distinguish an external-world change from persistent sensor-offset change? E065 found a correlated-noise failure for the E064 iid-emission estimator; E066 tests the underlying identifiability limit in a narrower, explicitly defined synthetic model.

## Frozen model and analytic prediction

Work in the group Z/3Z. Initially hidden world state R_0 is uniform on {0,1,2}, sensor offset O_0=0, and they evolve by independent random-walk increments U_t and V_t. Each U_t is zero with probability 1-h and 1 or 2 with probability h/2 each. Each V_t is zero with probability 1-s and 1 or 2 with probability s/2 each. The decoder sees only Y_t=(R_t+O_t) mod 3, not the two latent variables.

The probability that the *sum* of the independent increments is zero is (1-h)(1-s)+hs/2. Thus the entire observable process is a symmetric three-state random walk with effective_hazard = h+s-3hs/2, starting uniformly. **All finite Y-sequence distributions depend on h and s only through effective_hazard.**

Preregister two exact-rational pairs:
- A: world-only (h=1/8,s=0); B: sensor-only (h=0,s=1/8). Both effective hazards are 1/8.
- C: mixed (h=1/10,s=1/6); D: world-only (h=29/120,s=0). Both effective hazards are 29/120.

For each pair, equal likelihood for **every** observable history implies Bayes source-label accuracy at most 1/2 under equal prior probabilities, with *only* Y available. This is a counterexample to universal source attribution, not a claim that every HMM is non-identifiable.

## Frozen independent checks

Use Python's exact Fraction arithmetic. For every one of the 3^5 = 243 five-cue histories, require:
1. an independently implemented nine-state forward recursion over (R,O) to equal the closed-form observation-only Markov likelihood **exactly**, for A, B, C, and D;
2. observation-only likelihood to be identical within each pair, including all positive-likelihood histories;
3. total probability summed over all histories to equal one exactly for all four worlds;
4. total variation distance within each pair to equal zero exactly;
5. equal-prior best source-classification accuracy to equal exactly 1/2 for both pairs;
6. independent direct convolution of world/sensor increments to match the effective-hazard law exactly;
7. a paired latent witness can use the same Y trace but assign its changes to R in A and to O in B, without changing a single observed cue;
8. a genuinely trusted external world-state anchor can break the A/B equivalence: for Y=(0,1,1,2), jointly observing R_2=0 is impossible in A and possible in B.

The anchor is a **mathematical additional-information boundary**, not a simulated authentic sensor or a new authority grant. A Darwin-generated ID alone cannot provide it.

Tests must also reject malformed history symbols, invalid rational probabilities, boolean/float hazards, and invalid anchor indices or values. No prior E062–E065 seeds are reused; no fitted model, SQLite memory, kernel execution, physical sensor, provider, or tool action is invoked.

## Frozen execution order and reporting

1. Commit this protocol first.
2. Implement a separately imported standard-library module darwin_v50.causal_source_identifiability_lab, independent unit tests, and a separate deterministic runner research/e066/e066_evaluate.py.
3. Run local implementation-only unit tests and **commit the frozen implementation, test suite, and runner** before the first registered full enumeration.
4. Execute the runner **once** and record its canonical JSON findings even if any check fails. Do not change parameters, acceptance criteria, seeds, or the candidate after seeing a registered result. A later correction requires a separate new experiment.
5. Run focused tests and the maintained repository test suite in Windows CI on the exact head; report its state separately from this mathematical experiment.

A clean positive mathematical audit records PASS_NONIDENTIFIABILITY_BOUNDARY_EXACT; it must **not** register an ability to distinguish world and sensor causes. Any exact mismatch or test failure is a failed audit and must be retained and explained without rescue.

## Interpretation ceiling and prior literature

This is a deliberately symmetric, stationary, independent-increment toy model with **temporally correlated sensor-offset noise**, and no trusted side information. It establishes an impossibility only in this model class. Known observation models, independent stationary noise, interventions, or trusted external measurements can restore identifiability in other models.

Background (not originality claims):
- Cole (2019), *Parameter redundancy and identifiability in hidden Markov models*: https://doi.org/10.1007/s40300-019-00156-3
- Gassiat et al. (2020), *Identifiability and consistent estimation of nonparametric translation hidden Markov models with general state space*: https://jmlr.csail.mit.edu/papers/v21/19-802.html

The latter's positive identifiability theorem uses different hypotheses and is not contradicted by this experiment. No conclusion about general cognition, actual sensor reliability, autonomous goals, consciousness, or independent replication follows.
