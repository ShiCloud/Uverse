@echo off
chcp 65001 >nul
echo ========================================
echo   Build Uverse Full Package (with data)
echo   Includes: postgres, store, models, out
echo ========================================
echo.

set PROJECT_ROOT=%~dp0..
set BACKEND_DIR=%PROJECT_ROOT%\backend
set FRONTEND_DIR=%PROJECT_ROOT%\frontend
set CACHE_DIR=%LOCALAPPDATA%\electron-builder\Cache
set WIN_SIGN_DIR=%CACHE_DIR%\winCodeSign\winCodeSign-2.6.0
set SOURCE_FILE=%PROJECT_ROOT%\backend\support\win\winCodeSign-2.6.0.7z

:: ========================================
:: 步骤1: 构建 Backend
:: ========================================
echo [*] Step 1: Building Backend...
echo.

cd /d "%BACKEND_DIR%"

:: 检查虚拟环境
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Backend virtual environment not found!
    echo Please run: cd backend && python -m venv .venv
    pause
    exit /b 1
)

:: 检查 PyInstaller
if not exist ".venv\Scripts\pyinstaller.exe" (
    echo [INFO] Installing PyInstaller...
    .venv\Scripts\pip install pyinstaller
)

:: 清理旧构建
if exist "dist" (
    rmdir /s /q "dist" 2>nul
)
if exist "build" (
    rmdir /s /q "build" 2>nul
)

:: 构建 Backend
echo [*] Running PyInstaller...
.venv\Scripts\pyinstaller combined.spec --clean

if errorlevel 1 (
    echo [ERROR] Backend build failed!
    pause
    exit /b 1
)

:: 验证构建结果
if not exist "dist\backend\uverse-backend.exe" (
    echo [ERROR] Backend executable not found: dist\backend\uverse-backend.exe
    pause
    exit /b 1
)

echo [OK] Backend built successfully
echo.

:: ========================================
:: 步骤2: 检查数据目录
:: ========================================
echo [*] Step 2: Checking data directories...

set MISSING_DIRS=0

if not exist "%BACKEND_DIR%\postgres" (
    echo [WARN] postgres directory not found: %BACKEND_DIR%\postgres
    set MISSING_DIRS=1
) else (
    echo [OK] Found postgres directory
)

if not exist "%BACKEND_DIR%\store" (
    echo [WARN] store directory not found: %BACKEND_DIR%\store
    set MISSING_DIRS=1
) else (
    echo [OK] Found store directory
)

if not exist "%BACKEND_DIR%\models" (
    echo [WARN] models directory not found: %BACKEND_DIR%\models
    set MISSING_DIRS=1
) else (
    echo [OK] Found models directory
)

if not exist "%BACKEND_DIR%\out" (
    echo [WARN] out directory not found: %BACKEND_DIR%\out
    mkdir "%BACKEND_DIR%\out" 2>nul
    echo [INFO] Created empty out directory
) else (
    echo [OK] Found out directory
)

if %MISSING_DIRS%==1 (
    echo.
    echo [WARN] Some data directories are missing!
    echo The package will be built but may not work correctly.
    choice /C YN /M "Continue anyway"
    if errorlevel 2 exit /b 1
)

echo.

:: ========================================
:: 步骤3: 准备 winCodeSign 缓存
:: ========================================
echo [*] Step 3: Preparing winCodeSign cache...

if not exist "%SOURCE_FILE%" (
    echo [ERROR] winCodeSign source not found: %SOURCE_FILE%
    pause
    exit /b 1
)

:: 清理旧缓存
if exist "%CACHE_DIR%\winCodeSign" (
    rmdir /s /q "%CACHE_DIR%\winCodeSign" 2>nul
)
mkdir "%CACHE_DIR%\winCodeSign" 2>nul

:: 解压 winCodeSign
set SEVEN_ZIP=%FRONTEND_DIR%\node_modules\7zip-bin\win\x64\7za.exe
mkdir "%WIN_SIGN_DIR%" 2>nul
"%SEVEN_ZIP%" x -y -o"%WIN_SIGN_DIR%" "%SOURCE_FILE%" >nul 2>&1

if exist "%WIN_SIGN_DIR%\windows-10" (
    echo [OK] winCodeSign cache ready
) else (
    echo [ERROR] winCodeSign extraction failed
    pause
    exit /b 1
)

echo.

:: ========================================
:: 步骤4: 构建 Frontend (使用完整配置)
:: ========================================
echo [*] Step 4: Building Frontend with full config...
echo.

cd /d "%FRONTEND_DIR%"

set ELECTRON_BUILDER_CACHE=%CACHE_DIR%
npm run build && npm run build:electron && electron-builder --win --config electron-builder-full.yml

set BUILD_RESULT=%errorlevel%

echo.

:: ========================================
:: 完成
:: ========================================
if %BUILD_RESULT% neq 0 (
    echo [ERROR] Frontend build failed!
    pause
    exit /b 1
)

echo ========================================
echo   Build Complete!
echo ========================================
echo.
echo Output files:
echo   - Backend: %BACKEND_DIR%\dist\backend\
echo   - Frontend: %FRONTEND_DIR%\release\Uverse-*-win.zip
echo.
echo This package includes:
echo   - PostgreSQL binaries (postgres/)
echo   - RustFS storage (store/)
echo   - AI Models (models/)
echo   - Output files (out/)
echo.

exit /b 0
