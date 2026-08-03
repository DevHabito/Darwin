# Darwin v50 research protocol

## Purpose

Darwin v50 is a small causal kernel and a sequence of controlled learning
experiments. It does not inherit cognitive claims from the v47-v49 database and
does not treat implementation volume as evidence of intelligence.

The protocol has two jobs:

1. make false success difficult to represent in the kernel;
2. make learning claims easy to refute with registered baselines and held-out
   evaluation.

## Evidence levels

- **E0 — implementation:** code exists or a unit test exercises an internal
  function. No behavioral claim follows.
- **E1 — local automated evaluator:** a registered benchmark runs in this
  repository with separated data, baselines, and a falsifiable decision.
- **E2 — scoped external effect:** the system produces and observes a real,
  limited effect outside its in-memory model. The claim applies only to that
  effect.
- **E3 — independent evaluation:** a separately controlled evaluator holds the
  task data and scoring authority. No current learning experiment reaches E3.

Evidence levels describe the source of support, not how impressive a result
looks. A perfect local score remains E1.

## Kernel invariants

### H50-K1 — causal lineage

Every non-root event references an existing parent in the same session. An
observation of an action references the event that dispatched that exact action.

Refutation: an orphan event, cross-session parent, or observation without the
matching dispatch.

### H50-G1 — no false success

A goal can become `succeeded` only when it is waiting for an observation and the
observation matches its goal, expected action, declared source, and persisted
condition.

Refutation: any success transition with one of those checks false.

### H50-G2 — goal isolation

Evidence for one goal or action cannot complete another open goal.

### H50-R1 — restart recovery

After process restart, goal state, version, condition, and causal lineage remain
identical.

### H50-C1 — single conclusion

Concurrent observations can produce at most one success event for a goal.

## Effect and authority invariants

### H50-E1 — correlated external effect

A workspace action may affect only its declared root. The observation includes
the action digest, correlation identifiers, measured metrics, timestamp, and
nonce. Registered sources require a valid signature.

### H50-E2 — narrow application confinement

The adapter exposes create-new-text-file and inspect-file operations only. It
does not expose shell, network, deletion, overwrite, or arbitrary directories.
Path traversal, absolute paths, missing parents, and symbolic-link escapes are
rejected.

### H50-A1 — single-use capability

Execution requires a signed, scoped, registered, unexpired capability bound to
the exact session, goal, action, digest, adapter, and workspace. Consumption is
transactional and happens before the effect.

### H50-U1 — explicit consent

Capability registration requires a prior signed consent decision bound to the
same action and resource scope. Production policy requires an interactive TTY
channel and Ed25519 authority. Automated test consent and HMAC are rejected
unless explicitly enabled.

### H50-P1 — process separation

The fixed workspace worker runs in another process with `shell=False`. It does
not receive the approval secret. Running under the same Windows user is process
separation, not a security boundary.

## Learning protocol

Every new H50-L hypothesis must specify, before final evaluation:

- the capability being claimed;
- the environment and information boundary;
- development, calibration, and final seed families;
- baselines and causal ablations;
- selection and tie-breaking rules;
- metrics and conjunctive thresholds;
- persistence and tamper checks;
- conditions that refute the hypothesis;
- the maximum evidence level allowed.

Predictions must precede evaluated outcomes. An action learner may archive only
feedback from its executed action. Hidden world parameters and counterfactual
outcomes may be used by the evaluator for scoring, never by the candidate.

After a final run, its seeds are contaminated. They may be analyzed to explain a
result but cannot be reused to promote an altered version of the same claim.

## Learning ledger

### H50-L1 — learned transitions

A tabular transition model was trained by exhaustive census and evaluated on
held-out start-goal pairs. Model success was `1.0`, random success `0.1854167`,
untrained success `0.0`, and known-transition accuracy `1.0`.

