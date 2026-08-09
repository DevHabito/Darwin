# Experiment 014 — predictive history planning

Pre-registered: 2026-07-30\
Hypothesis: H50-L10\
Status: passed in the single official run

## Question

Can a finite state built only from observations represent controlled dynamics
well enough to plan toward delayed reward? Is the learned action model causally
necessary for that result?

The design was informed by
[predictive representations of state](https://papers.nips.cc/paper_files/paper/2001/hash/1e4d36177d71bbb3558e43af9577d70e-Abstract.html)
and Dyna in
[Reinforcement Learning: An Introduction](https://www.incompleteideas.net/book/bookdraft2018mar21.pdf).
It is far smaller than learned latent planners such as
[PlaNet](https://proceedings.mlr.press/v97/hafner19a.html) or
[MuZero](https://www.nature.com/articles/s41586-020-03051-4).

## Protocol

- development seeds: `17000–17031`;
- final seeds: `17100–17199`;
- three opaque cues and three opaque actions;
- state is the last four cues, giving 81 observable history states;
- each action maps to one of three next cues in every history state;
- the agent begins an episode with four priming observations and then receives
  one new cue per action;
- only executed transitions enter the archive;
- reward is delayed until a registered four-step target history is reached.

A frontier explorer collected transitions. Development chose among budgets 486,
729, and 972. The selected budget was 486. Final evaluation used 100 unique
worlds and 24 held-out tasks per world, or 2,400 episodes per policy.

Baselines were reactive, myopic, action-permuted, random, and an evaluator-only
oracle. The agent never received the true transition table or oracle actions.

## Official result

| Criterion | Observed | Threshold | Result |
| --- | ---: | ---: | --- |
| History-action coverage | `1.0` | `>= 0.90` | Passed |
| Accuracy on covered pairs | `1.0` | `= 1.0` | Passed |
| Candidate success | `1.0` | `>= 0.90` | Passed |
| Gain vs. reactive | `0.936666666667` | `>= 0.50` | Passed |
| Gain vs. myopic | `0.962083333333` | `>= 0.35` | Passed |
| Gain vs. permuted actions | `1.0` | `>= 0.40` | Passed |
| Gain vs. random | `0.9625` | `>= 0.50` | Passed |
| Simultaneous world win rate | `1.0` | `>= 0.90` | Passed |
| Excess steps over oracle | `0.0` | `<= 0.25` | Passed |
| Archive / snapshot / frozen model | `1.0` | `1.0` | Passed |

## Decision

H50-L10 passed locally. The model solved all registered four-step tasks and the
action permutation ablation solved none, supporting the causal role of the
learned mapping.

The history order was supplied, dynamics were deterministic, exploration
covered every pair, reward was not learned, and no representation transferred
between worlds. This is not a general world model. Final seeds `17100–17199`
are contaminated. Evidence level: `E1_LOCAL_AUTOMATED_EVALUATOR`.
