@echo off
rem ============================================================
rem start.bat - double-click this to run the Showdown tracker.
rem   1. finds Python (and says what to do if it isn't installed)
rem   2. installs what the tracker needs, the first time only
rem   3. checks your tracker key (tracker_key.txt)
rem   4. starts the tracker
rem "start.bat --check" only does steps 1 to 3 (for testing).
rem ============================================================
setlocal
chcp 65001 >nul
rem Work in the folder this file is in, wherever it was started from
cd /d "%~dp0"
title Showdown tracker

echo.
echo  SHOWDOWN TRACKER
echo  ================
echo.

rem ---------- 1. Python ----------
rem "py" is the Python launcher (installed with Python). "python" works if it's on the PATH.
set "PY="
py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "import sys" >nul 2>&1 && set "PY=python"
if not defined PY goto :no_python
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto :old_python
for /f "delims=" %%v in ('%PY% -c "import sys; print(sys.version.split()[0])"') do echo  [ok] Python %%v

rem ---------- 2. Packages (playwright = talks to the browser, pillow = draws the overlay) ----------
%PY% -c "import playwright, PIL" >nul 2>&1
if errorlevel 1 (
    echo  [..] First time: installing what the tracker needs. This takes a minute...
    %PY% -m pip install --disable-pip-version-check -r requirements.txt
    %PY% -c "import playwright, PIL" >nul 2>&1
    if errorlevel 1 goto :install_failed
)
echo  [ok] Packages installed

rem ---------- 3. Tracker key ----------
if exist "tracker_key.txt" (
    echo  [ok] tracker_key.txt found: your matches will be saved to the website
) else (
    if exist "tracker_key.txt.txt" (
        echo  [!!] Your key is saved as "tracker_key.txt.txt". Rename it to "tracker_key.txt".
        echo       ^(Windows hides the ".txt" at the end. See SETUP.md, step 3.^)
    ) else (
        echo  [!!] No tracker_key.txt: the tracker works, but your matches won't be saved
        echo       to the website. To add it: website ^> Tools ^> Create key. See SETUP.md, step 3.
    )
)

if /i "%~1"=="--check" goto :end

rem ---------- 4. Start ----------
echo.
echo  Starting... A browser window opens on Showdown: log in there, and play or watch in THAT window.
echo  To stop: click the X on the overlay, or close this window.
echo.
%PY% tracker.py
echo.
echo  The tracker stopped.
pause
goto :end

:no_python
echo  [!!] Python isn't installed (or Windows can't find it).
echo.
echo       1. Install Python from https://www.python.org/downloads/
echo       2. IMPORTANT: on the first screen, tick "Add python.exe to PATH"
echo       3. Then double-click start.bat again.
echo.
echo  Opening the download page...
start "" "https://www.python.org/downloads/"
pause
goto :end

:old_python
echo  [!!] Your Python is too old. Install the newest one from https://www.python.org/downloads/
pause
goto :end

:install_failed
echo.
echo  [!!] Installing the packages didn't work. Check your internet connection and try again.
echo       If it keeps failing, send a screenshot of this window to whoever gave you the tracker.
pause
goto :end

:end
endlocal
