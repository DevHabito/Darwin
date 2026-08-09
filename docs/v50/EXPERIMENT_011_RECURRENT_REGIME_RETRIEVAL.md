# Experiment 011 — recurrent regime retrieval

Date: 2026-07-29\
Hypothesis: H50-L7\
Status: refuted

## Question

Can Darwin recognize a previously observed Bernoulli regime, reuse its stored
prototype, and abstain when a genuinely new regime appears?

The design drew on work about
[recurring concept drift](https://www.sciencedirect.com/science/article/pii/S0167865513000494),
[concept profiling](https://arxiv.org/abs/1905.08848), and
[selective classification](https://jmlr.csail.mit.edu/papers/v11/el-yaniv10a.html).
The repository model is a much smaller hand-built prototype matcher.

## Protocol

Sixty final worlds were split evenly between recurrence and novelty families.
A detector created regime prototypes, matched a confirmed new segment against
stored prototypes, and either retrieved or abstained. H50-L6 without prototype
reuse served as the causal ablation.

Criteria required improvement over the best fixed window, a positive recurrence
gain over the no-retrieval ablation, correct retrieval coverage and precision,
novelty abstention, a bounded false-retrieval rate, and exact persistence.

## Observed result

| Metric | Observed | Threshold | Result |
| --- | ---: | ---: | --- |
| Total gain vs. fixed window | `0.0055156` | `>= 0.002` | Passed |
| World win rate | `1.0` | `>= 0.65` | Passed |
| Recurrence gain vs. no retrieval | `-0.0022052` | `>= 0.001` | **Failed** |
| Recurrence gain vs. fixed window | `0.0188235` | `>= 0.002` | Passed |
| Correct recurrence coverage | `0.96` | `>= 0.80` | Passed |
| Retrieval precision | `0.9801325` | `>= 0.90` | Passed |
| Novelty abstention coverage | `0.80` | `>= 0.70` | Passed |
| Novelty false retrieval | `0.0666667` | `<= 0.10` | Passed |
| Archive / snapshot | `1.0` / `1.0` | `1.0` | Passed |

## Decision

H50-L7 was refuted. Retrieval labels were usually correct, but activating the
stored prototype made recurrence prediction worse than H50-L6. Recognition
accuracy did not translate into causal benefit.

The final seeds are contaminated. The result remains E1 and cannot be promoted
by comparison with the weaker fixed-window baseline.
