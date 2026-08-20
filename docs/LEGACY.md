# Legacy prototypes

Darwin grew through a long sequence of v47-v49 experiments. Most of those
experiments live as standalone Python files in the repository root. They were
useful while the architecture was being explored, but they are not the current
development model.

## Why the files still live at the root

The prototypes form a dense compatibility graph:

- modules import one another by their root-level filenames;
- launchers call scripts through relative paths;
- some modules start other modules as subprocesses;
- most of them share `darwin_home/darwin.db`.

A cosmetic bulk move would silently break that graph. The files will remain in
place until a migration can introduce stable package imports, explicit runtime
paths, and compatibility launchers with tests.

## Maintenance policy

- v47-v49 code is preserved, not extended.
- Bug fixes should be narrow and accompanied by the existing self-test when one
  is available.
- New cognitive experiments belong under `src/darwin_v50`.
- New automated tests belong under `tests`.
- New research claims require a document under `docs/v50` before final seeds are
  run.
- New runtime data must never be committed.

## Local data

The legacy runtime stores conversations, learned values, snapshots, and other
session records under `darwin_home`. Those files can contain personal material.
Git now ignores the entire directory except for `config.example.json`.

Removing a file from the current Git tree does not remove it from older commits.
Rewriting public repository history is a separate destructive operation and
must be planned explicitly.

## Future migration

A safe migration should happen in this order:

1. map imports, subprocess targets, launcher targets, and database paths;
2. add tests around every still-used entry point;
3. move shared code behind package APIs;
4. replace versioned filenames with stable commands;
5. keep thin compatibility launchers for users of the old names;
6. archive prototypes only after the compatibility suite passes.

Until then, the root is a historical compatibility surface. The maintained
architecture is the v50 package.
