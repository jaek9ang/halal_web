#requires -Version 5.1
param(
    [string]$RuntimeRoot = 'D:\halal_web_runtime\certificate_classifier'
)

$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$builderPath = Join-Path $projectRoot 'backend\scripts\ml_field_extraction\01_build_field_label_candidates.py'

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "프로젝트 Python을 찾지 못했습니다: $pythonPath"
}

if (-not (Test-Path -LiteralPath $builderPath)) {
    throw "필드 라벨 생성기를 찾지 못했습니다: $builderPath"
}

& $pythonPath `
    $builderPath `
    --project-root $projectRoot `
    --runtime-root $RuntimeRoot

if ($LASTEXITCODE -ne 0) {
    throw "필드 라벨 후보 생성에 실패했습니다. 종료 코드: $LASTEXITCODE"
}

$pointerPath = Join-Path $RuntimeRoot 'reports\latest_field_label_candidates.txt'

if (Test-Path -LiteralPath $pointerPath) {
    $reportRoot = (
        Get-Content `
            -LiteralPath $pointerPath `
            -Raw `
            -Encoding UTF8
    ).Trim()

    $reportPath = Join-Path $reportRoot '09_annotation_report.html'

    Write-Host ''
    Write-Host '생성 결과:' -ForegroundColor Green
    Write-Host $reportRoot -ForegroundColor Cyan

    if (Test-Path -LiteralPath $reportPath) {
        Start-Process $reportPath
    }
}