Decision: **passed locally**. This measured recombination of known deterministic
dynamics, not generalization to new dynamics. See
[Experiment 005](EXPERIMENT_005_COGNITIVE_LEARNING_LAB.md).

### H50-L2 — active exploration

With thirty actions per world, frontier exploration achieved `0.9962963`
coverage and `0.9979167` held-out task success. Equal-budget random exploration
achieved `0.6648148` and `0.70625`.

Decision: **passed locally**. The exploration rule was hand-written. See
[Experiment 006](EXPERIMENT_006_ACTIVE_EXPLORATION.md).

### H50-L3 — calibrated uncertainty and information action

A Beta-Bernoulli model achieved Brier `0.1468837` and ten-bin ECE `0.0159365`.
A selective policy inspected `0.505` of episodes and beat both fixed inspection
policies in utility.

Decision: **passed locally**. The hidden-state world, cost, and policy thresholds
were designed by hand. See
[Experiment 007](EXPERIMENT_007_PARTIAL_OBSERVABILITY_AND_CALIBRATION.md).

### H50-L4 — abrupt temporal adaptation

A two-window detector found every registered change with no early world-level
alarm and maximum delay 57. Adaptive total Brier improved by `0.1116308` over
stationary memory; archive and snapshot rates were `1.0`.

Decision: **passed locally**. A fixed-window baseline still scored better than
the adaptive candidate. See
[Experiment 008](EXPERIMENT_008_TEMPORAL_ADAPTATION.md).

### H50-L5 — multiscale concept drift

The fixed-share candidate won every final world but improved mean total Brier by
only `0.0017292` over the selected fixed window, below the registered `0.002`.

Decision: **refuted**. See
[Experiment 009](EXPERIMENT_009_MULTISCALE_CONCEPT_DRIFT.md).

### H50-L6 — Bayesian run length

A pruned run-length posterior improved total Brier by `0.0034053` over the fixed
window and won every final world while staying within regional limits.

Decision: **passed locally**. The mean posterior size sat close to the pruning
cap. See [Experiment 010](EXPERIMENT_010_BAYESIAN_RUN_LENGTH.md).

### H50-L7 — recurrent regime retrieval

Retrieval precision was `0.9801325` and novelty abstention coverage `0.80`, but
retrieval worsened recurrence Brier by `0.0022052` against the H50-L6 ablation.

Decision: **refuted**. Correct recognition did not cause useful reuse. See
[Experiment 011](EXPERIMENT_011_RECURRENT_REGIME_RETRIEVAL.md).

### H50-L8 — adaptive memory arbitration

Online expert weighting reduced the damage of fixed retrieval and slightly
improved total Brier, but recurrence improvement against H50-L6 was
`-0.0000504` instead of the required positive gain.

Decision: **refuted**. See
[Experiment 012](EXPERIMENT_012_ADAPTIVE_MEMORY_ARBITRATION.md).

### H50-L9 — episodic contextual action memory

The candidate reached retrieval precision `0.9878658`, perfect novelty
abstention, and total gain `0.0315509` over the local learner. The required gain
was `0.04`, and three family-specific thresholds also failed.

Decision: **refuted**. See
[Experiment 013](EXPERIMENT_013_EPISODIC_CONTEXTUAL_ACTION_MEMORY.md).

### H50-L10 — predictive history planning

The learned finite-history model covered and predicted every registered
state-action pair, solved all 2,400 four-step tasks, and beat reactive, myopic,
action-permuted, and random ablations.

Decision: **passed locally**. History order was supplied, dynamics were
deterministic, and reward was not learned. See
[Experiment 014](EXPERIMENT_014_PREDICTIVE_HISTORY_PLANNING.md).

### H50-L11 — learned order, dynamics, and reward

The selected model recovered exact context order in `0.96` of worlds, achieved
transition and reward MAE `0.0634895` and `0.0558084`, and reached `0.9738612`
of oracle return. It passed every mean comparison but beat all relevant
ablations simultaneously in only `0.55` of worlds, below `0.70`.

