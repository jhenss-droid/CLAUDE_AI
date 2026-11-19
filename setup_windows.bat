@echo off
setlocal
rem One-time setup on a Windows computer. Safe to run again.
rem Double-click it, or run it from a Command Prompt in this folder.

set "PROJECT=%~dp0"
set "VENV=%USERPROFILE%\.alpaca-trader-venv"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto nopython
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul || goto nopython

if exist "%VENV%\Scripts\python.exe" goto haveenv
echo Creating the Python environment for this computer in %VENV% ...
%PY% -m venv "%VENV%" || goto fail
:haveenv
"%VENV%\Scripts\python.exe" -m pip install --quiet --upgrade pip
"%VENV%\Scripts\python.exe" -m pip install --quiet -r "%PROJECT%requirements.txt" || goto fail

where git >nul 2>nul || echo NOTE: Git for Windows was not found. Install it from https://git-scm.com/download/win so Claude Code can run the Trader safety check.

echo Running the tests...
pushd "%PROJECT%"
"%VENV%\Scripts\python.exe" -B -m pytest -q -p no:cacheprovider
set "RC=%errorlevel%"
popd
if not "%RC%"=="0" goto fail

echo.
echo Setup complete. Run the bot with:  trader.bat validate ^<plan_id^>
pause
exit /b 0

:nopython
echo Python 3.10 or newer is required.
echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH", then run this again.
pause
exit /b 1

:fail
echo Setup failed. See the messages above.
pause
exit /b 1
