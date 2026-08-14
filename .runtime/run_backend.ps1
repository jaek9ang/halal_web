#requires -Version 5.1

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $ProjectRoot "backend"
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

$PrimaryPmfSource = "\\홍진우\공유\1) 인증심사관련\4. MUI HALAL\★ 자사 PMF 파일"
$FallbackPmf = "D:\halal_web_runtime\pmf_test\active_pmf_test.xlsm"

if (-not (Test-Path -LiteralPath $BackendDir)) {
    throw "backend 폴더가 없습니다: $BackendDir"
}

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "가상환경 Python이 없습니다: $PythonExe"
}

$env:PMF_SOURCE_DIR = $PrimaryPmfSource

$PrimaryPmf = $null

try {
    if (Test-Path -LiteralPath $PrimaryPmfSource) {
        $PrimaryPmf = Get-ChildItem `
            -LiteralPath $PrimaryPmfSource `
            -Filter "Products and Materials File*.xlsm" `
            -File `
            -ErrorAction Stop |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    }
}
catch {
    $PrimaryPmf = $null
}

if ($null -ne $PrimaryPmf) {
    Remove-Item Env:PMF_ACTIVE_PATH -ErrorAction SilentlyContinue
    Remove-Item Env:PMF_UPDATE_PATH -ErrorAction SilentlyContinue

    $PmfMode = "운영 PMF"
    $PmfPath = $PrimaryPmf.FullName
}
else {
    if (-not (Test-Path -LiteralPath $FallbackPmf)) {
        throw @"
운영 PMF에 연결되지 않았고 테스트 PMF도 없습니다.
운영 경로: $PrimaryPmfSource
테스트 경로: $FallbackPmf
"@
    }

    $env:PMF_ACTIVE_PATH = $FallbackPmf
    $env:PMF_UPDATE_PATH = $FallbackPmf

    $PmfMode = "테스트 PMF 대체"
    $PmfPath = $FallbackPmf
}

Set-Location -LiteralPath $BackendDir

Write-Host ""
Write-Host "할랄인증관리 백엔드 실행" -ForegroundColor Cyan
Write-Host "모듈: app.main:app"
Write-Host "PMF 모드: $PmfMode" -ForegroundColor Yellow
Write-Host "PMF 경로: $PmfPath"
Write-Host "주소: http://127.0.0.1:8000"
Write-Host "API 문서: http://127.0.0.1:8000/docs"
Write-Host ""

& $PythonExe `
    -c `
    "import importlib; importlib.import_module('app.main'); print('app.main import OK')"

if ($LASTEXITCODE -ne 0) {
    throw "app.main import 검사 실패"
}

& $PythonExe `
    -m uvicorn `
    app.main:app `
    --host 127.0.0.1 `
    --port 8000 `
    --reload

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "백엔드 종료 코드: $LASTEXITCODE" -ForegroundColor Red
    Read-Host "Enter를 누르면 창이 닫힙니다"
}