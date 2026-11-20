# Experiment 067 — independent anchor reliability and adversarial source ambiguity

**Status at preregistration:** protocol only. No E067 evaluator has been run. No H50-L hypothesis or cognitive capability is registered.

## Question

E066 proved that a changing world and an independently drifting sensor can induce exactly the same observation-only law. Does a separately specified world-state reference make these sources distinguishable, and how badly can a corrupted reference mislead a classifier that trusts it?

This is an exact, finite mathematical experiment, not a test of a physical sensor, a Darwin kernel integration, or autonomous identification.

## Frozen model

Keep the E066 source pair unchanged:

- `W`: world-only random walk with `h=1/8, s=0`;
- `S`: sensor-only random walk with `h=0, s=1/8`;
- visible `Y_t = (R_t+O_t) mod 3`, initial `O_0=0` and uniform `R_0`;
- equal prior probability of W and S, length-five visible sequences, anchor at index 4.

Both sources yield exactly equal `P(Y_0,...,Y_4)`. Under W, `R_4=Y_4`; under S, `R_4=Y_0`. The candidate is told these two *hypotheses*, never the realized source.

One external anchor `A` reports the hidden world state. Its declared, symmetric likelihood is `P(A=R_4)=r` and `P(A!=R_4)=(1-r)/2`; require exact rational `1/3 <= r <= 1`. The fixed declared trusted value is `r=4/5`. Other candidate checks include `r=1/3` and `r=1`.

The source posterior is computed from the observable sequence, anchor reading, declared reliability, and source hypotheses only. Never pass the realized source label or hidden mode into the candidate. If the anchor reading is impossible under both declared hypotheses, return an explicit `UNMODELLED` status rather than a forced decision. Do not infer or self-certify anchor reliability.

## Frozen evaluator

Before running the registered enumeration, commit the protocol, the exact-rational candidate, unit tests and a separate enumerator.

Enumerate **all 243** length-five observation traces, three anchor symbols and both source hypotheses, using exact `fractions.Fraction`. The evaluator must independently compute joint probabilities via the existing E066 nine-state `joint_likelihood` and mix the three possible true world-state anchors. The candidate's direct posterior formula must agree with the independent enumerator for every supported event. Record complete normalization, with no floating-point decisions.

Evaluate these regimes:

1. **No anchor:** the best source classification from Y alone has accuracy exactly `1/2`.
2. **Uninformative anchor:** correct anchor generation at `r=1/3` gives exactly `1/2`.
3. **Honest anchor:** data generated using `r=4/5` and inferred with `r=4/5`.
4. **Compromised reference:** an adversary knowing which source generated Y supplies an anchor distributed as though the *other* source had generated it, still using the declared `r=4/5`; the candidate remains frozen and trusts `r=4/5`. This is an explicitly adversarial, evaluator-owned intervention, not a naturally failing independent sensor.

For equal priors, report exact total correct-classification probability under a fair tie rule. Introduce a selective policy: assert a source only when its posterior is at least `4/5`, otherwise abstain. Report assertion coverage and conditional accuracy. This threshold is frozen before any enumeration. Never count abstentions as correct source predictions.

## Frozen pass conjunction

All checks must hold:

1. the unit tests pass and reject malformed cue, anchor, declared reliability and impossible-anchor inputs;
2. all candidate calculations use only `Y, A, r` and the declared source pair; no hidden realized source enters the candidate;
3. the E066 independent nine-state evaluator and candidate agree for all positive-probability events;
4. each honest-source joint distribution sums exactly to one;
5. no-anchor and uninformative-anchor accuracies equal `1/2`;
6. honest-anchor Bayes accuracy is strictly greater than `1/2` and less than `3/4`;
7. compromised-reference accuracy is strictly below `1/2` when the candidate incorrectly trusts `r=4/5`;
8. honest selective accuracy on asserted cases equals `8/9`; compromised selective accuracy equals `1/9`;
9. the asserted fraction is strictly between `0` and `1` and equal under honest and compromised regimes; and
10. no existing E066/E063/H50-L17 code, SQLite database, external effect, live model, or branch `main` is modified.

Record a failed conjunction unchanged. All enumeration results become development-exposed. No post hoc threshold, source family or anchor reliability adjustment may rescue the experiment.

## Interpretation ceiling

Any pass supports only an **E0/E1 mathematical negative/positive boundary** for this exact specified pair and anchor mechanism. The inference depends on *externally warranted* reference reliability. A single plausible reference reading cannot certify that reliability and may make a wrong cause look highly likely. E067 does not build a sensor, estimate its true error rate, generalize to arbitrary nonstationary models, or prove autonomy, consciousness or real-world self-diagnosis. A future intervention/independent-sensor protocol would have to specify how its own reliability is established.
