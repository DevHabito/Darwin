@echo off
setlocal
cd /d "%~dp0"
title Darwin - Reparar reconhecimento de voz

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0darwin_windows_speech_repair_v49_35.ps1"
if errorlevel 1 (
    echo.
    echo O reparo encontrou um erro. Veja darwin_home\voice_repair_v49_35.log.
    pause
)

endlocal
