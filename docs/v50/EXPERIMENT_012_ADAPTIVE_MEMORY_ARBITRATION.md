# Experiment 012 — adaptive arbitration of retrieved memory

Date: 2026-07-30\
Hypothesis: H50-L8\
Status: refuted

## Question

H50-L7 often retrieved the right regime but assigned it a fixed weight that
hurt prediction. Can observed error learn when a retrieved memory should matter?

The arbiter combines a current-model expert and a retrieved-memory expert. Its
design was informed by
[prediction with expert advice for the Brier game](https://www.jmlr.org/papers/volume10/vovk09a/vovk09a.pdf),
[adaptive regret](https://jmlr.org/papers/volume17/13-533/13-533.pdf), and
[discounted expert loss](https://arxiv.org/abs/1005.1918).

## Protocol

Development selected an exponential weighting rate and loss discount. Eighty
final worlds covered exact recurrence, shifted recurrence, returning novelty,
and late novelty. Experts were updated only after the evaluated outcome.
Sleeping memory received no loss update when retrieval was inactive.

The candidate was compared with a fixed window, H50-L6, and the fixed H50-L7
mixture. Criteria covered total and recurrence-specific gains, novelty damage,
active regret, retrieval quality, archive retention, and exact replay.

## Observed result

| Metric | Observed | Threshold | Result |
| --- | ---: | ---: | --- |
| Total gain vs. fixed window | `0.0065148` | `>= 0.002` | Passed |
| World win rate vs. fixed | `1.0` | `>= 0.65` | Passed |
| Total gain vs. H50-L6 | `0.0000851` | `>= 0.0` | Passed |
| Recurrence gain vs. H50-L6 | `-0.0000504` | `>= 0.0005` | **Failed** |
| Recurrence gain vs. fixed mixture | `0.0045556` | `>= 0.001` | Passed |
| Exact-recurrence gain vs. H50-L6 | `-0.0000188` | `>= 0.0005` | **Failed** |
| Shifted-recurrence degradation | `0.0000190` | `<= 0.001` | Passed |
| Novelty degradation | `0.0005769` | `<= 0.001` | Passed |
| Correct retrieval coverage | `0.9722222` | `>= 0.80` | Passed |
| Retrieval precision | `0.9944904` | `>= 0.90` | Passed |
| Archive / snapshot | `1.0` / `1.0` | `1.0` | Passed |

## Decision

H50-L8 was refuted. The arbiter learned to reduce harmful fixed memory weight
and slightly improved total Brier, but it did not create the registered benefit
in recurrent regions over H50-L6. The small overall gain cannot be relabeled as
successful recurrent memory. Evidence level: `E1_LOCAL_AUTOMATED_EVALUATOR`.
