#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$RuntimeRoot = 'D:\halal_web_runtime\certificate_classifier',

    [Parameter(Mandatory = $true)]
    [string]$CoreEvalReportRoot
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = (Get-Location).Path
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
$scriptPath = Join-Path `
    $projectRoot `
    'backend\scripts\ml_data_augmentation\04_prepare_synthetic_training_pack.py'

$pythonArgs = @(
    $scriptPath
    '--runtime-root'
    $RuntimeRoot
    '--core-eval-report-root'
    $CoreEvalReportRoot
)

& $pythonExe @pythonArgs

if ($LASTEXITCODE -ne 0) {
    throw "합성 스캔 안전 편입 패키지 생성 실패. 종료 코드: $LASTEXITCODE"
}