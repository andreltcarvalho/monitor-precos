@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Requer Python 3.12 ou superior.
  py -3.12 -m venv .venv
  if errorlevel 1 (
    echo Instale Python 3.12 e execute novamente.
    pause
    exit /b 1
  )
)
".venv\Scripts\python.exe" -m pip install --cache-dir .cache\pip -r requirements.txt
pause
