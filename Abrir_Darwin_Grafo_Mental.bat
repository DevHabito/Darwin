@echo off
cd /d "%~dp0"

where pyw >nul 2>nul
if %errorlevel%==0 (
    start "" pyw darwin_mind_graph_v49_14.py
    exit /b
)

where py >nul 2>nul
if %errorlevel%==0 (
    start "" py darwin_mind_graph_v49_14.py
    exit /b
)

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw darwin_mind_graph_v49_14.py
    exit /b
)

where python >nul 2>nul
if %errorlevel%==0 (
    start "" python darwin_mind_graph_v49_14.py
    exit /b
)

echo Nao encontrei Python no PATH.
echo Abra pelo Codex com: py darwin_mind_graph_v49_14.py
pause
