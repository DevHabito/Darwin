# Darwin

Darwin is an evidence-first research project for building and testing small
pieces of a cognitive architecture. The current code can learn limited models,
retain causal histories, plan in synthetic environments, and refuse unsupported
success claims. It is not a conscious system, an artificial person, AGI, or a
recreation of Diana from *Pragmata*.

That distinction matters. This repository is a laboratory, not a demo built to
look more capable than it is.

## Where the project stands

The maintained code is the v50 package under `src/darwin_v50`. It replaced the
older pattern of adding another large standalone script for every idea. Each
v50 capability starts with a falsifiable hypothesis, fixed evaluation rules,
held-out seeds, baselines, and an explicit evidence ceiling.

The strongest results so far are narrow but real:

- causal goal state cannot be promoted by unrelated or false evidence;
- workspace effects require scoped, one-use authorization and explicit consent;
- tabular transition models can support planning on held-out tasks;
- active exploration can outperform equal-budget random exploration;
- probabilistic forecasts can be calibrated before outcomes are observed;
- bounded working memory can adapt while retaining a complete archive;
- a finite history model can compose four-step plans in a deterministic world;
- context order, stochastic dynamics, and reward can be estimated from chosen
  feedback, although the corresponding robustness hypothesis was refuted.

Several learning hypotheses failed. Those failures remain in the record. Darwin
does not turn a partial win into a pass when a pre-registered criterion misses.

## Evidence ledger

| Hypothesis | Question | Result |
| --- | --- | --- |
| H50-L1 | Can a learned transition model solve held-out goal pairs? | Passed locally |
| H50-L2 | Does active exploration beat equal-budget random exploration? | Passed locally |
| H50-L3 | Are hidden-state forecasts calibrated and useful for action? | Passed locally |
| H50-L4 | Can bounded memory adapt to one abrupt regime change? | Passed locally |
| H50-L5 | Does fixed-share multiscale memory beat the best fixed window? | Refuted |
| H50-L6 | Does a pruned run-length posterior improve variable schedules? | Passed locally |
| H50-L7 | Does explicit regime retrieval help when contexts recur? | Refuted |
| H50-L8 | Can online arbitration make retrieved memory reliably useful? | Refuted |
| H50-L9 | Does episodic action memory improve bandit feedback enough? | Refuted |
| H50-L10 | Can learned finite-history dynamics support multistep planning? | Passed locally |
| H50-L11 | Can learned order and reward produce robust stochastic planning? | Refuted |
| H50-L12 | Does online posterior sampling beat registered learned controls? | Refuted |
| H50-L13 | Does information-directed control remove that exploration cost? | Refuted |
| H50-L14 | Can source observations improve prediction in aligned related worlds while gating mismatch? | Passed locally |
| H50-L15 | Can the source-learned prior improve known-alignment contextual decisions while the gate bounds declared mismatch losses? | Passed locally |

“Passed locally” means the implementation met its registered thresholds under
the repository's own automated evaluator. It is E1 evidence, not independent
validation.

The full protocol and every result are in
[`docs/v50`](docs/v50/README.md).

## Quick start

Darwin v50 requires Python 3.11 or newer.

```powershell
py -m pip install -e .
$env:PYTHONPATH = "src"
py -m unittest discover -s tests -v
```

Run an individual laboratory from its registered command, for example:

```powershell
py -m darwin_v50.cognitive_evaluation
py -m darwin_v50.predictive_planning_evaluation
py -m darwin_v50.learned_context_evaluation
```

Do not rerun a final seed set to tune a failed experiment. Seed contamination is
part of the research record.

## Repository map

```text
src/darwin_v50/     Maintained v50 package
tests/              v50 unit, adversarial, and evaluation tests
docs/v50/           Protocol, pre-registrations, and observed results
legacy_modules/     Support modules used by historical prototypes
tools_archive/      Historical migration and repair tools
darwin_*.py         Coupled v47-v49 prototypes kept for compatibility
darwin_home/        Local runtime state; ignored by Git
```

The root-level v47-v49 files are historical prototypes. They remain in place
because many import one another by filename and some launch subprocesses using
relative paths. Moving them without a dedicated compatibility migration would
break working behavior. New work belongs in the v50 package, not in another
root-level versioned script. See [`docs/LEGACY.md`](docs/LEGACY.md).

## Design rules

- Every capability claim must be falsifiable.
- Final evaluation data must be separated from development data.
- Prediction must happen before the evaluated outcome is observed.
- Chosen-action feedback must not contain counterfactual outcomes.
- Baselines, ablations, seeds, and thresholds are fixed before the final run.
- A failed conjunctive criterion means the hypothesis failed.
- Snapshots must replay to the same derived state.
- Local evaluators never count as independent evidence.
- No result in this repository establishes consciousness or personhood.

## Legacy runtime

The older Windows launchers and v47-v49 scripts are preserved for historical
compatibility. They use a local SQLite database under `darwin_home`. Runtime
databases, logs, snapshots, and exports are not source code and are no longer
tracked.

To create a fresh legacy configuration:

```powershell
Copy-Item darwin_home/config.example.json darwin_home/config.json
```

