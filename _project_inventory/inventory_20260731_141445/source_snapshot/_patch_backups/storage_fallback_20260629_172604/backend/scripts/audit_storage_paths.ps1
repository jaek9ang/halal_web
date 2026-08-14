param(
    [string]$ProjectRoot = ""
)

$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
    $ProjectRoot = (Get-Location).Path
}

if (-not (Test-Path (Join-Path $ProjectRoot "backend\app\main.py"))) {
    throw "halal_web 프로젝트 루트에서 실행하세요."
}

$BackendRoot = Join-Path $ProjectRoot "backend"
$Droot = "D:\halal_web_runtime"
$Failures = 0

Write-Host "=== 저장경로 점검 ===" -ForegroundColor Cyan

foreach ($name in @("data", "output", "cache", "db")) {
    $logical = Join-Path $BackendRoot $name
    $expected = Join-Path $Droot $name

    if (-not (Test-Path $logical)) {
        Write-Host "[FAIL] 없음: $logical" -ForegroundColor Red
        $Failures++
        continue
    }

    $item = Get-Item $logical -Force

    if ($item.LinkType -ne "Junction") {
        Write-Host "[FAIL] Junction 아님: $logical" -ForegroundColor Red
        $Failures++
        continue
    }

    $actual = (Resolve-Path $item.Target).Path
    $expectedResolved = (Resolve-Path $expected).Path

    if ($actual -ne $expectedResolved) {
        Write-Host "[FAIL] 대상 불일치: $logical -> $actual" -ForegroundColor Red
        $Failures++
    }
    else {
        Write-Host "[OK] $logical -> $expected" -ForegroundColor Green
    }
}

$Patterns = @(
    "OneDrive",
    "C:\\TEMP",
    'Path\("data/mail_downloads"\)',
    "HALAL_RAW_MATERIAL_ROOT",
    "HALAL_DOC_ROOT",
    "\\\\홍진우"
)

$Files = Get-ChildItem `
    (Join-Path $BackendRoot "app"), `
    (Join-Path $BackendRoot "scripts") `
    -Recurse -File -Include *.py,*.ps1,*.json `
    -ErrorAction SilentlyContinue

$Findings = foreach ($pattern in $Patterns) {
    $matches = $Files | Select-String -Pattern $pattern -ErrorAction SilentlyContinue

    foreach ($match in $matches) {
        [PSCustomObject]@{
            Pattern = $pattern
            File = $match.Path
            Line = $match.LineNumber
            Text = $match.Line.Trim()
        }
    }
}

$ReportDir = "D:\halal_web_runtime\reports"
New-Item -ItemType Directory -Path $ReportDir -Force | Out-Null
$ReportPath = Join-Path $ReportDir ("storage_path_audit_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".json")

$Findings |
ConvertTo-Json -Depth 10 |
Set-Content -LiteralPath $ReportPath -Encoding UTF8

Write-Host ""
Write-Host "경로 관련 코드 검색 결과: $($Findings.Count)건"
Write-Host "보고서: $ReportPath"

$BadRelative = $Findings | Where-Object { $_.Pattern -eq 'Path\("data/mail_downloads"\)' }
$HardcodedTemp = $Findings | Where-Object { $_.Pattern -eq "C:\\TEMP" }

if ($BadRelative) {
    Write-Host "[FAIL] 상대 mail_downloads 경로가 남아 있습니다." -ForegroundColor Red
    $Failures++
}

if ($HardcodedTemp) {
    Write-Host "[WARN] C:\TEMP 참조가 남아 있습니다. 테스트 스크립트인지 확인하세요." -ForegroundColor Yellow
}

if ($Failures -gt 0) {
    throw "STORAGE_PATH_AUDIT_FAILED"
}

Write-Host "STORAGE_PATH_AUDIT_OK" -ForegroundColor Green
