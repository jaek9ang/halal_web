param(
    [string]$ProjectRoot = "",
    [string]$DestinationRoot = "D:\halal_web_runtime"
)

$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
    $ProjectRoot = (Get-Location).Path
}

$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$BackendRoot = Join-Path $ProjectRoot "backend"
$runtimeFolders = @("data", "output", "cache", "db")
$failed = $false

Write-Host "=== D 드라이브 런타임 저장 검증 ===" -ForegroundColor Cyan

foreach ($name in $runtimeFolders) {
    $logical = Join-Path $BackendRoot $name
    $physical = Join-Path $DestinationRoot $name

    if (-not (Test-Path -LiteralPath $logical)) {
        Write-Host "[FAIL] 논리 경로 없음: $logical" -ForegroundColor Red
        $failed = $true
        continue
    }

    $item = Get-Item -LiteralPath $logical -Force
    $isLink = [bool]($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)

    if (-not $isLink) {
        Write-Host "[FAIL] 정션이 아님: $logical" -ForegroundColor Red
        $failed = $true
        continue
    }

    if (-not (Test-Path -LiteralPath $physical)) {
        Write-Host "[FAIL] 물리 경로 없음: $physical" -ForegroundColor Red
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
