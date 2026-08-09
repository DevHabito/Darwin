# Experiment 023 — H50-L14 known-alignment predictive transfer

Status: all numerical criteria passed, but capability promotion is withheld
pending independent confirmation because of a disclosed output-recovery rerun.
The pre-registration was committed as `1256909` before either execution.

## H50-L14 capability claim

Given multiple source tasks from a declared synthetic family with known
context-action alignment, Darwin can estimate a reusable predictive prior from
chosen-action observations. On held-out related targets, that prior plus an
online compatibility gate improves early transition-and-reward prediction over
scratch and a source-shuffled causal control. On unrelated and adversarial
targets, the same gate limits negative transfer to a frozen tolerance.

This is a claim about a tabular predictive prior. It is not a claim about policy
transfer, reward improvement, learned representation, autonomous task-family
discovery, open-ended learning, or general intelligence.

## Selection provenance

- Experiment 020 validated that the task-family benchmark can distinguish a
  correct oracle prior from incompatible priors.
- Experiment 021 selected 16 source tasks, eight cycles, and initial source
  weight `0.5` on development seeds `27000–27031`.
- Experiment 022 froze that candidate and passed nine eligibility margins on
  calibration seeds `27500–27531`.
- Test and implementation seeds occupy `27300–27499`, `27600–27699`, and
  `28600–28699`.
- None of those seeds belongs to the final family `28500–28599`.

The development selection was not reliably separated from the weight-`0.25`
runner-up. The deterministic registered rule nevertheless selected `0.5`, and
that exact value passed independent calibration. It is frozen here rather than
portrayed as uniquely optimal.

## Information boundary

For each final family replicate:

1. 16 conditionally independent source tasks are drawn from one hidden family;
2. every source task supplies eight balanced chosen-action observations per
   aligned cell, for 2,048 source interactions;
3. the learner receives only successes, trials, opaque task identity, context,
   action, chosen transition, and chosen reward;
4. hidden family parameters, task parameters, evaluator seeds, and
   counterfactual outcomes remain evaluator-only;
5. the learned prior is frozen before the three target conditions begin;
6. related, unrelated, and adversarial target predictors each receive the same
   64-interaction balanced schedule.

Known alignment and a declared source-family grouping are supplied. The target
is not promised to match the source: the gate must infer compatibility from
observed target outcomes. Public identities are `source-task:N` and
`target-task`; they do not encode evaluator seeds.

## Frozen candidate

- per-cell smoothed source mean;
- Beta concentration selected by exact Beta-Binomial marginal likelihood over
  `1, 2, 4, 8, 12, 18, 24, 32, 48, 64`;
- source interactions: `2,048`;
- target interactions per condition: `64`;
- initial source mixture weight: `0.5`;
- global Bayesian compatibility update after each chosen transition and reward;
- no update before the corresponding observation.

The source budget is 32 times the target budget and is part of the reported
cost. The evaluator may recompute the same deterministic source archive for
different target conditions, but it counts as one 2,048-interaction source
dataset per family replicate.

## Baselines and causal controls

- scratch independent `Beta(1, 1)` target learning;
- learned source prior without compatibility gating;
- naive pooled source counts, which assume identical tasks;
- evaluator-only exact family oracle;
- source-shuffled gated prior, using fixed cyclic cell offset `1`.

The shuffled control preserves learned Beta distributions and source cost while
breaking context-action alignment.

## Final inputs

- final seeds: `28500–28599`, 100 family replicates;
- target conditions: related, unrelated, adversarial;
- bootstrap base seed: `29100`;
- paired bootstrap samples: `10,000`;
- all intervals: deterministic 95% paired bootstrap over family replicates;
- final execution: once after this pre-registration commit.

## Metrics

All improvement metrics equal scratch log loss minus candidate log loss. Log
loss combines transition and reward predictions made before each outcome.

