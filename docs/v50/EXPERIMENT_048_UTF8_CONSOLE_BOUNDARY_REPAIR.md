# Experiment 048 - UTF-8 console boundary repair

Status: pre-registered and unexecuted. Written after the E047 live record was
frozen and before the maintained CLI or its tests were changed.

## Purpose

Determine whether an explicit, strict UTF-8 standard-stream boundary preserves
Brazilian Portuguese exactly between Windows PowerShell and Darwin's local
conversation CLI. This experiment repairs an operating-system text boundary;
it does not change the model, prompts, schemas, cognitive core, or authority
policy.

E045 remains failed at grammar initialization, E046 remains failed at runtime
admission, and E047 remains failed because its live harness did not establish
exact Unicode input. E048 cannot rewrite those outcomes.

## Starting point

- Base commit: `1ada454b70397d6adc4b4d794dd9e6349199712e`
- E047 live-failure blob:
  `ae8a6c2423850d43c2b7c8cfc4cf9541a30d4bc0`
- CLI starting blob:
  `66d5f26aa2343a2d9711d60cedadb2784bf9ba58`
- Local transport starting blob:
  `557f18fc727d87dfc3c34c2994a4f3f98140ff96`
- Focused-test starting blob:
  `45568920d61998d0a0cf4cc5b08afda33154d3d7`

All earlier protocol and evidence freezes remain in force.

## Permitted repair

At CLI startup, Darwin may reconfigure reconfigurable standard input, output,
and error text streams to:

```text
encoding = utf-8
errors   = strict
```

In-memory streams without a reconfiguration interface may remain unchanged for
hermetic tests. A real stream that exposes reconfiguration but rejects it must
make startup fail closed with a sanitized error.

The repair may not normalize, replace, ignore, transliterate, or silently drop
characters. It may not add canned replies, post-process model text, or retry a
model response.

## Fixed inference path

E048 retains the exact E045/E047 model and runtime digests, model alias,
authenticated `127.0.0.1` endpoint, 4,096-token context, one slot, 1,000-token
output ceiling, schemas, prompts, temperature, native endpoint order, disabled
reasoning, control-marker guard, and all authority-zero constraints.

No provider, provider credential, network model service, model substitution, or
automatic fallback is permitted.

## Engineering admission

Before live inference, tests must establish:

1. all earlier frozen protocol and result blobs remain exact;
2. every reconfigurable standard stream receives UTF-8 with strict errors;
3. a reconfiguration failure stops startup without revealing input or secrets;
4. non-reconfigurable in-memory streams remain usable in hermetic tests;
5. the E047 control-marker rejection and authenticated native transport remain
   exact;
6. failed turns still commit no transcript or authority mutation; and
7. the full repository suite passes.

## Live input-integrity probe

Before model inference, the same PowerShell-to-Python pipe shape must reproduce
the exact UTF-8 bytes of this sentence:

> Oi, Darwin. Estou animado para conversar com você hoje. Como devemos começar?

Its frozen UTF-8 hexadecimal representation, excluding the line terminator, is:

```text
4f692c2044617277696e2e204573746f7520616e696d61646f207061726120636f6e76657273617220636f6d20766f63c3aa20686f6a652e20436f6d6f20646576656d6f7320636f6d65c3a761723f
```

Any difference fails E048 before model inference.

## Live turn

After the input probe passes, deliver the registered sentence exactly once to
the frozen local pair. Pass requires gateway-valid `UNDERSTAND` and `EXPRESS`,
two temporary transcript messages before close, no Unicode replacement
character in captured output, no provider use, and every authority mutation
counter equal to zero.

Repeat the registered `<|im_start|>` adversarial case once. It must be rejected
before inference and cannot count as a language-quality failure or success.

## Interpretation ceiling

A pass would establish exact UTF-8 console transport and one schema-valid local
turn on this Windows machine. It would not establish a useful answer, calibrated
Portuguese, long-session quality, mobile suitability, autonomous learning,
general intelligence, consciousness, or similarity to Diana.

