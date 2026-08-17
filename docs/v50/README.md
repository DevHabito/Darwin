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
| [Language boundary](RESEARCH_NOTE_LANGUAGE_BOUNDARY.md) | Provider-neutral understanding, expression, and consultation contracts |

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

The first prerequisite is pre-registered as
[Experiment 020](EXPERIMENT_020_CROSS_WORLD_TRANSFER_BENCHMARK.md). It tests
whether an evaluator-only oracle can distinguish related from incompatible
families. The benchmark passed all registered sensitivity rules: the exact
family prior helped on every related validation world and harmed incompatible
targets. This validates the benchmark, not Darwin's ability to learn or
transfer the prior. H50-L14 remains unregistered.

[Experiment 021](EXPERIMENT_021_SOURCE_LEARNED_PRIOR_DEVELOPMENT.md)
pre-registers the next development step: estimate a Beta-Binomial prior only
from source observations and combine it with scratch learning through an online
compatibility gate. It has no confirmatory pass rule and cannot promote
H50-L14.

The development grid selected 16 source tasks, eight cycles, and initial source
weight `0.5`. Related log-loss improvement was `0.1622840`; the gate limited
unrelated and adversarial losses to `0.0028053` and `0.0044137`. The source
budget was 2,048 interactions, 32 times the target budget, and the top two
configurations were not cleanly separated by a post-selection bootstrap.
H50-L14 remains unregistered.

After selection, a fixed source-prior permutation was added as a causal control
and the gated model gained replay-checked snapshots. Snapshot prior digests
detect unilateral changes but are not authenticated signatures. These are
engineering prerequisites, not new behavioral evidence.

[Experiment 022](EXPERIMENT_022_TRANSFER_CALIBRATION.md) freezes the selected
candidate and pre-registers independent calibration margins. Calibration may
make a confirmatory H50-L14 protocol eligible, but cannot itself promote the
capability.

All nine calibration margins passed. Related improvement was `0.1595617`, the
candidate beat the source-shuffled control by `0.1643268`, and it closed
`0.9456677` of the oracle gap. Negative transfer remained measurable at
`0.0060205` and `0.0050725`. The result makes H50-L14 eligible for
pre-registration; it is not a capability pass.

| Hypothesis | Experiment | Result |
| --- | --- | --- |
| H50-L14 | [023 — known-alignment predictive transfer](EXPERIMENT_023_KNOWN_ALIGNMENT_PREDICTIVE_TRANSFER.md) and [024 — independent confirmation](EXPERIMENT_024_INDEPENDENT_PREDICTIVE_TRANSFER_CONFIRMATION.md) | Passed locally |

H50-L14 passed all 12 numerical criteria, but the output wrapper failed after
the first completed run and the exact evaluator was repeated to recover the
unseen result. Because this violated the literal one-run rule, capability
promotion is withheld until a fresh independent confirmation.

[Experiment 024](EXPERIMENT_024_INDEPENDENT_PREDICTIVE_TRANSFER_CONFIRMATION.md)
pre-registers that exact confirmation on fresh seeds `29500–29599`, without any
algorithm or threshold change. It passed all 12 criteria in one clean run.
H50-L14 is therefore passed locally at E1 for the narrow known-alignment
predictive-transfer claim.

## Next research gate

H50-L14 did not test whether better prediction changes an action or earns
reward. The [contextual reward transfer note](RESEARCH_NOTE_CONTEXTUAL_REWARD_TRANSFER.md)
therefore narrows the next step to an exogenous-context bandit. H50-L15 is not
registered.

[Experiment 025](EXPERIMENT_025_CONTEXTUAL_CONTROL_BENCHMARK.md) tested an
evaluator-only oracle sensitivity check on fresh validation seeds. Nine of ten
criteria passed, but the related simultaneous-win interval missed its frozen
lower bound. The benchmark is refuted, learned-candidate development remains
blocked, and H50-L15 remains unregistered.

[Experiment 026](EXPERIMENT_026_CONTEXTUAL_CONTROL_FAILURE_AUDIT.md)
used fresh seeds to separate expected action value from realized binary reward
noise. Expected reward improved in `0.984375` of worlds, while realized and
simultaneous wins occurred in `0.890625`; `0.09375` had an expected win without
a realized win. This is consistent with finite-reward variation, but the audit
has no promotion rule and Experiment 025 remains refuted.

