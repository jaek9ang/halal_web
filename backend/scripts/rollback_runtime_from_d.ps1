param(
    [string]$ProjectRoot = "",
    [string]$DestinationRoot = "D:\halal_web_runtime",
    [switch]$ConfirmRollback
)

$ErrorActionPreference = "Stop"

if (-not $ConfirmRollback) {
    throw "안전상 -ConfirmRollback 옵션이 필요합니다."
}

if (-not $ProjectRoot) {
    $ProjectRoot = (Get-Location).Path
}

$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$BackendRoot = Join-Path $ProjectRoot "backend"
$runtimeFolders = @("data", "output", "cache", "db")

Write-Host "백엔드와 관련 Python 프로세스를 모두 종료해야 합니다." -ForegroundColor Yellow
$answer = Read-Host "D 드라이브 내용을 OneDrive 프로젝트로 다시 복사하려면 ROLLBACK 입력"
if ($answer -ne "ROLLBACK") {
    throw "사용자가 롤백을 취소했습니다."
}

foreach ($name in $runtimeFolders) {
    $logical = Join-Path $BackendRoot $name
    $physical = Join-Path $DestinationRoot $name

    if (Test-Path -LiteralPath $logical) {
        $item = Get-Item -LiteralPath $logical -Force
        $isLink = [bool]($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)

        if ($isLink) {
            Remove-Item -LiteralPath $logical -Force
        }
        else {
            throw "정션이 아닌 실제 폴더가 존재합니다: $logical"
        }
    }

    New-Item -ItemType Directory -Path $logical -Force | Out-Null

    if (Test-Path -LiteralPath $physical) {
        & robocopy $physical $logical /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /XJ /FFT /NP
        if ($LASTEXITCODE -gt 7) {
            throw "롤백 복사 실패: $name / 종료코드 $LASTEXITCODE"
        }
    }

    Write-Host "복원 완료: $logical" -ForegroundColor Green
}

Write-Host "롤백 완료. D 드라이브 원본은 안전을 위해 삭제하지 않았습니다." -ForegroundColor Green
