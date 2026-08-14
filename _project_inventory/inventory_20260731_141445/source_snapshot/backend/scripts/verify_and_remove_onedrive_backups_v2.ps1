param(
    [string]$ProjectRoot = "",
    [string]$DestinationRoot = "D:\halal_web_runtime",
    [switch]$DeleteBackups
)

$ErrorActionPreference = "Stop"

function Resolve-ProjectRoot {
    param([string]$Value)

    if ($Value) {
        $resolved = (Resolve-Path -LiteralPath $Value).Path
        if (-not (Test-Path (Join-Path $resolved "backend\app\main.py"))) {
            throw "지정한 경로가 halal_web 프로젝트 루트가 아닙니다: $resolved"
        }
        return $resolved
    }

    $current = (Get-Location).Path
    if (Test-Path (Join-Path $current "backend\app\main.py")) {
        return $current
    }

    $candidate = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    if (Test-Path (Join-Path $candidate "backend\app\main.py")) {
        return $candidate
    }

    throw "halal_web 프로젝트 루트를 찾지 못했습니다."
}

function Assert-Junction {
    param(
        [string]$LogicalPath,
        [string]$ExpectedTarget
    )

    if (-not (Test-Path -LiteralPath $LogicalPath)) {
        throw "논리 경로가 없습니다: $LogicalPath"
    }

    if (-not (Test-Path -LiteralPath $ExpectedTarget)) {
        throw "D 드라이브 대상 경로가 없습니다: $ExpectedTarget"
    }

    $item = Get-Item -LiteralPath $LogicalPath -Force
    if ($item.LinkType -ne "Junction" -or -not $item.Target) {
        throw "실제 Junction이 아닙니다: $LogicalPath"
    }

    $actual = (Resolve-Path -LiteralPath $item.Target).Path
    $expected = (Resolve-Path -LiteralPath $ExpectedTarget).Path

    if ($actual -ne $expected) {
        throw "Junction 대상 불일치: $LogicalPath -> $actual / 예상: $expected"
    }

    $testName = "_runtime_verify_$([guid]::NewGuid().ToString('N')).txt"
    $logicalTest = Join-Path $LogicalPath $testName
    $physicalTest = Join-Path $ExpectedTarget $testName

    Set-Content -LiteralPath $logicalTest -Value "runtime storage verify" -Encoding UTF8

    if (-not (Test-Path -LiteralPath $physicalTest)) {
        Remove-Item -LiteralPath $logicalTest -Force -ErrorAction SilentlyContinue
        throw "Junction 쓰기 검증 실패: $LogicalPath"
    }

    Remove-Item -LiteralPath $logicalTest -Force
    Write-Host "[OK] $LogicalPath -> $ExpectedTarget" -ForegroundColor Green
}

function Copy-FreshArchive {
    param(
        [string]$Source,
        [string]$Destination
    )

    # 이전 실행에서 남은 오래된 보관본이 같은 크기/시간으로 판단되어
    # Robocopy가 건너뛰는 문제를 방지하기 위해 매번 새로 만든다.
    if (Test-Path -LiteralPath $Destination) {
        Remove-Item -LiteralPath $Destination -Recurse -Force
    }

    New-Item -ItemType Directory -Path $Destination -Force | Out-Null

    & robocopy $Source $Destination /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /XJ /NP
    $code = $LASTEXITCODE

    if ($code -gt 7) {
        throw "Robocopy 실패: 종료코드 $code / $Source"
    }
}

