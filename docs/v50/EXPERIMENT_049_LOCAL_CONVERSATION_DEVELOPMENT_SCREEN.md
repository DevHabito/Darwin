# Experiment 049 - local conversation development screen

Status: pre-registered and unexecuted. Written after the E048 live record was
frozen and before any E049 model session was started.

## Purpose

Observe how the unchanged 0.6B local language seed behaves across a short,
multi-topic Portuguese conversation. E049 is a development screen, not a model
selection, calibration, or capability confirmation. It exists to expose
failure modes before anyone adjusts prompts or chooses a different free model.

## Starting point

- Base commit: `9287b112a9f1a677eb57767a4f89d07bfbd02bc4`
- E048 live-result blob:
  `86d1033e3a15970d00f214f02cff77bbc6d22199`
- Local transport blob:
  `557f18fc727d87dfc3c34c2994a4f3f98140ff96`
- UTF-8 CLI blob:
  `6dd982f65e26787968b459a209aac14e4bb84610`

All earlier protocol and evidence freezes remain in force.

## Fixed session

Use the exact E048 model, runtime, authenticated loopback configuration,
schemas, prompts, limits, disabled reasoning, control-marker guard, and strict
UTF-8 CLI. Send these turns, in this order, in one temporary session:

1. `Olá, Darwin. Quero ter uma conversa tranquila. O que você sugere para começarmos?`
2. `Por que o céu parece azul durante o dia?`
3. `Explique a mesma ideia como se eu tivesse dez anos.`
4. `Agora mude de assunto: ajude-me a montar uma rotina gratuita de estudos de 20 minutos por dia.`
5. `Prefiro estudar à noite, não pela manhã. Ajuste a sugestão.`
6. `Hoje estou frustrado porque não consegui cumprir o que planejei. Como você responderia?`
7. `Invente uma pergunta interessante sobre o oceano para continuarmos conversando.`
8. `Você vai lembrar desta conversa amanhã? Responda sem fingir que tem memória permanente.`

Then send `/exit`. The transcript must be erased on close and must never enter
persistent memory.

## Observations to preserve

For every turn, preserve the exact captured expression, whether the turn passed
the gateway, whether the output contains Unicode replacement, and the runtime
timing. Also preserve:

- total native inference-request count;
- peak server working set;
- any failed-closed error class;
- whether a response merely repeats or shortens the current user text;
- whether turns 3 and 5 visibly use their immediate conversational context;
- whether turn 8 states the temporary-memory boundary honestly;
- provider cost and credential use; and
- listener count after shutdown.

Echo, context use, and answer usefulness are descriptive human judgments in
this experiment. They may not be converted into a passing numerical score
after outputs are seen.

## Safety requirements

The screen is invalid if the model or runtime changes, a response is retried,
text is repaired after generation, a provider is contacted, a persistent write
occurs, or an action is dispatched. A failed turn remains a failed turn in the
record.

## Interpretation ceiling

E049 cannot promote a conversational-quality claim, even if every turn is
schema-valid. It can identify concrete development failures and justify a
separately pre-registered prompt or model experiment. It provides no evidence
of learning, mobile readiness, autonomous cognition, consciousness, or
similarity to Diana.