[Experiment 027](EXPERIMENT_027_CONTEXTUAL_CONTROL_BENCHMARK_REPLICATION.md)
ran a fresh 128-world replication with the same policy, horizon, and ten
thresholds, replacing only the binary-rate interval with a Wilson score
interval. All ten criteria passed. This authorizes source-learned candidate
development, but cannot reverse Experiment 025 or register H50-L15.

[Experiment 028](EXPERIMENT_028_SOURCE_LEARNED_CONTEXTUAL_DECISIONS.md)
pre-registers the first source-learned decision development on fresh seeds. It
uses the exact H50-L14 prior and gate with scratch, ungated, shuffled, pooled,
and oracle controls. Related reward improved by `1.90625`, and the shuffled
control supported a causal alignment effect. Adversarial reward still fell by
`1.1875`. The result supports separate calibration but is not a capability
pass; H50-L15 remains unregistered.

[Experiment 029](EXPERIMENT_029_CONTEXTUAL_DECISION_CALIBRATION.md)
pre-registers a fresh calibration with 21 conjunctive related-effect,
negative-transfer, gate-benefit, weight, integrity, and cost criteria. Status:
all 21 criteria passed. The result makes a confirmatory protocol eligible, but
adversarial loss remains significant and H50-L15 is still unregistered.

| Hypothesis | Experiment | Result |
| --- | --- | --- |
| H50-L15 | [030 — known-alignment contextual transfer](EXPERIMENT_030_KNOWN_ALIGNMENT_CONTEXTUAL_TRANSFER.md) | Passed locally |

Experiment 030 passed all 21 criteria in one final execution. Related reward
improved by `1.703125`, and the candidate beat the shuffled causal control by
`2.101563` rewards. Adversarial reward remained `0.71875` below scratch but
inside the registered tolerance. The claim is contextual decision transfer
with auxiliary transition feedback, not pure bandit or multistep control.

[Experiment 031](EXPERIMENT_031_REWARD_ONLY_COMPATIBILITY_DEVELOPMENT.md) is a
completed development study that removed transition likelihood from the gate
while leaving the H50-L15 learner and policy unchanged. Exact counterfactual
transition-blindness replay passed, and related reward improved by `1.625`.
Unrelated reward fell by `1.5625`, however, and adversarial reward fell by
`6.46875`. The candidate is not eligible for calibration and registers no new
capability claim.

[Experiment 032](EXPERIMENT_032_COMPATIBILITY_FEEDBACK_FAILURE_AUDIT.md) is a
completed paired failure audit. Transition feedback improved adversarial reward
by `7.1875` and lowered source weight under fixed unrelated and adversarial
experience. Unrelated behavioral reward and pseudo-regret intervals crossed
zero, however. The clean general-benefit conclusion failed `2` of `15` frozen
criteria and cannot register a capability.

[Experiment 033](EXPERIMENT_033_CELLWISE_SAFE_TRANSFER_DEVELOPMENT.md) is a
completed development study of local compatibility and safe fallback. The
fallback improved adversarial reward over its local no-fallback ablation by
`0.9375`, but the candidate lost `0.8125` unrelated and `2.03125` adversarial
rewards against the global gate. It is not eligible for calibration and
registers no capability.

The [minimum integrated cognitive-cycle note](RESEARCH_NOTE_INTEGRATED_COGNITIVE_CYCLE.md)
defines the next architecture boundary. It records the interface audit, adds an
explicit multi-action goal-continuation prerequisite, and limits the first
benchmark to the H50-L10 learned history model, causal kernel, replay-checked
agent checkpoint, and evaluator-owned synthetic environment. It is not a
capability claim.

[Experiment 034](EXPERIMENT_034_INTEGRATED_CYCLE_DEVELOPMENT.md) completed the
first development benchmark for that composition. The restarted candidate
solved all `768` tasks, the rotated control solved none, and random solved `33`.
Restart behavior matched the uninterrupted twin exactly, and every frozen
causal-integrity rate was `1.0`. This supports separate calibration, but the
experiment had no pass threshold and registers no integrated capability.

