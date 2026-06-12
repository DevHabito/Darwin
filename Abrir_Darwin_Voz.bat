@echo off
cd /d "%~dp0"

where pyw >nul 2>nul
if %errorlevel%==0 (
    start "" pyw darwin_first_words_v49_10.py
    exit /b
)

where py >nul 2>nul
if %errorlevel%==0 (
    start "" py darwin_first_words_v49_10.py
    exit /b
)

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw darwin_first_words_v49_10.py
    exit /b
)

where python >nul 2>nul
if %errorlevel%==0 (
    start "" python darwin_first_words_v49_10.py
    exit /b
)

echo Nao encontrei Python no PATH.
echo Abra pelo Codex com: py darwin_first_words_v49_10.py
pause
