@echo off
chcp 65001 >nul
echo ========================================
echo   Electron Builder (使用本地缓存)
echo ========================================
echo.

set "SOURCE_FILE=D:\workspace\Uverse\backend\support\win\winCodeSign-2.6.0.7z"
set "CACHE_DIR=%LOCALAPPDATA%\electron-builder\Cache\winCodeSign"
set "FRONTEND_DIR=D:\workspace\Uverse\frontend"
set "SEVEN_ZIP=%FRONTEND_DIR%\node_modules\7zip-bin\win\x64\7za.exe"

:: 检查源文件
if not exist "%SOURCE_FILE%" (
    echo [错误] 找不到 winCodeSign: %SOURCE_FILE%
    pause
    exit /b 1
)

echo [信息] 清理旧缓存...
if exist "%CACHE_DIR%" (
    rmdir /s /q "%CACHE_DIR%" 2>nul
)
mkdir "%CACHE_DIR%" 2>nul

echo [信息] 解压 winCodeSign...
"%SEVEN_ZIP%" x -y -o"%CACHE_DIR%\winCodeSign-2.6.0" "%SOURCE_FILE%" >nul 2>&1

if errorlevel 1 (
    echo [警告] 解压可能有问题，但继续尝试...
)

echo [信息] 验证解压结果...
if exist "%CACHE_DIR%\winCodeSign-2.6.0\windows-10" (
    echo [成功] winCodeSign 已准备好
) else (
    echo [错误] 解压失败
    pause
    exit /b 1
)

echo.
echo [信息] 运行 electron-builder...
echo.
cd /d "%FRONTEND_DIR%"

:: 设置环境变量并使用本地缓存
set ELECTRON_BUILDER_CACHE=%CACHE_DIR%
npm run electron:build:win

echo.
pause
