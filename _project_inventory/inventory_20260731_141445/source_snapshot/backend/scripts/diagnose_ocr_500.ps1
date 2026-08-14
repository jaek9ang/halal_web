param(
    [string]$ProjectRoot = "",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

function Resolve-ProjectRoot {
    param([string]$Value)

    if ($Value) {
        $resolved = (Resolve-Path -LiteralPath $Value).Path
        if (-not (Test-Path (Join-Path $resolved "backend\app\main.py"))) {
            throw "halal_web 프로젝트 루트가 아닙니다: $resolved"
        }
        return $resolved
    }

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

$ProjectRoot = Resolve-ProjectRoot -Value $ProjectRoot
$BackendRoot = Join-Path $ProjectRoot "backend"
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    throw ".venv Python을 찾지 못했습니다: $PythonExe"
}

$RuntimeRoot = "D:\halal_web_runtime"
$LogRoot = Join-Path $RuntimeRoot "logs"
$DemoRoot = Join-Path $RuntimeRoot "ocr_demo"
$DemoFile = Join-Path $DemoRoot "test.pdf"
$StdoutLog = Join-Path $LogRoot "uvicorn_ocr_debug_stdout.log"
$StderrLog = Join-Path $LogRoot "uvicorn_ocr_debug_stderr.log"

New-Item -ItemType Directory -Path $LogRoot, $DemoRoot -Force | Out-Null
Remove-Item $StdoutLog, $StderrLog -Force -ErrorAction SilentlyContinue

Write-Host "=== 1. 기존 8000 포트 서버 종료 ===" -ForegroundColor Cyan

$listeners = Get-NetTCPConnection `
    -LocalPort $Port `
    -State Listen `
    -ErrorAction SilentlyContinue

foreach ($listener in $listeners) {
    Write-Host "기존 PID 종료: $($listener.OwningProcess)"
    Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Seconds 2

Write-Host ""
Write-Host "=== 2. 짧은 경로 테스트 PDF 준비 ===" -ForegroundColor Cyan

$searchRoots = @(
    (Join-Path $RuntimeRoot "data\mail_downloads"),
    (Join-Path $RuntimeRoot "data\ocr_test_uploads"),
    (Join-Path $RuntimeRoot "output\received_certs")
)

$existingRoots = $searchRoots | Where-Object { Test-Path -LiteralPath $_ }

$source = Get-ChildItem `
    -LiteralPath $existingRoots `
    -Recurse `
    -File `
    -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Extension -in @(".pdf", ".PDF") -and $_.Length -gt 0
    } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $source) {
    throw "D:\halal_web_runtime에서 테스트할 PDF를 찾지 못했습니다."
}

Copy-Item -LiteralPath $source.FullName -Destination $DemoFile -Force

Write-Host "원본: $($source.FullName)"
Write-Host "짧은 테스트 파일: $DemoFile"
Write-Host "크기: $((Get-Item $DemoFile).Length) bytes"

Write-Host ""
Write-Host "=== 3. 현재 코드로 디버그 서버 실행 ===" -ForegroundColor Cyan

$env:PYTHONPATH = $BackendRoot
$env:HALAL_SHARED_RAW_MATERIAL_ROOT = "\\홍진우\공유\1) 인증심사관련\4. MUI HALAL\2) HALAL 하부원료 서류\1)원재료"
$env:HALAL_LOCAL_RAW_MATERIAL_ROOT = "D:\halal_web_runtime\원재료"
$env:HALAL_RAW_MATERIAL_ROOT = "D:\halal_web_runtime\원재료"
$env:PYTHONUNBUFFERED = "1"

$server = Start-Process `
    -FilePath $PythonExe `
    -ArgumentList @(
        "-u",
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "$Port",
        "--log-level",
        "debug"
    ) `
    -WorkingDirectory $BackendRoot `
    -RedirectStandardOutput $StdoutLog `
    -RedirectStandardError $StderrLog `
    -PassThru

try {
    $ready = $false

    for ($i = 1; $i -le 30; $i++) {
        Start-Sleep -Seconds 1

        if ($server.HasExited) {
            break
        }

        try {
            $response = Invoke-WebRequest `
                -Uri "http://127.0.0.1:$Port/health" `
                -UseBasicParsing `
                -TimeoutSec 2

            if ($response.StatusCode -eq 200) {
                $ready = $true
                break
            }
        }
        catch {
        }
    }

    if (-not $ready) {
        Write-Host "SERVER_START_FAILED" -ForegroundColor Red
    }
    else {
        Write-Host "서버 시작 정상" -ForegroundColor Green
        Write-Host ""
        Write-Host "=== 4. 짧은 파일명으로 OCR 업로드 테스트 ===" -ForegroundColor Cyan

        & $PythonExe `
            (Join-Path $BackendRoot "scripts\test_ocr_api.py") `
            --file $DemoFile

        $testExit = $LASTEXITCODE

        if ($testExit -eq 0) {
            Write-Host ""
            Write-Host "SHORT_PATH_OCR_TEST_OK" -ForegroundColor Green
        }
        else {
            Write-Host ""
            Write-Host "SHORT_PATH_OCR_TEST_FAILED" -ForegroundColor Red
        }
    }

    Start-Sleep -Seconds 2
}
finally {
    if (-not $server.HasExited) {
        Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
    }
}

Write-Host ""
Write-Host "=== 5. 서버 오류 로그 ===" -ForegroundColor Cyan

Write-Host ""
Write-Host "--- STDERR 마지막 120줄 ---" -ForegroundColor Yellow
if (Test-Path $StderrLog) {
    Get-Content -LiteralPath $StderrLog -Tail 120
}

Write-Host ""
Write-Host "--- STDOUT 마지막 120줄 ---" -ForegroundColor Yellow
if (Test-Path $StdoutLog) {
    Get-Content -LiteralPath $StdoutLog -Tail 120
}

Write-Host ""
Write-Host "로그 파일:"
Write-Host $StderrLog
Write-Host $StdoutLog
