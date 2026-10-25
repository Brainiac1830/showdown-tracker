@echo off
rem ============================================================
rem update.bat - double-click this to get the newest version of the tracker.
rem   1. downloads the newest version from GitHub (no git needed)
rem   2. copies the new files over the old ones
rem   3. installs anything new the tracker needs
rem Your own files are NOT in the download, so they're never touched:
rem   tracker_key.txt, games\ (your matches), browser-profile\ (your login),
rem   overlay_settings.json, tournament_mode.json, browser_path.txt
rem ============================================================
setlocal
chcp 65001 >nul
title Showdown tracker - update

rem A .bat file that replaces itself while running goes haywire, so the
rem real work runs from a copy in the temp folder.
if /i not "%~1"=="--from-temp" (
    copy /y "%~f0" "%TEMP%\showdown_tracker_update.bat" >nul
    call "%TEMP%\showdown_tracker_update.bat" --from-temp "%~dp0."
    exit /b
)
set "TARGET=%~f2"
set "REPO=Brainiac1830/showdown-tracker"
set "ZIP=%TEMP%\showdown-tracker-update.zip"
set "WORK=%TEMP%\showdown-tracker-update"

echo.
echo  SHOWDOWN TRACKER - UPDATE
echo  =========================
echo  Folder: %TARGET%
echo.

rem A git folder (the maintainer's copy) is updated with git, not with this
if exist "%TARGET%\.git" (
    echo  [!!] This folder is a git repository: update it with git instead
    echo       ^(VS Code: Source Control ^> Sync Changes, or "git pull"^).
    goto :done
)

rem ---------- 1. Download ----------
echo  [..] Downloading the newest version from GitHub...
if exist "%WORK%" rmdir /s /q "%WORK%"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference = 'SilentlyContinue';" ^
  "try { Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/%REPO%/archive/refs/heads/main.zip' -OutFile '%ZIP%';" ^
  "      Expand-Archive -Force -Path '%ZIP%' -DestinationPath '%WORK%'; exit 0 } catch { Write-Host $_; exit 1 }"
if errorlevel 1 (
    echo  [!!] The download didn't work. Check your internet connection and try again.
    goto :done
)
if not exist "%WORK%\showdown-tracker-main\tracker.py" (
    echo  [!!] The download looks wrong ^(no tracker.py in it^). Nothing was changed.
    goto :done
)

rem ---------- 2. Copy the new files over the old ones (nothing is deleted) ----------
robocopy "%WORK%\showdown-tracker-main" "%TARGET%" /E /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
    echo  [!!] Copying the new files failed. Close the tracker and try again.
    goto :done
)
echo  [ok] Tracker files updated

rem ---------- 3. New packages, if the update needs any ----------
set "PY="
py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "import sys" >nul 2>&1 && set "PY=python"
if defined PY (
    %PY% -m pip install --quiet --disable-pip-version-check -r "%TARGET%\requirements.txt"
    echo  [ok] Packages up to date
) else (
    echo  [!!] Python not found: start.bat will tell you what to do.
)

rem ---------- What's new (the newest change on GitHub) ----------
for /f "usebackq delims=" %%m in (`powershell -NoProfile -Command "try { (Invoke-RestMethod 'https://api.github.com/repos/%REPO%/commits/main').commit.message.Split([char]10)[0] } catch { '' }"`) do echo  Newest change: %%m

echo.
echo  Done. Your key, matches and login were kept. Start the tracker with start.bat.

:done
if exist "%WORK%" rmdir /s /q "%WORK%"
if exist "%ZIP%" del /q "%ZIP%"
echo.
pause
endlocal
