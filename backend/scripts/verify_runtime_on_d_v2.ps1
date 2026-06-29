param(
    [string]$ProjectRoot = "",
    [string]$DestinationRoot = "D:\halal_web_runtime"
)

$ErrorActionPreference = "Stop"

function Resolve-ProjectRoot {
    param([string]$Value)

    if ($Value) {
        return (Resolve-Path -LiteralPath $Value).Path
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
$runtimeFolders = @("data", "output", "cache", "db")
$failed = $false

Write-Host "=== D 드라이브 런타임 저장 검증 V2 ===" -ForegroundColor Cyan

foreach ($name in $runtimeFolders) {
    $logical = Join-Path $BackendRoot $name
    $physical = Join-Path $DestinationRoot $name

    if (-not (Test-Path -LiteralPath $logical)) {
        Write-Host "[FAIL] 논리 경로 없음: $logical" -ForegroundColor Red
        $failed = $true
        continue
    }

    $item = Get-Item -LiteralPath $logical -Force
    $isJunction = (
        $item.LinkType -eq "Junction" -and
        $null -ne $item.Target -and
        "$($item.Target)".Trim().Length -gt 0
    )

    if (-not $isJunction) {
        Write-Host "[FAIL] 실제 Junction이 아님: $logical / LinkType=$($item.LinkType)" -ForegroundColor Red
        $failed = $true
        continue
    }

    if (-not (Test-Path -LiteralPath $physical)) {
        Write-Host "[FAIL] 물리 경로 없음: $physical" -ForegroundColor Red
        $failed = $true
        continue
    }

    $expectedTarget = (Resolve-Path -LiteralPath $physical).Path
    $actualTarget = (Resolve-Path -LiteralPath $item.Target).Path

    if ($expectedTarget -ne $actualTarget) {
        Write-Host "[FAIL] 정션 대상 불일치: $logical -> $actualTarget" -ForegroundColor Red
        $failed = $true
        continue
    }

    $testDir = Join-Path $logical "_verify_storage"
    $testFile = Join-Path $testDir "verify.txt"

    New-Item -ItemType Directory -Path $testDir -Force | Out-Null
    Set-Content -LiteralPath $testFile -Value "verify runtime storage" -Encoding UTF8

    $physicalFile = Join-Path $physical "_verify_storage\verify.txt"
    if (-not (Test-Path -LiteralPath $physicalFile)) {
        Write-Host "[FAIL] 쓰기 검증 실패: $logical" -ForegroundColor Red
        $failed = $true
    }
    else {
        Write-Host "[OK] $logical -> $physical" -ForegroundColor Green
    }

    Remove-Item -LiteralPath $testDir -Recurse -Force
}

Write-Host ""
Get-PSDrive -Name D | Select-Object Name, Used, Free, Root

if ($failed) {
    throw "하나 이상의 저장 경로 검증이 실패했습니다."
}

Write-Host ""
Write-Host "모든 런타임 경로가 D 드라이브에 연결되어 있습니다." -ForegroundColor Green
