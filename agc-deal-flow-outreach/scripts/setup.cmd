@echo off
rem ---------------------------------------------------------------------------
rem AGC deal flow outreach - one-time setup for this computer.
rem
rem Behaves like an installer: it brings everything the tool needs and asks the
rem user for nothing. It downloads a private copy of Python from python.org into
rem the user's own profile, then the two Python packages the tool uses.
rem
rem   - no administrator rights needed
rem   - nothing is added to PATH, no file types are re-associated, and any Python
rem     already on the machine is left exactly as it is
rem   - removing the tool again is deleting one folder:
rem         %LOCALAPPDATA%\AGC-DealFlow
rem
rem It is a batch file on purpose. Windows blocks PowerShell script files by
rem default on a fresh machine; batch files are not affected.
rem
rem The only thing it cannot bring is classic Microsoft Outlook, which has to be
rem installed and set up with the user's mailbox.
rem
rem Exit codes:  0 ready    1 ready, but Outlook could not be reached    2 failed
rem ---------------------------------------------------------------------------
setlocal EnableExtensions

set "PY_VERSION=3.12.10"
set "PY_ZIP=python-%PY_VERSION%-embed-amd64.zip"
set "PY_URL=https://www.python.org/ftp/python/%PY_VERSION%/%PY_ZIP%"
set "PY_SHA256=4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"
set "PIP_URL=https://bootstrap.pypa.io/get-pip.py"

set "AGC_HOME=%LOCALAPPDATA%\AGC-DealFlow"
set "RUNTIME=%AGC_HOME%\runtime"
set "PY=%RUNTIME%\python.exe"
set "HERE=%~dp0"
set "LOG=%AGC_HOME%\setup-log.txt"

echo.
echo  =============================================================
echo   AG CAPITAL  -  Deal flow outreach  -  setting up this computer
echo  =============================================================
echo   This happens once and takes two to three minutes.
echo   Nothing is needed from you.
echo.

if not exist "%AGC_HOME%" mkdir "%AGC_HOME%"
if not exist "%AGC_HOME%" (
    echo   PROBLEM  Could not create %AGC_HOME%
    echo            Send this line to IT.
    exit /b 2
)
echo Setup started %DATE% %TIME% > "%LOG%"

rem ---- 1. a private Python ---------------------------------------------------
if exist "%PY%" (
    "%PY%" -c "import sys;sys.exit(0 if sys.version_info[:2]==(3,12) else 1)" >nul 2>&1
    if not errorlevel 1 (
        echo   [1/4] Python is already in place
        goto have_python
    )
    echo   [1/4] Replacing an incomplete earlier setup
    rmdir /s /q "%RUNTIME%" >nul 2>&1
)

echo   [1/4] Downloading Python %PY_VERSION% from python.org  ^(11 MB^)
if exist "%AGC_HOME%\%PY_ZIP%" del "%AGC_HOME%\%PY_ZIP%" >nul 2>&1
call :download "%PY_URL%" "%AGC_HOME%\%PY_ZIP%"
if not exist "%AGC_HOME%\%PY_ZIP%" goto fail_network

rem Check the download is the file python.org published, not something else.
set "GOT="
for /f "skip=1 tokens=* delims=" %%H in ('certutil -hashfile "%AGC_HOME%\%PY_ZIP%" SHA256 2^>nul') do (
    if not defined GOT set "GOT=%%H"
)
set "GOT=%GOT: =%"
if /i not "%GOT%"=="%PY_SHA256%" (
    echo   PROBLEM  The downloaded file is not the one expected.
    echo            This usually means the company network changed it on the way.
    echo            Send this to IT:  checksum mismatch for %PY_ZIP%
    echo checksum got %GOT% expected %PY_SHA256% >> "%LOG%"
    del "%AGC_HOME%\%PY_ZIP%" >nul 2>&1
    exit /b 2
)

