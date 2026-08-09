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
