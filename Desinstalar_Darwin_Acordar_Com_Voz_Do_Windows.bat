@echo off
setlocal

set "DARWIN_LINK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Darwin Wake Guardian.lnk"

if exist "%DARWIN_LINK%" (
    del /q "%DARWIN_LINK%"
)

if exist "%DARWIN_LINK%" (
    echo Nao foi possivel remover o atalho de inicializacao.
) else (
    echo Darwin Wake Guardian removido da inicializacao do Windows.
)

pause
endlocal
