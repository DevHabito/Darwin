# E066 result — observation-only source attribution is not identifiable

**Decision:** PASS_NONIDENTIFIABILITY_BOUNDARY_EXACT, an exact mathematical
counterexample and engineering audit. It is a *negative source-identification
result*, not a newly demonstrated Darwin capability.

## Reproducible result

E066 was preregistered at commit 4c85671909ae98e41be12ae1b414be4a1aee520a.
The standard-library reference, 21 tests and evaluation runner were frozen at
commit 84b3e9c16cab6dc115d8023ec33e3ac31cb4692d **before** the registered
enumeration. The first registered audit ran on Python 3.13.5 and produced
the immutable JSON record in the same results directory:

- 243/243 distinct five-symbol observation traces were enumerated.
- Each of four hidden-world configurations matched an independently written
  nine-state forward recursion with exact rational likelihoods.
- Every distribution summed to exactly one.
- Pair A/B: h=1/8,s=0 versus h=0,s=1/8. Both have effective hazard 1/8.
- Pair C/D: h=1/10,s=1/6 versus h=29/120,s=0. Both have effective
  hazard 29/120.
- Total-variation distance is **exactly zero** in both pairs; an equal-prior
  source classifier restricted to the observation trace has Bayes accuracy
  **exactly 1/2**, regardless of trace length.
- All 9 registered conjunction checks passed. All 21 engineering tests passed.
- For observed (0,1,1,2), a separate *trusted* measurement R_2=0 has
  joint probability zero under A and 7/6144 under B. This is a proof
  of a possible information boundary, **not** a tested physical sensor.
- The exact, source-locked result is in
  [EXPERIMENT_066_EXACT_IDENTIFIABILITY_AUDIT.json](EXPERIMENT_066_EXACT_IDENTIFIABILITY_AUDIT.json).

## Interpretation and limitations

Under the frozen symmetric additive model, the observer measures only
Y_t=(R_t+O_t) mod 3. Independent world and sensor increments combine into
an observable random-walk hazard h+s-(3/2)hs. Changes in that observable
hazard cannot in general be assigned uniquely to their hidden causes.
This is **structural non-identifiability**, not an inaccurate classifier that
can be repaired by more training data from the same channel.

The toy model does not include real sensors, authenticated physical anchors,
non-additive emissions, known calibrated sensor dynamics, intervention effects,
independent replication, or the Darwin kernel. This result must not be used
to claim that source attribution is impossible in richer physical systems.

E066 source code is intentionally independent of the older deterministic
H50-L17 cycle and E063–E065 modules. E061 license/consent restrictions,
the database and the main branch were not changed.

## Next falsifiable boundary

Before building a source-attribution policy, require at least one *separate,
reliably sourced* signal with demonstrably different predictions under the
competing hypotheses. A future protocol should test a corrupted or misleading
anchor as a negative control and require the system to abstain if that
information is untrustworthy. The current E066 toy anchor is neither authentic
nor sufficient evidence for a deployed Darwin intervention.
