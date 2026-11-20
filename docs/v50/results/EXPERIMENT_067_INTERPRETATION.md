# E067 — exact anchor reliability audit: result and limits

**Registered outcome:** `PASS_EXACT_FINITE_ANCHOR_BOUNDARY`. This is a finite mathematical source-identification study, **not** confirmation of a new Darwin H50-L capability.

The protocol was committed at `c2ba8546112c066fe028c7c2023695c7c167cf3b`. The candidate, its 24 focused tests and the independent exact evaluator were frozen at `59c0baef4733d1b334321b9fac8519d3d5937d38`, before the complete registered enumeration.

## Exact results

The evaluator considered all 243 five-symbol observation histories, each of three possible anchor readings and both E066 source hypotheses. All 729 observed-history/anchor combinations had a valid posterior. All 10 registered checks returned true.

| Evidence | Exact equal-prior classification accuracy | Approximation |
| --- | ---: | ---: |
| Observation sequence alone | `1/2` | 50.000% |
| Uninformative reference (`r=1/3`) | `1/2` | 50.000% |
| Correctly specified reference (`r=4/5`) | `82791/131072` | 63.165% |
| Compromised reference, falsely treated as `r=4/5` | `48281/131072` | 36.835% |

The reliability-informed selective policy requires posterior source confidence at least `4/5`; otherwise it abstains.

| Selective outcome | Exact fraction | Approximation |
| --- | ---: | ---: |
| Assertion coverage, both reference regimes | `22185/65536` | 33.852% |
| Accuracy among asserted cases, honest reference | `8/9` | 88.889% |
| Accuracy among asserted cases, compromised reference | `1/9` | 11.111% |

Under the honest reference, the stated confidence is justified by the generator's model. Under reference substitution by an adversary who knows the realized source, the **same inference code and confidence threshold** lead to mostly false high-confidence assertions. The anchor's reliability was assumed, not measured. This is an intentional intervention on the information source, not evidence that an ordinary sensor spontaneously behaves that way.

The evaluator used exact rational probabilities. It checked each candidate posterior against the existing E066 nine-state forward enumeration and verified that each source joint law sums to one. These are same-project cross-checks, not an external independent replication.

## Interpretation

A reference measurement improves source identification only when the candidate world and sensor hypotheses predict different hidden world states. Even then, an 80%-correct reference does not necessarily yield 80% overall source-classification accuracy; the reference adds no discriminatory information when the hypotheses predict the same state.

Abstention reduces the number of asserted cases but does not provide protection against an unrecognized, source-aware compromised reference. A confidence threshold conditional on an invalid trust model can amplify error. E067 therefore establishes **a condition on evidence use**, not a self-diagnosis ability.

No physical reference was connected, no source reliability was learned online, no causal-kernel dispatch was authenticated, no user database was accessed, and no runtime effect was performed. The original E066/E063/H50-L17 modules and `main` remain unchanged.

## Reproduction and operational incident

Run the 24 focused tests under `PYTHONPATH=src` and then execute `research/e067/e067_exact_evaluator.py --output <writable-path>`. The runner writes the registered exact record to `EXPERIMENT_067_ANCHOR_SOURCE_AUDIT.json`.

The first complete local evaluation calculated the result but failed when writing its JSON output because the selected directory did not grant the executing user's write permission. The frozen evaluator was rerun unchanged with a writable output path. The resulting data were checked against the frozen gates without changing inputs, reliability, code, threshold or hypothesis family. No random seeds or stochastic realizations are involved. See `E067_CAPTURE_INCIDENT_01.md`.

## Next boundary

An E068 protocol would need to define **how a reference's own trustworthiness is established**, rather than treating reliability as an oracle-supplied constant. Replicated but correlated references, and a source-aware adversary, must be kept distinct from independent measurements. Until this distinction is supported, an honest decision to remain undecided is more defensible than a high-confidence causal attribution.
