# Experiment 021 — source-learned prior development

Status: pre-registered development selection. Development seeds had not been
run when this document and evaluator were committed. This is not H50-L14 and
has no confirmatory pass rule.

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

Not run at pre-registration time.