mkdir "%RUNTIME%" >nul 2>&1
rem Windows' own tar, by full path: another tar earlier on PATH (Git ships one)
rem reads "C:" as the name of a remote computer.
set "WINTAR=%SystemRoot%\System32\tar.exe"
if exist "%WINTAR%" "%WINTAR%" -xf "%AGC_HOME%\%PY_ZIP%" -C "%RUNTIME%" >> "%LOG%" 2>&1
if not exist "%PY%" (
    powershell -NoProfile -Command "Expand-Archive -LiteralPath '%AGC_HOME%\%PY_ZIP%' -DestinationPath '%RUNTIME%' -Force" >> "%LOG%" 2>&1
)
if not exist "%PY%" (
    echo   PROBLEM  Python could not be unpacked. Details are in:
    echo            %LOG%
    exit /b 2
)
del "%AGC_HOME%\%PY_ZIP%" >nul 2>&1

rem The embedded Python ignores installed packages until told where they live.
> "%RUNTIME%\python312._pth" echo python312.zip
>> "%RUNTIME%\python312._pth" echo .
>> "%RUNTIME%\python312._pth" echo Lib\site-packages
>> "%RUNTIME%\python312._pth" echo import site

:have_python

rem ---- 2. the package installer ---------------------------------------------
"%PY%" -m pip --version >nul 2>&1
if not errorlevel 1 (
    echo   [2/4] Package installer is already in place
    goto have_pip
)
echo   [2/4] Adding the package installer
call :download "%PIP_URL%" "%AGC_HOME%\get-pip.py"
if not exist "%AGC_HOME%\get-pip.py" goto fail_network
"%PY%" "%AGC_HOME%\get-pip.py" --no-warn-script-location --disable-pip-version-check >> "%LOG%" 2>&1
del "%AGC_HOME%\get-pip.py" >nul 2>&1
"%PY%" -m pip --version >nul 2>&1
if errorlevel 1 goto fail_network
:have_pip

rem ---- 3. the packages -------------------------------------------------------
echo   [3/4] Installing what the tool needs to read Excel and drive Outlook
"%PY%" -m pip install --no-warn-script-location --disable-pip-version-check --quiet -r "%HERE%requirements.txt" >> "%LOG%" 2>&1
if errorlevel 1 goto fail_network

rem ---- 4. does Outlook answer? ----------------------------------------------
echo   [4/4] Checking Microsoft Outlook
"%PY%" "%HERE%preflight.py" --quiet
set "RESULT=%ERRORLEVEL%"
if "%RESULT%"=="2" exit /b 2

copy /y "%HERE%requirements.txt" "%AGC_HOME%\installed-requirements.txt" >nul 2>&1
echo.
if "%RESULT%"=="0" (
    echo   Ready. Everything is in place.
) else (
    echo   Ready, with one limitation: classic Outlook could not be reached.
    echo   A round can be prepared, but nothing can be sent until Outlook is
    echo   installed and set up with your mailbox.
)
echo.
exit /b %RESULT%

rem ---------------------------------------------------------------------------
:download
rem %1 = address, %2 = file. curl ships with Windows 10 and 11.
if exist "%SystemRoot%\System32\curl.exe" "%SystemRoot%\System32\curl.exe" --location --fail --silent --show-error --retry 2 --output %2 %1 >> "%LOG%" 2>&1
if exist %2 exit /b 0
powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol='Tls12'; Invoke-WebRequest -UseBasicParsing -Uri '%~1' -OutFile '%~2'" >> "%LOG%" 2>&1
exit /b 0

:fail_network
echo.
echo   PROBLEM  The setup could not download what it needs.
echo.
echo   This is almost always the company network blocking the download.
echo   Send this to IT:
echo.
echo       Please allow this computer to reach python.org, bootstrap.pypa.io,
echo       pypi.org and files.pythonhosted.org. They are needed once, to set
echo       up an internal Outlook automation tool. Details of what failed are in
echo       %LOG%
echo.
exit /b 2
