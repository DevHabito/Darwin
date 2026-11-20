# Experiment 069 — independent third view versus copied evidence

**Status:** preregistered, before implementation or registered enumeration. This experiment is a finite exact-rational study, not a newly established Darwin H50-L capability.

## Motivation and falsifiable question

E068 demonstrated that two sources with distinct hidden reliability and copy probabilities can produce identical pairwise readings. Does a third measurement break this observational equivalence **when it is conditionally independent of the first two given the hidden state**, and fail to do so if it is uninformative or merely a copy?

The distinction between genuinely independent conditional views and duplicated evidence is established in latent-class-identifiability research, not a Darwin-specific theorem. Relevant sources:

- Allman, Matias, Rhodes (2009), *Identifiability of parameters in latent structure models with many observed variables*: https://arxiv.org/abs/0809.5032
- Collins and Huynh (2014), *Estimation of diagnostic test accuracy without full verification: a review of latent class methods*: https://pmc.ncbi.nlm.nih.gov/articles/PMC4199084/
- Toft et al. (2005), *Diagnosing diagnostic tests: evaluating the assumptions underlying the estimation of sensitivity and specificity in the absence of a gold standard*: https://pubmed.ncbi.nlm.nih.gov/15795013/

These sources motivate the conditional-independence warning; they are not evidence that any real Darwin sensor is independent.

## Frozen generative models

Keep the E068 definitions unchanged. A hidden state R is uniform on {0,1,2}.

- **A:** first-sensor reliability q=4/5 and probability that sensor 2 copies sensor 1 alpha=3/4.
- **B:** q=19/20 and alpha=9/77.
- For both, Y1|R has probability q of equalling R and (1-q)/2 for either other symbol.
- Y2|R,Y1 copies Y1 with probability alpha; otherwise independently draws from the same emission distribution.
- The two-sensor law P_A(Y1,Y2) equals P_B(Y1,Y2) for every ordered pair; agreement probability is 183/200.

Evaluate three separate third-view mechanisms, not one mixture:

1. **Independent informative:** Y3 is conditionally independent of (Y1,Y2) given R; its externally specified probability of a correct observation is t=4/5 and each incorrect symbol has probability (1-t)/2.
2. **Independent uninformative:** exactly the same conditional structure with t=1/3.
3. **Copied control:** Y3 equals Y1 deterministically. It does not provide a new observation.

An **adversarial interpretation** evaluates copied-control data through a candidate that falsely *assumes* the informative, independent t=4/5 mechanism. The candidate must not receive the actual mechanism label or realized A/B source; that label is evaluator-owned.

The independent model implies

    P(Y1 = Y3) = q*t + (1-q)*(1-t)/2.

For t=4/5, the two hypotheses imply respectively 33/50 (A) and 153/200 (B): a difference of 21/200. For the copied mechanism, Y1=Y3 always and the entire triplet law remains identical under A and B. For t=1/3, the third view is independent uniform noise and again does not distinguish A and B.

## Frozen implementation and evaluator

Commit a standard-library-only, exact-Fraction module `darwin_v50.third_view_identifiability_lab`, tests, and a separate pure evaluator before any registered enumeration. Neither may import the Darwin kernel, SQLite store, action or tool adapters, language runtime, or a model service.

- Candidate `independent_triplet_posterior(Y1,Y2,Y3,t)` receives only the readings, externally declared t, and frozen A/B model descriptions. It returns exact (P(A|data), P(B|data)) under equal source priors; it must not accept a realized source label, true R, sensor-copy flag, or oracle data.
- A separate evaluator directly enumerates hidden R and the 81 possible (R,Y1,Y2,Y3) assignments for each model and mechanism. It must calculate observable probabilities independently from the candidate posterior, verify full normalization and compare candidate posterior to exact Bayes for each positive-mass observation.
- For each mechanism calculate the exact total-variation distance between A and B over the 27 observable triples, and exact equal-prior optimal source-classification accuracy (1+TV)/2. Also calculate the pair-only distance.
- In the adversarial copied case, freeze the candidate's assumed independence and compute its **mean declared maximum posterior probability** using the observed copy-law mixture of A and B. Under identical real A and B laws the true balanced classification accuracy remains exactly 1/2. Report any confidence excess over that ceiling as a miscalibration warning; a larger confidence is not evidence of success.
- Reject floats, booleans, malformed cue labels, nonexact probabilities, reliabilities outside [1/3,1], and zero-probability observations. Perform no output repair or fallback.

This is an exact enumeration; there are no sampling seeds, model downloads, cost-bearing providers, or uncontrolled external measurements.

## Frozen pass conjunction

Every condition must hold:

1. new-module unit tests and its independent reference checks pass unchanged;
2. source A and B share exactly the same two-view law and pair-only TV is zero;
3. candidate posteriors equal independently enumerated Bayes results on all supported triples of the informative third-view mechanism;
4. all source/mechanism joint probability masses sum to exactly one, and no arithmetic is approximate;
5. informative-independent third-view TV is **at least 21/200**, and equal-prior Bayes accuracy exceeds 1/2;
6. P(Y1=Y3) under informative independence equals 33/50 for A and 153/200 for B;
7. uninformative-independent third view has TV=0 and Bayes accuracy exactly 1/2;
8. copied third view has TV=0 and Bayes accuracy exactly 1/2, with Y3=Y1 on every positive-probability triple;
9. when copied readings are falsely treated as independent t=4/5 evidence, true balanced accuracy remains 1/2 but the mean reported maximum posterior exceeds 1/2;
10. no changes occur to E062–E068, H50-L17, the maintained Darwin kernel, SQLite state, installed models or `main`.

Any failure produces a recorded failed E069 result. Do not modify these thresholds or re-use the same E069 label to fix an observed result.

## Interpretation ceiling and next step

An E069 pass would be an exact mathematical boundary, not evidence of self-verified independence or reliable real-world sensor fusion. Reliability t and independence are imposed by the evaluator and are not inferred by Darwin. A third source is useful here only because of its guaranteed conditional connection to latent R and different emission law. In real deployments, independent provenance, interventions, blinded labels, and common-mode failure checks require separate protocols. The present findings neither establish open-world autonomy nor consciousness.
