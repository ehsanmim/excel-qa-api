@echo off
rem Run the test suite. Extra arguments go to pytest, e.g. bin\test.bat -k upload
rem The live LLM tests run only when an LLM key is configured (see .env.example).
setlocal
cd /d "%~dp0.."
if not exist .venv\Scripts\python.exe (
  echo No .venv found. Create it first: python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
  exit /b 1
)
.venv\Scripts\python.exe -m pytest %*