Decision: **refuted**. See
[Experiment 015](EXPERIMENT_015_LEARNED_CONTEXT_REWARD_PLANNING.md).

### H50-L12 — online posterior-sampling control

The hypothesis removed the fixed random training phase. The posterior-sampling
agent learned context order, dynamics, and reward while acting. It recovered
the exact order in `0.96` of worlds and reached `0.9564634` of oracle reward in
the final quarter, but cumulative exploration cost remained too high. Mean
reward was `0.016421875` below certainty-equivalent control, improvement over
epsilon-greedy was only `0.0033671875` against a required `0.005`, and the
simultaneous learned-baseline win rate was `0.04` against `0.60`.

Decision: **refuted**. Final seeds `22100–22199` are retired. See
[Experiment 016](EXPERIMENT_016_ONLINE_POSTERIOR_SAMPLING_CONTROL.md).

### H50-L12 failure audit

Fresh diagnostic seeds `23200–23231` reproduced the candidate's reward deficit:
candidate minus certainty-equivalent reward was `-0.0162597656`, with a 95%
paired bootstrap interval of `[-0.0219726562, -0.0104248047]`. The parameter
channel changed `0.1313232422` of actions, against `0.0044677734` for the order
channel. In quarters three and four, the order channel was exactly zero while
parameter disagreement persisted.

Decision: diagnostic only; no capability promoted. The audit seeds are retired.
See [Experiment 017](EXPERIMENT_017_POSTERIOR_SAMPLING_FAILURE_AUDIT.md).

Protocol deviation: Experiment 017 said its diagnostic seeds would not choose
H50-L13's algorithm, but its parameter-channel result subsequently motivated
the H50-L13 design. The audit is therefore adaptive design evidence, not
independent controller evidence. H50-L13's disjoint final refutation remains
valid; a pass would have required another independent confirmation.

### H50-L13 — information-directed online control

H50-L13 is pre-registered to test a blockwise Monte Carlo approximation of
information-directed sampling. It targets information about the current
posterior-optimal action and must improve on certainty-equivalent,
posterior-sampling, epsilon-greedy, and random baselines under a conjunctive
held-out decision rule.

The selected 16-action controller earned `0.274296875`, improved by
`0.00821875` over same-cadence posterior sampling, and reached `0.9760024613` of
oracle final-quarter reward. It remained `0.0071796875` below
certainty-equivalent control, missed the registered `0.010` posterior-sampling
margin, and won all learned-baseline comparisons in only `0.14` of worlds.

Decision: **refuted**. Final seeds `24100–24199` are retired. See
[Experiment 018](EXPERIMENT_018_INFORMATION_DIRECTED_CONTROL.md).

### H50-L13 failure audit

Diagnostic seeds `25200–25231` reproduced the candidate's deficit against
certainty-equivalent control at `-0.0062255859`, with a 95% paired bootstrap
interval of `[-0.0102294922, -0.0019287109]`. Mean disagreement was
`0.0312744141` for block staleness, `0.0522460938` for the posterior ensemble,
and `0.0556640625` for the information-directed mixture. Both ensemble and
mixture exceeded staleness, but their paired difference included zero.

Decision: diagnostic only; channel dominance unresolved. H50-L14 is not
registered. Audit seeds are retired. See
[Experiment 019](EXPERIMENT_019_INFORMATION_DIRECTED_FAILURE_AUDIT.md).

### Cross-world transfer gate

The current online model creates independent `Beta(1, 1)` priors and a new
archive for every world. Existing worlds randomize both actionable dynamics and
reward mappings, so their shared marginal structure does not by itself provide
useful aligned transfer.

The next research step is therefore a benchmark prerequisite, not H50-L14. It
must define an explicit related-task family, show that an oracle family prior
has an early-target advantage on related but not unrelated targets, and include
negative-transfer controls. Only then may a hierarchical prior candidate and
final seed families be pre-registered. See the
[cross-world transfer research gate](RESEARCH_NOTE_CROSS_WORLD_TRANSFER.md).

