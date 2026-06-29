param(
    [string]$ProjectRoot = "",
    [string]$DestinationRoot = "D:\halal_web_runtime",
    [switch]$Force
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

    # 이 파일이 backend\scripts 안에 있을 때 프로젝트 루트는 두 단계 위
    $scriptRoot = $PSScriptRoot
    $candidate = Split-Path -Parent (Split-Path -Parent $scriptRoot)
    if (Test-Path (Join-Path $candidate "backend\app\main.py")) {
        return $candidate
    }

    throw "halal_web 프로젝트 루트를 찾지 못했습니다. -ProjectRoot 경로를 지정하세요."
}

function Get-TrueJunctionInfo {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return [PSCustomObject]@{
            IsJunction = $false
            Target = $null
        }
    }

    $item = Get-Item -LiteralPath $Path -Force

    # OneDrive 폴더도 ReparsePoint 속성을 가질 수 있으므로
    # Attributes가 아니라 LinkType/Target으로 실제 Junction만 판정한다.
    $linkType = $item.LinkType
    $target = $item.Target

    $isJunction = (
        $linkType -eq "Junction" -and
        $null -ne $target -and
        "$target".Trim().Length -gt 0
    )

    return [PSCustomObject]@{
        IsJunction = $isJunction
        Target = $target
    }
}

