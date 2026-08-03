# Experiment 033 — cellwise safe-transfer development

Status: registered development; development seeds have not been run.

This protocol, evaluator, candidate, implementation-only tests, and seed
constants must be committed before development execution. The experiment has
no pass rule and cannot register a capability hypothesis.

## Question

Can compatibility localized to each context-action cell, with a deterministic
scratch fallback, preserve related transfer while reducing the residual
negative transfer observed in H50-L15 and Experiments 031–032?

The H50-L15 gate uses one global source weight. Evidence from any chosen cell
therefore changes source influence everywhere. Experiment 032 found that global
transition feedback helped strongly on adversarial targets but did not establish
a behavioral benefit on unrelated targets. A local gate is a new mechanism,
not a larger-sample retry of either failed experiment.

## Selection history

Implementation-only seeds `37900–37903` test determinism, active fallback,
causal archives, public identity, snapshot replay, cost accounting, complete
interval construction, and fail-closed validation. They are contaminated and
excluded from every later decision.

Development seeds `38000–38031` are fresh. They will be executed once after
this protocol and evaluator are committed. No aggregate from those seeds has
been inspected while writing this registration.

## Frozen candidate

The source learner and target policy remain unchanged:

- 16 source tasks and eight source cycles;
- 2,048 chosen-action source interactions;
- the H50-L14 empirical-Bayes Beta-Binomial source prior;
- initial source weight `0.50`;
- transition-and-reward compatibility likelihood;
- 64 target interactions in eight balanced context cycles;
- epsilon-greedy action selection with epsilon `0.10`;
- known context and action alignment;
- action ranking from reward estimates.

The candidate replaces the single global compatibility odds with 16 independent
odds, one for every aligned context-action cell. Only a chosen cell's evidence
updates that cell's odds.

For a cell with posterior source weight `w`:

- if `w >= 0.50`, forecasts use the ordinary source/scratch mixture with weight
  `w`;
- if `w < 0.50`, effective source weight is exactly `0` and the cell forecasts
  from scratch;
- the latent posterior continues updating and can later recover above `0.50`.

The threshold is the frozen prior odds, not a tuned performance threshold. The
rule reads as: use source influence only while the local evidence leaves source
at least as probable as it was initially.

## Comparison set

All policies receive identical source evidence, target specification, context
schedule, policy-randomness stream, outcome-randomness stream, and budgets.

- **scratch:** independent `Beta(1, 1)` priors;
- **global:** the H50-L15 global dual-channel gate;
- **cellwise:** independent cell weights without hard fallback;
- **candidate:** independent cell weights with scratch fallback;
- **ungated:** the learned prior with full fixed influence;
- **shuffled:** cyclically permuted learned prior with cellwise fallback;
- **oracle:** evaluator-only exact source-family prior.

Candidate minus cellwise isolates the fallback rule. Candidate minus global
tests localization plus fallback. Candidate minus shuffled tests whether aligned
source structure causes any advantage. The oracle is not a Darwin component.

## Frozen inputs

- implementation-only seeds: `37900–37903`;
- development seeds: `38000–38031`;
- related, unrelated, and adversarial target conditions;
- target interactions per world: `64`;
- bootstrap samples: `2,000`;
- bootstrap seed: `38700`;
- all Experiment 020–032 seed families are excluded.

## Reported metrics

For every condition, the evaluator reports:

- candidate reward, pseudo-regret, and preferred-action improvement over
  scratch;
- candidate-minus-global reward and pseudo-regret;
- candidate-minus-cellwise reward and pseudo-regret;
- candidate-minus-ungated reward and pseudo-regret;
- candidate-minus-shuffled reward and pseudo-regret;
- mean candidate posterior source weight;
- mean effective source weight after fallback;
- final fallback-cell rate;
- related simultaneous reward-and-pseudo-regret win rate;
- causal archive, opaque identity, four snapshot replay, and cost rates.

Continuous paired means use percentile bootstrap intervals over worlds. The
related simultaneous-win rate uses a 95% Wilson interval.

## Decision boundary

There is no capability decision and no numerical pass threshold. A separate
calibration may be considered only if development shows:

- a positive related reward and pseudo-regret signal;
- a causal related advantage over the shuffled prior;
- materially less mismatch damage than the global and ungated controls;
- mismatch performance compatible with scratch rather than merely a looser
  negative-transfer tolerance;
- complete integrity and fixed cost checks.

This is a qualitative screening boundary. Numerical thresholds can be frozen
only on a later calibration family. Failure or ambiguity will be recorded; the
candidate will not be tuned on development seeds.

## Interpretation ceiling

A favorable result would remain source transfer with supplied alignment in a
synthetic tabular contextual task. It would not establish learned alignment,
multistep control, real-world safety, general lifelong learning, autonomous
goals, consciousness, personhood, AGI, or a Diana-like brain.

