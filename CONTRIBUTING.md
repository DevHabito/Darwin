# Contributing to Darwin

Darwin is easier to improve when claims stay smaller than the code that supports
them. A useful contribution makes the evidence clearer, the failure mode harder
to hide, or the architecture easier to test.

## Development setup

```powershell
py -m pip install -e .
$env:PYTHONPATH = "src"
py -m unittest discover -s tests -v
```

Python 3.11 or newer is required.

## Where new work belongs

- package code: `src/darwin_v50`
- tests: `tests`
- experiment records: `docs/v50`
- architecture and maintenance guides: `docs`

Do not add another versioned Python program to the repository root. Root-level
v47-v49 files are a compatibility surface and will be migrated separately.

## Experiment checklist

Before running final seeds, write down:

- the exact capability claim;
- development, calibration, and final seed families;
- what information the agent can observe;
- baselines and ablations;
- metrics and conjunctive thresholds;
- tie-breaking and selection rules;
- snapshot and causal-order invariants;
- conditions that refute the hypothesis;
- the strongest evidence level the evaluator can support.

After the final run, record every metric and every failed criterion. Do not tune
against final seeds and then present the same seeds as held out.

## Writing style

Use direct, ordinary English. Avoid promotional claims, synthetic enthusiasm,
and vague phrases such as “revolutionary intelligence” or “human-like
understanding.” Prefer a concrete sentence:

> The planner solved 96 of 100 registered tasks.

over an interpretation the experiment did not test:

> Darwin now understands the world.

State limitations close to the result they qualify. A failed hypothesis is a
valid result and should remain visible.

## Pull requests

A pull request should explain:

- what changed;
- why the change was needed;
- which claim or invariant it affects;
- how it was tested;
- what remains unsupported.

Keep runtime databases, logs, exports, credentials, and local snapshots out of
Git.