[Experiment 020](EXPERIMENT_020_CROSS_WORLD_TRANSFER_BENCHMARK.md) passed this
prerequisite on validation seeds `27100–27131`. Related log-loss improvement
was `0.1591006`, while unrelated and adversarial improvements were
`-0.1984957` and `-0.3781785`. The result shows that the synthetic benchmark is
sensitive to prior compatibility. The evaluator supplied the oracle prior, so
this is not evidence that Darwin learned or transferred it. H50-L14 remains
unregistered.

[Experiment 021](EXPERIMENT_021_SOURCE_LEARNED_PRIOR_DEVELOPMENT.md) then fit a
Beta-Binomial prior from source observations only. Its selected compatibility
gate improved related-target log loss by `0.1622840` while limiting unrelated
and adversarial losses to `0.0028053` and `0.0044137`. This required 2,048
source interactions for 64 target interactions. The top-two selection interval
crossed zero, and confirmatory controls and persistence are not implemented.
Decision: development only; H50-L14 remains unregistered.

Post-development implementation added a source-shuffled prior control and
replay-checked gated-model snapshots. Snapshot prior digests are integrity
checks, not authentication. No confirmatory seed was used for these changes.

[Experiment 022](EXPERIMENT_022_TRANSFER_CALIBRATION.md) froze the candidate and
passed all nine independent calibration margins on seeds `27500–27531`.
Related log-loss improvement was `0.1595617`, candidate-minus-shuffled was
`0.1643268`, and oracle-gap closure was `0.9456677`. Unrelated and adversarial
improvements remained negative at `-0.0060205` and `-0.0050725`, within the
registered `-0.01` tolerance. Decision: H50-L14 may now be pre-registered, but
no capability has passed.

### H50-L14 — known-alignment predictive transfer

H50-L14 is pre-registered in
[Experiment 023](EXPERIMENT_023_KNOWN_ALIGNMENT_PREDICTIVE_TRANSFER.md). It
tests whether a prior learned from 16 aligned source tasks improves held-out
related transition-and-reward prediction while a Bayesian compatibility gate
limits loss on unrelated and adversarial targets. Final seeds are
`28500–28599`; 12 behavioral and integrity criteria are conjunctive.

All 12 numerical criteria passed on final seeds `28500–28599`. The first
completed execution produced no visible metrics because the result wrapper
raised `AttributeError`; the exact deterministic evaluator was repeated without
any adaptive change to recover its output. This made the final execution count
two and violated the literal one-run rule.

Decision: numerical support recorded, capability promotion withheld. A fresh,
pre-registered independent confirmation is required. See Experiment 023.

[Experiment 024](EXPERIMENT_024_INDEPENDENT_PREDICTIVE_TRANSFER_CONFIRMATION.md)
freezes an exact independent repetition on seeds `29500–29599` with bootstrap
seed `30100`. No method or threshold changed after Experiment 023. Status:
all 12 criteria passed in one clean execution. Related improvement was
`0.1643499`, candidate-minus-shuffled was `0.1686076`, and oracle-gap closure
was `0.9234612`. Unrelated and adversarial improvements were `-0.0042322` and
`-0.0043924`, within the registered tolerance. Integrity rates were `1.0`.

Decision: **H50-L14 passed locally** for known-alignment predictive prior
transfer in the synthetic tabular family. This is E1 local evidence and does
not establish policy transfer, reward improvement, unknown alignment, or
general lifelong learning.

### Contextual reward transfer gate

The next question is restricted to immediate action selection under exogenous
contexts. It is a contextual bandit, not multistep control. H50-L15 remains
unregistered.

