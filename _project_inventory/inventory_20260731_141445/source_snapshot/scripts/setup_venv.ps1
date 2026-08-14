param(
    [switch]$Recreate
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvDir = Join-Path $ProjectRoot '.venv'
$Requirements = Join-Path $ProjectRoot 'backend\requirements.txt'
$PythonExe = Join-Path $VenvDir 'Scripts\python.exe'

Set-Location $ProjectRoot

Write-Host '=== Halal Web .venv setup ===' -ForegroundColor Cyan

if ($env:CONDA_PREFIX) {
    Write-Host "현재 Conda 환경이 활성화되어 있습니다: $env:CONDA_PREFIX" -ForegroundColor Yellow
    Write-Host '이 스크립트는 Conda를 삭제하지 않고 별도의 .venv를 생성합니다.' -ForegroundColor Yellow
}

if ($Recreate -and (Test-Path $VenvDir)) {
    Remove-Item $VenvDir -Recurse -Force
}

if (-not (Test-Path $VenvDir)) {
    $py310 = & py -3.10 -c "import sys; print(sys.executable)" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw 'Python 3.10을 찾지 못했습니다. `py -0p`로 설치된 Python을 확인하세요.'
    }

    & py -3.10 -m venv $VenvDir
}

& $PythonExe -m pip install --upgrade pip setuptools wheel
& $PythonExe -m pip install -r $Requirements

$LocalEnvExample = Join-Path $ProjectRoot 'scripts\local_env.ps1.example'
$LocalEnv = Join-Path $ProjectRoot 'scripts\local_env.ps1'
if ((Test-Path $LocalEnvExample) -and -not (Test-Path $LocalEnv)) {
    Copy-Item $LocalEnvExample $LocalEnv
    Write-Host 'scripts\local_env.ps1을 생성했습니다. 이 파일은 Git에서 제외됩니다.' -ForegroundColor Green
}

& $PythonExe -m pip freeze | Set-Content -Encoding UTF8 (Join-Path $ProjectRoot 'backend\requirements.lock.txt')

Write-Host ''
Write-Host '가상환경 생성 완료' -ForegroundColor Green
Write-Host "Python: $PythonExe"
Write-Host 'VS Code에서 Python: Select Interpreter → .venv\Scripts\python.exe 선택'
Write-Host '다음 실행: .\scripts\run_backend.ps1'
