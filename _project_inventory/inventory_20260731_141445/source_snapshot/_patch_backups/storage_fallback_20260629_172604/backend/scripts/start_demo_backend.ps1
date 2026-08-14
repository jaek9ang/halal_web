param(
    [string]$SharedRoot = "\\홍진우\공유\1) 인증심사관련\4. MUI HALAL\2) HALAL 하부원료 서류\1)원재료",
    [string]$FallbackRoot = "D:\halal_web_runtime\원재료",
    [int]$NetworkTimeoutSeconds = 5,
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

function Resolve-ProjectRoot {
    $current = (Get-Location).Path

    if (Test-Path (Join-Path $current "backend\app\main.py")) {
        return $current
    }

    $candidate = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    if (Test-Path (Join-Path $candidate "backend\app\main.py")) {
        return $candidate
    }

    throw "halal_web 프로젝트 루트를 찾지 못했습니다."
}

function Test-WritableWithTimeout {
    param(
        [string]$Path,
        [int]$TimeoutSeconds
    )

    $job = Start-Job -ScriptBlock {
        param($Target)

        try {
            if (-not (Test-Path -LiteralPath $Target)) {
                return $false
            }

            $testFile = Join-Path $Target (".__write_test_" + [guid]::NewGuid().ToString("N") + ".tmp")
            Set-Content -LiteralPath $testFile -Value "write test" -Encoding UTF8
            Remove-Item -LiteralPath $testFile -Force
            return $true
        }
        catch {
            return $false
        }
    } -ArgumentList $Path

    try {
        $done = Wait-Job -Job $job -Timeout $TimeoutSeconds

        if (-not $done) {
            Stop-Job -Job $job -ErrorAction SilentlyContinue
            return $false
        }

        return [bool](Receive-Job -Job $job)
    }
    finally {
        Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
    }
}

$ProjectRoot = Resolve-ProjectRoot
$BackendRoot = Join-Path $ProjectRoot "backend"
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    throw ".venv Python을 찾지 못했습니다: $PythonExe"
}

New-Item -ItemType Directory -Path $FallbackRoot -Force | Out-Null

$SharedOk = Test-WritableWithTimeout `
    -Path $SharedRoot `
    -TimeoutSeconds $NetworkTimeoutSeconds

if ($SharedOk) {
    $ActiveRoot = $SharedRoot
    $StorageMode = "SHARED"
}
else {
    $ActiveRoot = $FallbackRoot
    $StorageMode = "LOCAL_FALLBACK"
}

$env:HALAL_SHARED_RAW_MATERIAL_ROOT = $SharedRoot
$env:HALAL_LOCAL_RAW_MATERIAL_ROOT = $FallbackRoot
$env:HALAL_RAW_MATERIAL_ROOT = $ActiveRoot
$env:HALAL_DOC_ROOT = $ActiveRoot
$env:HALAL_STORAGE_MODE = $StorageMode

$PmfSource = Join-Path $BackendRoot "cache\source_pmf\active_pmf.xlsm"
$PmfTestDir = "D:\halal_web_runtime\pmf_test"
$PmfTestPath = Join-Path $PmfTestDir "active_pmf_test.xlsm"

New-Item -ItemType Directory -Path $PmfTestDir -Force | Out-Null

if (Test-Path $PmfSource) {
    $copyPmf = (
        -not (Test-Path $PmfTestPath) -or
        (Get-Item $PmfSource).LastWriteTimeUtc -gt (Get-Item $PmfTestPath).LastWriteTimeUtc
    )

    if ($copyPmf) {
        Copy-Item $PmfSource $PmfTestPath -Force
    }

    $env:PMF_UPDATE_PATH = $PmfTestPath
}
else {
    Write-Host "경고: PMF 캐시 파일이 없습니다: $PmfSource" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== 데모 백엔드 저장경로 ===" -ForegroundColor Cyan
Write-Host "STORAGE_MODE : $StorageMode"
Write-Host "FILING_ROOT  : $ActiveRoot"
Write-Host "PMF_TEST     : $env:PMF_UPDATE_PATH"
Write-Host "MAIL/OCR/DB  : D:\halal_web_runtime (backend Junction)"
Write-Host ""

Push-Location $BackendRoot
try {
    & $PythonExe -m uvicorn app.main:app --reload --host 127.0.0.1 --port $Port
}
finally {
    Pop-Location
}
