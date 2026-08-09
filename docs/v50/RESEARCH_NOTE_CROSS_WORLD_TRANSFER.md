# Cross-world transfer research gate

Status: design note only. This document does not register H50-L14, claim a new
capability, allocate final seeds, or report an experiment.

Date: 2026-08-02

## Why this is the next question

Darwin currently learns within one synthetic world at a time. A new
`OnlineBayesianModel` starts with equal order evidence and independent
`Beta(1, 1)` transition and reward priors for every candidate
context-action pair. Its archive is bound to that world. Nothing learned in a
solved world changes the starting state in the next world.

This is a real architectural limit. An agent that repeatedly starts from an
uninformative prior is adapting, but it is not accumulating reusable task
knowledge.

The current generator also prevents a superficial transfer result. Context
order changes by seed, and the context-specific dynamics mapping, rewarded
contexts, and rewarded actions are sampled again for every world. The numerical
probabilities are shared constants, but the actionable mappings are symmetric
across seeds. Pooling the existing worlds by context and action should therefore
converge toward an uninformative average, not a useful cross-world policy.

## What the literature supports

The literature supports studying transfer, but not attaching a transfer method
to the current benchmark without checking its assumptions.

- Wilson, Fern, and Tadepalli describe hierarchical Bayesian transfer for
  sequential decision problems and report faster learning when tasks are
  hierarchically related. This is the closest conceptual match to Darwin's
  exact Bayesian tables, but their result does not establish that Darwin's task
  family contains a learnable hierarchy.
- Barreto and colleagues' successor-feature framework gives a principled
  separation of dynamics and reward when tasks share dynamics and differ in
  reward. Darwin's current worlds change both the dynamics mapping and the
  reward mapping, so the classical guarantee does not apply.
- Abdolshah and colleagues extend successor-feature transfer to differing
  dynamics with Gaussian-process models. That is evidence that the harder case
  can be studied, not a reason to add a Gaussian process before a simpler
  tabular transfer question has been isolated.
- Distral shares a distilled policy across tasks and explicitly identifies
  negative interference between tasks. It targets deep multitask learning and
  is not an architectural match for the present tabular laboratory, but its
  failure mode is directly relevant.
- Abel and colleagues formulate lifelong reinforcement learning over tasks
  drawn from a distribution and study policy and value initialization. Mann and
  Choe treat improvement over learning from scratch and preservation of target
  learning as separate requirements for positive transfer. Both support using
  a scratch learner and a negative-transfer control rather than reporting only
  the transferred learner's score.
- Zhang and Wang analyze tabular multitask reinforcement learning for similar
  but non-identical MDPs. Their setting reinforces the need to state task
  relatedness explicitly instead of assuming that different seeds are related.

These papers motivate the question and the controls. They do not constitute
evidence that Darwin transfers knowledge.

## Rejected immediate moves

### Do not register another online controller

The Experiment 019 audit replicated H50-L13's deficit but did not distinguish
posterior-ensemble disagreement from randomized-mixture disagreement. Choosing
one channel now would turn an unresolved diagnostic into a preferred story.

### Do not apply successor features to the current generator

The classical formulation assumes shared dynamics. More importantly, the
current generator does not define a stable cross-world feature or task relation
that the agent could recover. A positive result would require changing the
benchmark, and that change must be visible.

### Do not pool the existing world archives

Treating all source observations as if they came from the target would assume
identical parameters. The worlds are not identical. This can create
overconfident priors and negative transfer while appearing to increase the
amount of data.

### Do not add a neural meta-learner yet

A recurrent or gradient-based meta-learner would change representation,
optimization, memory, and control at once. A result would not identify which
change caused the effect. The tabular system can test the narrower transfer
claim first.

## Required benchmark before H50-L14

The next implementation should be a benchmark validation, not a capability
experiment. It must introduce a task-family generator with a real, hidden
shared cause and make that relationship explicit in the evaluator.

The first benchmark should use known cross-world alignment. Context and action
labels retain the same meaning across tasks. A hidden family template defines
transition and reward tendencies, while each world's parameters are independent
draws conditioned on that template. Source and target worlds may be related
without copying exact parameters.

The benchmark must contain three target conditions:

1. **Related:** source and target worlds are conditionally independent draws
   from the same hidden family.
2. **Unrelated:** target worlds are drawn from an independently generated
   family.
3. **Adversarial mismatch:** target tendencies oppose the source family where
   the generator permits it.

Before testing a learned transfer mechanism, an oracle family prior must show a
measurable early-target advantage over `Beta(1, 1)` on related targets. It must
not show the same advantage on unrelated targets. If this sensitivity check
fails, the benchmark cannot support a transfer claim and H50-L14 remains
unregistered.

Known alignment is a limitation, not a hidden convenience. It isolates prior
transfer. Learning cross-task alignment or representation is a later and
separate claim.

## Candidate mechanism after the benchmark passes

The smallest compatible candidate is a hierarchical empirical-Bayes prior:

1. observe chosen-action outcomes in source worlds;
2. estimate family-level Beta hyperparameters for aligned transition and reward
   channels;
3. freeze those hyperparameters before any target evaluation;
4. initialize a fresh target model from the learned family prior;
5. continue updating only from actions actually taken in that target world.

