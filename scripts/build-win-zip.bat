@echo off
chcp 65001 >nul
echo ========================================
echo   Electron Builder ZIP (Local Cache)
echo ========================================
echo.

:: 获取项目根目录（脚本所在目录的父目录）
set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..
set SOURCE_FILE=%PROJECT_ROOT%\backend\support\win\winCodeSign-2.6.0.7z
set CACHE_DIR=%LOCALAPPDATA%\electron-builder\Cache
set WIN_SIGN_DIR=%CACHE_DIR%\winCodeSign\winCodeSign-2.6.0
set FRONTEND_DIR=%PROJECT_ROOT%\frontend
set SEVEN_ZIP=%FRONTEND_DIR%\node_modules\7zip-bin\win\x64\7za.exe

if not exist "%SOURCE_FILE%" (
    echo [ERROR] Source file not found: %SOURCE_FILE%
    pause
    exit /b 1
)

echo [*] Preparing cache...

:: 清理旧的 winCodeSign 缓存
if exist "%CACHE_DIR%\winCodeSign" (
    rmdir /s /q "%CACHE_DIR%\winCodeSign" 2>nul
)
mkdir "%CACHE_DIR%\winCodeSign" 2>nul

echo [*] Extracting winCodeSign...
mkdir "%WIN_SIGN_DIR%" 2>nul
"%SEVEN_ZIP%" x -y -o"%WIN_SIGN_DIR%" "%SOURCE_FILE%" >nul 2>&1

:: 验证解压结果（检查 windows-10 目录）
if exist "%WIN_SIGN_DIR%\windows-10" (
    echo [OK] winCodeSign cache ready
) else (
    echo [ERROR] winCodeSign extraction failed
    pause
    exit /b 1
)

echo.
echo [*] Building ZIP package with electron-builder...
echo.

cd /d "%FRONTEND_DIR%"

:: 设置缓存环境变量并构建
set ELECTRON_BUILDER_CACHE=%CACHE_DIR%
npm run build && npm run build:electron && electron-builder --win

echo.
if %errorlevel% equ 0 (
    echo ========================================
    echo   Build Success!
    echo   Output: release\Uverse-*-win.zip
    echo ========================================
) else (
    echo ========================================
    echo   Build failed, code: %errorlevel%
    echo ========================================
)

exit /b %errorlevel%