- related gated improvement;
- related candidate improvement minus source-shuffled improvement;
- related oracle-gap closure;
- unrelated and adversarial gated improvement;
- final source weights in all three conditions;
- related per-family simultaneous win rate over scratch and shuffled control;
- causal archive, snapshot round-trip, and public-identity integrity rates.

## Conjunctive final decision

H50-L14 passes locally only if all 12 rules pass:

1. related improvement interval lower bound at least `0.12`;
2. related candidate-minus-shuffled lower bound at least `0.10`;
3. related oracle-gap-closure lower bound at least `0.80`;
4. unrelated improvement lower bound at least `-0.01`;
5. adversarial improvement lower bound at least `-0.01`;
6. related final source-weight lower bound at least `0.95`;
7. unrelated final source-weight upper bound at most `0.20`;
8. adversarial final source-weight upper bound at most `0.05`;
9. related simultaneous-win-rate lower bound at least `0.75`;
10. causal archive rate exactly `1.0`;
11. snapshot round-trip rate exactly `1.0`;
12. public-identity boundary rate exactly `1.0`.

Any miss refutes H50-L14. No favorable subset, mean, or secondary baseline can
override a failed rule. Final seeds are retired after the run regardless of the
decision.

The causal kernel receives one Boolean conjunction plus the registered metrics.
An unauthenticated local evaluator cannot promote a failed conjunction.

## Persistence and integrity

Snapshots serialize the source prior and provenance, initial weight, complete
target observation archive, derived source weight, and weight history. Restore
replays the archive to reconstruct both target learners and the gate. Strict
JSON, duplicate-key rejection, prior digest, replay equality, and pending-action
rejection are tested.

The prior digest detects unilateral changes but is not a signature. Snapshots
are structurally checked, not authenticated against an actor who can replace
both content and digest.

## Evidence ceiling

A pass is E1 local evidence for known-alignment predictive prior transfer in
this synthetic tabular family. It would show one concrete form of reusable
cross-world learning beyond restarting from `Beta(1, 1)` every time.

It would not establish improvement in cumulative reward, policy transfer,
unknown task alignment, natural perception, language grounding, emotion,
consciousness, personhood, AGI, or a brain comparable to Diana from
*Pragmata*.

## Result

All 12 registered numerical and integrity rules passed on seeds
`28500–28599`.

| Metric | Mean | 95% interval |
| --- | ---: | ---: |
| Related gated improvement | `0.1641195` | [`0.1579007`, `0.1702157`] |
| Related candidate minus shuffled | `0.1689450` | [`0.1626785`, `0.1750909`] |
| Related oracle-gap closure | `0.9330070` | [`0.9208946`, `0.9447894`] |
| Unrelated gated improvement | `-0.0054459` | [`-0.0063368`, `-0.0045766`] |
| Adversarial gated improvement | `-0.0047526` | [`-0.0052250`, `-0.0042615`] |
| Related simultaneous win rate | `1.0` | [`1.0`, `1.0`] |

Causal archive, snapshot round trip, and public identity rates were all `1.0`.
The local kernel accepted the observation and marked its Boolean conjunction
satisfied.

### Operational deviation

The first final evaluator execution completed, but the wrapper then attempted
to serialize a nonexistent `ObservationResult.evidence` attribute. It raised
`AttributeError` before printing or exposing any metric. The exact evaluator
was repeated to recover the output, with no code, seed, threshold,
configuration, or method change and no first-run metric available for adaptive
choice.

This does not introduce observed-result tuning, and the evaluator is
deterministic. It nevertheless violates the literal one-execution rule for
final seeds. Seeds `28500–28599` were executed twice and are retired.

Decision: **numerical criteria passed; H50-L14 promotion withheld until an
independent, pre-registered confirmation on fresh seeds**. This is stricter
than the local kernel's state and prevents an operational recovery from being
silently represented as a clean confirmation.

The machine-readable record is
[`results/EXPERIMENT_023_FINAL_AGGREGATE.json`](results/EXPERIMENT_023_FINAL_AGGREGATE.json).