The candidate must include a pre-registered shrinkage or abstention rule. Its
purpose is to fall back toward the base prior when early target evidence is
incompatible with the source family. The rule and all strengths must be chosen
on development tasks, not on final targets.

This mechanism transfers a distribution over parameters. It does not transfer
an exact world model, a policy, semantic knowledge, or a learned
representation.

## Minimum comparison set

Any later H50-L14 registration must include at least:

- scratch learning with independent `Beta(1, 1)` priors;
- the frozen learned hierarchical prior;
- an oracle prior derived from the hidden family parameters;
- naive pooled-source counts, to expose overconfidence and negative transfer;
- a source-shuffled or family-permuted causal control;
- the transferred learner with its compatibility gate disabled.

Every policy must receive the same target interaction budget. Source experience
is training cost and must be reported even if the primary target metric focuses
on adaptation speed.

## Evaluation boundary

The data split must occur at the task level, not only at the action or episode
level.

- Source, development, calibration, and final target families use disjoint seed
  namespaces.
- Family hyperparameters are fit only from source worlds.
- Method choices, prior strength, and compatibility thresholds use development
  worlds.
- Numerical pass thresholds use calibration worlds and are frozen before final
  evaluation.
- Final target worlds are run once. Their seeds are retired afterward.
- Environment randomness, policy randomness, bootstrap randomness, and family
  generation use separate deterministic streams.
- Hidden family parameters and counterfactual outcomes are evaluator-only.
- The candidate receives the declared family label in the first benchmark, but
  never the hidden family parameters.

Snapshots must preserve the source-derived prior, its provenance, target-only
counts, the compatibility state, and causal observation order. Replay must
reconstruct the same posterior without access to evaluator secrets.

## Metrics and decision shape

Exact thresholds are deliberately not set in this note. They require a working
benchmark and calibration data. The later decision must nevertheless be
conjunctive and cover all of these quantities:

- early-target cumulative reward or regret;
- prequential transition and reward loss before substantial target learning;
- samples required to reach a frozen target-performance level;
- final-target performance, to detect a fast start followed by lasting bias;
- related-target improvement over scratch with a paired uncertainty interval;
- unrelated and adversarial degradation relative to scratch;
- oracle-gap closure, so a tiny result in an insensitive benchmark cannot pass;
- simultaneous per-world wins, not only a favorable grand mean;
- source interaction cost and target interaction cost reported separately.

A positive mean on related targets is insufficient. A candidate that transfers
quickly but remains materially worse than scratch on unrelated targets must be
refuted under the intended robust-transfer claim.

## Evidence ceiling and stopping rule

The strongest possible outcome from this repository is E1: local automated
evidence that a tabular prior learned from a declared synthetic task family
improves adaptation to held-out related tasks while a registered gate limits
negative transfer. It would not establish general transfer, open-ended lifelong
learning, human-like learning, consciousness, or an artificial person.

H50-L14 may be registered only after:

1. the family relation is implemented and documented;
2. the oracle sensitivity check passes on non-final data;
3. leakage and causal-boundary tests pass;
4. candidate choices and thresholds can be frozen without examining final
   targets.

If any prerequisite fails, record that failure and change the benchmark only on
new seed families. Do not turn the prerequisite run into a capability result.

The first prerequisite is specified in
[Experiment 020](EXPERIMENT_020_CROSS_WORLD_TRANSFER_BENCHMARK.md). It uses an
evaluator-only oracle to test benchmark sensitivity before any learned-prior
candidate is introduced.

After that benchmark passed, the source-only estimator and compatibility-gate
development grid were specified in
[Experiment 021](EXPERIMENT_021_SOURCE_LEARNED_PRIOR_DEVELOPMENT.md). This stage
selects a configuration on development tasks and still cannot support a
capability claim.

## Primary sources

- Wilson, A., Fern, A., and Tadepalli, P. (2012),
  [Transfer Learning in Sequential Decision Problems: A Hierarchical Bayesian Approach](https://proceedings.mlr.press/v27/wilson12a.html).
- Barreto, A. et al. (2017),
  [Successor Features for Transfer in Reinforcement Learning](https://proceedings.neurips.cc/paper/2017/hash/350db081a661525235354dd3e19b8c05-Abstract.html).
- Teh, Y. et al. (2017),
  [Distral: Robust Multitask Reinforcement Learning](https://proceedings.neurips.cc/paper/2017/hash/0abdc563a06105aee3c6136871c9f4d1-Abstract.html).
- Abel, D. et al. (2018),
  [Policy and Value Transfer in Lifelong Reinforcement Learning](https://proceedings.mlr.press/v80/abel18b.html).
- Abdolshah, M. et al. (2021),
  [A New Representation of Successor Features for Transfer across Dissimilar Environments](https://proceedings.mlr.press/v139/abdolshah21a.html).
- Zhang, C. and Wang, Z. (2021),
  [Provably Efficient Multi-Task Reinforcement Learning with Model Transfer](https://proceedings.neurips.cc/paper/2021/hash/a440a3d316c5614c7a9310e902f4a43e-Abstract.html).
- Mann, T. and Choe, Y. (2013),
  [Directed Exploration in Reinforcement Learning with Transferred Knowledge](https://proceedings.mlr.press/v24/mann12a.html).
