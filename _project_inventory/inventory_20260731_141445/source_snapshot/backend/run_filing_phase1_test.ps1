$ErrorActionPreference = "Stop"

Write-Host "=== Halal Filing Phase 1 Test ===" -ForegroundColor Cyan

if (-not (Test-Path ".\app\services\filing_name_service.py")) {
    throw "app\services\filing_name_service.py 파일이 없습니다. backend 폴더에서 실행하세요."
}

if (-not (Test-Path ".\app\services\certificate_filing_service.py")) {
    throw "app\services\certificate_filing_service.py 파일이 없습니다. backend 폴더에서 실행하세요."
}

New-Item -ItemType Directory -Force ".\scripts" | Out-Null
New-Item -ItemType File -Force ".\scripts\__init__.py" | Out-Null

Copy-Item ".\test_filing_copy.py" ".\scripts\test_filing_copy.py" -Force

python -m py_compile ".\app\services\filing_name_service.py"
python -m py_compile ".\app\services\certificate_filing_service.py"
python -m py_compile ".\scripts\test_filing_copy.py"

Write-Host "구문 검증 완료" -ForegroundColor Green

python -m scripts.test_filing_copy

Write-Host ""
Write-Host "정상 기대값:" -ForegroundColor Yellow
Write-Host "첫 번째 실행  -> COPIED"
Write-Host "두 번째 실행  -> DUPLICATE_SKIPPED"
