param(
    [string]$UserName = '',
    [string]$UserEmail = ''
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Git이 설치되어 있지 않습니다.'
}

if (-not (Test-Path '.git')) {
    git init -b main
}

git config core.quotepath false
git config core.longpaths true
git config i18n.commitEncoding utf-8
git config i18n.logOutputEncoding utf-8

$currentName = git config user.name
$currentEmail = git config user.email

if ($UserName) {
    git config user.name $UserName
} elseif (-not $currentName) {
    $UserName = Read-Host 'Git 변경이력에 표시할 이름'
    git config user.name $UserName
}

if ($UserEmail) {
    git config user.email $UserEmail
} elseif (-not $currentEmail) {
    $UserEmail = Read-Host 'Git 변경이력용 이메일(외부 전송되지 않음)'
    git config user.email $UserEmail
}

$remotes = git remote
if ($remotes) {
    Write-Warning "원격 저장소가 설정되어 있습니다: $remotes"
} else {
    Write-Host '원격 저장소 없음: 로컬 변경이력만 저장합니다.' -ForegroundColor Green
}

git add .
$hasCommit = git rev-parse --verify HEAD 2>$null
if ($LASTEXITCODE -ne 0) {
    git commit -m 'chore: initialize local project history'
} else {
    Write-Host '기존 Git 이력이 있어 초기 커밋은 생략합니다.' -ForegroundColor Yellow
}

Write-Host ''
git status --short
Write-Host '로컬 Git 설정 완료' -ForegroundColor Green