[Experiment 025](EXPERIMENT_025_CONTEXTUAL_CONTROL_BENCHMARK.md) pre-registers
an evaluator-only oracle sensitivity check on seeds `30300–30331`. It freezes
64 target interactions, epsilon `0.10`, paired reward and pseudo-regret
comparisons, 5,000 bootstrap resamples, and ten conjunctive criteria before any
validation execution. Passing it can only authorize learned-candidate
development. See the
[contextual reward transfer gate](RESEARCH_NOTE_CONTEXTUAL_REWARD_TRANSFER.md).

The validation was executed once after commit `793c686`. Nine criteria passed,
including positive related reward and pseudo-regret intervals, but the related
simultaneous-win interval was [`0.65625`, `0.9375`] against a frozen lower bound
of `0.75`. Decision: **refuted benchmark**. Candidate development is blocked,
the validation seeds are retired, and H50-L15 remains unregistered.

[Experiment 026](EXPERIMENT_026_CONTEXTUAL_CONTROL_FAILURE_AUDIT.md) freezes a
diagnostic repetition on fresh related seeds `31000–31127`. It compares the
sign of realized reward with evaluator-only expected reward improvement under
the unchanged policy. The audit has no pass or promotion rule.

The audit found a `0.984375` expected-reward win rate and a `0.890625`
realized/simultaneous win rate. In `0.09375` of worlds, expected reward improved
without a positive realized difference. This is consistent with finite binary
reward noise contributing to the miss, but cannot reverse Experiment 025.

[Experiment 027](EXPERIMENT_027_CONTEXTUAL_CONTROL_BENCHMARK_REPLICATION.md)
freezes a new 128-world-per-condition validation on seeds `32000–32127`. The
policy, 64-interaction horizon, task family, and ten thresholds remain fixed.
Continuous means retain paired bootstrap intervals; the binary simultaneous-win
rate uses a 95% Wilson interval. All ten criteria passed in one execution. The
related reward improvement was `1.851563`, pseudo-regret reduction was
`2.028021`, and the simultaneous-win Wilson interval was [`0.806574`,
`0.921574`]. Decision: passed benchmark sensitivity locally; learned-candidate
development is eligible, while Experiment 025 remains refuted and H50-L15
remains unregistered.

[Experiment 028](EXPERIMENT_028_SOURCE_LEARNED_CONTEXTUAL_DECISIONS.md) freezes
source-learned candidate development on seeds `33000–33031`. It reuses the
H50-L14 source estimator, initial gate weight, 2,048 source interactions, and
the Experiment 027 64-interaction epsilon-greedy target policy. The decision
uses reward estimates, while the frozen compatibility gate observes both
chosen-action transition and reward outcomes. Status: registered development,
not run; there is no pass rule or H50-L15 registration.

## Standing safety boundary

- The kernel records dispatch and evidence; it does not expose an arbitrary
  command interface.
- Workspace execution has a fixed operation set and a declared root.
- Grants and consent receipts are bound, registered, and single-use.
- JSON is strict; duplicate keys, `NaN`, and infinity are rejected where
  persisted state is accepted.
- Events are immutable and goal updates use optimistic versions.
- Accepted nonces cannot be replayed.
- A consumed grant is not retried automatically after a crash.
- A legacy database without a v50 schema identity is refused.
- HMAC proves possession of a secret, not truth of a measurement.
- Ed25519 separates signing authority from verification but does not prove who
  operated the signer or whether they understood the request.
- The current worker has no AppContainer, restricted token, hypervisor, or
  verified network boundary.
- Structurally replayed snapshots are not cryptographically authenticated.
- Runtime databases and session exports are local data and must not be committed.

## Validation

From the repository root:

```powershell
py -m pip install -e .
$env:PYTHONPATH = "src"
py -m unittest discover -s tests -v
```

One symlink test may be skipped on Windows when the account lacks the privilege
to create symbolic links. That skip does not count as evidence that symlink
escape is impossible; it records that the adversarial case could not be created
in that environment.
