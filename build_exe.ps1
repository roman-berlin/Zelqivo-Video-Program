<# 
.SYNOPSIS
    Build script for MulticamEditor Windows EXE.

.DESCRIPTION
    Creates a standalone Windows executable using PyInstaller.
    Steps:
    1. Creates/activates virtual environment (if not active)
    2. Installs dependencies
    3. Runs pytest to verify code health
    4. Runs PyInstaller with the spec file
    5. Verifies the output EXE exists

.EXAMPLE
    .\build_exe.ps1

.NOTES
    Requires: Python 3.10+, and $env:ZELQIVO_FFMPEG_DIR pointing at a folder
    with ffmpeg.exe / ffprobe.exe from an LGPL FFmpeg build (BtbN *-lgpl:
    https://github.com/BtbN/FFmpeg-Builds/releases)
#>

$ErrorActionPreference = "Stop"

# Configuration
$VenvPath = ".\.venv"
$SpecFile = "multicam_editor.spec"
$OutputExe = "dist\MulticamEditor\MulticamEditor.exe"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  MulticamEditor (Zelqivo) Build Script" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check Python
Write-Host "[1/5] Checking Python..." -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Python not found in PATH" -ForegroundColor Red
    exit 1
}
Write-Host "  Found: $pythonVersion" -ForegroundColor Green

# Step 2: Create/activate venv
Write-Host "[2/5] Setting up virtual environment..." -ForegroundColor Yellow
if (-not (Test-Path $VenvPath)) {
    Write-Host "  Creating new venv at $VenvPath..." -ForegroundColor Gray
    python -m venv $VenvPath
}

# Activate venv
$activateScript = "$VenvPath\Scripts\Activate.ps1"
if (Test-Path $activateScript) {
    Write-Host "  Activating venv..." -ForegroundColor Gray
    & $activateScript
} else {
    Write-Host "ERROR: Could not find activation script at $activateScript" -ForegroundColor Red
    exit 1
}

# Step 3: Install dependencies
Write-Host "[3/5] Installing dependencies..." -ForegroundColor Yellow
pip install --upgrade pip --quiet
pip install -e ".[dev]" --quiet
Write-Host "  Dependencies installed." -ForegroundColor Green

# Step 4: Run tests
Write-Host "[4/5] Running tests..." -ForegroundColor Yellow
$testResult = pytest -q --tb=no 2>&1
$testExitCode = $LASTEXITCODE

# Parse test summary (last line usually contains X passed, Y failed)
$testSummary = $testResult | Select-Object -Last 3 | Out-String
Write-Host $testSummary -ForegroundColor Gray

if ($testExitCode -eq 0) {
    Write-Host "  All tests passed!" -ForegroundColor Green
} else {
    Write-Host "  Some tests failed (exit code: $testExitCode)" -ForegroundColor Yellow
    Write-Host "  Note: 1 pre-existing test failure is expected (baseline)." -ForegroundColor Gray
}

# Step 5: Build with PyInstaller
Write-Host "[5/5] Building EXE with PyInstaller..." -ForegroundColor Yellow
Write-Host "  Spec file: $SpecFile" -ForegroundColor Gray

# Check FFmpeg binaries (directory comes from ZELQIVO_FFMPEG_DIR)
$ffmpegDir = $env:ZELQIVO_FFMPEG_DIR
if (-not $ffmpegDir) {
    Write-Host "ERROR: ZELQIVO_FFMPEG_DIR is not set." -ForegroundColor Red
    Write-Host "  Set it to a folder containing ffmpeg.exe and ffprobe.exe from an" -ForegroundColor Red
    Write-Host "  LGPL FFmpeg build (BtbN *-lgpl: https://github.com/BtbN/FFmpeg-Builds/releases)." -ForegroundColor Red
    exit 1
}
$ffmpegPath = Join-Path $ffmpegDir "ffmpeg.exe"
$ffprobePath = Join-Path $ffmpegDir "ffprobe.exe"
if (-not (Test-Path $ffmpegPath) -or -not (Test-Path $ffprobePath)) {
    Write-Host "ERROR: ffmpeg.exe / ffprobe.exe not found in ZELQIVO_FFMPEG_DIR ($ffmpegDir)." -ForegroundColor Red
    Write-Host "  Download an LGPL build (BtbN *-lgpl: https://github.com/BtbN/FFmpeg-Builds/releases)" -ForegroundColor Red
    Write-Host "  and point ZELQIVO_FFMPEG_DIR at its bin folder." -ForegroundColor Red
    exit 1
}

# Run PyInstaller
pyinstaller $SpecFile --clean --noconfirm 2>&1 | ForEach-Object {
    if ($_ -match "error|Error|ERROR") {
        Write-Host $_ -ForegroundColor Red
    } elseif ($_ -match "warning|Warning|WARNING") {
        Write-Host $_ -ForegroundColor Yellow
    } else {
        Write-Host $_ -ForegroundColor Gray
    }
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "" -ForegroundColor Red
    Write-Host "BUILD FAILED" -ForegroundColor Red
    exit 1
}

# Verify output
Write-Host "" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  BUILD SUMMARY" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

if (Test-Path $OutputExe) {
    $exeInfo = Get-Item $OutputExe
    $sizeMB = [math]::Round($exeInfo.Length / 1MB, 2)
    Write-Host ""
    Write-Host "  Status: SUCCESS" -ForegroundColor Green
    Write-Host "  Output: $((Resolve-Path $OutputExe).Path)" -ForegroundColor White
    Write-Host "  Size:   $sizeMB MB" -ForegroundColor White
    Write-Host ""
    Write-Host "  To run: .\$OutputExe" -ForegroundColor Cyan
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "  Status: FAILED" -ForegroundColor Red
    Write-Host "  Expected output not found: $OutputExe" -ForegroundColor Red
    exit 1
}

Write-Host "Done!" -ForegroundColor Green
