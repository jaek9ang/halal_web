#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$RuntimeRoot = 'D:\halal_web_runtime\certificate_classifier'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = (Get-Location).Path
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
$scriptPath = Join-Path $projectRoot 'backend\scripts\ml_field_extraction\02_refine_field_label_candidates.py'
$sourcePointer = Join-Path $RuntimeRoot 'reports\latest_field_label_candidates.txt'

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "프로젝트 .venv Python 없음: $pythonExe"
}
if (-not (Test-Path -LiteralPath $scriptPath)) {
    throw "정제 Python 스크립트 없음: $scriptPath"
}
if (-not (Test-Path -LiteralPath $sourcePointer)) {
    throw "4A 결과 포인터 없음: $sourcePointer"
}

$sourceReportRoot = (
    Get-Content -LiteralPath $sourcePointer -Raw -Encoding UTF8
).Trim()

& $pythonExe `
    $scriptPath `
    --project-root $projectRoot `
    --runtime-root $RuntimeRoot `
    --source-report-root $sourceReportRoot

if ($LASTEXITCODE -ne 0) {
    throw "필드 라벨 정제 실패. 종료 코드: $LASTEXITCODE"
}