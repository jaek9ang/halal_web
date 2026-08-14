#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$RuntimeRoot = 'D:\halal_web_runtime\certificate_classifier',

    [Parameter(Mandatory = $true)]
    [string]$SyntheticRoot,

    [int]$RenderDpi = 220
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = (Get-Location).Path
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
$scriptPath = Join-Path `
    $projectRoot `
    'backend\scripts\ml_data_augmentation\02_evaluate_synthetic_scan_ocr.py'

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "프로젝트 .venv Python 없음: $pythonExe"
}

if (-not (Test-Path -LiteralPath $scriptPath)) {
    throw "합성 OCR 평가 스크립트 없음: $scriptPath"
}

$pythonArgs = @(
    $scriptPath
    '--runtime-root'
    $RuntimeRoot
    '--synthetic-root'
    $SyntheticRoot
    '--render-dpi'
    [string]$RenderDpi
)

& $pythonExe @pythonArgs

if ($LASTEXITCODE -ne 0) {
    throw "합성 스캔 OCR 평가 실패. 종료 코드: $LASTEXITCODE"
}