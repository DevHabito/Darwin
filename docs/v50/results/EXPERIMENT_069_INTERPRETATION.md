# E069 — exact third-view identifiability result and limits

**Registered decision:** `PASS_EXACT_THIRD_VIEW_BOUNDARY`, for the frozen mathematical model only. **No new H50-L capability is registered.**

## Evidence chain

- Protocol, before implementation: commit `9d4e2dd22d8523d776453c346b35adef8315ba1b`.
- Candidate, 21 unit tests and separate evaluator, frozen before the full enumeration: commit `e80849790c26e457b2422c42573fb0ce8b2bce63`.
- Complete frozen output: [EXPERIMENT_069_THIRD_VIEW_EXACT_AUDIT.json](EXPERIMENT_069_THIRD_VIEW_EXACT_AUDIT.json).
- Registered evaluation executed once after the freeze. All 21 focused tests passed at the runner preflight and all ten frozen criteria returned true.
- Each of the two models was enumerated over 81 latent-state-and-three-reading assignments for each of three third-view mechanisms. All 27 visible triples per mechanism were recorded. All calculations used exact rational arithmetic and the independent enumerator matched the candidate's posteriors on the admitted third-view mechanism.

## Measured exact results

| Observations | Total variation between A and B | Equal-prior optimal source-classification accuracy |
| --- | ---: | ---: |
| Original two sensors | `0` | `1/2` (50%) |
| Independent third sensor, externally declared reliability `4/5` | `117/1100` | `1217/2200` (55.3182%) |
| Independent but uninformative third sensor, reliability `1/3` | `0` | `1/2` (50%) |
| Third reading copied from the first | `0` | `1/2` (50%) |

Under the independent informative model, `P(Y1=Y3)` is `33/50` for hypothesis A and `153/200` for B, a difference of `21/200`. This proves that their complete three-view observable laws differ, but the optimal *single-triple* classification accuracy improves only 5.3182 percentage points over chance in this example. A detectable difference between distributions does not guarantee an accurate attribution from one observation.

The copied-control law is still identical under A and B. When copied observations are **falsely** processed as conditionally independent, the candidate reports mean maximum posterior confidence `521008979/972242080` (53.5884%), while its actual balanced source-classification accuracy remains exactly `1/2`. The confidence excess is `34887939/972242080` (3.5884 percentage points). Additional data do not create additional evidence when they are duplicate readings of the same event.

## Interpretation and non-claims

These are exact identities for specified, externally supplied probability distributions. E069 does **not** infer independence, discover sensor reliability, validate a physical reference instrument, classify faults in Darwin's runtime, or access any actual sensors. The registered comparison relies on the third view's conditional independence and fixed reliability being true. A copied third reading is an especially clear failure control, not a comprehensive model for every shared error mechanism.

The E069 code lives in a separately imported mathematical laboratory and introduces no SQLite, model, network, tool or kernel calls. The `no_effectful_integration` field in the JSON is a scope declaration, **not** a security proof produced by the numerical evaluator. Repository diff review and full Windows CI are separate admission checks; neither changes the registered mathematical result.

This is not evidence of consciousness, understanding, goal autonomy, continuous learning or general real-world diagnosis. The relevant identifiability and conditional-independence limitations are already part of the statistical latent-class literature; the Darwin contribution here is a traceable, predeclared engineering example and its exact failure controls.

## Next falsifiable question

Can an independent intervention or externally audited instrument certify useful cross-view information **without** presupposing the very independence the learner is meant to discover? A follow-on experiment should use distinct, preregistered intervention outcomes and an explicit invalid-intervention control before adding any Darwin kernel authority.
