@echo off
rem Start the API with auto-reload and print where to open it.
rem Usage: bin\serve.bat   (set HOST or PORT first to override, e.g. set PORT=9000)
setlocal
cd /d "%~dp0.."
if not exist .venv\Scripts\python.exe (
  echo No .venv found. Create it first: python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
  exit /b 1
)
if "%HOST%"=="" set HOST=127.0.0.1
if "%PORT%"=="" set PORT=8000
echo.
echo   Excel Q^&A API
echo   API:     http://%HOST%:%PORT%
echo   Swagger: http://%HOST%:%PORT%/docs
echo   Stop with Ctrl+C
echo.
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host %HOST% --port %PORT%