Existing local state is left untouched by this change.

## Latest research result

The pre-registered
[failure audit](docs/v50/EXPERIMENT_017_POSTERIOR_SAMPLING_FAILURE_AUDIT.md)
replicated the deficit on fresh diagnostic worlds and found that transition and
reward parameter sampling, rather than context-order sampling, was the dominant
action-change channel. H50-L13 then tested an information-directed alternative.
It learned the hidden tabular model, improved on posterior sampling, and reached
`0.9760` of oracle reward in the final quarter. It remained below
certainty-equivalent control and failed the registered simultaneous-win rule,
so it is
[refuted](docs/v50/EXPERIMENT_018_INFORMATION_DIRECTED_CONTROL.md).
The subsequent
[failure audit](docs/v50/EXPERIMENT_019_INFORMATION_DIRECTED_FAILURE_AUDIT.md)
ruled out block staleness as the dominant explanation but could not distinguish
posterior-ensemble effects from the randomized mixture strongly enough to
justify another controller. H50-L14 is not registered.

The next research gate is
[cross-world transfer](docs/v50/RESEARCH_NOTE_CROSS_WORLD_TRANSFER.md). Current
agents discard their learned prior when a new world begins, while the existing
world generator does not contain an aligned task-family structure that would
make naive pooling meaningful. The note defines the benchmark and
negative-transfer checks that must pass before a new capability hypothesis can
be registered. It reports no new experimental result.

The first prerequisite
[benchmark](docs/v50/EXPERIMENT_020_CROSS_WORLD_TRANSFER_BENCHMARK.md) has now
passed locally. An evaluator-only exact family prior improved early prediction
on every related validation world and was decisively harmful on unrelated and
adversarial families. That establishes benchmark sensitivity only: Darwin has
not yet learned the prior from source worlds or used transferred knowledge to
control a target. H50-L14 remains unregistered.

The subsequent
[source-learned development run](docs/v50/EXPERIMENT_021_SOURCE_LEARNED_PRIOR_DEVELOPMENT.md)
estimated a prior from chosen outcomes in 16 source tasks. Its compatibility
gate retained a `0.1622840` related-target log-loss gain while reducing large
ungated negative transfer to losses of `0.0028053` and `0.0044137`. The source
budget was 32 times the target budget, the leading configuration was not
reliably separated from the runner-up, and persistence and causal controls are
still missing. This is development evidence, not a passed capability;
H50-L14 remains unregistered.

Independent
[calibration](docs/v50/EXPERIMENT_022_TRANSFER_CALIBRATION.md) subsequently
passed all nine frozen eligibility margins. The candidate closed `0.9456677`
of the evaluator-oracle gap and beat a source-shuffled control, but retained
small measurable losses on incompatible targets and a 32-to-1 source/target
interaction ratio. This permits pre-registration of H50-L14; it still does not
establish a transfer capability.

H50-L14's
[confirmatory run](docs/v50/EXPERIMENT_023_KNOWN_ALIGNMENT_PREDICTIVE_TRANSFER.md)
met all 12 numerical criteria. Its first result wrapper failed after evaluation
but before exposing metrics, so the exact evaluator was repeated to recover the
output. Because that violated the literal one-run rule, the result is recorded
as supportive but procedurally inconclusive. Capability promotion is withheld
pending a fresh independent confirmation.

That exact
[independent confirmation](docs/v50/EXPERIMENT_024_INDEPENDENT_PREDICTIVE_TRANSFER_CONFIRMATION.md)
passed all 12 frozen criteria on fresh seeds `29500–29599` in one clean run,
with no algorithm or threshold change. H50-L14 therefore passes locally for
known-alignment predictive prior transfer. It remains a synthetic tabular E1
result: source training costs 32 times the target budget, negative transfer is
limited rather than eliminated, and policy or reward transfer was not tested.

The next gate is deliberately narrower than reinforcement learning. The
[contextual reward transfer note](docs/v50/RESEARCH_NOTE_CONTEXTUAL_REWARD_TRANSFER.md)
defines an exogenous-context bandit in which prediction can affect a chosen
action and immediate reward. [Experiment 025](docs/v50/EXPERIMENT_025_CONTEXTUAL_CONTROL_BENCHMARK.md)
then passed nine of ten frozen oracle-sensitivity rules, but failed the related
simultaneous-win interval. The benchmark is refuted, H50-L15 is not registered,
and no learned reward-transfer result is claimed.

[Experiment 026](docs/v50/EXPERIMENT_026_CONTEXTUAL_CONTROL_FAILURE_AUDIT.md)
then found expected reward wins in `98.44%` of fresh worlds and realized wins in
`89.06%`. This is consistent with finite binary-reward variation contributing
to the failed interval, but it cannot reverse the refutation.

[Experiment 027](docs/v50/EXPERIMENT_027_CONTEXTUAL_CONTROL_BENCHMARK_REPLICATION.md)
then passed all ten criteria on a fresh 128-world replication with the same
policy, horizon, and thresholds, using a Wilson interval for the binary
robustness rate. Source-learned candidate development is now eligible, but
Experiment 025 remains refuted and H50-L15 remains unregistered.

