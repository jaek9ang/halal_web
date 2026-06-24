param(
    [Parameter(Mandatory = $true)]
    [string]$Message
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if (-not (Test-Path '.git')) {
    throw 'Git 저장소가 아닙니다. 먼저 .\scripts\init_local_git.ps1을 실행하세요.'
}

git add -A
$changes = git status --porcelain
if (-not $changes) {
    Write-Host '커밋할 변경사항이 없습니다.' -ForegroundColor Yellow
    exit 0
}

git commit -m $Message
Write-Host ''
git status --short
Write-Host '로컬 체크포인트 저장 완료' -ForegroundColor Green
