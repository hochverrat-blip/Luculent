@echo off
setlocal
cd /d "%~dp0"

set "VENV_PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%VENV_PYTHON%" goto find_python

"%VENV_PYTHON%" -c "import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] <= (3, 13) else 1)" >nul 2>&1
if not errorlevel 1 goto environment_ready
echo The existing .venv uses an incompatible Python version.
echo Delete the .venv folder and run this file again.
goto launch_failed

:find_python
set "PYTHON_COMMAND="
call :try_python py -3.13
call :try_python py -3.12
call :try_python py -3.11
call :try_python py -3.10
call :try_python python
call :try_python python3

if not defined PYTHON_COMMAND (
    echo Luculent requires Python 3.10, 3.11, 3.12, or 3.13.
    echo Install a compatible version from https://www.python.org/downloads/ and try again.
    goto launch_failed
)

echo Creating Luculent's virtual environment...
%PYTHON_COMMAND% -m venv .venv
if errorlevel 1 goto launch_failed

:environment_ready
echo Installing Luculent's requirements...
"%VENV_PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 goto launch_failed

echo Starting Luculent on an available local port...
"%VENV_PYTHON%" -m app.web --open-browser
if errorlevel 1 goto launch_failed
exit /b %errorlevel%

:launch_failed
echo.
echo Luculent could not start. Review the message above for details.
pause
exit /b 1

:try_python
if defined PYTHON_COMMAND exit /b
%* -c "import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] <= (3, 13) else 1)" >nul 2>&1
if not errorlevel 1 set "PYTHON_COMMAND=%*"
exit /b
