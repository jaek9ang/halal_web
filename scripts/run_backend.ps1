param(
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $ProjectRoot 'backend'
$PythonExe = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$LocalEnv = Join-Path $ProjectRoot 'scripts\local_env.ps1'

if (-not (Test-Path $PythonExe)) {
    throw '.venv가 없습니다. 먼저 .\scripts\setup_venv.ps1을 실행하세요.'
}

if (Test-Path $LocalEnv) {
    . $LocalEnv
}

New-Item -ItemType Directory -Force 'C:\TEMP\halal_filing_test' | Out-Null
New-Item -ItemType Directory -Force 'C:\TEMP\halal_pmf_source' | Out-Null

Set-Location $BackendDir

Write-Host '=== Backend runtime ===' -ForegroundColor Cyan
Write-Host "Python: $PythonExe"
Write-Host "HALAL_RAW_MATERIAL_ROOT: $env:HALAL_RAW_MATERIAL_ROOT"
Write-Host "PMF_SOURCE_DIR: $env:PMF_SOURCE_DIR"
Write-Host "Port: $Port"

& $PythonExe -m uvicorn app.main:app --reload --host 127.0.0.1 --port $Port
