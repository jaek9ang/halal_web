#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$RuntimeRoot = 'D:\halal_web_runtime\certificate_classifier'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = (Get-Location).Path
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
$scriptPath = Join-Path $projectRoot 'backend\scripts\ml_field_extraction\06_diagnose_product_ocr_bias.py'
$productPointer = Join-Path $RuntimeRoot 'reports\latest_product_item_labels.txt'
$ocrPointer = Join-Path $RuntimeRoot 'reports\latest_ocr_run.txt'

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "프로젝트 .venv Python 없음: $pythonExe"
}
if (-not (Test-Path -LiteralPath $scriptPath)) {
    throw "OCR 편향 진단 스크립트 없음: $scriptPath"
}
if (-not (Test-Path -LiteralPath $productPointer)) {
    throw "4C 제품행 결과 포인터 없음: $productPointer"
}
if (-not (Test-Path -LiteralPath $ocrPointer)) {
    throw "OCR 결과 포인터 없음: $ocrPointer"
}

$productReportRoot = (
    Get-Content -LiteralPath $productPointer -Raw -Encoding UTF8
).Trim()
$ocrReportRoot = (
    Get-Content -LiteralPath $ocrPointer -Raw -Encoding UTF8
).Trim()

& $pythonExe `
    $scriptPath `
    --project-root $projectRoot `
    --runtime-root $RuntimeRoot `
    --product-report-root $productReportRoot `
    --ocr-report-root $ocrReportRoot

if ($LASTEXITCODE -ne 0) {
    throw "4C-1 OCR 편향 진단 실패. 종료 코드: $LASTEXITCODE"
}