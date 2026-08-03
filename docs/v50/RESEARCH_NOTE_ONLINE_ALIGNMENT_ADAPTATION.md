# Research note — online alignment adaptation inside the integrated cycle

Status: foundational engineering note. H50-L17 was later registered at E1 by
Experiment 039 for a narrow deterministic claim.

## Why this is the next boundary

H50-L16 established a continuing deterministic cycle with an external goal,
frozen learned transition model, multistep planning, causal kernel evidence,
and local replay-based recovery. It did not learn during target control.

The obvious implementation shortcut is unsafe. `PredictiveHistoryModel`
accepts one contiguous trace from one world and rejects reset episodes. Its
exploration archive ends at the exploration world's last history, while each
target task starts at a separately supplied history. Appending target episodes
directly would either violate continuity or require weakening a causal
invariant that H50-L10 already tested.

H50-L17 therefore starts with a smaller online-learning question. The base
transition prior remains immutable. A separate state estimator learns which
registered action alignment currently explains the agent's own chosen-action
observations and feeds that estimate back into planning.

## Research basis

The benchmark design follows four ideas from primary work without claiming to
implement those papers' full algorithms:

- [Bayesian Online Changepoint Detection](https://arxiv.org/abs/0710.3742)
  motivates causal filtering from observations available before the next
  decision, rather than retrospective boundary labels.
- [Hidden-mode MDPs](https://proceedings.mlr.press/r3/choi01a.html) formalize
  nonstationary control in which environment dynamics depend on an unobserved
  changing mode.
- [Hidden Parameter MDPs](https://www.ijcai.org/Proceedings/16/Papers/206.pdf)
  motivate rapid adaptation through a low-dimensional latent description of a
  related dynamics family.
- [Experience Replay for Continual Learning](https://papers.nips.cc/paper_files/paper/2019/hash/fa7cdfad1a5aaf8370ebeda47a1ff1c3-Abstract.html)
  states the stability–plasticity requirement: new knowledge must be acquired
  without erasing behavior needed when an earlier condition returns.

Darwin's first test is deliberately simpler than each of these settings. It
uses three known discrete hypotheses and deterministic observations.

## Online state and causal boundary

The hidden variable is an action rotation `r ∈ {0, 1, 2}`. If Darwin executes
action index `a`, the environment applies the frozen model's action
`(a + r) mod 3`. The evaluator changes `r` without giving a boundary or mode
label to the agent.

After an action returns a cue, the tracker compares the resulting history with
the frozen prior's prediction under all three rotations. Each registered world
maps the three actions at a history to three distinct cues, so exactly one
rotation is compatible. The candidate adopts that rotation only after the
observation. The next planner call uses the updated alignment.

This is one-step latent-mode identification. It is not gradient learning,
transition-count revision, representation learning, or discovery of an
unbounded mode family.

The tracker archive enforces:

- one global unreplayed sequence;
- contiguous histories within an episode;
- explicit monotonic episode transitions at evaluator resets;
- chosen actions only, with no counterfactual observation;
- immutable prior digest;
- replay-checked updates, counts, and current rotation;
- fail-closed behavior if the tracker or prior changes outside the cycle.

## Development schedule

Each world supplies `24` target tasks in four six-task segments:

1. `base`, rotation `0`;
2. `shifted`, rotation `1`;
3. `recurrent`, rotation `0` again;
4. `novel`, rotation `2`.

The tracker persists across all target tasks. The first action after a boundary
may use the previous estimate; only its returned cue may change the estimate.
The six-action target budget allows one incorrect boundary action followed by
the registered four-action route.

The recurrent segment measures return to an earlier alignment, not recall of a
learned neural representation. The novel segment is novel only relative to the
target schedule; rotation `2` is already a registered hypothesis.

## Required controls

- **Frozen:** observes the same trace but never leaves rotation `0`.
- **Cumulative:** uses all historical mode counts without change reset, testing
  whether unbounded averaging is too inertial.
- **Shifted evidence:** applies a fixed `+1` error to every correctly inferred
  rotation, testing whether observations causally determine control.
- **Seeded random:** acts without the model or tracker.
- **Oracle:** receives the evaluator rotation as a ceiling.
- **Pure candidate twin:** runs the same tracker without the kernel; its actions
  and outcomes must exactly match the integrated candidate.

## Evidence ceiling

Even a favorable development result would establish only that a small
registered latent variable can be revised online and affect planning in one
deterministic symbolic family. It would not establish general continual
learning, unknown-mode discovery, stochastic change detection, modification of
the transition prior, self-generated goals, natural-language grounding,
consciousness, personhood, AGI, or a Diana-like mind.
