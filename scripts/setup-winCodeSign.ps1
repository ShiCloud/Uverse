# 设置本地 winCodeSign 缓存
$ErrorActionPreference = "Stop"

$sourceFile = "D:\workspace\Uverse\backend\support\win\winCodeSign-2.6.0.7z"
$cacheDir = "$env:LOCALAPPDATA\electron-builder\Cache\winCodeSign"
$targetDir = "$cacheDir\winCodeSign-2.6.0"

Write-Host "Setting up local winCodeSign cache..." -ForegroundColor Cyan

# 确保缓存目录存在
if (!(Test-Path $cacheDir)) {
    New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null
}

# 清理旧的数字目录
Get-ChildItem -Path $cacheDir -Directory | Where-Object { $_.Name -match '^\d+$' } | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $cacheDir -Filter "*.7z" | Remove-Item -Force -ErrorAction SilentlyContinue

# 创建目标目录
if (Test-Path $targetDir) {
    Remove-Item -Recurse -Force $targetDir
}
New-Item -ItemType Directory -Force -Path $targetDir | Out-Null

# 使用 7-Zip 解压（跳过符号链接错误）
$7zip = "D:\workspace\Uverse\frontend\node_modules\7zip-bin\win\x64\7za.exe"

Write-Host "Extracting winCodeSign-2.6.0.7z..." -ForegroundColor Cyan
& $7zip x -y -o"$targetDir" "$sourceFile" 2>&1 | Out-Null

# 检查解压结果
if (Test-Path "$targetDir\windows-10") {
    Write-Host "SUCCESS: winCodeSign extracted to $targetDir" -ForegroundColor Green
    
    # 列出内容
    Write-Host "Contents:" -ForegroundColor Gray
    Get-ChildItem $targetDir | ForEach-Object { Write-Host "  - $($_.Name)" -ForegroundColor Gray }
} else {
    Write-Error "Failed to extract winCodeSign"
    exit 1
}

# 设置环境变量并运行构建
Write-Host "`nRunning electron-builder with local cache..." -ForegroundColor Cyan

$env:ELECTRON_BUILDER_CACHE = $cacheDir
cd "D:\workspace\Uverse\frontend"
npm run electron:build:win
