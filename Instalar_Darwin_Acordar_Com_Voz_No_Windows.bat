@echo off
setlocal
cd /d "%~dp0"

set "DARWIN_TARGET=%~dp0Abrir_Darwin_Acordar_Com_Voz.bat"
set "DARWIN_WORKDIR=%~dp0"
set "DARWIN_LINK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Darwin Wake Guardian.lnk"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$shell = New-Object -ComObject WScript.Shell; $shortcut = $shell.CreateShortcut($env:DARWIN_LINK); $shortcut.TargetPath = $env:DARWIN_TARGET; $shortcut.WorkingDirectory = $env:DARWIN_WORKDIR; $shortcut.WindowStyle = 7; $shortcut.Description = 'Darwin Wake Guardian v49.34'; $shortcut.Save()"

if exist "%DARWIN_LINK%" (
    echo Darwin Wake Guardian instalado na inicializacao do Windows.
    echo Ele iniciara oculto no proximo login.
) else (
    echo Nao foi possivel criar o atalho de inicializacao.
)

pause
endlocal
