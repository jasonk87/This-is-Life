@echo off
setlocal EnableDelayedExpansion

:: ---------------------------------------------------------
:: AUTO-SWITCH TO LATEST BRANCH (FORCE OVERWRITE MODE)
:: ---------------------------------------------------------

echo Checking for Git repository...
git rev-parse --is-inside-work-tree >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Not a git repository.
    pause
    exit /b
)

echo.
echo Fetching latest info from remote...
git fetch --all --prune 

:: --- FIND THE NEWEST BRANCH ---
set "LATEST_REF_RAW="
for /f "tokens=*" %%i in ('git for-each-ref --sort=-committerdate refs/remotes/origin/ --format="%%(refname:short)" --count=1') do (
    set "LATEST_REF_RAW=%%i"
)

:: Use a temporary variable and string replacement to strip the prefix
:: and automatically trim leading/trailing whitespace/newlines.
set "LATEST_REF=!LATEST_REF_RAW:origin/=!"

:: We don't need the temporary raw variable anymore
set "LATEST_REF_RAW="

:: The branch name is now the clean variable, trimming any potential
:: whitespace/newlines from the end of the value.
set "LATEST_BRANCH=!LATEST_REF: =!"

echo.
echo ========================================================
echo  MOST RECENT BRANCH FOUND: !LATEST_BRANCH!
echo ========================================================
echo.

:: --- CONFIRMATION STEP ---
echo  [WARNING] You are about to FORCE update to this branch.
echo  Any local changes (like your API keys in config.py or config.json)
echo  WILL BE LOST and overwritten by the remote version.
echo.
set /p "CHOICE=Are you sure you want to overwrite local files? (Y/N): "

if /i not "!CHOICE!"=="Y" (
    echo.
    echo  [CANCELLED] No changes were made.
    pause
    exit /b
)

:: --- THE FORCE OVERWRITE LOGIC ---
echo.
echo  Forcing checkout of !LATEST_BRANCH!...
git checkout -f !LATEST_BRANCH!

if !errorlevel! equ 0 (
    echo  Resetting local files to match remote exactly...
    git reset --hard origin/!LATEST_BRANCH!
    
    echo.
    echo  [SUCCESS] Updated to !LATEST_BRANCH! - Local changes overwritten.
) else (
    echo.
    echo  [ERROR] Could not checkout the branch.
)

echo.
pause