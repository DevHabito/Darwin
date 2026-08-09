@echo off
cd /d "%~dp0"

where pyw >nul 2>nul
if %errorlevel%==0 (
    start "" pyw darwin_wake_word_guardian_v49_34.py
    exit /b
)

where py >nul 2>nul
if %errorlevel%==0 (
    start "" py darwin_wake_word_guardian_v49_34.py
    exit /b
)

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw darwin_wake_word_guardian_v49_34.py
    exit /b
)

where python >nul 2>nul
if %errorlevel%==0 (
    start "" python darwin_wake_word_guardian_v49_34.py
    exit /b
)

set "DARWIN_CODEX_PYTHONW=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"
if exist "%DARWIN_CODEX_PYTHONW%" (
    start "" "%DARWIN_CODEX_PYTHONW%" darwin_wake_word_guardian_v49_34.py
    exit /b
)

echo Nao encontrei Python no PATH.
echo Tambem nao encontrei o runtime Python fornecido pelo Codex.
pause
