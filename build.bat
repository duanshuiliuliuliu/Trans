@echo off
rem ---------------------------------------------------------------------------
rem Build script: package Trans into a standalone Windows executable.
rem
rem Prerequisite: python -m pip install pyinstaller
rem Usage:        build.bat [onefile|onedir]
rem               double-click = onefile (default)
rem
rem   onefile  -> dist\Trans.exe            single portable file, copy it anywhere
rem               (self-extracts to %TEMP% on each start, so startup is ~1s slower)
rem   onedir   -> dist\Trans\Trans.exe      a folder; starts faster, but the whole
rem               folder must be copied, the .exe alone will not run
rem
rem Notes:
rem   - This file is ASCII only on purpose: cmd.exe reads .bat files using the
rem     console code page (GBK on Chinese Windows), so non-ASCII text would be
rem     mangled and can even break parsing.
rem   - The exe needs no Python installed on the target machine. The API key is
rem     NOT inside the exe: settings live in %APPDATA%\Trans\config.json, so a new
rem     machine asks you to fill it in once.
rem ---------------------------------------------------------------------------

setlocal
cd /d "%~dp0"

set "MODE=%~1"
if "%MODE%"=="" set "MODE=onefile"
if /I "%MODE%"=="onefile" goto :mode_ok
if /I "%MODE%"=="onedir" goto :mode_ok
echo ERROR: unknown build mode "%MODE%". Use "onefile" or "onedir".
goto :failed

:mode_ok
where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: python not found in PATH.
    goto :failed
)

if not exist "Trans.pyw" (
    echo ERROR: Trans.pyw not found next to this script.
    goto :failed
)
if not exist "assets\icon.ico" (
    echo ERROR: assets\icon.ico not found next to this script.
    goto :failed
)

python -c "import importlib.util,sys;sys.exit(0 if importlib.util.find_spec('PyInstaller') else 3)"
if errorlevel 1 (
    echo ERROR: PyInstaller is not installed. Run this first:
    echo        python -m pip install pyinstaller
    goto :failed
)

rem A running Trans.exe holds dist locked, which makes PyInstaller fail half way
rem and leaves an incomplete dist folder behind.
tasklist /FI "IMAGENAME eq Trans.exe" 2>nul | find /I "Trans.exe" >nul
if not errorlevel 1 (
    echo ERROR: Trans.exe is running. Quit it first ^(tray icon -^> Quit^), then build again.
    goto :failed
)

if /I "%MODE%"=="onefile" (
    set "MODE_ARG=--onefile"
    set "OUTPUT=%~dp0dist\Trans.exe"
) else (
    set "MODE_ARG=--onedir"
    set "OUTPUT=%~dp0dist\Trans\Trans.exe"
)

rem Drop the artifact of the other mode so dist\ holds exactly one build result.
if /I "%MODE%"=="onefile" (
    if exist "dist\Trans" rmdir /s /q "dist\Trans" 2>nul
) else (
    if exist "dist\Trans.exe" del /q "dist\Trans.exe" 2>nul
)

echo Building mode: %MODE%
python -m PyInstaller --noconfirm --clean --windowed %MODE_ARG% --name Trans ^
    --icon "assets\icon.ico" --add-data "assets;assets" "Trans.pyw"
if errorlevel 1 (
    echo ERROR: PyInstaller failed.
    goto :failed
)

echo.
echo Build finished: %OUTPUT%
echo Settings are stored in %%APPDATA%%\Trans\config.json (API key is not inside the exe)
goto :done

:failed
echo.
echo Build aborted.
:done
pause
endlocal
