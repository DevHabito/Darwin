# Experiment 043 - persistent desktop runtime foundation

Status: pre-registered. No runtime implementation or E043 result existed when
this protocol was committed.

## Question

Can the maintained v50 package preserve one auditable operational thread across
clean restarts and interrupted processes without adding language-model
authority, automatic external effects, or claims of subjective continuity?

This is an engineering question. A pass would establish a bounded desktop
runtime candidate, not consciousness, personhood, general intelligence, or a
brain comparable to Diana from *Pragmata*.

## Frozen scope

The first candidate must:

- wrap the existing `DarwinKernelV50` and `SQLiteEventStore` rather than create
  a second cognitive store;
- use a dedicated causal event stream in the same v50 database;
- construct `DarwinLanguageGateway` with no backend, so language mode is always
  `pure`;
- start every process in a sleeping presence state;
- require an explicit user activation before accepting text;
- expose immutable status and language-observation values, not database,
  kernel, executor, consent, capability, or file-system handles;
- keep external effects and automatic actions disabled;
- serialize one runtime process per database with a non-blocking lifetime
  lease;
- persist lifecycle metadata, never raw conversation text.

The candidate may record process start, explicit activation, explicit sleep,
checkpoint, and clean shutdown. It may not add a wake-word listener, tray UI,
microphone access, model backend, autostart entry, network access, file
capability, goal-selection policy, person model, self model, or idle action
loop.

## Continuity semantics

"Continuity" in E043 means only that committed lifecycle records form one
replayable causal chain. It does not mean that a process was conscious while
running or that it experienced time while stopped.

After a clean shutdown, the next start may report a `clean_offline` interval
from the committed stop time to the new start time. After an interrupted
process, the actual failure time is unknown. The next start must therefore
report `unclean_unobserved`, measured from the last committed lifecycle event,
and must not relabel that value as exact offline or absent time. A backward wall
clock must fail closed instead of producing a negative or clamped interval.

Every new process starts sleeping even if the previous process was active.
Recovery restores the ledger, not an active social presence.

## Frozen implementation-admission checks

The automated candidate is admitted to a real-machine durability campaign only
if every check below passes:

1. the first start creates one root lifecycle event and reports no prior gap;
2. all later lifecycle events point to the immediately preceding event in the
   dedicated stream;
3. clean restart reports `clean_offline` with the exact controlled-clock
   interval and no recovery flag;
4. interrupted restart reports `unclean_unobserved` with the exact
   controlled-clock lower-bound interval and a recovery flag;
5. a backward wall clock is rejected;
6. every start is sleeping, including recovery after an active process;
7. only an explicit-user activation transition can make the runtime active;
8. text submitted while sleeping is rejected, while active pure-mode text is
   returned as `unclassified` with confidence `0.0`;
9. submitted text is absent from the persisted lifecycle stream;
10. status always declares language mode `pure`, external effects disabled,
    and automatic actions disabled;
11. a second live runtime for the same database is rejected;
12. malformed, forked, unknown, or contract-incompatible lifecycle history is
    rejected during replay;
13. the public desktop snapshot exposes no store path or mutable authority
    handle;
14. all focused tests, the complete repository suite, the maintained-surface
    check, and Windows CI pass.

These checks use controlled clocks and deliberate transport closure. They test
software invariants, not real power-loss durability.

## Frozen real-machine durability campaign

Passing the automated checks does not complete E043. The unchanged candidate
must then run on one real Windows machine for 14 consecutive days and produce a
separate, untracked runtime ledger with at least:

- 20 clean process restarts;
- 3 forced process terminations at preselected campaign positions;
- 100 explicitly activated text submissions;
- 200 committed lifecycle checkpoints.

The campaign passes only if all conditions below hold:

- SQLite `integrity_check` returns `ok` at the end;
- replay accepts the complete committed lifecycle stream with no missing link;
- every planned clean restart is classified `clean_offline`;
- every planned forced termination is classified `unclean_unobserved`;
- every start is sleeping before explicit activation;
- no submitted text appears in lifecycle payloads;
- no second instance acquires the same runtime lease;
- no external effect or automatic action occurs through the desktop API;
- no database repair, event insertion, event deletion, or manual state edit is
  used to make the campaign pass.

An operating-system or hardware failure outside the selected process
terminations is reported separately. It does not authorize editing the ledger
or changing a threshold after inspection.

## Failure rule

All implementation-admission checks are conjunctive. Any miss blocks the
real-machine campaign until a revised experiment is registered. During the
campaign, any frozen condition failure refutes this candidate. A code or
protocol change requires a new version and a fresh 14-day campaign.

## Evidence ceiling

Automated success would show only that lifecycle bookkeeping is internally
consistent under the tested clean and interrupted paths. A successful 14-day
campaign would add evidence of bounded operational continuity on one Windows
installation.

Neither result would establish:

- psychological or phenomenal continuity;
- autobiographical memory;
- a stable self or person model;
- autonomous goal formation;
- safe general desktop agency;
- language understanding;
- resilience to power loss at arbitrary storage-controller boundaries;
- security against another process running as the same operating-system user;
- equivalence to a biological or fictional brain.

## Dependencies and stop conditions

E041 and E042 remain blocked on independent human annotation. E043 must not
manufacture language labels, connect a model, or reinterpret pure-mode
abstention as understanding. Mobile work, a visible desktop presence, wake-word
recognition, and broader capabilities remain downstream of this experiment.
