param(
    [string]$ProjectRoot = "",
    [string]$TestCopyDir = "C:\TEMP\halal_pmf_test"
)

$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
}

$ProjectRoot = (Resolve-Path $ProjectRoot).Path
$BackendDir = Join-Path $ProjectRoot "backend"
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$CachedPmf = Join-Path $BackendDir "cache\source_pmf\active_pmf.xlsm"
$MetaFile = Join-Path $BackendDir "cache\source_pmf\active_pmf_meta.json"

if (-not (Test-Path $PythonExe)) {
    throw ".venv Python을 찾지 못했습니다: $PythonExe"
}

if (-not (Test-Path (Join-Path $BackendDir "app\services\pmf_service.py"))) {
    throw "pmf_service.py를 찾지 못했습니다: $BackendDir"
}

Write-Host "=== 최신 PMF 동기화 ===" -ForegroundColor Cyan
Write-Host "Project root: $ProjectRoot"

Push-Location $BackendDir
try {
    & $PythonExe -c @"
import json
from app.services.pmf_service import sync_latest_pmf_copy
result = sync_latest_pmf_copy(force=True)
print(json.dumps(result, ensure_ascii=False, indent=2))
"@

    if ($LASTEXITCODE -ne 0) {
        throw "최신 PMF 동기화에 실패했습니다."
    }
}
finally {
    Pop-Location
}

if (-not (Test-Path $CachedPmf)) {
    throw "동기화 후 active_pmf.xlsm을 찾지 못했습니다: $CachedPmf"
}

New-Item -ItemType Directory -Path $TestCopyDir -Force | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LatestTestCopy = Join-Path $TestCopyDir "active_pmf_test.xlsm"
$TimestampCopy = Join-Path $TestCopyDir "active_pmf_test_$timestamp.xlsm"

Copy-Item $CachedPmf $LatestTestCopy -Force
Copy-Item $CachedPmf $TimestampCopy -Force

$env:PMF_UPDATE_PATH = $LatestTestCopy

Write-Host ""
Write-Host "=== 복사 완료 ===" -ForegroundColor Green
Write-Host "캐시 원본: $CachedPmf"
Write-Host "테스트 사용본: $LatestTestCopy"
Write-Host "시점 백업본: $TimestampCopy"
Write-Host "PMF_UPDATE_PATH: $env:PMF_UPDATE_PATH"

if (Test-Path $MetaFile) {
    Write-Host ""
    Write-Host "=== PMF 메타 ===" -ForegroundColor Cyan
    Get-Content $MetaFile -Raw
}

Write-Host ""
Write-Host "주의: 현재 PowerShell에 환경변수를 유지하려면 이 스크립트를 점(.)으로 실행하세요."
Write-Host '. .\scripts\refresh_latest_pmf_copy.ps1'
