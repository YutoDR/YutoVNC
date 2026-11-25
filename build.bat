@echo off
setlocal enabledelayedexpansion
title YutoVNC - Build Pipeline and Installer Generator
cd /d "%~dp0"

echo ========================================================
echo   YutoVNC - Windows Build Pipeline and Installer
echo ========================================================
echo.

REM 1. Check Python
where python.exe >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python tidak ditemukan di PATH sistem!
    echo Silakan install Python 3.8+ dari https://www.python.org/
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python -c "import sys; print(sys.version.split()[0])"') do set PYTHON_VER=%%i
echo [*] Python terdeteksi: %PYTHON_VER%

REM 2. Check and Install PyInstaller
python -m pip show pyinstaller >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [*] PyInstaller belum terinstall. Menginstall PyInstaller sekarang...
    python -m pip install --upgrade pyinstaller
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Gagal menginstall PyInstaller via pip.
        pause
        exit /b 1
    )
)
echo [*] PyInstaller siap digunakan.

REM 3. Check for bundled TightVNC binary
if not exist "bin" mkdir bin
if not exist "bin\tvnviewer.exe" (
    if exist "C:\Program Files\TightVNC\tvnviewer.exe" (
        echo [*] Menyalin tvnviewer.exe dari Program Files ke bin...
        copy /y "C:\Program Files\TightVNC\tvnviewer.exe" "bin\tvnviewer.exe" >nul
    ) else if exist "C:\Program Files (x86)\TightVNC\tvnviewer.exe" (
        echo [*] Menyalin tvnviewer.exe dari Program Files x86 ke bin...
        copy /y "C:\Program Files (x86)\TightVNC\tvnviewer.exe" "bin\tvnviewer.exe" >nul
    )
)

if exist "bin\tvnviewer.exe" (
    echo [*] Binary TightVNC siap dibundel: bin\tvnviewer.exe
) else (
    echo [!] Catatan: tvnviewer.exe tidak ditemukan di bin.
)

REM 4. Clean old build and dist folders
echo [*] Membersihkan folder build lama...
if exist "build" rmdir /s /q "build"
if exist "dist\YutoVNC" rmdir /s /q "dist\YutoVNC"

REM 5. Run PyInstaller
echo [*] Menjalankan PyInstaller mode windowed...
python -m PyInstaller YutoVNC.spec --noconfirm --clean
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Proses kompilasi PyInstaller gagal!
    pause
    exit /b 1
)

if not exist "dist\YutoVNC\YutoVNC.exe" (
    echo [ERROR] File dist\YutoVNC\YutoVNC.exe tidak ditemukan setelah build!
    pause
    exit /b 1
)

REM Ensure assets and bin are also available in dist root
if exist "assets" (
    if not exist "dist\YutoVNC\assets" xcopy /e /i /y "assets" "dist\YutoVNC\assets" >nul
)
if exist "bin" (
    if not exist "dist\YutoVNC\bin" xcopy /e /i /y "bin" "dist\YutoVNC\bin" >nul
)

echo.
echo ========================================================
echo   [OK] Build Standalone Berhasil: dist\YutoVNC\YutoVNC.exe
echo ========================================================
echo.

REM 6. Check Inno Setup Compiler (ISCC.exe) - Support v5, v6, v7
set ISCC_PATH=
where iscc.exe >nul 2>&1
if %ERRORLEVEL% equ 0 (
    for /f "tokens=*" %%a in ('where iscc.exe') do (
        if not defined ISCC_PATH set ISCC_PATH="%%a"
    )
)

if not defined ISCC_PATH (
    if exist "C:\Program Files\Inno Setup 7\ISCC.exe" set ISCC_PATH="C:\Program Files\Inno Setup 7\ISCC.exe"
    if exist "C:\Program Files (x86)\Inno Setup 7\ISCC.exe" set ISCC_PATH="C:\Program Files (x86)\Inno Setup 7\ISCC.exe"
    if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set ISCC_PATH="C:\Program Files\Inno Setup 6\ISCC.exe"
    if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set ISCC_PATH="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if exist "C:\Program Files\Inno Setup 5\ISCC.exe" set ISCC_PATH="C:\Program Files\Inno Setup 5\ISCC.exe"
    if exist "C:\Program Files (x86)\Inno Setup 5\ISCC.exe" set ISCC_PATH="C:\Program Files (x86)\Inno Setup 5\ISCC.exe"
)

if defined ISCC_PATH (
    echo [*] Inno Setup terdeteksi di: !ISCC_PATH!
    echo [*] Mengompilasi installer Setup_YutoVNC.exe...
    if not exist "Output" mkdir Output
    !ISCC_PATH! "installer.iss"
    if !ERRORLEVEL! equ 0 (
        echo.
        echo ========================================================
        echo   [OK] INSTALLER BERHASIL DIBUAT: Output\Setup_YutoVNC.exe
        echo ========================================================
    ) else (
        echo [!] Kompilasi Inno Setup gagal. Cek file installer.iss.
    )
) else (
    echo [INFO] Inno Setup tidak ditemukan di sistem.
)

echo.
echo Selesai. Tekan tombol apa saja untuk menutup.
pause >nul
