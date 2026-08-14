#requires -Version 5.1
#
# 프론트엔드 개발서버 실행 (Windows).
#   .\scripts\run_frontend.ps1

$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$FrontendDir = Join-Path $ProjectRoot 'frontend'

if (-not (Test-Path -LiteralPath $FrontendDir)) {
    throw "frontend 폴더가 없습니다: $FrontendDir"
}

Set-Location -LiteralPath $FrontendDir

if (-not $env:VITE_API_BASE_URL) {
    $env:VITE_API_BASE_URL = 'http://127.0.0.1:8000'
}

Write-Host ''
Write-Host '할랄인증관리 프론트엔드 실행' -ForegroundColor Cyan
Write-Host "API: $env:VITE_API_BASE_URL"
Write-Host '주소: http://127.0.0.1:5173'
Write-Host ''

if (-not (Test-Path -LiteralPath '.\node_modules')) {
    Write-Host 'node_modules가 없어 npm install을 실행합니다.' -ForegroundColor Yellow

    & npm install

    if ($LASTEXITCODE -ne 0) {
        throw "npm install 실패. 종료 코드: $LASTEXITCODE"
    }
}

& npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
