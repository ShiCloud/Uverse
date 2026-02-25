@echo off
chcp 65001 >nul
title Electron Builder Windows 修复工具
echo ========================================
echo   Electron Builder Windows 修复工具
echo ========================================
echo.

:: 检查是否以管理员身份运行
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [错误] 此脚本需要以管理员身份运行！
    echo.
    echo 正在尝试以管理员身份重新启动...
    timeout /t 2 >nul
    
    :: 以管理员身份重新运行
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo [信息] 已获取管理员权限
echo.

:: 设置路径
set "CACHE_PATH=%LOCALAPPDATA%\electron-builder\Cache"
set "SCRIPT_DIR=%~dp0"
set "FRONTEND_PATH=%SCRIPT_DIR%..\frontend"

:: 步骤1: 清除缓存
echo [信息] 检查 electron-builder 缓存...
if exist "%CACHE_PATH%" (
    echo [信息] 正在清除缓存目录...
    rmdir /s /q "%CACHE_PATH%" 2>nul
    if exist "%CACHE_PATH%" (
        echo [警告] 普通删除失败，尝试强制删除...
        :: 创建空目录用于 robocopy 镜像删除
        mkdir "%TEMP%\empty_dir" 2>nul
        robocopy "%TEMP%\empty_dir" "%CACHE_PATH%" /MIR /NFL /NDL /NJH /NJS >nul
        rmdir /s /q "%CACHE_PATH%" 2>nul
    )
    echo [成功] 缓存已清除
) else (
    echo [信息] 缓存目录不存在，无需清理
)
echo.

:: 步骤2: 启用开发者模式
echo [信息] 检查并启用开发者模式...
reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock" /v AllowDevelopmentWithoutDevLicense 2>nul | find "0x1" >nul
if %errorLevel% equ 0 (
    echo [成功] 开发者模式已启用
) else (
    echo [信息] 正在启用开发者模式...
    reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock" /v AllowDevelopmentWithoutDevLicense /t REG_DWORD /d 1 /f >nul
    echo [成功] 开发者模式已启用
)
echo.

:: 询问是否构建
echo ========================================
echo 修复完成！
echo ========================================
echo.
echo 请选择操作：
echo [1] 立即运行构建 (npm run electron:build:win)
echo [2] 仅修复，不构建
echo [3] 退出
echo.
set /p choice="输入选项 (1/2/3): "

if "%choice%"=="1" goto :build
if "%choice%"=="2" goto :done
if "%choice%"=="3" goto :exit

:build
echo.
echo [信息] 正在构建项目...
cd /d "%FRONTEND_PATH%"
echo [信息] 当前目录: %CD%
echo.
echo ----------------------------------------
npm run electron:build:win
echo ----------------------------------------
echo.
if %errorLevel% equ 0 (
    echo [成功] 构建完成！
) else (
    echo [错误] 构建失败，错误代码: %errorLevel%
)
goto :done

:done
echo.
echo ========================================
echo   修复完成！
echo ========================================
echo.
echo 提示：如果仍然遇到符号链接错误，请尝试：
echo 1. 重启计算机后再试
echo 2. 手动删除 %CACHE_PATH%
echo 3. 将项目移动到非系统盘（如 D: 盘）
echo.
pause

:exit
exit /b
