# Electron Builder Auto-Fix Build Script
$ErrorActionPreference = "Continue"

$sourceFile = "D:\workspace\Uverse\backend\support\win\winCodeSign-2.6.0.7z"
$cacheParentDir = "$env:LOCALAPPDATA\electron-builder\Cache"
$cacheDir = "$cacheParentDir\winCodeSign"
$frontendDir = "D:\workspace\Uverse\frontend"
$sevenZip = "$frontendDir\node_modules\7zip-bin\win\x64\7za.exe"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Electron Builder (Auto-Fix Mode)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if (!(Test-Path $sourceFile)) {
    Write-Error "Source file not found: $sourceFile"
    exit 1
}

# Ensure cache directory exists
if (!(Test-Path $cacheDir)) {
    New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null
}

# Clean old cache
Write-Host "[*] Cleaning old cache..." -ForegroundColor Yellow
Get-ChildItem -Path $cacheDir -File -Filter "*.7z" -ErrorAction SilentlyContinue | Remove-Item -Force
Get-ChildItem -Path $cacheDir -Directory | Where-Object { $_.Name -match '^\d+$' } | Remove-Item -Recurse -Force

# Create FileSystemWatcher to monitor winCodeSign subdirectory
$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = $cacheDir
$watcher.Filter = "*.7z"
$watcher.NotifyFilter = [System.IO.NotifyFilters]::FileName
$watcher.IncludeSubdirectories = $false

$action = {
    $path = $Event.SourceEventArgs.FullPath
    $name = $Event.SourceEventArgs.Name
    
    Write-Host ""
    Write-Host "[Monitor] Detected: $name" -ForegroundColor Magenta
    
    # Wait for download to complete
    Start-Sleep -Milliseconds 800
    
    try {
        # Get directory name (remove .7z)
        $dirName = [System.IO.Path]::GetFileNameWithoutExtension($name)
        $targetDir = Join-Path $cacheDir $dirName
        
        Write-Host "[Monitor] Stopping 7z extraction..." -ForegroundColor Cyan
        
        # Kill any running 7za processes that might be extracting
        Get-Process | Where-Object { $_.ProcessName -like "*7za*" } | Stop-Process -Force -ErrorAction SilentlyContinue
        
        # Wait a bit
        Start-Sleep -Milliseconds 500
        
        # Delete downloaded file
        if (Test-Path $path) {
            Remove-Item -Path $path -Force -ErrorAction SilentlyContinue
        }
        
        # Remove partially extracted directory if exists
        if (Test-Path $targetDir) {
            Remove-Item -Path $targetDir -Recurse -Force -ErrorAction SilentlyContinue
        }
        
        # Create directory and extract local file
        New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
        
        Write-Host "[Monitor] Extracting local file..." -ForegroundColor Cyan
        & $sevenZip x -y -o"$targetDir" "$sourceFile" 2>&1 | Out-Null
        
        if ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq 2) {
            Write-Host "[Monitor] Extraction done (exit: $LASTEXITCODE)" -ForegroundColor Green
        }
        
        # Create empty .7z file as marker
        New-Item -ItemType File -Path $path -Force | Out-Null
        
        Write-Host "[Monitor] Cache fixed!" -ForegroundColor Green
    } catch {
        Write-Host "[Monitor Error] $_" -ForegroundColor Red
    }
}

Register-ObjectEvent -InputObject $watcher -EventName Created -Action $action | Out-Null
$watcher.EnableRaisingEvents = $true

Write-Host "[*] Cache monitor started on: $cacheDir" -ForegroundColor Green
Write-Host "[*] Starting build..." -ForegroundColor Yellow
Write-Host ""

# Run build - ELECTRON_BUILDER_CACHE should point to parent Cache dir
$env:ELECTRON_BUILDER_CACHE = $cacheParentDir
Set-Location $frontendDir

try {
    cmd /c "npm run electron:build:win 2>&1"
    $exitCode = $LASTEXITCODE
    
    Write-Host ""
    if ($exitCode -eq 0) {
        Write-Host "========================================" -ForegroundColor Green
        Write-Host "  Build Success!" -ForegroundColor Green
        Write-Host "========================================" -ForegroundColor Green
    } else {
        Write-Host "========================================" -ForegroundColor Red
        Write-Host "  Build finished, exit code: $exitCode" -ForegroundColor Red
        Write-Host "========================================" -ForegroundColor Red
    }
} catch {
    Write-Error "Build error: $_"
} finally {
    # Cleanup
    $watcher.EnableRaisingEvents = $false
    $watcher.Dispose()
    Get-EventSubscriber | Where-Object { $_.SourceObject -eq $watcher } | Unregister-Event -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
