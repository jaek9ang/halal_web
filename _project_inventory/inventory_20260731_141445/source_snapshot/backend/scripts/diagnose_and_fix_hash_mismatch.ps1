param(
    [string]$ProjectRoot = "",
    [string]$DestinationRoot = "D:\halal_web_runtime",
    [int]$MaxRetries = 5,
    [int]$StableWaitSeconds = 3
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

function Get-FileState {
    param([string]$Path)

    $item = Get-Item -LiteralPath $Path -Force
    $hash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash

    return [PSCustomObject]@{
        Path = $Path
        Length = $item.Length
        LastWriteTimeUtc = $item.LastWriteTimeUtc
        Attributes = "$($item.Attributes)"
        LinkType = "$($item.LinkType)"
        Hash = $hash
    }
}

function Wait-ForStableSource {
    param(
        [string]$Path,
        [int]$WaitSeconds
    )

    # OneDrive Files On-Demand 파일이면 로컬 고정/수화 요청.
    try {
        & attrib.exe +P -U $Path 2>$null | Out-Null
    }
    catch {
        # 일반 파일이면 attrib 요청이 필요 없으므로 계속 진행한다.
    }

    for ($i = 1; $i -le 6; $i++) {
        $first = Get-FileState -Path $Path
        Start-Sleep -Seconds $WaitSeconds
        $second = Get-FileState -Path $Path

        $stable = (
            $first.Hash -eq $second.Hash -and
            $first.Length -eq $second.Length -and
            $first.LastWriteTimeUtc -eq $second.LastWriteTimeUtc
        )

        Write-Host (
            "  안정성 확인 {0}/6: {1}" -f
            $i,
            $(if ($stable) { "STABLE" } else { "CHANGING" })
        )

        if ($stable) {
            return $second
        }
    }

    return $null
}

function Copy-AtomicallyAndVerify {
    param(
        [string]$Source,
        [string]$Destination,
        [int]$Retries
    )

    $destinationDir = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Path $destinationDir -Force | Out-Null

    for ($attempt = 1; $attempt -le $Retries; $attempt++) {
        Write-Host "  복구 복사 시도 $attempt/$Retries"

        $before = Get-FileState -Path $Source
        $temp = "$Destination.__repair_$([guid]::NewGuid().ToString('N')).tmp"

        try {
            # OneDrive 셸 복사 대신 .NET 파일 스트림을 사용해 실제 바이트를 읽어 쓴다.
            $sourceStream = [System.IO.File]::Open(
                $Source,
                [System.IO.FileMode]::Open,
                [System.IO.FileAccess]::Read,
                [System.IO.FileShare]::Read
            )

            try {
                $targetStream = [System.IO.File]::Open(
                    $temp,
                    [System.IO.FileMode]::Create,
                    [System.IO.FileAccess]::Write,
                    [System.IO.FileShare]::None
                )

                try {
                    $sourceStream.CopyTo($targetStream, 1024 * 1024)
                    $targetStream.Flush($true)
                }
                finally {
                    $targetStream.Dispose()
                }
            }
            finally {
                $sourceStream.Dispose()
            }

            $tempState = Get-FileState -Path $temp
            $after = Get-FileState -Path $Source

            $sourceWasStable = (
                $before.Hash -eq $after.Hash -and
                $before.Length -eq $after.Length -and
                $before.LastWriteTimeUtc -eq $after.LastWriteTimeUtc
            )

            $copyMatches = (
                $before.Hash -eq $tempState.Hash -and
                $before.Length -eq $tempState.Length
            )

            if ($sourceWasStable -and $copyMatches) {
                Move-Item -LiteralPath $temp -Destination $Destination -Force
                $final = Get-FileState -Path $Destination

                if ($final.Hash -ne $before.Hash) {
                    throw "최종 이동 후 SHA-256이 다시 달라졌습니다."
                }

                return [PSCustomObject]@{
                    Ok = $true
                    Hash = $final.Hash
                    Length = $final.Length
                    Attempts = $attempt
                }
            }

            Write-Host "  복사 중 원본 변경 또는 바이트 불일치 감지" -ForegroundColor Yellow
        }
        finally {
            if (Test-Path -LiteralPath $temp) {
                Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue
            }
        }

        Start-Sleep -Seconds 2
    }

    return [PSCustomObject]@{
        Ok = $false
        Hash = ""
        Length = 0
        Attempts = $Retries
    }
}

$ProjectRoot = Resolve-ProjectRoot -Value $ProjectRoot
$BackendRoot = Join-Path $ProjectRoot "backend"
$ArchiveRoot = Join-Path $DestinationRoot "_onedrive_backup_archive"

Write-Host "=== HALAL SHA-256 불일치 진단·복구 ===" -ForegroundColor Cyan
Write-Host "프로젝트: $ProjectRoot"
Write-Host "보관본: $ArchiveRoot"
Write-Host ""

$backups = @(
    Get-ChildItem -LiteralPath $BackendRoot -Directory -Force |
    Where-Object {
        $_.Name -match "^(data|output|cache|db)\.__onedrive_backup_\d{8}_\d{6}$"
    } |
    Sort-Object Name
)

if ($backups.Count -eq 0) {
    Write-Host "NO_ONEDRIVE_BACKUPS_FOUND" -ForegroundColor Yellow
    exit 0
}

$mismatches = New-Object System.Collections.Generic.List[object]

foreach ($backup in $backups) {
    $archive = Join-Path $ArchiveRoot $backup.Name

    if (-not (Test-Path -LiteralPath $archive)) {
        New-Item -ItemType Directory -Path $archive -Force | Out-Null
    }

    $sourceFiles = @(Get-ChildItem -LiteralPath $backup.FullName -File -Recurse -Force)

    foreach ($sourceFile in $sourceFiles) {
        $relative = $sourceFile.FullName.Substring($backup.FullName.Length).TrimStart("\")
        $targetFile = Join-Path $archive $relative

        $isMismatch = $false

        if (-not (Test-Path -LiteralPath $targetFile)) {
            $isMismatch = $true
        }
        else {
            $sourceHash = (Get-FileHash -LiteralPath $sourceFile.FullName -Algorithm SHA256).Hash
            $targetHash = (Get-FileHash -LiteralPath $targetFile -Algorithm SHA256).Hash
            $isMismatch = $sourceHash -ne $targetHash
        }

        if ($isMismatch) {
            $runtimeName = $backup.Name.Split(".")[0]
            $liveRuntimeFile = Join-Path (Join-Path $DestinationRoot $runtimeName) $relative

            $mismatches.Add([PSCustomObject]@{
                BackupName = $backup.Name
                RelativePath = $relative
                Source = $sourceFile.FullName
                Archive = $targetFile
                LiveRuntime = $liveRuntimeFile
            })
        }
    }
}

if ($mismatches.Count -eq 0) {
    Write-Host "ALL_HASHES_ALREADY_OK" -ForegroundColor Green
    exit 0
}

Write-Host "불일치 파일: $($mismatches.Count)개" -ForegroundColor Yellow

$failures = New-Object System.Collections.Generic.List[object]

foreach ($item in $mismatches) {
    Write-Host ""
    Write-Host "대상: $($item.RelativePath)" -ForegroundColor Magenta

    $sourceState = Get-FileState -Path $item.Source
    Write-Host "  원본 속성: $($sourceState.Attributes)"
    Write-Host "  원본 크기: $($sourceState.Length)"
    Write-Host "  원본 SHA : $($sourceState.Hash)"

    if (Test-Path -LiteralPath $item.Archive) {
        $archiveState = Get-FileState -Path $item.Archive
        Write-Host "  보관 SHA : $($archiveState.Hash)"
    }
    else {
        Write-Host "  보관 파일: 없음"
    }

    if (Test-Path -LiteralPath $item.LiveRuntime) {
        $liveState = Get-FileState -Path $item.LiveRuntime
        Write-Host "  현재 D 런타임 SHA: $($liveState.Hash)"
    }

    $stableState = Wait-ForStableSource `
        -Path $item.Source `
        -WaitSeconds $StableWaitSeconds

    if (-not $stableState) {
        Write-Host "SOURCE_NOT_STABLE_PAUSE_ONEDRIVE" -ForegroundColor Red
        $failures.Add([PSCustomObject]@{
            RelativePath = $item.RelativePath
            Reason = "SOURCE_NOT_STABLE"
        })
        continue
    }

    $result = Copy-AtomicallyAndVerify `
        -Source $item.Source `
        -Destination $item.Archive `
        -Retries $MaxRetries

    if ($result.Ok) {
        Write-Host "FIXED_OK" -ForegroundColor Green
        Write-Host "  SHA-256: $($result.Hash)"
        Write-Host "  시도 횟수: $($result.Attempts)"
    }
    else {
        Write-Host "REPAIR_FAILED" -ForegroundColor Red
        $failures.Add([PSCustomObject]@{
            RelativePath = $item.RelativePath
            Reason = "COPY_VERIFY_FAILED"
        })
    }
}

Write-Host ""

if ($failures.Count -gt 0) {
    Write-Host "HASH_REPAIR_INCOMPLETE" -ForegroundColor Red
    $failures | Format-Table -AutoSize
    Write-Host ""
    Write-Host "OneDrive 동기화를 잠시 일시 중지하고 이 스크립트를 다시 실행하세요." -ForegroundColor Yellow
    exit 1
}

# 최종 전체 재검증
foreach ($backup in $backups) {
    $archive = Join-Path $ArchiveRoot $backup.Name
    $sourceFiles = @(Get-ChildItem -LiteralPath $backup.FullName -File -Recurse -Force)

    foreach ($sourceFile in $sourceFiles) {
        $relative = $sourceFile.FullName.Substring($backup.FullName.Length).TrimStart("\")
        $targetFile = Join-Path $archive $relative

        if (-not (Test-Path -LiteralPath $targetFile)) {
            throw "최종 검증 파일 누락: $relative"
        }

        $sourceHash = (Get-FileHash -LiteralPath $sourceFile.FullName -Algorithm SHA256).Hash
        $targetHash = (Get-FileHash -LiteralPath $targetFile -Algorithm SHA256).Hash

        if ($sourceHash -ne $targetHash) {
            throw "최종 검증 SHA-256 불일치: $relative"
        }
    }
}

Write-Host "ALL_HASH_MISMATCHES_FIXED" -ForegroundColor Green
Write-Host "이제 백업 삭제 V2를 실행할 수 있습니다." -ForegroundColor Green
