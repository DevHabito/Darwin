# Contextual reward transfer research gate

Status: design note only. H50-L15 is not registered. This note defines the
boundary between H50-L14's predictive result and any later decision claim.

Date: 2026-08-02

## What H50-L14 did not establish

H50-L14 showed that source observations can improve prequential prediction in
held-out, known-alignment tasks from the same synthetic family. Its target
actions were scheduled by the evaluator. Better log loss did not cause Darwin
to choose a different action or earn additional reward.

The next question is whether that predictive information can improve decisions
under the same narrow family assumptions. It should not be described as
multistep control. The context sequence is exogenous, actions do not alter the
next context, and each action produces an immediate binary reward. The correct
name for this laboratory is a contextual bandit.

## Why this gate is justified

Sequential-transfer and hierarchical-bandit work evaluates reused task
knowledge through cumulative regret, not prediction alone. It also makes the
task relation an explicit assumption. Recent contextual-bandit transfer work
continues to report negative transfer when source and target environments do
not match. These results support the question and its controls; they are not
evidence that Darwin answers it.

The existing family is a suitable first laboratory because it already contains
related, unrelated, and adversarial targets, and because its reward channel has
an actionable source-family structure. Known labels and family grouping remain
supplied. Unknown alignment is a later and separate problem.

## Required benchmark prerequisite

Before a source-learned controller is developed, an evaluator-only oracle must
show that this benchmark can detect both useful and harmful prior-guided
decisions. Experiment 025 compares:

- scratch `Beta(1, 1)` reward learning;
- the exact source-family oracle prior, including when that prior is wrong.

Both use the same fixed epsilon-greedy rule. They receive the same balanced
sequence of 64 exogenous contexts. Separate task instances use the same outcome
seed, so each round uses common random numbers even when actions differ. This
reduces comparison noise but never reveals an unchosen outcome to either
policy.

The policy may inspect its own current reward estimates for both actions. A
non-mutating `peek` operation creates no pending forecast, count, archive row,
or compatibility update. Only the chosen action is forecast, executed, and
observed.

## Metrics that matter

Actual cumulative reward is the operational metric. Evaluator-only
pseudo-regret is included because binary reward noise can conceal a poor
choice. The family-preferred action rate measures whether decisions follow the
shared reward structure in the three contexts where family means differ.

The oracle benchmark must improve all three on related targets and must become
measurably harmful on unrelated and adversarial targets. The latter is not a
safety success. It demonstrates that the benchmark exposes negative transfer
and that a later learned candidate needs a compatibility gate.

## Requirements before H50-L15

Passing Experiment 025 would permit candidate development, not H50-L15. A later
candidate must use the exact H50-L14 source-learned prior and frozen gate, and
must include at least:

- scratch learning under the same exploration rule and target budget;
- gated source-learned transfer;
- ungated transfer;
- the source-shuffled causal control;
- the evaluator-only oracle ceiling;
- source and target interaction costs reported separately;
- actual reward, pseudo-regret, and late-target performance;
- unrelated and adversarial non-inferiority rules;
- disjoint development, calibration, and final task seeds.

Policy hyperparameters cannot be selected on H50-L14 final seeds or Experiment
025 validation seeds. A positive related mean cannot compensate for a frozen
negative-transfer criterion.

## Evidence ceiling

The maximum outcome remains E1 local evidence for known-alignment contextual
reward transfer in a synthetic tabular family. It would not establish
multistep planning, real-world generalization, autonomous goal formation,
consciousness, personhood, AGI, or a Diana-like brain.

## Primary sources

- Azar, M., Lazaric, A., and Brunskill, E. (2013),
  [Sequential Transfer in Multi-armed Bandit with Finite Set of Models](https://proceedings.neurips.cc/paper/2013/hash/062ddb6c727310e76b6200b7c71f63b5-Abstract.html).
- Deshmukh, A., Dogan, U., and Scott, C. (2017),
  [Multi-Task Learning for Contextual Bandits](https://proceedings.neurips.cc/paper/2017/hash/b06f50d1f89bd8b2a0fb771c1a69c2b0-Abstract.html).
- Wan, R., Ge, L., and Song, R. (2021),
  [Metadata-based Multi-Task Bandits with Bayesian Hierarchical Models](https://proceedings.neurips.cc/paper/2021/hash/f7cfdde9db36af8e0d9a6d123d5c385e-Abstract.html).
- Deng, M., Kyrki, V., and Baumann, D. (2025),
  [Transfer Learning in Latent Contextual Bandits with Covariate Shift through Causal Transportability](https://proceedings.mlr.press/v275/deng25a.html).
