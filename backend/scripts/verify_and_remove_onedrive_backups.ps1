param(
    [string]$ProjectRoot = "",
    [string]$DestinationRoot = "D:\halal_web_runtime",
    [switch]$DeleteBackups,
    [switch]$FastVerify
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

function Get-JunctionTarget {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }

    $item = Get-Item -LiteralPath $Path -Force
    if ($item.LinkType -ne "Junction" -or $null -eq $item.Target) {
        return $null
    }

    $target = "$($item.Target)".Trim()
    if (-not $target) {
        return $null
    }

    return $target
}

function Test-LogicalRuntimePath {
    param(
        [string]$LogicalPath,
        [string]$ExpectedPhysicalPath
    )

    $target = Get-JunctionTarget -Path $LogicalPath
    if (-not $target) {
        throw "실제 Junction이 아닙니다: $LogicalPath"
    }

    if (-not (Test-Path -LiteralPath $ExpectedPhysicalPath)) {
        throw "D 드라이브 대상 폴더가 없습니다: $ExpectedPhysicalPath"
    }

    $actual = (Resolve-Path -LiteralPath $target).Path
    $expected = (Resolve-Path -LiteralPath $ExpectedPhysicalPath).Path

    if ($actual -ne $expected) {
        throw "Junction 대상 불일치: $LogicalPath -> $actual / 예상: $expected"
    }

    $testName = "_cleanup_verify_$([guid]::NewGuid().ToString('N')).txt"
    $logicalTest = Join-Path $LogicalPath $testName
    $physicalTest = Join-Path $ExpectedPhysicalPath $testName

    Set-Content -LiteralPath $logicalTest -Value "runtime cleanup verification" -Encoding UTF8

    if (-not (Test-Path -LiteralPath $physicalTest)) {
        Remove-Item -LiteralPath $logicalTest -Force -ErrorAction SilentlyContinue
        throw "Junction 쓰기 검증 실패: $LogicalPath"
    }

    Remove-Item -LiteralPath $logicalTest -Force
    Write-Host "[OK] $LogicalPath -> $ExpectedPhysicalPath" -ForegroundColor Green
}

function Copy-BackupToDArchive {
    param(
        [string]$BackupPath,
        [string]$ArchivePath
    )

    New-Item -ItemType Directory -Path $ArchivePath -Force | Out-Null

    Write-Host "D 드라이브 안전보관 복사 중..." -ForegroundColor Cyan
    Write-Host "  원본: $BackupPath"
    Write-Host "  보관: $ArchivePath"

    & robocopy $BackupPath $ArchivePath /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /XJ /FFT /NP
    $code = $LASTEXITCODE

    if ($code -gt 7) {
        throw "Robocopy 실패: 종료코드 $code / $BackupPath"
    }
}

