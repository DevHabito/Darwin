# Experiment 021 — source-learned prior development

Status: development selection completed. The protocol and evaluator were
committed as `488bf85` before the grid run. This is not H50-L14 and has no
confirmatory pass rule.

## Development question

Can a prior estimated only from chosen-action observations in source tasks
retain useful related-task prediction while a compatibility gate limits the
damage on unrelated and adversarial targets?

This experiment selects one configuration for later audit and calibration. It
cannot promote a capability regardless of its metrics.

## Boundary correction before development

The first implementation exposed family and world seeds inside the public
`world_id`. The estimator did not use them, but a learner could have
reconstructed evaluator parameters from those identifiers. This was treated as
a real information leak, not ignored because the current code happened to be
benign.

Before any development seed was run, source observations were changed to use
identities `source-task:N` and every isolated target learner was changed to use
`target-task`. Tests now require that public observations omit family and world
seeds. The evaluator still holds the full specification, so this is structural
API separation inside one process, not a security sandbox.

## Learned prior

For every aligned context-action cell and for transition and reward separately:

1. each source task contributes successes and trials from a balanced
   chosen-action schedule;
2. the learner estimates a smoothed pooled mean from source outcomes;
3. it selects a Beta concentration by exact Beta-Binomial marginal likelihood
   over the frozen grid `1, 2, 4, 8, 12, 18, 24, 32, 48, 64`;
4. the resulting Beta distribution initializes a fresh target learner.

Source task parameters, family parameters, target parameters, counterfactual
outcomes, and evaluator seeds are not inputs to the estimator. Duplicate source
task evidence is rejected.

This is empirical-Bayes estimation on a known alignment. It does not learn the
alignment, a representation, a policy, or semantic task identity.

## Compatibility gate

The gated candidate maintains two target predictors:

- the source-learned Beta prior with target-only updates;
- scratch `Beta(1, 1)` learning with the same target outcomes.

Its forecast is a Bayesian mixture of their prequential forecasts. After the
chosen transition and reward are observed, their weights are updated by the
joint predictive likelihood. No weight change occurs before an observation.
The gate is global across aligned cells, so evidence of family mismatch may
reduce source influence before every cell has been visited.

## Development conditions

Every configuration is evaluated on the same three conditions used in
Experiment 020:

- related target drawn independently from the source family;
- unrelated target drawn from an independent family;
- adversarial target with reversed transition and reward-action tendencies.

All target predictors receive the same 64 interactions, covering every cell
once in each of four balanced cycles.

## Frozen development grid

- source task counts: `4`, `8`, `16`;
- balanced cycles per source task: `4`, `8`;
- initial source weights: `0.25`, `0.5`, `0.75`;
- total configurations: `18`;
- source interaction cost: task count × cycles × 16, reported explicitly;
- development seeds: `27000–27031`;
- test-only estimator seeds: `27300–27399`;
- test-only evaluator seeds: `27400–27407`;
- H50-L14 final seeds: not allocated.

Test-only seeds were used to debug determinism, the information boundary, and
the expected direction of the gate. Their output was inspected and is
contaminated. In those seeds the provisional grid winner used 16 tasks, eight
cycles, and initial weight `0.5`; that is not the development selection.

## Comparison set

Each target outcome scores five predictors prequentially:

1. scratch `Beta(1, 1)`;
2. the learned prior without a gate;
3. the learned prior with the compatibility gate;
4. naive pooling of all source counts as if source and target were identical;
5. the evaluator-only exact family oracle.

Source-shuffled control, persistence, and a confirmatory reward or regret claim
remain prerequisites for any later H50-L14 registration. Their absence is why
this stage is development only.

## Primary development metric

For each condition and predictor, improvement is scratch binary log loss minus
predictor binary log loss, combining transition and reward forecasts. Positive
values favor transfer. Final source weight is diagnostic.

The selection score is fixed as:

```text
related gated improvement
+ min(0, unrelated gated improvement)
+ min(0, adversarial gated improvement)
```

The selected configuration maximizes that score, then:

1. maximizes related gated improvement;
2. uses fewer source interactions;
3. uses the lower initial source weight.

This rule allows development selection; it is not a pass threshold. A high
score may still reveal too much incompatible-target damage for a confirmatory
hypothesis.

## Stopping rule

After the single development-grid run, record the full selected summary and
inspect causal and failure diagnostics. Do not alter the grid and rerun these
seeds as if the result remained held out.

H50-L14 may be considered only if a frozen candidate can later add:

- an explicit source-shuffled causal control;
- snapshot and replay integrity;
- calibration-derived conjunctive thresholds;
- new confirmatory target seeds;
- a claim no broader than known-alignment predictive transfer.

## Result

The 18 configurations were evaluated once on development seeds `27000–27031`.
The frozen rule selected:

- 16 source tasks;
- eight balanced cycles per source task;
- initial source weight `0.5`;
- 2,048 source interactions for 64 target interactions.

The selected configuration produced these mean log-loss improvements over
scratch:

| Predictor | Related | Unrelated | Adversarial |
| --- | ---: | ---: | ---: |
| Learned prior with gate | `0.1622840` | `-0.0028053` | `-0.0044137` |
| Learned prior without gate | `0.1679871` | `-0.2167923` | `-0.3605912` |
| Naive pooled source counts | `0.1669304` | `-0.2709335` | `-0.4369891` |
| Evaluator oracle | `0.1744282` | `-0.1968349` | `-0.3441606` |

The gate preserved most of the related-task improvement while sharply reducing
negative transfer. Its mean final source weight was `0.9999966` on related
targets, `0.0520974` on unrelated targets, and effectively zero on adversarial
targets.

The result also exposes two costs that cannot be omitted:

1. source training used 32 times as many interactions as target evaluation;
2. the gate reduced but did not eliminate incompatible-target loss.

The runner-up used the same source budget with initial weight `0.25`. A
post-selection paired bootstrap on the contaminated development worlds put the
selected-minus-runner-up robust-score difference at `0.0005886`, with interval
`[-0.0005756, 0.0027837]`. The deterministic selection rule chose `0.5`, but
the data do not resolve it as reliably better than `0.25`.

Decision: **configuration selected for further engineering only**. H50-L14 is
not registered. Before a confirmatory hypothesis, the selected mechanism still
needs a source-shuffled causal control, snapshot replay, and independently
calibrated thresholds. The development seeds are contaminated and retired from
confirmatory use.

The machine-readable record, including all 18 ranked configurations, is
[`results/EXPERIMENT_021_DEVELOPMENT_AGGREGATE.json`](results/EXPERIMENT_021_DEVELOPMENT_AGGREGATE.json).

## Post-development engineering

No development or validation claim was rerun for these changes.

- A fixed cyclic permutation of the learned cell priors now provides the
  source-shuffled causal control. It preserves the fitted Beta distributions
  while breaking their context-action alignment.
- The gated model now has a strict JSON snapshot. It stores the learned prior,
  provenance, target observation archive, initial mixture weight, derived
  weight history, and current source weight.
- Restoration recomputes target counts and mixture weights by causal replay and
  rejects a pending forecast, duplicate JSON keys, non-finite values, and
  derived state that disagrees with replay.
- A SHA-256 digest detects unilateral or accidental changes to the serialized
  source prior. It is not a signature or authentication boundary; an actor who
  can replace both prior and digest still controls the snapshot.

On test-only seeds, the selected candidate's related improvement was `0.1521059`
and the source-shuffled control's was `-0.0049915`. This is implementation
evidence from contaminated test seeds, not a confirmatory causal result.
