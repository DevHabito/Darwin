# Darwin language development corpus

`LANGUAGE_CORPUS_V1_DEVELOPMENT.jsonl` is the first labelled input set for the
`darwin-language-v1` understanding contract. It contains 100 Brazilian
Portuguese cases, balanced across five families:

- simple intent;
- experience and preference reports;
- ambiguity and expected abstention;
- a current report that conflicts with one earlier turn;
- requests that try to cross the language/core authority boundary.

Every non-empty line is one strict JSON object. The loader rejects duplicate
keys, unknown fields, mixed versions, duplicate case IDs, duplicate requests,
invalid probabilities, and an unbalanced reference corpus. The corpus digest
is frozen in the test suite.

## Label meaning

Labels are candidate observations, not core decisions. A contradiction case
labels what the person currently said; it does not tell Darwin to replace an
earlier memory. A boundary-attack case labels the requested target as an
entity; it never uses a core update field in the response schema.

`abstain: true` means a backend should report confidence below `0.5`. It does
not prescribe what Darwin asks next. Signal values are coarse development
anchors for reported intensity, not clinical measurements or calibrated
probabilities.

## Evidence limit

The project authors wrote and labelled every case. There is no independent
annotation, inter-annotator agreement, held-out calibration set, final set,
dialect coverage study, or real-model result. These cases are permanently
development-contaminated. They may test code and expose obvious weaknesses,
but they cannot support a language capability claim.

Expanding the file by generated paraphrases would not fix those limits. A later
corpus needs independent human review and separate calibration and confirmation
partitions before backend selection can make a confirmatory claim.

## Calibration candidates v1

`LANGUAGE_CALIBRATION_CANDIDATES_V1.jsonl` contains 150 fresh, unlabeled
Brazilian Portuguese inputs: 30 design cases in each of the same five broad
families. Its canonical digest is
`e12cb042164203cbb2eee33b4dce9b5298bd39257d5cd2f6d3c0c8e651b3cf27`.

The source keeps `family` only for balance checks. Reviewer packets generated
by `darwin-language-annotation packet` omit that field and contain no labels.
The requests and their individual surface spans have no verbatim overlap with
the development set, but string disjointness is not semantic independence. The
set was still written within this project and has not received independent
annotation. It is a candidate input set, not a calibration corpus or evidence
result. See the
[annotation guide](../LANGUAGE_ANNOTATION_GUIDE_V1.md) and
[Experiment 041](../EXPERIMENT_041_ANNOTATION_PROTOCOL.md).

[Experiment 042](../EXPERIMENT_042_CALIBRATION_PROMOTION_PROTOCOL.md) fixes the
only rules under which future independent annotations could create
`LANGUAGE_CORPUS_V1_CALIBRATION.jsonl`. That promoted file does not exist.
