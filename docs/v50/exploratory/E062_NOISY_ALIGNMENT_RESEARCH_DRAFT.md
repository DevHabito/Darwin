# Darwin v50 — Draft research direction: noisy action-alignment inference

**Status:** Analysis and benchmark-design draft, 19 November 2026. **Not pre-registered, not committed, not implemented in Darwin, and not tested against the Darwin kernel.** This note proposes an independent cognitive research track while E061 remains blocked by explicit model-license consent. The experiment number **E062 is provisional** until assigned and frozen in the repository.

## Verified starting point

The maintained v50 line is in the open GitHub branch `codex/v50-kernel-foundation`; subsequent development branches are `codex/conversational-darwin-dev` and `codex/portable-local-language-seed`. The `main` branch remains the v49.44 legacy baseline.

- Experiment 039 records H50-L17 as an E1-local pass: `1,536/1,536` tasks, a known set of three action rotations, an externally prescribed `0→1→0→2` schedule, frozen transition prior, deterministic and uniquely identifying observations, and exactly one observation to identify each boundary.
- Experiment 060 records the Granite 4.0 H-350M Q4 candidate's exact echo of turn one's Portuguese input. The frozen screen stopped immediately; there is no admitted local conversational model from that result.
- Experiment 061 is **pre-registered but blocked before download**. Its consent requirement expressly states that a general instruction to continue does not count as accepting the relevant Gemma terms. This draft does not authorize download, credential access, or voice integration.

Evidence source files in the existing branch:

- `docs/v50/EXPERIMENT_039_ONLINE_ALIGNMENT_CONFIRMATION.md`
- `docs/v50/results/EXPERIMENT_039_FINAL_AGGREGATE.json`
- `docs/v50/EXPERIMENT_060_H350M_PORTUGUESE_CONVERSATION_SCREEN.md`
- `docs/v50/results/EXPERIMENT_060_H350M_PORTUGUESE_CONVERSATION_SCREEN.json`
- `docs/v50/EXPERIMENT_061_GEMMA_270M_CONSENT_LOCKED_ADMISSION.md`
- `docs/v50/RESEARCH_PROTOCOL.md`

## Research question

Can a causal agent preserve correct action–observation lineage and improve decisions under ambiguous, noisy evidence about a changing latent action rotation, without knowing the evaluator's hidden mode and without conflating a single surprising observation with a genuine regime change?

The immediately testable hypothesis is **not** that Darwin is conscious or generally intelligent. It is that a correctly implemented probabilistic evidence accumulator can distinguish stronger from weaker evidence about a finite latent mode, and that the agent's decisions can be evaluated against a mathematically defined reference under measured information limits.

## Exact mathematical feasibility check — completed independently

Let the unknown latent state be `R ∈ {0,1,2}` with uniform prior `P(R=r)=1/3`. Given fixed `R`, each independent observation `Y` reports `R` with probability `4/5` and each other state with probability `1/10`. This is an **illustrative synthetic sensor**, not an observed property of Darwin or of any physical sensor.

For `n` independent observations and label counts `(a,b,c)`, the maximum possible mean classification accuracy under 0–1 loss is

\[
A_n = \frac{1}{3}\sum_{a+b+c=n}
\frac{n!}{a!b!c!}
\max_{r\in\{0,1,2\}}
\left[\left(\frac{4}{5}\right)^{n_r}
\left(\frac{1}{10}\right)^{n-n_r}\right].
\]

This expression was evaluated using exact rational arithmetic in the included `darwin_noisy_alignment_exact_reference.py`. Two independently coded enumerations agree exactly; the script was executed successfully on 19 November 2026. It has **not** executed any Darwin code.

| Independent observations | Bayes-optimal accuracy | Exact probability |
| ---: | ---: | ---: |
| 0 | 33.333333% | 1/3 |
| 1 | 80.000000% | 4/5 |
| 2 | 80.000000% | 4/5 |
| 3 | 91.200000% | 114/125 |
| 4 | 93.440000% | 584/625 |
| 5 | 96.128000% | 3004/3125 |
| 7 | 98.457600% | 15384/15625 |
| 9 | 99.360768% | 388128/390625 |