[Experiment 028](docs/v50/EXPERIMENT_028_SOURCE_LEARNED_CONTEXTUAL_DECISIONS.md)
pre-registers source-learned decision development on fresh seeds with the exact
H50-L14 prior and gate. The development run found positive related reward and a
causal advantage over a shuffled prior, but also significant residual
adversarial loss. It supports calibration, not H50-L15 registration.

[Experiment 029](docs/v50/EXPERIMENT_029_CONTEXTUAL_DECISION_CALIBRATION.md)
passed all 21 conjunctive calibration criteria on fresh seeds. This permits a
confirmatory pre-registration, but adversarial loss remains measurable and
H50-L15 is still unregistered.

[Experiment 030](docs/v50/EXPERIMENT_030_KNOWN_ALIGNMENT_CONTEXTUAL_TRANSFER.md)
passed all 21 criteria on fresh final seeds. Related reward improved, while
residual adversarial loss stayed within the registered tolerance. The claim
includes auxiliary transition feedback and does not assert pure bandit or
multistep control.

[Experiment 031](docs/v50/EXPERIMENT_031_REWARD_ONLY_COMPATIBILITY_DEVELOPMENT.md)
removed that auxiliary transition likelihood from the compatibility gate. The
counterfactual check passed, and related transfer remained positive, but
unrelated and adversarial performance fell significantly below scratch. The
candidate is not eligible for calibration and no new capability is registered.

[Experiment 032](docs/v50/EXPERIMENT_032_COMPATIBILITY_FEEDBACK_FAILURE_AUDIT.md)
compared the dual-channel and reward-only gates directly on paired fresh worlds.
Transition feedback strongly improved adversarial behavior and reduced source
weight under fixed unrelated experience, but unrelated behavioral intervals
crossed zero. The clean general-benefit audit failed `2` of `15` criteria.

[Experiment 033](docs/v50/EXPERIMENT_033_CELLWISE_SAFE_TRANSFER_DEVELOPMENT.md)
replaced the global source weight with independent context-action weights and a
deterministic scratch fallback. The fallback helped its no-fallback ablation,
but localization performed significantly worse than the global gate on both
mismatch classes. The candidate is not eligible for calibration.

The next architectural line is defined by the
[minimum integrated cognitive-cycle note](docs/v50/RESEARCH_NOTE_INTEGRATED_COGNITIVE_CYCLE.md).
It limits the first integration to an externally supplied goal, the H50-L10
history model and planner, explicit per-step kernel evidence, and agent-state
restart. No integrated capability is registered yet.

[Experiment 034](docs/v50/EXPERIMENT_034_INTEGRATED_CYCLE_DEVELOPMENT.md)
completed that first integrated development benchmark. The restarted cycle
solved all `768` tasks, exactly matched its uninterrupted twin, and passed all
frozen causal-integrity checks; the rotated control solved none. This supports
a separate calibration stage, but the experiment had no capability threshold
and registers no integrated capability.

[Experiment 035](docs/v50/EXPERIMENT_035_INTEGRATED_DURABILITY_CALIBRATION.md)
completed the stronger calibration. All 17 criteria passed across `1,536`
tasks and four balanced recovery boundaries, including deterministic
environment reconstruction by causal replay. This permits confirmatory
pre-registration but does not register H50-L16.

[Experiment 036](docs/v50/EXPERIMENT_036_DETERMINISTIC_INTEGRATED_CYCLE_CONFIRMATION.md)
passed all 17 unchanged criteria on `1,536` fresh final tasks, and the local
kernel accepted the complete conjunction. H50-L16 therefore passes locally at
E1 for deterministic externally-goaled integrated planning with local
replay-based recovery. This is not a claim of online learning, endogenous
goals, open-world autonomy, consciousness, or AGI.

The next line is narrower than general continual learning. The
[online alignment note](docs/v50/RESEARCH_NOTE_ONLINE_ALIGNMENT_ADAPTATION.md)
keeps the transition prior frozen and learns only a three-value latent action
alignment after chosen-action observations. [Experiment 037](docs/v50/EXPERIMENT_037_ONLINE_ALIGNMENT_DEVELOPMENT.md)
completed a base–shifted–recurrent–novel development schedule. The candidate
matched the oracle on all `768` goals and adapted after one observation at each
boundary, while frozen and cumulative controls solved half and shifted evidence
solved none. [Experiment 038](docs/v50/EXPERIMENT_038_ONLINE_ALIGNMENT_CALIBRATION.md)
passed its frozen 20-criterion conjunction on `1,536` disjoint calibration
tasks. The result is eligible for confirmatory pre-registration, but H50-L17
is not registered. [Experiment 039](docs/v50/EXPERIMENT_039_ONLINE_ALIGNMENT_CONFIRMATION.md)
pre-registers the unchanged claim on a fresh final family; no final seed has
been run.

## Contributing

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before changing a claim, evaluator, or
experiment. Plain language is preferred. Describe what the code establishes,
what it does not establish, and how somebody else could prove the claim wrong.
