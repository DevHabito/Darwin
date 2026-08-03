# Experiment 029 — source-learned contextual decision calibration

Status: pre-registered calibration. Calibration seeds had not been run when
this document, evaluator, thresholds, and seed constants were committed. This
experiment cannot register H50-L15.

## Purpose

Experiment 028 found a related decision signal and a causal advantage over a
source-shuffled control. It also found significant residual adversarial loss.
This calibration asks whether the exact frozen candidate repeats both facts
within explicit bounds on fresh task families.

Every threshold below was chosen after Experiment 028 development and before
accessing calibration seeds. Passing calibration can only make a confirmatory
H50-L15 protocol eligible for pre-registration.

## Frozen candidate and controls

No algorithm or interaction budget changes:

- exact H50-L14 source estimator and compatibility gate;
- 16 source tasks, eight cycles, and 2,048 source interactions;
- initial source weight `0.50`;
- 64 target interactions and epsilon `0.10`;
- reward-based action ranking;
- transition-plus-reward compatibility feedback;
- scratch, candidate, ungated, shuffled, pooled, and oracle policies.

## Fresh inputs

- implementation-only calibration seeds: `33900–33903`;
- calibration seeds: `34000–34063`;
- three conditions, 64 worlds each;
- bootstrap samples: `5,000`;
- bootstrap seed: `34700`;
- related simultaneous-win interval: 95% Wilson score;
- all earlier source, development, validation, final, audit, replication, test,
  and calibration seeds are excluded.

## Development-informed tolerances

The related thresholds require a measurable operational and causal effect. The
mismatch thresholds are non-inferiority tolerances, not claims that negative
transfer disappears.

- unrelated lower bounds may lose at most one realized reward and one
  pseudo-regret unit over 64 target interactions;
- adversarial lower bounds may lose at most two realized rewards and `1.5`
  pseudo-regret units;
- the gate must also recover at least two unrelated and eight adversarial
  rewards relative to ungated transfer.

These tolerances are deliberately reported in raw target-budget units. A later
reader can therefore see that a pass still permits bounded negative transfer.

## Conjunctive calibration decision

All 21 criteria must pass:

1. related candidate reward-improvement lower bound `>= 1.0`;
2. related candidate pseudo-regret lower bound `>= 0.75`;
3. related preferred-action improvement lower bound `>= 0.05`;
4. related candidate-minus-shuffled reward lower bound `>= 1.0`;
5. related candidate-minus-shuffled pseudo-regret lower bound `>= 1.0`;
6. related simultaneous-win Wilson lower bound `>= 0.65`;
7. unrelated candidate reward lower bound `>= -1.0`;
8. unrelated candidate pseudo-regret lower bound `>= -1.0`;
9. adversarial candidate reward lower bound `>= -2.0`;
10. adversarial candidate pseudo-regret lower bound `>= -1.5`;
11. unrelated candidate-minus-ungated reward lower bound `>= 2.0`;
12. adversarial candidate-minus-ungated reward lower bound `>= 8.0`;
13. related source-weight lower bound `>= 0.95`;
14. unrelated source-weight upper bound `<= 0.10`;
15. adversarial source-weight upper bound `<= 0.01`;
16. causal archive rate equals `1.0`;
17. opaque public identity rate equals `1.0`;
18. candidate snapshot replay rate equals `1.0`;
19. shuffled snapshot replay rate equals `1.0`;
20. source interaction cost equals `2,048`;
21. target interaction cost equals `64`.

Any miss yields `calibration_failed`. A favorable subset cannot authorize final
pre-registration.

## Interpretation boundary

Calibration remains E1 local development evidence. Even a complete pass would
not establish H50-L15, pure bandit transfer, multistep control, open-world
learning, consciousness, personhood, AGI, or a Diana-like brain.

## Result

Not run at pre-registration time.