function Copy-And-VerifyDirectory {
    param(
        [string]$Source,
        [string]$Destination
    )

    New-Item -ItemType Directory -Path $Destination -Force | Out-Null

    Write-Host "복사 중: $Source -> $Destination" -ForegroundColor Cyan
    & robocopy $Source $Destination /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /XJ /FFT /NP
    $robocopyExit = $LASTEXITCODE

    if ($robocopyExit -gt 7) {
        throw "Robocopy 실패: 종료코드 $robocopyExit / $Source"
    }

    $sourceFiles = Get-ChildItem -LiteralPath $Source -File -Recurse -Force -ErrorAction Stop
    $problems = New-Object System.Collections.Generic.List[string]

    foreach ($sourceFile in $sourceFiles) {
        $relative = $sourceFile.FullName.Substring($Source.Length).TrimStart("\")
        $targetFile = Join-Path $Destination $relative

        if (-not (Test-Path -LiteralPath $targetFile)) {
            $problems.Add("누락: $relative")
            continue
        }

        $targetItem = Get-Item -LiteralPath $targetFile -Force
        if ($targetItem.Length -ne $sourceFile.Length) {
            $problems.Add("크기 불일치: $relative")
        }
    }

    if ($problems.Count -gt 0) {
        $preview = ($problems | Select-Object -First 20) -join [Environment]::NewLine
        throw "복사 검증 실패:`n$preview"
    }

    Write-Host "복사 검증 완료: 파일 $($sourceFiles.Count)개" -ForegroundColor Green
}

function New-SafeJunction {
    param(
        [string]$LinkPath,
        [string]$TargetPath
    )

    New-Item -ItemType Junction -Path $LinkPath -Target $TargetPath | Out-Null

    $info = Get-TrueJunctionInfo -Path $LinkPath
    if (-not $info.IsJunction) {
        throw "정션 생성 확인 실패: $LinkPath"
    }

    $resolvedTarget = (Resolve-Path -LiteralPath $TargetPath).Path
    $actualTarget = (Resolve-Path -LiteralPath $info.Target).Path

    if ($resolvedTarget -ne $actualTarget) {
        throw "정션 대상 불일치: $LinkPath -> $actualTarget (예상: $resolvedTarget)"
    }

    $testDir = Join-Path $LinkPath "_junction_write_test"
    $testFile = Join-Path $testDir "write_test.txt"

    New-Item -ItemType Directory -Path $testDir -Force | Out-Null
    Set-Content -LiteralPath $testFile -Value "halal runtime junction test" -Encoding UTF8

    $physicalTestFile = Join-Path $TargetPath "_junction_write_test\write_test.txt"
    if (-not (Test-Path -LiteralPath $physicalTestFile)) {
        throw "정션 쓰기 검증 실패: $LinkPath -> $TargetPath"
    }

    Remove-Item -LiteralPath $testDir -Recurse -Force
}

$ProjectRoot = Resolve-ProjectRoot -Value $ProjectRoot
$BackendRoot = Join-Path $ProjectRoot "backend"
$driveRoot = [System.IO.Path]::GetPathRoot($DestinationRoot)

if (-not (Test-Path -LiteralPath $driveRoot)) {
    throw "대상 드라이브를 찾지 못했습니다: $driveRoot"
}

Write-Host "=== HALAL 런타임 데이터 D 드라이브 이전 V2 ===" -ForegroundColor Green
Write-Host "프로젝트: $ProjectRoot"
Write-Host "대상 경로: $DestinationRoot"
Write-Host ""
Write-Host "백엔드(Uvicorn), OCR, 메일 동기화 작업이 모두 종료되어 있어야 합니다." -ForegroundColor Yellow

if (-not $Force) {
    $answer = Read-Host "계속하려면 YES 입력"
    if ($answer -ne "YES") {
        throw "사용자가 작업을 취소했습니다."
    }
}

New-Item -ItemType Directory -Path $DestinationRoot -Force | Out-Null

$runtimeFolders = @("data", "output", "cache", "db")
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$manifestRows = @()

foreach ($name in $runtimeFolders) {
    $source = Join-Path $BackendRoot $name
    $destination = Join-Path $DestinationRoot $name

    Write-Host ""
    Write-Host "[$name]" -ForegroundColor Magenta

    $junctionInfo = Get-TrueJunctionInfo -Path $source

    if ($junctionInfo.IsJunction) {
        Write-Host "이미 실제 정션입니다: $source -> $($junctionInfo.Target)" -ForegroundColor Yellow

        $manifestRows += [PSCustomObject]@{
            name = $name
            source = $source
            destination = $destination
            backup = ""
            status = "ALREADY_JUNCTION"
        }
        continue
    }

    # 이전 V1은 OneDrive ReparsePoint를 Junction으로 오인했지만,
    # V2에서는 일반 폴더로 보고 실제 복사를 수행한다.
    $backup = ""

    if (Test-Path -LiteralPath $source) {
        Copy-And-VerifyDirectory -Source $source -Destination $destination

        $backup = "$source.__onedrive_backup_$stamp"

        if (Test-Path -LiteralPath $backup) {
            throw "동일한 백업 경로가 이미 존재합니다: $backup"
        }

        Rename-Item -LiteralPath $source -NewName (Split-Path -Leaf $backup)

        try {
            New-SafeJunction -LinkPath $source -TargetPath $destination
        }
        catch {
            if (Test-Path -LiteralPath $source) {
                Remove-Item -LiteralPath $source -Force
            }

            if (Test-Path -LiteralPath $backup) {
                Rename-Item -LiteralPath $backup -NewName $name
            }

            throw
        }

        Write-Host "완료: $source -> $destination" -ForegroundColor Green
        Write-Host "임시 백업: $backup" -ForegroundColor DarkYellow
    }
    else {
        New-Item -ItemType Directory -Path $destination -Force | Out-Null
        New-SafeJunction -LinkPath $source -TargetPath $destination
        Write-Host "빈 정션 생성 완료: $source -> $destination" -ForegroundColor Green
    }

    $manifestRows += [PSCustomObject]@{
        name = $name
        source = $source
        destination = $destination
        backup = $backup
        status = "MIGRATED"
    }
}

$manifest = [PSCustomObject]@{
    migrated_at = (Get-Date).ToString("s")
    project_root = $ProjectRoot
    destination_root = $DestinationRoot
    folders = $manifestRows
}

$manifestPath = Join-Path $DestinationRoot "migration_manifest_$stamp.json"
$manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

Write-Host ""
Write-Host "=== 이전 완료 ===" -ForegroundColor Green
Write-Host "Manifest: $manifestPath"
Write-Host ""
Write-Host "다음 작업:"
Write-Host '1. & ".\backend\scripts\verify_runtime_on_d_v2.ps1"'
Write-Host "2. 백엔드 실행 및 메일/OCR 1건 테스트"
Write-Host '3. 정상 확인 후 & ".\backend\scripts\remove_onedrive_runtime_backups.ps1" -ConfirmDelete'
