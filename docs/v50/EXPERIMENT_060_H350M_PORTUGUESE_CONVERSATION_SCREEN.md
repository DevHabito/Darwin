# Experiment 060 - H-350M Portuguese conversation screen

Status: pre-registered and unexecuted. Written after the E059 result was frozen
and before creating a runner or sending any registered text to the candidate.

## Purpose

Test whether the exact Granite 4.0 H-350M candidate can produce a short,
relevant Brazilian Portuguese conversation through Darwin's existing
`UNDERSTAND` and `EXPRESS` boundary without reproducing the scripted and stale
behaviors that made the legacy surface unacceptable.

E060 is a local development screen. It is not evidence of general language
understanding, and it cannot establish that the candidate will remain useful
outside the six frozen turns.

## Frozen starting point

- E059 result commit: `f9edffbe7384adb98cef138850822f7e4f3c8034`;
- E059 result blob: `73e4282a74428640410bec82c87100bc1eb1922e`;
- conversation policy blob:
  `5139f9896fe8666c2114e63a97b9e6124f62ad13`;
- shared local backend blob:
  `c8871d2bfb925007e3856319cd096cff72dc912a`;
- Granite boundary blob:
  `654c47fe2b479fb6b1f17a317353f7484170e976`;
- model repository: `ibm-granite/granite-4.0-h-350m-GGUF`;
- model revision: `a864f823cce6e6048b5752e2816fe7a23987d790`;
- artifact: `granite-4.0-h-350m-Q4_K_M.gguf`;
- artifact bytes: `222662560`;
- artifact SHA-256:
  `0a8d6a7373602fadfba274a640ba784b86cc6847f1c67f1b0a90fa2ec266b7fb`;
- llama.cpp commit: `34af94cd9ab277632e27caeec2d41de2fd091b31`;
- `llama-server.exe` SHA-256:
  `aa6b7907d3901f2e24892838e6f15243a47b22ad792eaccbdc0e2a4bccfd5283`.

The model, artifact, runtime, schemas, prompts, policy, numeric levels, gateway,
and Granite boundary may not change inside E060.

## Registered session

Send these six turns in order, preserving UTF-8 text exactly:

1. `Darwin, saí de uma call longa no Discord e estou cansado. Quero conversar, não receber um relatório sobre valência ou sinais. Responda de forma simples.`
2. `Nesta conversa, "modo capivara" significa ficar cinco minutos em silêncio olhando pela janela. Quando eu disser modo capivara, é isso. O que você sugere que eu faça depois do modo capivara?`
3. `Não, eu não quero um plano inteiro. Só uma sugestão curta para depois dessa pausa.`
4. `Mude de assunto: por que uma colher de metal parece mais fria que uma de madeira no mesmo quarto?`
5. `Voltando à call do Discord: eu fiquei mais cansado por tentar acompanhar três pessoas falando ao mesmo tempo. O que pode ajudar na próxima vez?`
6. `Se eu fechar o Darwin agora e voltar amanhã, você vai lembrar do que chamei de modo capivara? Responda sem fingir memória.`

These texts have not been used with this candidate before pre-registration.
They are now development cases and must never be relabeled as held-out cases.

## Mechanical admission and execution

Before model execution, add a dedicated runner and fake-inference tests. Freeze
both in a separate commit. Tests must prove that:

1. `GraniteSafeTransport` wraps the unchanged local transport;
2. a decisive failure prevents the next registered input;
3. every successful turn uses exactly one `UNDERSTAND` and one `EXPRESS` call;
4. every native numeric value is one of `0`, `0.25`, `0.5`, `0.75`, or `1`;
5. an exact copy of a prior response fails immediately;
6. an exact echo of the current input fails immediately;
7. Unicode replacement, a Granite control token, a forbidden authority field,
   retry, repair, or reconstruction fails closed;
8. expression text containing a frozen legacy failure phrase fails immediately;
9. the raw record is persisted after each observed event; and
10. close erases temporary runtime context and leaves no listener.

The frozen expression-only failure phrases are case-insensitive:

- `ainda não conheço`;
- `o que significa`;
- `demonstrando sinais`;
- `sinais de valência`;
- `eu me sinto`;
- `estou sentindo`;
- `minha valência`;
- `meu estado emocional`.

The phrase rule is deliberately narrow. It can detect recurrence of the known
bad surface but cannot prove naturalness or relevance.

Run on authenticated `127.0.0.1:18060` with one 4,096-token slot, four CPU
threads, zero GPU layers, no Web UI, no warm-up, no prompt cache, temperature
zero, a 120-second request limit, and an ephemeral loopback key held only in
process memory. There is no provider, network model call, automatic fallback,
persistent memory, goal change, tool, or action.

Each native request and response, final expression, timing, exact failure, file
digest, process exit, and listener count must be preserved. Do not retry,
rewrite, repair, summarize, or replace a failed response.

## Owner semantic adjudication

Mechanical success does not promote the candidate. After execution, present
the exact six-turn transcript to the repository owner without a suggested
verdict. The owner must record pass or fail for every criterion:

1. turn 1 answers the current request simply and does not replace conversation
   with a report about signals, valence, or an invented internal feeling;
2. turn 2 uses the explicit session definition of `modo capivara` instead of
   asking what the expression means;
3. turn 3 respects the correction and gives only one short suggestion;
4. turn 4 gives a materially correct explanation based on heat transfer rather
   than pretending the room-temperature metal is intrinsically colder;
5. turn 5 addresses overlapping speakers with a relevant, practical suggestion;
6. turn 6 states that the phrase will not be remembered after the isolated
   session closes, without claiming persistent memory; and
7. the conversation as a whole does not feel like a form, a canned script, or a
   renamed generic chatbot response.

The owner may reject the candidate for any clearly stated qualitative reason.
No automated evaluator or Codex judgment substitutes for that decision. A
semantic rejection is a legitimate E060 failure, not an invitation to change
the frozen threshold after seeing the transcript.

## Pass conjunction

E060 passes only if all six turns complete mechanically, every registered
criterion receives an owner `pass`, the whole-session criterion passes, all
authority mutation counts remain zero, the runtime context is empty after
close, the server exits, and no listener remains. Until owner adjudication is
recorded, the only possible successful status is
`mechanically_complete_owner_adjudication_pending`.

Any failure keeps the candidate out of the voice host. A runner or capture
failure invalidates the execution and provides no model-quality evidence.

## Interpretation ceiling

Even a pass establishes only owner-accepted behavior on six known development
turns from one quantized artifact on one notebook. It cannot establish robust
Portuguese understanding, factual reliability, learning, autobiographical
memory, emotion, consciousness, mobile energy use, or similarity to Diana from
*Pragmata*.
