# Darwin Local

Darwin e um laboratorio local de arquitetura cognitiva em Python, com RZS/Romero como regulador, memoria SQLite, loops cognitivos, preferencias, voz, grafo mental, jogos de memoria, historias, musica, desenho de formulas, curriculo autonomo, executor controlado e geometria relacional RZS/ELCL Regge.

## Como abrir

Use os atalhos `.bat` na raiz do projeto, por exemplo:

- `Abrir_Darwin_Executor_Controlado.bat`
- `Abrir_Darwin_RZS_ELCL_Regge.bat`
- `Abrir_Darwin_Acordar_Com_Voz.bat`
- `Abrir_Darwin_Grafo_Mental.bat`
- `Abrir_Darwin_Lapis_Formulas.bat`

Ou rode direto com Python:

```powershell
py darwin_controlled_autonomous_executor_v49_32.py
py darwin_rzs_elcl_regge_geometry_v49_33.py
py darwin_wake_word_guardian_v49_34.py
py darwin_basic_language_core_v49_36.py --self-test --details
py darwin_contextual_language_learning_v49_37.py --self-test --details
py darwin_autonomous_activity_choice_v49_38.py --self-test --details
py darwin_activity_outcome_learning_v49_39.py --self-test --details
py darwin_relational_world_model_v49_40.py --self-test --details
py darwin_predictive_goal_planner_v49_41.py --self-test --details
py darwin_goal_execution_loop_v49_42.py --self-test --details
py darwin_intrinsic_motivation_core_v49_43.py --self-test --details
```

## Acordar por voz

O v49.34 inicia oculto e fica escutando em segundo plano:

- diga `Darwin` para abrir a presenca;
- diga `ta na hora de mimir Darwin` para voltar ao descanso;
- use `Instalar_Darwin_Acordar_Com_Voz_No_Windows.bat` para iniciar o guardiao junto com o Windows;
- use `Desinstalar_Darwin_Acordar_Com_Voz_Do_Windows.bat` para remover a inicializacao automatica.

O guardiao usa `System.Speech` quando ha um reconhecedor classico e a API
moderna `Windows.Media.SpeechRecognition` no Windows 11. Execute
`Reparar_Darwin_Voz_Windows.bat` uma vez para instalar `Speech pt-BR`,
verificar microfone e consentimento de fala online e ativar a inicializacao.
Quando a voz nao esta pronta, a janela permanece aberta com os botoes
`Reparar voz` e `Testar voz`.

## Vocabulario basico

O v49.36 integra ao `CompanionCore` perguntas sobre nome, estado, sentimento
e sono, junto com sinonimos e respostas basicas do Felipe. As respostas sobre
estado e descanso consultam o SQLite; o Darwin tambem faz perguntas de volta.

```powershell
py darwin_basic_language_core_v49_36.py --self-test --details
py darwin_check_v49_36_basic_language.py --details
```

## Aprendizagem de palavras

O v49.37 mantem contexto entre turnos, pergunta o significado de palavras
desconhecidas, aceita definicoes, exemplos e correcoes e recupera o conceito
em outra sessao. Uma palavra so entra na memoria semantica depois de evidencia
repetida.

```powershell
py darwin_contextual_language_learning_v49_37.py --self-test --details
py darwin_check_v49_37_contextual_language.py --details
```

## Escolha autonoma de atividades

O v49.38 permite perguntar ao Darwin se ele quer jogar ou fazer alguma
atividade. O convite nao escolhe por ele: memoria afetiva, curiosidade,
aprendizagem, energia, novidade, repeticao e RZS calculam uma competicao entre
jogo da memoria, musica, historias, desenho de formulas, conversa e descanso.
Somente no guardiao de voz real a opcao vencedora pode abrir sua janela.

```powershell
py darwin_autonomous_activity_choice_v49_38.py --self-test --details
py darwin_check_v49_38_activity_choice.py --details
```

## Aprendizagem pelo resultado

O v49.39 observa a conclusao real da atividade que o v49.38 abriu. Ele compara
o valor previsto com conforto, curiosidade, estabilidade, erros, correcoes ou
eficiencia registrados pelo aplicativo. O erro de previsao atualiza uma
preferencia operacional, regulada pelo RZS, que participa da proxima escolha.
Depois da atividade, pergunte `Darwin, voce gostou?`.

```powershell
py darwin_activity_outcome_learning_v49_39.py --self-test --details
py darwin_check_v49_39_activity_outcome_learning.py --details
```

## Modelo de mundo relacional

O v49.40 traduz jogo, musica, historia, desenho, conversa e descanso para
propriedades comuns. Assim, uma relacao aprendida em um dominio pode contribuir
para prever outro dominio. As previsoes de valor e incerteza entram na escolha
de atividades e continuam submetidas ao RZS.

```powershell
py darwin_relational_world_model_v49_40.py --self-test --details
py darwin_check_v49_40_relational_world_model.py --details
```

## Objetivos e planejamento

O v49.41 transforma incerteza, preferencias, erros de previsao e energia em
objetivos concorrentes. O RZS escolhe ou bloqueia o objetivo, e cada objetivo
gera etapas causais e uma condicao explicita de parada. Pergunte
`Darwin, qual seu objetivo agora?`.

```powershell
py darwin_predictive_goal_planner_v49_41.py --self-test --details
py darwin_check_v49_41_predictive_goal_planner.py --details
```

## Execucao de objetivos

O v49.42 acompanha o plano ate uma evidencia real. Uma atividade alinhada fica
aguardando seu resultado; uma escolha diferente provoca replanejamento; e
objetivos internos podem ser concluidos sem inventar resultado externo.
Use `Darwin, comece seu objetivo`.

```powershell
py darwin_goal_execution_loop_v49_42.py --self-test --details
py darwin_check_v49_42_goal_execution_loop.py --details
```

## Motivacoes e valores

O v49.43 transforma incerteza, erro, energia, continuidade relacional,
autonomia e coerencia em impulsos concorrentes. Valores so emergem depois de
evidencia repetida em mais de um contexto. Pergunte
`Darwin, o que te motiva agora?`.

```powershell
py darwin_intrinsic_motivation_core_v49_43.py --self-test --details
py darwin_check_v49_43_intrinsic_motivation.py --details
```

## Checkers principais

```powershell
py darwin_check_v49_33_rzs_elcl_regge_geometry.py --details
py darwin_check_v49_34_wake_word_guardian.py --details
py darwin_check_v49_32_controlled_executor.py --details
py darwin_check_v49_31_autonomous_curriculum.py --details
py darwin_check_v49_3_rzs_nervous_system.py --details
```

## Estado local

O arquivo `darwin_home/darwin.db` e a memoria atual do Darwin e esta versionado neste backup.

Ficam fora do Git por serem pesados ou regeneraveis:

- `baselines/`
- `darwin_home/backups/`
- `darwin_home/logs/`
- `darwin_home/snapshots/`
- `darwin_home/music_cache_v49_16/`
- caches Python

## Nota

Este repositorio deve ser mantido privado se o banco `darwin_home/darwin.db` contiver memoria pessoal, experimentos privados ou dados sensiveis.
