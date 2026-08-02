# Experiment 020 — cross-world transfer benchmark sensitivity

Status: pre-registered benchmark validation. No validation result had been run
when this section was committed. This is not H50-L14 and cannot establish a
transfer capability.

## Question

Can a synthetic task-family benchmark distinguish an evaluator-only correct
family prior from an uninformative `Beta(1, 1)` prior on related, unrelated, and
adversarial target tasks?

This is a prerequisite question. The oracle is given hidden family parameters.
Darwin does not learn them in this experiment.

## Selection history

The generator constants and four-cycle early window were implemented before
the validation run. Eight test-only seeds `27200–27207` were then used to check
determinism, causal ordering, and whether the implementation had a signal in
the intended direction. Those outputs were inspected and are contaminated.
They cannot support this decision or a later capability claim.

Development seeds `27000–27031` are reserved for later candidate development
and are not part of this benchmark decision. Validation seeds `27100–27131`
will be executed once after this document and the evaluator are committed.

## Generator

Every task uses known alignment: three-bit context labels and the actions
`amber` and `violet` retain their meaning across worlds. This is a deliberate
limitation that isolates parameter-prior transfer from representation learning.

A hidden family contains one transition and reward mean for each of 16 aligned
context-action cells:

- each context assigns transition means `0.82` and `0.18` to opposite actions;
- three of eight contexts assign reward means `0.72` and `0.12` to opposite
  actions;
- the remaining reward means are `0.04`;
- a task draws every transition and reward probability independently from a
  Beta distribution centered on its family mean with concentration `18`.

Related targets use the source family. Unrelated targets use an independently
generated family with the same marginal construction. Adversarial targets
reverse transition tendencies and swap reward-action tendencies within each
context while preserving the same set of marginal values.

The source-family seed, target-world draw, outcome stream, and balanced action
schedule use separate deterministic XOR-derived streams. Within each of four
cycles, every context-action cell occurs exactly once. Each target therefore
provides 64 chosen-action interactions and 128 prequential binary predictions.

This generator is engineered to contain a transferable signal. Passing this
experiment means only that the evaluator can detect that signal.

## Compared predictors

### Scratch

Every transition and reward channel begins with `Beta(1, 1)`.

### Evaluator oracle

Every channel begins with the exact Beta distribution used to draw target-task
parameters from the source family. The target then updates this prior using the
same chosen outcomes as scratch.

For unrelated and adversarial targets, the predictor deliberately retains the
source-family prior. This measures whether the benchmark exposes incompatible
transfer rather than rewarding every informative-looking prior.

The predictors forecast before the task produces an outcome. They receive no
counterfactual result and cannot accept an observation from another world,
index, context, or action.

## Metrics

For transition and reward predictions combined:

- mean prequential binary log loss;
- mean Brier score;
- paired improvement, defined as scratch loss minus oracle-prior loss;
- the fraction of worlds with positive log-loss improvement;
- deterministic 95% paired bootstrap intervals over worlds, using 2,000
  resamples.

Positive improvement favors the source-family oracle. Negative improvement is
negative transfer.

## Frozen validation inputs

- validation seeds: `27100–27131`;
- interactions: four balanced cycles, 64 per target;
- bootstrap samples: `2,000`;
- bootstrap base seed: `27801`, with fixed offsets by condition and metric;
- implementation/test seeds: contaminated and excluded;
- development seeds: excluded from this decision;
- no H50-L14 final seeds exist.

## Conjunctive sensitivity decision

The benchmark is sensitive only if every rule passes:

1. related log-loss improvement interval lower bound is at least `0.10`;
2. related Brier improvement interval lower bound is at least `0.04`;
3. related log-loss win rate is at least `0.90`;
4. unrelated log-loss improvement interval upper bound is at most `0.0`;
5. unrelated Brier improvement interval upper bound is at most `0.0`;
6. adversarial log-loss improvement interval upper bound is at most `-0.20`;
7. adversarial Brier improvement interval upper bound is at most `-0.08`;
8. deterministic replay, balanced coverage, forecast-before-observe ordering,
   and cross-world rejection tests pass.

These margins were chosen after inspecting test-only seeds and before accessing
the validation seeds. They are benchmark-separation margins, not estimates of
real-world importance.

Failure of any rule rejects this benchmark version. The failed validation seeds
would be retired, and an altered generator would require a new validation seed
family. A favorable subset cannot be promoted as a pass.

## Interpretation boundary

A pass would make a later learned-prior experiment eligible for
pre-registration. It would not register H50-L14 automatically. It would not
show that Darwin learned a family, transferred knowledge, chose better actions,
or avoided negative transfer. The oracle is evaluator-only and the aligned
family is synthetic.

Maximum evidence level: E1 for benchmark sensitivity, not for a cognitive
capability.

## Result

Not run at pre-registration time.
