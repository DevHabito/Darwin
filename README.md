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

H50-L14 is now
[pre-registered](docs/v50/EXPERIMENT_023_KNOWN_ALIGNMENT_PREDICTIVE_TRANSFER.md)
with 100 untouched final family seeds and 12 conjunctive criteria. It claims
only known-alignment predictive prior transfer in the synthetic tabular family.
No final result has been run or claimed at pre-registration time.

## Contributing

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before changing a claim, evaluator, or
experiment. Plain language is preferred. Describe what the code establishes,
what it does not establish, and how somebody else could prove the claim wrong.
