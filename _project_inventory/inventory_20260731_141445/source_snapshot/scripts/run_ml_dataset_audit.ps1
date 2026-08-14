$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path `
    $projectRoot `
    '.venv\Scripts\python.exe'

$auditScript = Join-Path `
    $projectRoot `
    'backend\scripts\ml_certificate_classifier\01_audit_dataset.py'

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "프로젝트 .venv Python이 없습니다: $venvPython"
}

if (-not (Test-Path -LiteralPath $auditScript)) {
    throw "데이터 점검 스크립트가 없습니다: $auditScript"
}

$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

& $venvPython $auditScript

if ($LASTEXITCODE -ne 0) {
    throw "데이터셋 점검 실패. 종료코드: $LASTEXITCODE"
}

$latestAuditPointer = `
    'D:\halal_web_runtime\certificate_classifier\reports\latest_audit.txt'

if (Test-Path -LiteralPath $latestAuditPointer) {
    $latestAuditRoot = (
        Get-Content `
            -LiteralPath $latestAuditPointer `
            -Raw
    ).Trim()

    if (Test-Path -LiteralPath $latestAuditRoot) {
        Start-Process explorer.exe $latestAuditRoot
    }
}
