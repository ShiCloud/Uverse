#Requires -RunAsAdministrator
<#
.SYNOPSIS
    修复 electron-builder 在 Windows 上的符号链接权限问题

.DESCRIPTION
    此脚本用于解决 electron-builder 构建时出现的 "Cannot create symbolic link" 错误
    功能：
    1. 清除损坏的 electron-builder 缓存
    2. 启用 Windows 开发者模式（如未启用）
    3. 重新运行构建命令

.USAGE
    以管理员身份运行 PowerShell，然后执行：
    .\scripts\fix-electron-build-win.ps1
    
    或直接运行（脚本会自动请求管理员权限）：
    powershell -ExecutionPolicy Bypass -File .\scripts\fix-electron-build-win.ps1
#>

param(
    [switch]$SkipBuild,
    [switch]$OnlyCleanCache
)

$ErrorActionPreference = "Stop"
$cachePath = "$env:LOCALAPPDATA\electron-builder\Cache"
$frontendPath = "$PSScriptRoot\..\frontend"

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[SUCCESS] $Message" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

# 检查是否以管理员身份运行
function Test-Administrator {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# 启用开发者模式
function Enable-DeveloperMode {
    Write-Info "检查开发者模式状态..."
    
    try {
        $regPath = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock"
        $regName = "AllowDevelopmentWithoutDevLicense"
        
        if (!(Test-Path $regPath)) {
            Write-Info "创建注册表路径..."
            New-Item -Path $regPath -Force | Out-Null
        }
        
        $currentValue = Get-ItemProperty -Path $regPath -Name $regName -ErrorAction SilentlyContinue
        
        if ($currentValue.$regName -eq 1) {
            Write-Success "开发者模式已启用"
            return $true
        } else {
            Write-Info "正在启用开发者模式..."
            Set-ItemProperty -Path $regPath -Name $regName -Value 1
            Write-Success "开发者模式已启用，请重启计算机使设置生效"
            return $true
        }
    } catch {
        Write-Error "启用开发者模式失败: $_"
        return $false
    }
}

# 清除 electron-builder 缓存
function Clear-ElectronBuilderCache {
    Write-Info "检查 electron-builder 缓存..."
    
    if (Test-Path $cachePath) {
        Write-Info "正在清除缓存目录: $cachePath"
        try {
            Remove-Item -Path $cachePath -Recurse -Force -ErrorAction Stop
            Write-Success "缓存已清除"
        } catch {
            Write-Warning "清除缓存时出错: $_"
            Write-Info "尝试强制删除..."
            
            # 使用 robocopy 删除顽固目录
            $emptyDir = "$env:TEMP\empty_dir_for_delete"
            if (!(Test-Path $emptyDir)) {
                New-Item -ItemType Directory -Path $emptyDir | Out-Null
            }
            robocopy $emptyDir $cachePath /MIR /NFL /NDL /NJH /NJS
            Remove-Item -Path $cachePath -Force -Recurse -ErrorAction SilentlyContinue
            Write-Success "缓存已强制清除"
        }
    } else {
        Write-Info "缓存目录不存在，无需清理"
    }
}

# 主函数
function Main {
    Write-Host "========================================" -ForegroundColor Blue
    Write-Host "  Electron Builder Windows 修复工具" -ForegroundColor Blue
    Write-Host "========================================" -ForegroundColor Blue
    Write-Host ""
    
    # 检查管理员权限
    if (!(Test-Administrator)) {
        Write-Error "此脚本需要以管理员身份运行！"
        Write-Info "请右键点击 PowerShell，选择'以管理员身份运行'，然后重新执行此脚本"
        Write-Host ""
        Write-Host "按任意键退出..."
        $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
        exit 1
    }
    
    Write-Success "已获取管理员权限"
    Write-Host ""
    
    # 步骤1: 清除缓存
    Clear-ElectronBuilderCache
    Write-Host ""
    
    if ($OnlyCleanCache) {
        Write-Success "仅清理缓存模式，操作完成！"
        exit 0
    }
    
    # 步骤2: 启用开发者模式
    Enable-DeveloperMode
    Write-Host ""
    
    if ($SkipBuild) {
        Write-Success "跳过构建模式，修复完成！"
        Write-Info "现在可以直接运行: npm run electron:build:win"
        exit 0
    }
    
    # 步骤3: 运行构建
    Write-Info "准备构建项目..."
    
    if (!(Test-Path $frontendPath)) {
        Write-Error "找不到前端目录: $frontendPath"
        exit 1
    }
    
    Set-Location $frontendPath
    Write-Info "当前目录: $(Get-Location)"
    Write-Host ""
    
    Write-Info "正在执行: npm run electron:build:win"
    Write-Host "----------------------------------------" -ForegroundColor Gray
    
    try {
        npm run electron:build:win
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host ""
            Write-Success "构建成功完成！"
        } else {
            Write-Host ""
            Write-Error "构建失败，退出代码: $LASTEXITCODE"
            exit $LASTEXITCODE
        }
    } catch {
        Write-Host ""
        Write-Error "构建过程中发生错误: $_"
        exit 1
    }
    
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "  修复和构建全部完成！" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
}

# 执行主函数
Main
