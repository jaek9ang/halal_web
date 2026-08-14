#requires -Version 5.1

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath 'C:\Users\user\OneDrive\바탕 화면\한재광\회사SW\DT준전문가교육\DLAB\SW Project\halal_web\backend'

# BEGIN TEMP PMF TEST CONFIG
# 임시 PMF 테스트 연결
$env:PMF_TEST_MODE = 'true'
$env:PMF_FILE_PATH = 'D:\halal_web_runtime\pmf_test\active_pmf_test.xlsm'
$env:PMF_PATH = 'D:\halal_web_runtime\pmf_test\active_pmf_test.xlsm'
$env:PMF_ACTIVE_FILE = 'D:\halal_web_runtime\pmf_test\active_pmf_test.xlsm'
$env:PMF_ACTIVE_FILE_PATH = 'D:\halal_web_runtime\pmf_test\active_pmf_test.xlsm'
$env:PMF_WORKBOOK_PATH = 'D:\halal_web_runtime\pmf_test\active_pmf_test.xlsm'
$env:PMF_SOURCE_PATH = 'D:\halal_web_runtime\pmf_test\active_pmf_test.xlsm'
$env:ACTIVE_PMF_PATH = 'D:\halal_web_runtime\pmf_test\active_pmf_test.xlsm'
$env:HALAL_PMF_FILE_PATH = 'D:\halal_web_runtime\pmf_test\active_pmf_test.xlsm'
$env:PMF_ROOT = 'D:\halal_web_runtime\pmf_test'
$env:PMF_DIR = 'D:\halal_web_runtime\pmf_test'
$env:PMF_DIRECTORY = 'D:\halal_web_runtime\pmf_test'
$env:PMF_FILE_NAME = 'active_pmf_test.xlsm'
$env:PMF_FILENAME = 'active_pmf_test.xlsm'
$env:PMF_WORKBOOK_NAME = 'active_pmf_test.xlsm'
Write-Host 'PMF 테스트 파일 연결: D:\halal_web_runtime\pmf_test\active_pmf_test.xlsm' -ForegroundColor Yellow
# END TEMP PMF TEST CONFIG




Write-Host ''
Write-Host '할랄인증관리 백엔드 실행' -ForegroundColor Cyan
Write-Host '모듈: app.main.:app'
Write-Host '주소: http://127.0.0.1:8000'
Write-Host 'API 문서: http://127.0.0.1:8000/docs'
Write-Host ''

$PythonArgs = @(
    '-m'
    'uvicorn'
    'app.main.:app'
    '--host'
    '127.0.0.1'
    '--port'
    '8000'
    '--reload'
)

& 'C:\Users\user\OneDrive\바탕 화면\한재광\회사SW\DT준전문가교육\DLAB\SW Project\halal_web\.venv\Scripts\python.exe' @PythonArgs

if ($LASTEXITCODE -ne 0) {
    Write-Host ''
    Write-Host "백엔드 종료 코드: $LASTEXITCODE" -ForegroundColor Red
    Read-Host 'Enter를 누르면 창이 닫힙니다'
}
