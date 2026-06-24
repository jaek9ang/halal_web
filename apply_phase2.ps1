$ErrorActionPreference = "Stop"

$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Get-Location
$BackendRoot = Join-Path $ProjectRoot "backend"
$SourceBackend = Join-Path $PackageRoot "backend"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupRoot = Join-Path $ProjectRoot "_patch_backups\certificate_filing_phase2_$Stamp"

if (-not (Test-Path (Join-Path $BackendRoot "app\main.py"))) {
    throw "halal_web 프로젝트 루트에서 실행하세요. backend\app\main.py를 찾지 못했습니다."
}

New-Item -ItemType Directory -Force $BackupRoot | Out-Null

$Targets = @(
    "app\main.py",
    "app\routers\certificate_filing.py",
    "app\services\mail_request_item_service.py",
    "app\services\pmf_filing_service.py",
    "app\services\certificate_filing_workflow_service.py",
    "scripts\test_certificate_filing_phase2.py"
)

foreach ($relative in $Targets) {
    $target = Join-Path $BackendRoot $relative
    if (Test-Path $target) {
        $backup = Join-Path $BackupRoot $relative
        New-Item -ItemType Directory -Force (Split-Path -Parent $backup) | Out-Null
        Copy-Item $target $backup -Force
    }
}

Copy-Item (Join-Path $SourceBackend "app\main.py") (Join-Path $BackendRoot "app\main.py") -Force
Copy-Item (Join-Path $SourceBackend "app\routers\certificate_filing.py") (Join-Path $BackendRoot "app\routers\certificate_filing.py") -Force
Copy-Item (Join-Path $SourceBackend "app\services\mail_request_item_service.py") (Join-Path $BackendRoot "app\services\mail_request_item_service.py") -Force
Copy-Item (Join-Path $SourceBackend "app\services\pmf_filing_service.py") (Join-Path $BackendRoot "app\services\pmf_filing_service.py") -Force
Copy-Item (Join-Path $SourceBackend "app\services\certificate_filing_workflow_service.py") (Join-Path $BackendRoot "app\services\certificate_filing_workflow_service.py") -Force
New-Item -ItemType Directory -Force (Join-Path $BackendRoot "scripts") | Out-Null
Copy-Item (Join-Path $SourceBackend "scripts\test_certificate_filing_phase2.py") (Join-Path $BackendRoot "scripts\test_certificate_filing_phase2.py") -Force

$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    throw ".venv Python을 찾지 못했습니다: $PythonExe"
}

& $PythonExe -m py_compile `
    (Join-Path $BackendRoot "app\main.py") `
    (Join-Path $BackendRoot "app\routers\certificate_filing.py") `
    (Join-Path $BackendRoot "app\services\mail_request_item_service.py") `
    (Join-Path $BackendRoot "app\services\pmf_filing_service.py") `
    (Join-Path $BackendRoot "app\services\certificate_filing_workflow_service.py") `
    (Join-Path $BackendRoot "scripts\test_certificate_filing_phase2.py")

Push-Location $BackendRoot
try {
    & $PythonExe -m scripts.test_certificate_filing_phase2
    & $PythonExe -c "from app.main import app; print('main import ok', len(app.routes))"
}
finally {
    Pop-Location
}

Write-Host "Phase 2 적용 및 검증 완료" -ForegroundColor Green
Write-Host "백업 위치: $BackupRoot"
