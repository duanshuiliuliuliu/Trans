@echo off
rem ---------------------------------------------------------------------------
rem Build script: package Trans into a standalone Windows executable.
rem
rem Prerequisite: python -m pip install pyinstaller
rem Usage:        double-click this file, or run "build.bat" from a console
rem
rem Notes:
rem   - This file is ASCII only on purpose: cmd.exe reads .bat files using the
rem     console code page (GBK on Chinese Windows), so non-ASCII text would be
rem     mangled and can even break parsing.
rem   - --onedir is used instead of --onefile: it starts faster and uses less
rem     memory, which matters for a tray app that stays resident. Swap in
rem     --onefile if you need a single self-contained .exe (slower startup).
rem ---------------------------------------------------------------------------

setlocal
cd /d "%~dp0"

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

rem A running Trans.exe holds dist\Trans locked, which makes PyInstaller fail
rem half way and leaves an incomplete dist folder behind.
tasklist /FI "IMAGENAME eq Trans.exe" 2>nul | find /I "Trans.exe" >nul
if not errorlevel 1 (
    echo ERROR: Trans.exe is running. Quit it first ^(tray icon -^> Quit^), then build again.
    goto :failed
)

python -m PyInstaller --noconfirm --clean --windowed --onedir --name Trans ^
    --icon "assets\icon.ico" --add-data "assets;assets" "Trans.pyw"
if errorlevel 1 (
    echo ERROR: PyInstaller failed.
    goto :failed
)

echo.
echo Build finished: %~dp0dist\Trans\Trans.exe
echo Run Trans.exe directly; settings are stored in %%APPDATA%%\Trans\config.json
goto :done

:failed
echo.
echo Build aborted.
:done
pause
endlocal