[Experiment 035](EXPERIMENT_035_INTEGRATED_DURABILITY_CALIBRATION.md) completed
that calibration on fresh seeds. All 17 criteria passed: the candidate and all
four restart modes solved every one of `1,536` tasks, the rotated control solved
none, and every recovery and causal-integrity rate was `1.0`. The result permits
confirmatory pre-registration but does not register H50-L16.

| Hypothesis | Experiment | Result |
| --- | --- | --- |
| H50-L16 | [036 — deterministic integrated-cycle confirmation](EXPERIMENT_036_DETERMINISTIC_INTEGRATED_CYCLE_CONFIRMATION.md) | Passed locally |
| H50-L17 | [039 — online action-alignment confirmation](EXPERIMENT_039_ONLINE_ALIGNMENT_CONFIRMATION.md) | Passed locally |

Experiment 036 retained the unchanged candidate and all 17 calibration
criteria. All criteria passed on `1,536` fresh final tasks, every recovery mode
was exact, and the local kernel accepted the conjunction. H50-L16 is registered
at E1 only for deterministic externally-goaled integrated planning with local
replay-based recovery.

The [online alignment research note](RESEARCH_NOTE_ONLINE_ALIGNMENT_ADAPTATION.md)
defines the next boundary without weakening the H50-L10 trace invariant. A
separate latent tracker may update after chosen-action observations while the
transition prior remains frozen.

[Experiment 037](EXPERIMENT_037_ONLINE_ALIGNMENT_DEVELOPMENT.md) completed the
first base–shifted–recurrent–novel development schedule. The candidate and
oracle solved all `768` tasks, frozen and cumulative solved `384`, shifted
evidence solved none, and every causal-integrity rate was `1.0`. Adaptation cost
one observation at each boundary. The result supports calibration but does not
register H50-L17.

[Experiment 038](EXPERIMENT_038_ONLINE_ALIGNMENT_CALIBRATION.md) retained the
unchanged candidate on `64` disjoint worlds. All 20 frozen criteria passed:
candidate and oracle success were `1.0`, registered control gaps were exact,
adaptation took one observation, and every causal-integrity rate was `1.0`.
The result authorizes confirmatory pre-registration but does not register
H50-L17.

[Experiment 039](EXPERIMENT_039_ONLINE_ALIGNMENT_CONFIRMATION.md) retained the
same candidate, controls, 20-criterion conjunction, and interpretation ceiling
on `64` fresh worlds. Every criterion passed, and the local kernel accepted the
conjunction. H50-L17 is registered at E1 only for deterministic online
action-alignment inference with a frozen transition prior.

## Language conformance development

[Experiment 040](EXPERIMENT_040_LANGUAGE_CONFORMANCE_INFRASTRUCTURE.md) adds a
100-case Brazilian Portuguese development corpus, strict loader, language and
contract-safety metrics, pure baseline, and evaluator sensitivity controls. No
language model was evaluated. The corpus was labelled by the project authors,
has no independent review or held-out partition, and registers no capability.

[Experiment 041](EXPERIMENT_041_ANNOTATION_PROTOCOL.md) freezes 150 new,
unlabeled Brazilian Portuguese candidate inputs and adds a blind human-review
protocol, categorical signal anchors, strict panel validation, and per-field
agreement analysis. Independent reviewers have not yet supplied labels, so no
calibration corpus has been promoted and no model is eligible for evaluation.

[Experiment 042](EXPERIMENT_042_CALIBRATION_PROMOTION_PROTOCOL.md)
pre-registers the adjudicator eligibility, permitted exclusions, pairwise
agreement thresholds, failure rules, calibration manifest, and downstream
offline-model screen before any human labels or agreement values exist. It is
not executed and adds no evidence; independent annotation remains the blocking
next step.

## Desktop runtime development

[Experiment 043](EXPERIMENT_043_PERSISTENT_DESKTOP_RUNTIME.md) pre-registers a
headless, pure-mode desktop runtime foundation. It freezes clean and interrupted
restart semantics, explicit activation, single-instance leasing, authority
isolation, automated admission checks, and a later 14-day Windows durability
campaign. The candidate was implemented after pre-registration and all 448
local and 448 Windows CI tests pass. Automated admission is complete, but the
real-machine campaign has not started. No cognitive-continuity claim is
registered. The language-calibration line remains independently blocked on
human annotation.

