param(
    [string]$ProjectRoot = "",
    [switch]$ConfirmDelete
)

$ErrorActionPreference = "Stop"

if (-not $ConfirmDelete) {
    throw "안전상 -ConfirmDelete 옵션이 필요합니다."
}

if (-not $ProjectRoot) {
    $ProjectRoot = (Get-Location).Path
}

$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$BackendRoot = Join-Path $ProjectRoot "backend"

Write-Host "=== OneDrive 임시 런타임 백업 삭제 ===" -ForegroundColor Yellow
Write-Host "백엔드 실행과 실제 메일/OCR 테스트가 정상 완료된 뒤에만 실행하세요." -ForegroundColor Yellow

$backups = Get-ChildItem -LiteralPath $BackendRoot -Directory -Force |
    Where-Object { $_.Name -match "^(data|output|cache|db)\.__onedrive_backup_\d{8}_\d{6}$" }

if (-not $backups) {
    Write-Host "삭제할 임시 백업이 없습니다."
    exit 0
}

$backups | Select-Object FullName, LastWriteTime

$answer = Read-Host "위 폴더를 영구 삭제하려면 DELETE 입력"
if ($answer -ne "DELETE") {
    throw "사용자가 삭제를 취소했습니다."
}

foreach ($backup in $backups) {
    Remove-Item -LiteralPath $backup.FullName -Recurse -Force
    Write-Host "삭제: $($backup.FullName)" -ForegroundColor Green
}

Write-Host "OneDrive 임시 백업 삭제 완료" -ForegroundColor Green