function Compare-BackupAndArchive {
    param(
        [string]$BackupPath,
        [string]$ArchivePath,
        [bool]$UseHash
    )

    $sourceFiles = @(Get-ChildItem -LiteralPath $BackupPath -File -Recurse -Force)
    $checked = 0

    foreach ($sourceFile in $sourceFiles) {
        $relative = $sourceFile.FullName.Substring($BackupPath.Length).TrimStart("\")
        $archiveFile = Join-Path $ArchivePath $relative

        if (-not (Test-Path -LiteralPath $archiveFile)) {
            throw "보관본 파일 누락: $relative"
        }

        $archiveItem = Get-Item -LiteralPath $archiveFile -Force
        if ($sourceFile.Length -ne $archiveItem.Length) {
            throw "보관본 파일 크기 불일치: $relative"
        }

        if ($UseHash) {
            $sourceHash = (Get-FileHash -LiteralPath $sourceFile.FullName -Algorithm SHA256).Hash
            $archiveHash = (Get-FileHash -LiteralPath $archiveFile -Algorithm SHA256).Hash

            if ($sourceHash -ne $archiveHash) {
                throw "보관본 SHA-256 불일치: $relative"
            }
        }

        $checked += 1
        if ($checked % 100 -eq 0) {
            Write-Host "  검증 진행: $checked / $($sourceFiles.Count)"
        }
    }

    Write-Host "[OK] 보관본 검증 완료: 파일 $checked개" -ForegroundColor Green
}

$ProjectRoot = Resolve-ProjectRoot -Value $ProjectRoot
$BackendRoot = Join-Path $ProjectRoot "backend"
$runtimeNames = @("data", "output", "cache", "db")
$archiveRoot = Join-Path $DestinationRoot "_onedrive_backup_archive"

Write-Host "=== HALAL 런타임 백업 안전 삭제 검사 ===" -ForegroundColor Cyan
Write-Host "프로젝트: $ProjectRoot"
Write-Host "D 저장소: $DestinationRoot"
Write-Host ""

foreach ($name in $runtimeNames) {
    Test-LogicalRuntimePath `
        -LogicalPath (Join-Path $BackendRoot $name) `
        -ExpectedPhysicalPath (Join-Path $DestinationRoot $name)
}

$backups = @(
    Get-ChildItem -LiteralPath $BackendRoot -Directory -Force |
    Where-Object {
        $_.Name -match "^(data|output|cache|db)\.__onedrive_backup_\d{8}_\d{6}$"
    } |
    Sort-Object Name
)

Write-Host ""

if ($backups.Count -eq 0) {
    Write-Host "OK_NO_BACKUPS_FOUND" -ForegroundColor Green
    exit 0
}

Write-Host "발견한 OneDrive 임시 백업: $($backups.Count)개" -ForegroundColor Yellow
$backups | Select-Object Name, FullName, LastWriteTime | Format-Table -AutoSize

New-Item -ItemType Directory -Path $archiveRoot -Force | Out-Null
$useHash = -not $FastVerify

foreach ($backup in $backups) {
    $archivePath = Join-Path $archiveRoot $backup.Name
    Copy-BackupToDArchive -BackupPath $backup.FullName -ArchivePath $archivePath
    Compare-BackupAndArchive `
        -BackupPath $backup.FullName `
        -ArchivePath $archivePath `
        -UseHash $useHash
}

Write-Host ""
Write-Host "OK_TO_DELETE_BACKUPS" -ForegroundColor Green
Write-Host "D 드라이브 안전보관 위치: $archiveRoot" -ForegroundColor Green

if (-not $DeleteBackups) {
    Write-Host ""
    Write-Host "검증만 완료했습니다. 실제 삭제하려면 아래 명령을 실행하세요." -ForegroundColor Yellow
    Write-Host '& ".\backend\scripts\verify_and_remove_onedrive_backups.ps1" -DeleteBackups'
    exit 0
}

Write-Host ""
Write-Host "주의: OneDrive 임시 백업을 삭제합니다." -ForegroundColor Yellow
$answer = Read-Host "삭제하려면 DELETE 입력"

if ($answer -ne "DELETE") {
    throw "사용자가 삭제를 취소했습니다."
}

foreach ($backup in $backups) {
    Remove-Item -LiteralPath $backup.FullName -Recurse -Force

    if (Test-Path -LiteralPath $backup.FullName) {
        throw "백업 삭제 실패: $($backup.FullName)"
    }

    Write-Host "삭제 완료: $($backup.FullName)" -ForegroundColor Green
}

$remaining = @(
    Get-ChildItem -LiteralPath $BackendRoot -Directory -Force |
    Where-Object {
        $_.Name -match "^(data|output|cache|db)\.__onedrive_backup_\d{8}_\d{6}$"
    }
)

if ($remaining.Count -gt 0) {
    throw "일부 OneDrive 백업이 남았습니다."
}

Write-Host ""
Write-Host "BACKUPS_DELETED_OK" -ForegroundColor Green
Write-Host "백업 보관본: $archiveRoot"
