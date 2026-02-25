# Electron Builder 本地缓存构建脚本
$ErrorActionPreference = "Stop"

$sourceFile = "D:\workspace\Uverse\backend\support\win\winCodeSign-2.6.0.7z"
$cacheDir = "$env:LOCALAPPDATA\electron-builder\Cache\winCodeSign"
$frontendDir = "D:\workspace\Uverse\frontend"
$sevenZip = "$frontendDir\node_modules\7zip-bin\win\x64\7za.exe"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Electron Builder (本地缓存模式)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检查源文件
if (!(Test-Path $sourceFile)) {
    Write-Error "找不到 winCodeSign: $sourceFile"
    exit 1
}

# 确保缓存目录存在
if (!(Test-Path $cacheDir)) {
    New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null
}

# 清理旧的数字目录和 .7z 文件
Write-Host "[1/3] 清理旧缓存..." -ForegroundColor Yellow
Get-ChildItem -Path $cacheDir -File -Filter "*.7z" | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $cacheDir -Directory | Where-Object { $_.Name -match '^\d+$' } | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# 预先解压到多个可能的随机目录名（提高命中率）
Write-Host "[2/3] 准备缓存..." -ForegroundColor Yellow
$randomNames = @("038143455", "124065659", "995360575", "252144815", "999491427")

foreach ($name in $randomNames) {
    $targetDir = Join-Path $cacheDir $name
    if (!(Test-Path $targetDir)) {
        New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
        & $sevenZip x -y -o"$targetDir" "$sourceFile" 2>&1 | Out-Null
    }
}

# 同时解压到标准名称
$standardDir = Join-Path $cacheDir "winCodeSign-2.6.0"
if (!(Test-Path $standardDir)) {
    New-Item -ItemType Directory -Force -Path $standardDir | Out-Null
    & $sevenZip x -y -o"$standardDir" "$sourceFile" 2>&1 | Out-Null
}

# 验证
$testPath = Join-Path $cacheDir "winCodeSign-2.6.0\windows-10"
if (!(Test-Path $testPath)) {
    # 检查随机目录
    $anyValid = Get-ChildItem -Path $cacheDir -Directory | Where-Object { 
        Test-Path (Join-Path $_.FullName "windows-10") 
    } | Select-Object -First 1
    
    if (!$anyValid) {
        Write-Error "缓存准备失败"
        exit 1
    }
}

Write-Host "[成功] 缓存已准备" -ForegroundColor Green
Write-Host ""

# 设置环境变量并运行构建
Write-Host "[3/3] 运行 electron-builder..." -ForegroundColor Yellow
Write-Host ""

$env:ELECTRON_BUILDER_CACHE = $cacheDir
Set-Location $frontendDir

# 运行构建
try {
    npm run electron:build:win 2>&1 | ForEach-Object {
        $line = $_
        # 如果是下载相关的行，显示警告
        if ($line -match "downloading.*winCodeSign") {
            Write-Host $line -ForegroundColor Yellow
        }
        # 如果是错误行，显示红色
        elseif ($line -match "ERROR|error|cannot execute|failed") {
            Write-Host $line -ForegroundColor Red
        }
        # 成功信息
        elseif ($line -match "built|success|✓|done") {
            Write-Host $line -ForegroundColor Green
        }
        else {
            Write-Host $line
        }
    }
    
    $exitCode = $LASTEXITCODE
    
    Write-Host ""
    if ($exitCode -eq 0) {
        Write-Host "========================================" -ForegroundColor Green
        Write-Host "  构建成功！" -ForegroundColor Green
        Write-Host "========================================" -ForegroundColor Green
    } else {
        Write-Host "========================================" -ForegroundColor Red
        Write-Host "  构建失败，退出代码: $exitCode" -ForegroundColor Red
        Write-Host "========================================" -ForegroundColor Red
    }
} catch {
    Write-Error "构建过程出错: $_"
}

Write-Host ""
Write-Host "按任意键退出..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