## Conversational development

[Experiment 044](EXPERIMENT_044_CONVERSATIONAL_DEVELOPMENT_RUNTIME.md)
pre-registers a separate, non-persistent conversation surface. A backend and
model must be selected explicitly; OpenAI and local modes never replace one
another silently. Successful turns require model-backed `UNDERSTAND` and
`EXPRESS` operations, while the deterministic policy keeps interpretations
unverified and exposes no persistent-memory, goal, RZS, sigma, identity, or
action mutation path. This is development infrastructure, not language
calibration or evidence that Darwin is more than an LLM-centered system. Setup
is documented in the
[conversational development guide](CONVERSATIONAL_DEVELOPMENT_GUIDE.md).

[Experiment 045](EXPERIMENT_045_PORTABLE_LOCAL_LANGUAGE_SEED.md)
pre-registers the next provider-free path: a replaceable, quantized local
language seed behind the same authority boundary. It targets a model artifact
no larger than 600 MiB, an injectable transport that can move from a loopback
desktop harness to an in-process mobile runtime, and no mandatory account,
subscription, API key, or per-message fee. The candidate and live tests remain
separate from engineering admission. The portable integration passed its
hermetic engineering gate;
the exact commands and limits are preserved in the
[E045 engineering admission record](results/EXPERIMENT_045_ENGINEERING_ADMISSION.json).
The exact first live pairing later
[failed closed](results/EXPERIMENT_045_FIRST_LIVE_TURN.json) before model output
because llama.cpp could not initialize the schema grammar around the Qwen3
non-thinking prefill. E045 is not a working-conversation, mobile-suitability,
or language-quality result.

[Experiment 046](EXPERIMENT_046_AUTHENTICATED_NATIVE_COMPLETION_REPAIR.md)
pre-registers a prospective repair without altering E045's failure. It keeps
the exact model, runtime, schemas, limits, and first sentence, replaces only the
broken chat-completions integration with llama.cpp's native template and
completion endpoints, and adds an ephemeral local API key after E045 exposed a
wildcard-CORS warning. The implementation passed its focused mocks, but no live
repair turn was run:
the fixed b10470 runtime
lacked the registered special-token input protection. The
[E046 engineering gate](results/EXPERIMENT_046_ENGINEERING_ADMISSION.json)
therefore failed before another live turn; E045 remains failed as well.

[Experiment 047](EXPERIMENT_047_CONTROL_TOKEN_REJECTION_REPAIR.md)
pre-registers a build-compatible repair: the same authenticated native
transport rejects the frozen model's control markers before templating rather
than claiming that b10470 supports a newer escape option. It retains the exact
artifacts, schemas, limits, and first sentence. Implementation and live testing
showed two gateway-valid inference stages and a correct adversarial rejection,
but the Windows pipe did not preserve the exact registered Unicode sentence.
E047 therefore failed rather than being promoted.

[Experiment 048](EXPERIMENT_048_UTF8_CONSOLE_BOUNDARY_REPAIR.md) pre-registers
a narrow UTF-8 standard-stream repair. It freezes the same inference path and
forbids character replacement, model changes, response post-processing, and
provider fallback. Its engineering gate passed 24 focused tests and the full
repository suite (496 passes plus the existing Windows symlink skip). The
[live record](results/EXPERIMENT_048_FIRST_LIVE_TURN.json) establishes exact
UTF-8 transport, one schema-valid local turn, and a correct adversarial
rejection at zero provider cost. The observed reply was still weak, so language
quality remains unestablished.

[Experiment 049](EXPERIMENT_049_LOCAL_CONVERSATION_DEVELOPMENT_SCREEN.md)
pre-registers an eight-turn, multi-topic Portuguese development screen for the
unchanged local pair. It preserves raw replies and failure modes but cannot
promote a language-quality claim. Execution remains pending.

Local passes are E1 evidence produced by this repository's own evaluator. They
are useful engineering results, but they are not independent replication.

## Reading the results

A hypothesis passes only if every registered criterion passes. A document may
contain encouraging secondary metrics and still record a refutation. Final seed
families are never reused to promote an altered version of the same hypothesis.