**Consequence:** In this symmetric noisy model, even the optimal estimator cannot achieve perfect mean mode identification from a single observation. Two observations do not improve mean classification accuracy because disagreement creates ties. This benchmark supplies a reference for diagnosing measurement or information leakage, not an estimate of Darwin's present performance. The formula assumes a fixed mode during the `n` observations, conditional independence, known likelihoods, and equal prior odds. None of these assumptions should be silently imported into a changing-mode task.

## Proposed next gate: benchmark sensitivity, before any capability claim

Keep the learned transition prior and causal kernel contracts frozen. Build a separate, evaluator-owned synthetic observation instrument. The candidate must receive only observations following the actions it actually dispatches. It must not receive hidden mode labels, evaluator seeds, unexecuted-action outcomes, or future boundaries. The evaluator owns the noise RNG.

Study three conditions:

1. **Regression control:** an error-free observation channel with all three cues unique. The established E039 causal path should remain valid under its existing assumptions; a failure is a regression, not a new hypothesis result.
2. **Informative noisy channel:** each action's returned cue identifies the appropriate normalized rotation label with probability `0.8`, or either alternative with probability `0.1`. The mode is held constant during the exact probability reference checks. For the later control benchmark, mode switches are evaluator-owned and are hidden from the agent.
3. **Uninformative negative control:** cues are uniformly distributed and independent of the hidden rotation. No evaluator may report successful latent identification from these cues as evidence of learning; chance is `1/3` under the stated equal prior.

Benchmark admission must demonstrate that the observation instrument has the registered conditional distribution, that changes of evaluator seed affect only permitted random draws, that the agent cannot access hidden labels, and that replaying the same evaluator observation trace reproduces the same causal event history. Use fake candidates and deliberate information-leak tests before allowing any Darwin candidate to run.

## Comparison design for later, separate candidate development

Only after benchmark admission, compare a fixed one-observation estimator; an exact Bayesian filter using the stated likelihood model; a cumulative no-reset estimator; an intentionally shifted-evidence control; an uninformative-cue control; and an evaluator oracle. The Bayesian filter is a **reference**, not a claimed novel algorithm. If actions can select more or less informative evidence, add an explicit action-cost control rather than crediting extra observations for free.

Record mode-classification accuracy by evidence count, negative log-likelihood, Brier score, calibration by confidence bin, identification delay after each hidden mode switch, success and action cost per task, false regime-change alarms, restart replay equality, and the existing v50 causal-integrity invariants. Evaluate errors, not only successes. Retain the distinct development, calibration, and single-use final families required by `docs/v50/RESEARCH_PROTOCOL.md`.

**Do not register a new H50-L capability or set confirmatory thresholds from this draft.** First freeze the environment implementation, baseline, metrics, candidate and control definitions, seed-family allocations, and conjunctive failure rules in a separate committed pre-registration. Verify that no selected seeds or test items were used for prior development. Run a sensitivity benchmark before any candidate selection. Any final-family reuse, altered threshold, extra retry, or unregistered data access invalidates a confirmatory claim.

## Interpretation limits

A successful synthetic experiment could at most show finite-mode noisy evidence integration and a causal observation-to-decision path within the frozen task family. It would not demonstrate discovery of an unknown state space, online learning of the transition prior, open-world autonomous learning, subjectivity, consciousness, emotion, a satisfactory natural-language model, or robustness to arbitrary noise. Higher evidence levels require independently controlled evaluation and real scoped effects.

The existing E061 Gemma license gate stays untouched. No Hugging Face terms are presumed accepted, no model weights have been downloaded, no GitHub repository files were changed, and no Darwin tests have been claimed as executed in this continuation.

## Related primary literature

- Adams, Ryan Prescott; MacKay, David J. C. (2007). *Bayesian Online Changepoint Detection*. https://arxiv.org/abs/0710.3742
- Choi, Samuel Ping-Man; Yeung, Dit-Yan; Zhang, Nevin Lianwen (2001). *Solving Hidden-Mode Markov Decision Problems*. https://proceedings.mlr.press/r3/choi01a.html
- *Theoretical perspectives on active sensing* (review). https://pmc.ncbi.nlm.nih.gov/articles/PMC6116896/

These works provide established context for probabilistic change detection, hidden-mode control and active sensing. No priority or originality claim is made for the Bayesian reference calculation or the proposed controls.
