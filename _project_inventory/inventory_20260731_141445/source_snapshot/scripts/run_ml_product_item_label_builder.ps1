#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$RuntimeRoot = 'D:\halal_web_runtime\certificate_classifier'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = (Get-Location).Path
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
$scriptPath = Join-Path $projectRoot 'backend\scripts\ml_field_extraction\05_build_product_item_labels.py'
$fieldPointer = Join-Path $RuntimeRoot 'reports\latest_field_label_candidates.txt'

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "프로젝트 .venv Python 없음: $pythonExe"
}
if (-not (Test-Path -LiteralPath $scriptPath)) {
    throw "제품행 라벨 생성 스크립트 없음: $scriptPath"
}
if (-not (Test-Path -LiteralPath $fieldPointer)) {
    throw "4A 결과 포인터 없음: $fieldPointer"
}

$fieldReportRoot = (
    Get-Content -LiteralPath $fieldPointer -Raw -Encoding UTF8
).Trim()

& $pythonExe `
    $scriptPath `
    --project-root $projectRoot `
    --runtime-root $RuntimeRoot `
    --field-report-root $fieldReportRoot

if ($LASTEXITCODE -ne 0) {
    throw "4C 제품행 라벨 생성 실패. 종료 코드: $LASTEXITCODE"
}