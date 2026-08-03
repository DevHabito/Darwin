# Experiment 030 — H50-L15 known-alignment contextual transfer

Status: pre-registered confirmatory experiment. Final seeds had not been run
when this document, evaluator, criteria, and seed constants were committed.

## Registered claim

H50-L15 asks whether a source-learned prior can improve immediate contextual
decisions and realized reward on held-out related synthetic tasks, retain a
causal advantage over a source-shuffled prior, and use an online compatibility
gate to keep unrelated and adversarial losses within declared tolerances.

The claim includes important qualifiers:

- context and action alignment is known and supplied;
- tasks come from the registered synthetic tabular family;
- contexts are exogenous and actions do not control the next context;
- action ranking uses reward estimates;
- the gate receives chosen-action transition and reward feedback;
- source training uses 2,048 interactions for a 64-interaction target;
- negative transfer is limited by tolerance, not eliminated.

The short name is **known-alignment contextual decisions with auxiliary
transition feedback**. This is not a pure contextual-bandit or multistep-control
claim.

## Frozen method

No algorithm, policy, budget, or threshold changed after Experiment 029:

- 16 source tasks and eight source cycles;
- H50-L14 empirical-Bayes source prior;
- initial source weight `0.50`;
- Bayesian compatibility gate;
- epsilon-greedy target policy with epsilon `0.10`;
- 64 balanced target interactions;
- scratch, candidate, ungated, shuffled, pooled, and oracle comparisons;
- paired target randomness;
- causal archive, opaque identity, and snapshot replay checks.

## Final inputs

- implementation-only confirmation seeds: `34900–34903`;
- final seeds: `35000–35127`;
- related, unrelated, and adversarial conditions;
- 128 worlds per condition;
- bootstrap samples: `10,000`;
- bootstrap seed: `35700`;
- related simultaneous-win rate: 95% Wilson interval;
- all earlier seed namespaces are excluded.

Final seeds will be run once. Any operational deviation, rerun, code change, or
threshold change after execution blocks promotion and requires a separately
pre-registered confirmation on fresh seeds.

## Frozen 21-criterion conjunction

The exact Experiment 029 criteria are retained:

1. related reward lower bound `>= 1.0`;
2. related pseudo-regret lower bound `>= 0.75`;
3. related preferred-action lower bound `>= 0.05`;
4. related minus shuffled reward lower bound `>= 1.0`;
5. related minus shuffled pseudo-regret lower bound `>= 1.0`;
6. related simultaneous-win Wilson lower bound `>= 0.65`;
7. unrelated reward lower bound `>= -1.0`;
8. unrelated pseudo-regret lower bound `>= -1.0`;
9. adversarial reward lower bound `>= -2.0`;
10. adversarial pseudo-regret lower bound `>= -1.5`;
11. unrelated gate reward benefit lower bound `>= 2.0`;
12. adversarial gate reward benefit lower bound `>= 8.0`;
13. related source-weight lower bound `>= 0.95`;
14. unrelated source-weight upper bound `<= 0.10`;
15. adversarial source-weight upper bound `<= 0.01`;
16–19. all four integrity rates equal `1.0`;
20. source interactions equal `2,048`;
21. target interactions equal `64`.

Any miss refutes H50-L15. Related gains cannot compensate for a mismatch,
causal-control, integrity, or cost failure.

## Causal kernel

The local Darwin kernel receives a single Boolean conjunction from the frozen
evaluator. It cannot promote a report with any failed criterion. Kernel success
records causal acceptance of the evaluator output; it does not raise the
evidence above E1.

## Interpretation ceiling

A complete pass supports only the registered synthetic capability. It does not
establish learned representation alignment, pure bandit transfer, multistep
control, general lifelong learning, self-generated goals, consciousness,
personhood, AGI, or a Diana-like brain.

## Result

Not run at pre-registration time.
