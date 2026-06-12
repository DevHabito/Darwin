@echo off
cd /d "%~dp0"

where pyw >nul 2>nul
if %errorlevel%==0 (
    start "" pyw darwin_formula_sketchbook_v49_28.py
    exit /b
)

where py >nul 2>nul
if %errorlevel%==0 (
    start "" py darwin_formula_sketchbook_v49_28.py
    exit /b
)

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw darwin_formula_sketchbook_v49_28.py
    exit /b
)

where python >nul 2>nul
if %errorlevel%==0 (
    start "" python darwin_formula_sketchbook_v49_28.py
    exit /b
)

echo Nao encontrei Python no PATH.
echo Abra pelo Codex com: py darwin_formula_sketchbook_v49_28.py
pause
