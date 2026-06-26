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
```

## Acordar por voz

O v49.34 inicia oculto e fica escutando em segundo plano:

- diga `Darwin` para abrir a presenca;
- diga `ta na hora de mimir Darwin` para voltar ao descanso;
- use `Instalar_Darwin_Acordar_Com_Voz_No_Windows.bat` para iniciar o guardiao junto com o Windows;
- use `Desinstalar_Darwin_Acordar_Com_Voz_Do_Windows.bat` para remover a inicializacao automatica.

O Windows precisa ter um reconhecedor de fala instalado. Se nao tiver, execute `Abrir_Darwin_Reparo_Voz.bat`.
O guardiao verifica isso antes de se esconder: quando a voz nao esta pronta, ele mostra os botoes `Reparar voz` e `Testar voz`. Instale o pacote de fala em portugues do Brasil antes de adicionar o guardiao a inicializacao do Windows.

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
