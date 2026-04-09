@echo off
cd /d "%~dp0"

echo ============================================================
echo   Photo Organizer - Full Build Script
echo   Builds EXE + Windows Installer
echo ============================================================
echo.

echo [1/4] Installing Python dependencies...
python -m pip install pillow pyinstaller --quiet
if %errorlevel% neq 0 (
    echo ERROR: pip failed. Make sure Python is installed.
    pause & exit /b 1
)

echo [2/4] Building EXE (30-60 seconds)...
python -m PyInstaller --onefile --windowed --name "Photo Organizer" photo_organizer.py
if %errorlevel% neq 0 (
    echo ERROR: PyInstaller failed.
    pause & exit /b 1
)

echo [3/4] Checking for Inno Setup...
set INNO="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist %INNO% (
    echo.
    echo ============================================================
    echo   Inno Setup not found.
    echo   To build the installer:
    echo   1. Download Inno Setup from https://jrsoftware.org/isinfo.php
    echo   2. Install it
    echo   3. Run this build.bat again
    echo ============================================================
    echo.
    echo   Your standalone EXE is still ready at:
    echo   dist\Photo Organizer.exe
    echo.
    pause & exit /b 0
)

echo [4/4] Building installer...
%INNO% installer.iss
if %errorlevel% neq 0 (
    echo ERROR: Inno Setup build failed.
    pause & exit /b 1
)

echo.
echo ============================================================
echo   BUILD COMPLETE
echo ============================================================
echo.
echo   Standalone EXE:  dist\Photo Organizer.exe
echo   Installer:       installer_output\PhotoOrganizer_Setup_v1.0.0.exe
echo.
echo   The installer is what you ship to customers.
echo   They double-click it and it handles everything.
echo ============================================================
echo.
pause
