@echo off
rem ---------------------------------------------------------------------------
rem AGC deal flow outreach - the one command everything is run through.
rem
rem     outreach.cmd start
rem     outreach.cmd wait
rem     outreach.cmd submit <job>
rem     ...                                (outreach.cmd help lists them all)
rem
rem On a computer that has never run the tool it sets everything up first, by
rem itself, and then carries on with what was asked. Later it starts instantly.
rem
rem It runs the tool from a copy it keeps under %LOCALAPPDATA%\AGC-DealFlow\app.
rem Claude stores a skill many folders deep and in a place that changes between
rem sessions, while the app keeps running after the session that started it.
rem The copy is refreshed on every start; an app still running an older copy is
rem restarted by the start command itself.
rem ---------------------------------------------------------------------------
setlocal EnableExtensions
set "AGC_HOME=%LOCALAPPDATA%\AGC-DealFlow"
set "PY=%AGC_HOME%\runtime\python.exe"
set "APP=%AGC_HOME%\app"
set "HERE=%~dp0"

if /i "%~1"=="setup" goto setup
if not exist "%PY%" goto setup
fc /b "%HERE%requirements.txt" "%AGC_HOME%\installed-requirements.txt" >nul 2>&1
if errorlevel 1 goto setup
goto run

:setup
call "%HERE%setup.cmd"
if errorlevel 2 exit /b 2
if /i "%~1"=="setup" exit /b %ERRORLEVEL%

:run
if /i not "%~1"=="start" goto go
"%SystemRoot%\System32\robocopy.exe" "%HERE%.." "%APP%" /MIR /R:1 /W:1 /NJH /NJS /NFL /NDL /NP /XD __pycache__ >nul 2>&1
if errorlevel 8 (
    echo   PROBLEM  The tool could not be prepared in %APP%
    echo            Close any window that has files open there and try again.
    exit /b 2
)
:go
if not exist "%APP%\scripts\outreach.py" (
    echo   PROBLEM  The tool is not prepared yet. Run: outreach.cmd start
    exit /b 2
)
"%PY%" "%APP%\scripts\outreach.py" %*
exit /b %ERRORLEVEL%