function Verify-And-RepairArchive {
    param(
        [string]$Source,
        [string]$Destination
    )

    $sourceFiles = @(Get-ChildItem -LiteralPath $Source -File -Recurse -Force)
    $checked = 0
    $repaired = 0

    foreach ($sourceFile in $sourceFiles) {
        $relative = $sourceFile.FullName.Substring($Source.Length).TrimStart("\")
        $targetFile = Join-Path $Destination $relative

        if (-not (Test-Path -LiteralPath $targetFile)) {
            New-Item -ItemType Directory -Path (Split-Path -Parent $targetFile) -Force | Out-Null
            Copy-Item -LiteralPath $sourceFile.FullName -Destination $targetFile -Force
            $repaired += 1
        }

        $sourceHash = (Get-FileHash -LiteralPath $sourceFile.FullName -Algorithm SHA256).Hash
        $targetHash = (Get-FileHash -LiteralPath $targetFile -Algorithm SHA256).Hash

        if ($sourceHash -ne $targetHash) {
            # 파일 하나만 강제 재복사 후 다시 검증한다.
            Copy-Item -LiteralPath $sourceFile.FullName -Destination $targetFile -Force
            $repaired += 1

            $targetHash = (Get-FileHash -LiteralPath $targetFile -Algorithm SHA256).Hash
            if ($sourceHash -ne $targetHash) {
                throw "재복사 후에도 SHA-256 불일치: $relative"
            }
        }

        $checked += 1
        if ($checked % 100 -eq 0) {
            Write-Host "  검증 진행: $checked / $($sourceFiles.Count)"
        }
    }

    Write-Host "[OK] 보관본 검증 완료: $checked개 / 자동복구 $repaired개" -ForegroundColor Green
}

$ProjectRoot = Resolve-ProjectRoot -Value $ProjectRoot
$BackendRoot = Join-Path $ProjectRoot "backend"
$archiveRoot = Join-Path $DestinationRoot "_onedrive_backup_archive"
$runtimeNames = @("data", "output", "cache", "db")

Write-Host "=== HALAL OneDrive 백업 검증·삭제 V2 ===" -ForegroundColor Cyan

foreach ($name in $runtimeNames) {
    Assert-Junction `
        -LogicalPath (Join-Path $BackendRoot $name) `
        -ExpectedTarget (Join-Path $DestinationRoot $name)
}

$backups = @(
    Get-ChildItem -LiteralPath $BackendRoot -Directory -Force |
    Where-Object {
        $_.Name -match "^(data|output|cache|db)\.__onedrive_backup_\d{8}_\d{6}$"
    } |
    Sort-Object Name
)

if ($backups.Count -eq 0) {
    Write-Host "OK_NO_BACKUPS_FOUND" -ForegroundColor Green
    exit 0
}

New-Item -ItemType Directory -Path $archiveRoot -Force | Out-Null

foreach ($backup in $backups) {
    $archivePath = Join-Path $archiveRoot $backup.Name

    Write-Host ""
    Write-Host "[$($backup.Name)]" -ForegroundColor Magenta

    Copy-FreshArchive `
        -Source $backup.FullName `
        -Destination $archivePath

    Verify-And-RepairArchive `
        -Source $backup.FullName `
        -Destination $archivePath
}

Write-Host ""
Write-Host "OK_TO_DELETE_BACKUPS" -ForegroundColor Green
Write-Host "D 보관본: $archiveRoot" -ForegroundColor Green

if (-not $DeleteBackups) {
    Write-Host '삭제 실행: & ".\backend\scripts\verify_and_remove_onedrive_backups_v2.ps1" -DeleteBackups'
    exit 0
}

$answer = Read-Host "OneDrive 임시 백업을 삭제하려면 DELETE 입력"
if ($answer -ne "DELETE") {
    throw "사용자가 삭제를 취소했습니다."
}

foreach ($backup in $backups) {
    Remove-Item -LiteralPath $backup.FullName -Recurse -Force

    if (Test-Path -LiteralPath $backup.FullName) {
        throw "삭제 실패: $($backup.FullName)"
    }

    Write-Host "삭제 완료: $($backup.Name)" -ForegroundColor Green
}

Write-Host ""
Write-Host "BACKUPS_DELETED_OK" -ForegroundColor Green
Write-Host "D 드라이브 보관본은 유지됩니다: $archiveRoot"
