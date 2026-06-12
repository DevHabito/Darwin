@echo off
cd /d "%~dp0"

where pyw >nul 2>nul
if %errorlevel%==0 (
    start "" pyw darwin_voice_orb_v49_6.py
    exit /b
)

where py >nul 2>nul
if %errorlevel%==0 (
    start "" py darwin_voice_orb_v49_6.py
    exit /b
)

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw darwin_voice_orb_v49_6.py
    exit /b
)

where python >nul 2>nul
if %errorlevel%==0 (
    start "" python darwin_voice_orb_v49_6.py
    exit /b
)

echo Nao encontrei Python no PATH.
echo Abra pelo Codex com: py darwin_voice_orb_v49_6.py
pause
