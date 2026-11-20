# Experiment 068 — shared sensor error, redundant evidence and observational equivalence

**Status at registration:** Protocol frozen before implementation, unit tests, and the registered exact enumeration. No H50-L capability is registered.

## Question

Can two apparently agreeing sensors be treated as independent evidence, and can agreement between two unlabelled sensors identify either their reliability or their common-error dependence?

E065 demonstrated temporal error persistence and E067 showed that an externally supplied reference can be adversarial. E068 tests a different, simultaneous failure: sensor 2 can copy sensor 1's value rather than obtain a new independent measurement.

## Exact model

Let the hidden state R be uniformly distributed over {0,1,2}. Sensor 1 reports Y1=R with probability q and either wrong symbol with probability (1-q)/2. Sensor 2 uses the following fixed generative rule:

- with probability alpha, it copies sensor 1's exact reading Y2=Y1;
- otherwise it independently measures the same R using the same q.

Then, conditioned on R=r,

    P(Y1=i, Y2=j | R=r)
      = L_q(i|r) [ alpha * 1_(i=j) + (1-alpha) * L_q(j|r) ],

where L_q(x|r)=q if x=r, otherwise (1-q)/2.

Use exact rational arithmetic only. Input probabilities must be exact Fraction or int, with 1/3 <= q <= 1 and 0 <= alpha <= 1. Reject booleans, floats, malformed labels, and zero-mass observations. The candidate posterior accepts only (Y1,Y2,q,alpha), not R or an evaluator-only source label.

The observable probability that the sensors agree is

    d(q) = q^2 + (1-q)^2/2
    g(q,alpha) = alpha + (1-alpha)*d(q).

For uniform R and permutation-symmetric emissions, the complete nine-entry joint law of (Y1,Y2) depends only on g: each matching pair has probability g/3 and each distinct ordered pair (1-g)/6. Therefore a single observed two-sensor joint distribution need not separately identify q and alpha. This is an **existing conditional-dependence/latent-class phenomenon**; the purpose is to give Darwin a falsifiable, exact internal warning, not to claim a new general theorem.

## Frozen configurations

- **A (shared noise):** q=4/5, alpha=3/4.
- **B (confounded alternative):** q=19/20, alpha=9/77. These parameters were selected algebraically so that both A and B have g=183/200.
- **I (independent control):** q=4/5, alpha=0.
- **D (complete duplication control):** q=4/5, alpha=1.

The observer sees only Y1 and Y2. The evaluator may enumerate R to assess truth-conditional error, but cannot provide R to the candidate posterior.

## Frozen implementation and reference checks

Commit the implementation, unit tests and a separate evaluator after this document, **before running the registered full enumeration**. All cases use fractions.Fraction, no pseudo-random seeds, no selection of favorable trials.

1. Evaluate all 27 possible (R,Y1,Y2) events for each configuration and all nine observable pairs. Check that their exact total mass is 1.
2. A and B must give **the same exact probability for each of nine observable pairs**, hence total variation 0, despite different q and alpha. Check g=183/200 exactly and the distinct ordered pair law.
3. A and B must disagree on the posterior for R given (Y1,Y2)=(0,0) by more than 1/10. This makes the nonidentifiability consequential, rather than merely a parameter re-labelling.
4. Under A, the naive independent-fusion posterior (q=4/5, alpha=0) after (0,0) must place probability >9/10 on R=0, while the correct A posterior places <9/10.
5. For I, independent fusion must equal the correctly specified posterior on every supported observation.
6. For D, all off-diagonal sensor observations have exactly zero mass and the posterior given (i,i) equals the single sensor posterior for Y1=i.
7. Under true A, the expected multi-class Brier score of the correctly specified posterior must be strictly **lower** than naive independent fusion's expected Brier. Verify the proper-scoring identity

    E_A[Brier(naive)] - E_A[Brier(correct)]
       = sum_(i,j) P_A(i,j) * sum_r (p_naive(r|i,j)-p_correct(r|i,j))^2.

8. Freeze a source-assertion threshold of 9/10. Under A, a correctly specified model must abstain on every observation; naive fusion must assert only on matching sensor pairs, exactly g=183/200 of the time. The actual accuracy of those naive assertions must be <9/10. Abstention is neither counted as a correct prediction nor treated as a capability.
9. Reject malformed probability inputs, unsupported/zero-probability observations, and non-finite or inexact arithmetic at the boundary. Keep all existing E062–E067 modules, Darwin kernel and E039 result unchanged.
10. No SQLite, provider, live sensor, external effect, user memory, or model weights may be accessed or modified. The exact frozen report must preserve the full conjunction, including any failure.

All thresholds, hypotheses, and case counts are fixed here before evaluation. Any failure remains recorded and cannot be repaired into an E068 pass by editing this candidate or evaluator after observing results.

## Evidence and literature boundary

A pass establishes only **exact mathematical evidence** in this small symmetric, known-generative-model family. It neither establishes that Darwin can estimate dependence from two unlabelled sensors nor confers authority to trust a physical sensor. No H50-L claim follows. The duplication model is not the same as all possible correlated errors, and a third independent sensor or external labels would require a different frozen model and experiment.

Relevant prior work:

- Collins and Huynh (2014), *Estimation of diagnostic test accuracy without full verification: a review of latent class methods*: https://pmc.ncbi.nlm.nih.gov/articles/PMC4199084/ (conditional dependence and missing gold-standard information).
- A cautionary note on the robustness of latent class models for estimating diagnostic error without a gold standard (2004): https://pubmed.ncbi.nlm.nih.gov/15180668/ (bias under dependence misspecification).
- *Homogeneous functionals and Bayesian data fusion with unknown correlation* (2018): https://www.sciencedirect.com/science/article/abs/pii/S1566253517302890 (common information and double-counted evidence).

## Follow-on gate

An experiment proposing **learned** source independence must specify the source of independent labels, interventions, distinct sensor physics or admissible constraints. Mere agreement rate cannot certify its own causal independence.
