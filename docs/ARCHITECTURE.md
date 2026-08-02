# Darwin v50 architecture

Darwin v50 is a collection of small laboratories built around one rule: a claim
must be tied to causal evidence that could also show the claim is false.

## Layers

### Causal kernel

The kernel records goals, dispatched actions, observations, and immutable event
lineage. A goal reaches `succeeded` only when an observation matches the exact
goal, action, source, and persisted condition.

### Authority and effects

Workspace effects are deliberately small. Capability grants are scoped,
signed, registered, and single-use. Consent is a separate signed record. A
worker process can perform the fixed effect, but process separation under the
same operating-system user is not described as a security boundary.

### Learning laboratories

Each learning module owns a small synthetic environment, an agent-facing
observation interface, a causal archive, a model, and an evaluator. Evaluator
truth is kept out of the agent interface. Snapshots are rebuilt from the archive
so derived-state tampering is detectable.

### Evidence documents

Every experiment records its seed families, selection procedure, baselines,
metrics, thresholds, observed result, and limitations. Passing an internal
benchmark remains local E1 evidence.

## Data flow

```text
registered hypothesis
        |
        v
action chosen ----> environment effect
        |                    |
        |                    v
        +---------- observed chosen outcome
                             |
                             v
                       causal archive
                             |
                             v
                    model and/or planner
                             |
                             v
                     held-out evaluator
```

Counterfactual outcomes and hidden world parameters may be used by the evaluator
to score a model, but they cannot enter the learner's archive.

## Current boundary

The learning systems are tabular and synthetic. They do not share a general
latent state, do not perceive the physical world, and do not maintain one
continually learned model across open-ended tasks. Language-facing legacy
modules are separate from the v50 learning kernel.

H50-L12 tested one part of that boundary: online action selection while the
transition and reward model was still being learned. It was refuted because
accurate posterior learning did not translate into the registered cumulative
control advantage.

The H50-L12 failure audit localized the persistent action perturbations to
sampled transition and reward parameters after context order had converged.
H50-L13 now provides an unevaluated blockwise information-directed controller.
It estimates regret and mutual information about the current posterior-optimal
action from 16 tabular posterior models, then selects a two-action mixture. This
is a finite-sample engineering approximation, not an implementation of a
published regret theorem.
