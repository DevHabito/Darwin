# Darwin v50 research record

This directory is the evidence ledger for the maintained Darwin architecture.
It contains the standing protocol and one record for each experiment. Documents
are written before final evaluation whenever a held-out result is claimed.

## Foundation

| Document | Scope |
| --- | --- |
| [Research protocol](RESEARCH_PROTOCOL.md) | Evidence levels, kernel invariants, experiment ledger, and safety boundary |
| [Experiment 001](EXPERIMENT_001_WORKSPACE_E2.md) | A real, scoped workspace effect |
| [Experiment 002](EXPERIMENT_002_CAPABILITY_SUBPROCESS.md) | Single-use capability and subprocess execution |
| [Experiment 003](EXPERIMENT_003_EXPLICIT_CONSENT_AND_ISOLATION.md) | Explicit consent and honest isolation classification |
| [Experiment 004](EXPERIMENT_004_EXTERNAL_AUTHORITY_AND_APPCONTAINER_GATE.md) | External signing authority and fail-closed AppContainer gate |

## Learning sequence

| Hypothesis | Experiment | Result |
| --- | --- | --- |
| H50-L1 | [005 — transition learning](EXPERIMENT_005_COGNITIVE_LEARNING_LAB.md) | Passed locally |
| H50-L2 | [006 — active exploration](EXPERIMENT_006_ACTIVE_EXPLORATION.md) | Passed locally |
| H50-L3 | [007 — partial observability](EXPERIMENT_007_PARTIAL_OBSERVABILITY_AND_CALIBRATION.md) | Passed locally |
| H50-L4 | [008 — temporal adaptation](EXPERIMENT_008_TEMPORAL_ADAPTATION.md) | Passed locally |
| H50-L5 | [009 — multiscale drift](EXPERIMENT_009_MULTISCALE_CONCEPT_DRIFT.md) | Refuted |
| H50-L6 | [010 — Bayesian run length](EXPERIMENT_010_BAYESIAN_RUN_LENGTH.md) | Passed locally |
| H50-L7 | [011 — recurrent regime retrieval](EXPERIMENT_011_RECURRENT_REGIME_RETRIEVAL.md) | Refuted |
| H50-L8 | [012 — adaptive memory arbitration](EXPERIMENT_012_ADAPTIVE_MEMORY_ARBITRATION.md) | Refuted |
| H50-L9 | [013 — episodic action memory](EXPERIMENT_013_EPISODIC_CONTEXTUAL_ACTION_MEMORY.md) | Refuted |
| H50-L10 | [014 — predictive history planning](EXPERIMENT_014_PREDICTIVE_HISTORY_PLANNING.md) | Passed locally |
| H50-L11 | [015 — learned context and reward](EXPERIMENT_015_LEARNED_CONTEXT_REWARD_PLANNING.md) | Refuted |
| H50-L12 | [016 — online posterior-sampling control](EXPERIMENT_016_ONLINE_POSTERIOR_SAMPLING_CONTROL.md) | Refuted |
| H50-L13 | [018 — information-directed online control](EXPERIMENT_018_INFORMATION_DIRECTED_CONTROL.md) | Refuted |

The [H50-L12 failure audit](EXPERIMENT_017_POSTERIOR_SAMPLING_FAILURE_AUDIT.md)
replicated the reward deficit and localized persistent action changes to
transition and reward parameter sampling.
[H50-L13](EXPERIMENT_018_INFORMATION_DIRECTED_CONTROL.md) then tested
action-targeted information-directed control and was refuted because it did not
beat certainty-equivalent control or meet the simultaneous-win rule.
Its [pre-registered failure audit](EXPERIMENT_019_INFORMATION_DIRECTED_FAILURE_AUDIT.md)
replicated the deficit and ruled out block staleness as the dominant channel,
but could not resolve ensemble versus mixture dominance. H50-L14 is not
registered.

## Next research gate

The [cross-world transfer note](RESEARCH_NOTE_CROSS_WORLD_TRANSFER.md) examines
the next architectural limit: every current world starts with an uninformative,
world-local prior. The note rejects direct archive pooling and an immediate
successor-feature or neural implementation. It specifies the benchmark
validation, related-task assumptions, and negative-transfer controls required
before H50-L14 can be registered. It is a design record, not experimental
evidence.

Local passes are E1 evidence produced by this repository's own evaluator. They
are useful engineering results, but they are not independent replication.

## Reading the results

A hypothesis passes only if every registered criterion passes. A document may
contain encouraging secondary metrics and still record a refutation. Final seed
families are never reused to promote an altered version of the same hypothesis.
