# Experiment 063 — causal, uncertainty-preserving observation boundary

**Status:** Engineering protocol frozen before implementation. No new H50-L hypothesis is registered. This experiment does not supply an E1 cognitive result.

## Context and reason for the boundary

H50-L17 (E039) passed locally on deterministic, uniquely identifying action-rotation cues. Its current `OnlineActionAlignmentTracker` demands exactly one matching rotation and updates from that cue. The independent E062 exploration subsequently demonstrated that accumulating seemingly reliable cues can perform worse than using only the latest cue when sensor errors persist. That exploration used development seeds `62000–62127`, was not pre-registered, did not execute the v50 kernel, and may not be used as confirmatory evidence.

E063 builds a small alternative evidence boundary, not a replacement for the E039 tracker. The new module may be imported separately, but **the existing deterministic tracker, evaluator, E039 result, kernel, and v50 runtime stay unchanged**. The purpose is to preserve ambiguity and test causal input/replay handling before any proposed integration or new learning claim.

## Frozen contract

Implement a standard-library-only `darwin_v50.noisy_alignment_lab` module with:

- `NoisyCue`: one observation containing a positive, contiguous integer sequence; a non-empty dispatched action identifier; and an integer cue in `{0,1,2}`. The observation carries no hidden rotation, sensor-offset label, future mode, evaluator seed or alternative-action outcome.
- `NoisyAlignmentBelief`: a three-mode posterior, initially uniform, with declared finite model-switch probability `h` in `[0,1]` and declared sensor correctness `q` in `[1/3,1]`. These are **given parameters**; the component does not learn them.
- An explicit two-step causal API: `register_dispatch(action_id)` followed by `observe(cue)`. At most one dispatch may be pending; each identifier must be unique; an observation is accepted only for the pending identifier and exact next sequence. An invalid submission must not change posterior, archive or pending dispatch.
- A predictive step `P(R_t=r)= (1-h)P(R_{t-1}=r) + h/2 * (1-P(R_{t-1}=r))` for non-initial observations, followed by the Bayes update with likelihood `q` for the matching cue and `(1-q)/2` for each other cue. Zero normalizing mass is rejected. Every posterior stays finite, nonnegative and normalized.
- No default threshold for selecting a rotation, no fabricated hard observation, and no claim that the posterior is calibrated to an unknown real sensor. Consumers receive the full three-number distribution.
- A versioned canonical-JSON snapshot of accepted observations, posterior, declared parameters and any pending dispatch, with SHA-256 for accidental-corruption detection. Restoring must independently replay all accepted events and reject changed posterior values, missing/duplicated sequence, malformed data or a changed contract. A matching digest is **not** an authenticated signature, and someone who can rewrite both the archive and digest can forge a consistent history.

A `register_dispatch` call proves only that a caller supplied an identifier. It does **not** authenticate a Darwin kernel dispatch or grant tool/action authority. E063 explicitly does not write to SQLite or invoke the external-effect adapter; it is a candidate for later kernel-bound work, not proof that such binding already exists.

## Frozen engineering checks

Tests must cover at minimum: uniform prior, a known first posterior, a non-initial mode-transition prediction, exact symmetric tie behavior, uninformative-cue neutrality, valid and invalid model parameters (including NaN and infinity), invalid cue/sequence/types, missing and wrong action identifiers, duplicate identifiers, out-of-order observations, concurrent dispatches, unchanged state on rejection, replay after a completed observation, replay with an outstanding dispatch, corruption detection, rewritten-checksum-and-replayed-belief mismatch, and independent calculations of Bayes updates. Run a deterministic randomized sequence and verify posterior normalization at each step. A synthetically ambiguous observation must remain probabilistic rather than be forced into a single asserted rotation.

Any test failure blocks engineering admission. Do not weaken an earlier v50 check to make E063 pass. Existing repository tests and the maintained-surface checker must also pass before a wider engineering admission claim can be made; a local isolated test run alone only establishes focused E063 behavior. Windows CI results must be reported separately from local tests.

## Interpretation and future research

A passing E063 is **E0 engineering**, not an E1 model-learning result. The likelihoods are fixed by the experimenter. It does not infer sensor reliability, distinguish latent mode change from correlated sensor failure, execute a goal, or bind to the actual v50 kernel. There are no performance thresholds or final seeds in E063. Follow-on experiments must separately preregister a world/interface sensitivity test, genuine kernel action–observation binding, independent evaluator seeds and both positive and negative controls before claiming a new H50-L capability. Prior E062 seeds are development-only. Existing E061 Gemma terms and model-download restrictions remain unchanged.

## Reproduction intent

Focused tests should run on Python 3.11+ using `PYTHONPATH=src python -m unittest tests.test_v50_noisy_alignment_lab -v`, followed by the repository test suite and maintained-surface check when the repository is available. No model weights, network inference or existing Darwin database are needed.
