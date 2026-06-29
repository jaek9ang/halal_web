param(
    [string]$ProjectRoot = ""
)

$ErrorActionPreference = "Stop"

$PatchRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ProjectRoot) {
    $ProjectRoot = (Get-Location).Path
}

$ProjectRoot = (Resolve-Path $ProjectRoot).Path
$BackendDir = Join-Path $ProjectRoot "backend"
$ServiceDir = Join-Path $BackendDir "app\services"
$ScriptDir = Join-Path $BackendDir "scripts"
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path (Join-Path $ServiceDir "ocr_service.py"))) {
    throw "프로젝트 루트가 올바르지 않습니다. backend\app\services\ocr_service.py를 찾지 못했습니다: $ProjectRoot"
}

if (-not (Test-Path $PythonExe)) {
    $PythonExe = (Get-Command python -ErrorAction Stop).Source
}

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupDir = Join-Path $ProjectRoot "_patch_backups\ocr_rule_v2_$Timestamp"
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
New-Item -ItemType Directory -Path $ScriptDir -Force | Out-Null

Write-Host "=== OCR Rule V2 적용 ===" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"
Write-Host "Python : $PythonExe"
Write-Host "Backup : $BackupDir"

foreach ($name in @("certificate_rule_service.py", "ocr_context_service.py", "ocr_service.py")) {
    $source = Join-Path $ServiceDir $name
    if (Test-Path $source) {
        Copy-Item $source (Join-Path $BackupDir $name) -Force
    }
}

Copy-Item `
    (Join-Path $PatchRoot "backend\app\services\certificate_rule_service.py") `
    (Join-Path $ServiceDir "certificate_rule_service.py") `
    -Force

Copy-Item `
    (Join-Path $PatchRoot "backend\app\services\ocr_context_service.py") `
    (Join-Path $ServiceDir "ocr_context_service.py") `
    -Force

Copy-Item `
    (Join-Path $PatchRoot "backend\scripts\patch_ocr_service_v2.py") `
    (Join-Path $ScriptDir "patch_ocr_service_v2.py") `
    -Force

Copy-Item `
    (Join-Path $PatchRoot "backend\scripts\test_ocr_rule_v2.py") `
    (Join-Path $ScriptDir "test_ocr_rule_v2.py") `
    -Force

& $PythonExe (Join-Path $ScriptDir "patch_ocr_service_v2.py")
if ($LASTEXITCODE -ne 0) {
    throw "ocr_service.py 연결 패치에 실패했습니다."
}

$CompileTargets = @(
    (Join-Path $ServiceDir "certificate_rule_service.py"),
    (Join-Path $ServiceDir "ocr_context_service.py"),
    (Join-Path $ServiceDir "ocr_service.py"),
    (Join-Path $ScriptDir "test_ocr_rule_v2.py")
)

foreach ($target in $CompileTargets) {
    & $PythonExe -m py_compile $target
    if ($LASTEXITCODE -ne 0) {
        throw "구문 검증 실패: $target"
    }
}

if (-not (Test-Path (Join-Path $ServiceDir "mail_request_item_service.py"))) {
    Write-Host "경고: mail_request_item_service.py가 없습니다." -ForegroundColor Yellow
    Write-Host "OCR 기본 규칙은 작동하지만 메일/PMF 문맥 보강은 비활성 상태로 동작합니다." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "OCR Rule V2 적용 및 구문 검증 완료" -ForegroundColor Green
Write-Host "실제 회귀 테스트 예시:" -ForegroundColor Yellow
Write-Host '  .\.venv\Scripts\python.exe .\backend\scripts\test_ocr_rule_v2.py --bundle "C:\TEMP\halal_ocr_rule_review\ocr_rule_review_bundle_20260629_102333.zip"'
