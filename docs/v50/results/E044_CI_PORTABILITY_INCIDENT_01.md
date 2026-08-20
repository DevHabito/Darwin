# E044 CI portability incident 01

Status: first failing run recorded. The failure is classified as a portability
defect in the freeze measurement, not a mutation of E043. This document records
the first run only; it does not claim that a later corrective run passed.

## Run

- Pull request: <https://github.com/DevHabito/Darwin/pull/2>
- Workflow run: <https://github.com/DevHabito/Darwin/actions/runs/31335446640>
- Head commit: `ca04a2c23615e3713700a56269126ab264cacab2`
- Event: `pull_request`
- Result: failed
- Total tests: 472
- Passed tests: 470
- Failed tests: 2
- Failed step: `Run test suite`

The only failures were:

- `test_e043_runtime_remains_byte_identical`
- `test_e043_protocol_remains_byte_identical`

## Observed hashes

The first test version hashed raw working-tree bytes. The local checkout used
LF, while the Windows Actions checkout materialized the same lines as CRLF.

| Frozen file | Registered LF SHA-256 | CI raw CRLF SHA-256 |
| --- | --- | --- |
| `src/darwin_v50/desktop_runtime.py` | `fd0d8aaf2bd1011addea581eaef172ce940157164dc013681d5326476d49f7e8` | `b3cfca4be41a59a6a80fe0ea6c16855b6c73846abf3f9081bf88470a5f22bc7f` |
| `docs/v50/EXPERIMENT_043_PERSISTENT_DESKTOP_RUNTIME.md` | `beea70ce6bcfd177a18d36feca016f5f93ed0bed7743fc73c31152cc19eaefad` | `86cf2b12a05ead4c124bd9b48df50765915067135a77ec78fd476c1be0489148` |

Converting the frozen LF content to CRLF reproduces both CI hashes exactly.
Normalizing only CRLF back to LF reproduces the originally registered hashes.
No expected SHA-256 value was recalibrated from the E044 head.

## Independent Git identity check

The Git blob identifiers are identical at the frozen base and the failing head:

| Frozen file | Base blob | Head blob |
| --- | --- | --- |
| `src/darwin_v50/desktop_runtime.py` | `01687c8e57aa1a867b18a66df9442b8745c08566` | `01687c8e57aa1a867b18a66df9442b8745c08566` |
| `docs/v50/EXPERIMENT_043_PERSISTENT_DESKTOP_RUNTIME.md` | `5becbc0177c7fc1fc1cfe0e2903e7a8323a7bd7d` | `5becbc0177c7fc1fc1cfe0e2903e7a8323a7bd7d` |

The frozen base is
`2602c57f21dc930b6fbe4426610469b39357119f`. A direct Git diff from that base
to the failing head is empty for both files.

## Classification

The first test conflated two properties:

1. semantic and Git-object identity of the frozen files; and
2. the checkout's platform-specific line-ending materialization.

E043 satisfied the first property. The test failed on the second. The failure
therefore does not show a change to the E043 runtime or protocol.

## Authorized correction boundary

The corrective test may:

- replace only `CRLF` byte pairs with `LF` before SHA-256 calculation;
- retain the original registered SHA-256 values;
- reject any remaining lone carriage return;
- require the frozen-base blob identifier to equal its registered value; and
- require the current `HEAD` blob identifier to equal the frozen-base blob.

It may not:

- modify either frozen E043 file;
- derive an expected digest or blob from the E044 head;
- normalize any content other than CRLF/LF line endings;
- remove the digest check;
- remove the Git blob identity check; or
- weaken another E044 admission criterion.

The first red run remains part of the record even if the bounded correction
later passes.
