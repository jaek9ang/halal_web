#requires -Version 5.1
#
# 백엔드 실행 (Windows).
#   .\scripts\run_backend.ps1            # 기본 포트 8000
#   .\scripts\run_backend.ps1 -Port 8080
#
# PMF 원본은 운영 공유폴더를 먼저 보고, 연결되지 않으면 로컬 테스트 PMF로 대체한다.

param(
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $ProjectRoot 'backend'
$PythonExe = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$LocalEnv = Join-Path $ProjectRoot 'scripts\local_env.ps1'

$PrimaryPmfSource = "\\홍진우\공유\1) 인증심사관련\4. MUI HALAL\★ 자사 PMF 파일"
$FallbackPmf = 'D:\halal_web_runtime\pmf_test\active_pmf_test.xlsm'

if (-not (Test-Path -LiteralPath $BackendDir)) {
    throw "backend 폴더가 없습니다: $BackendDir"
}

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw '.venv가 없습니다. 먼저 .\scripts\setup_venv.ps1을 실행하세요.'
}

# 로컬 환경변수 (있으면) — PMF 판정보다 먼저 읽어 덮어쓸 수 있게 한다.
if (Test-Path -LiteralPath $LocalEnv) {
    . $LocalEnv
}

$env:PMF_SOURCE_DIR = $PrimaryPmfSource

$PrimaryPmf = $null

try {
    if (Test-Path -LiteralPath $PrimaryPmfSource) {
        $PrimaryPmf = Get-ChildItem `
            -LiteralPath $PrimaryPmfSource `
            -Filter 'Products and Materials File*.xlsm' `
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

    $PmfMode = '운영 PMF'
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

    $PmfMode = '테스트 PMF 대체'
    $PmfPath = $FallbackPmf
}

Set-Location -LiteralPath $BackendDir

Write-Host ''
Write-Host '할랄인증관리 백엔드 실행' -ForegroundColor Cyan
Write-Host "PMF 모드: $PmfMode" -ForegroundColor Yellow
Write-Host "PMF 경로: $PmfPath"
Write-Host "HALAL_RAW_MATERIAL_ROOT: $env:HALAL_RAW_MATERIAL_ROOT"
Write-Host "주소: http://127.0.0.1:$Port  (API 문서: /docs)"
Write-Host ''

# 기동 전 import 사전검사 — 실패하면 uvicorn 로그에 묻히지 않고 여기서 멈춘다.
& $PythonExe -c "import importlib; importlib.import_module('app.main'); print('app.main import OK')"

if ($LASTEXITCODE -ne 0) {
    throw 'app.main import 검사 실패'
}

& $PythonExe -m uvicorn app.main:app --reload --host 127.0.0.1 --port $Port
