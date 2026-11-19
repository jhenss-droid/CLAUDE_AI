@echo off
setlocal
rem Runs the bot on Windows, e.g.:  trader.bat validate btcusd-2026-11-20
set "VENV_PY=%USERPROFILE%\.alpaca-trader-venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo This computer is not set up yet. Run setup_windows.bat first.
  exit /b 1
)
set "PYTHONPATH=%~dp0."
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONIOENCODING=utf-8"
"%VENV_PY%" -m alpaca_bot %*
