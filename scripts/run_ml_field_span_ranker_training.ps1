#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$RuntimeRoot = 'D:\halal_web_runtime\certificate_classifier'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = (Get-Location).Path
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
$trainingScript = Join-Path $projectRoot 'backend\scripts\ml_field_extraction\04_train_field_span_rankers.py'
$refinementPointer = Join-Path $RuntimeRoot 'reports\latest_field_label_refinement.txt'

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "프로젝트 .venv Python 없음: $pythonExe"
}
if (-not (Test-Path -LiteralPath $trainingScript)) {
    throw "학습 스크립트 없음: $trainingScript"
}
if (-not (Test-Path -LiteralPath $refinementPointer)) {
    throw "4A-2 결과 포인터 없음: $refinementPointer"
}

$refinementRoot = (
    Get-Content -LiteralPath $refinementPointer -Raw -Encoding UTF8
).Trim()

& $pythonExe `
    $trainingScript `
    --project-root $projectRoot `
    --runtime-root $RuntimeRoot `
    --refinement-root $refinementRoot

if ($LASTEXITCODE -ne 0) {
    throw "4B-2 Span 모델 학습 실패. 종료 코드: $LASTEXITCODE"
}