# Experiment 026 — contextual decision failure audit

Status: pre-registered diagnostic. Audit seeds had not been run when this
document and evaluator were committed. This audit cannot reverse Experiment
025, authorize candidate development, or register H50-L15.

## Question

Why did Experiment 025's related simultaneous-win interval miss its frozen
lower bound even though its aggregate reward and pseudo-regret intervals were
positive?

Two explanations remain plausible:

1. the oracle often chooses actions with lower conditional expected reward;
2. the oracle usually chooses better actions, but 64 binary rewards do not
   reliably turn that expected advantage into a positive realized difference
   in each world.

This audit separates the signs of realized reward improvement and
evaluator-only expected reward improvement. In this benchmark, scratch
pseudo-regret minus oracle pseudo-regret equals the conditional expected reward
difference along the two policies' chosen action trajectories.

## Frozen method

The Experiment 025 environment and policies are unchanged:

- related targets only;
- 64 exogenous-context interactions;
- epsilon `0.10`;
- scratch versus exact source-family oracle;
- common context, policy, and outcome randomness;
- chosen-action observations only.

No horizon, prior, exploration rule, task distribution, or threshold changes.

## Fresh inputs

- diagnostic seeds: `31000–31127`;
- implementation-only audit seeds: `31150–31153`;
- bootstrap samples: `5,000`;
- bootstrap seed: `31700`;
- Experiment 025 validation seeds remain retired.

## Reported diagnostics

Paired bootstrap intervals over diagnostic worlds are reported for:

- realized reward improvement;
- expected reward improvement;
- realized minus expected improvement;
- realized reward win rate;
- expected reward win rate;
- simultaneous win rate;
- expected-win/realized-nonwin rate;
- expected-nonwin/realized-win rate;
- causal archive and opaque public identity rates.

## Interpretation boundary

This audit has no pass rule. If expected wins substantially exceed simultaneous
wins, reward noise is a plausible contributor. If expected wins are themselves
unstable, the policy benchmark is decision-unstable. Neither finding changes
the registered refutation.

Any revised benchmark must explain its metric or horizon change, allocate new
test and validation seeds, and be pre-registered separately. The audit data
cannot be reused for that decision.

## Result

Not run at pre-registration time.
