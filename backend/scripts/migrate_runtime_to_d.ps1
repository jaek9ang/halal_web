param(
    [string]$ProjectRoot = "",
    [string]$DestinationRoot = "D:\halal_web_runtime",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Resolve-ProjectRoot {
    param([string]$Value)

    if ($Value) {
        return (Resolve-Path -LiteralPath $Value).Path
    }

    $current = (Get-Location).Path
    if (Test-Path (Join-Path $current "backend\app\main.py")) {
        return $current
    }

    $scriptParent = Split-Path -Parent $PSScriptRoot
    if (Test-Path (Join-Path $scriptParent "backend\app\main.py")) {
        return $scriptParent
    }

    throw "halal_web 프로젝트 루트를 찾지 못했습니다. -ProjectRoot 경로를 지정하세요."
}

function Test-IsJunction {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return $false
    }

    $item = Get-Item -LiteralPath $Path -Force
    return [bool]($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)
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

    $problems = New-Object System.Collections.Generic.List[string]

    Get-ChildItem -LiteralPath $Source -File -Recurse -Force | ForEach-Object {
        $relative = $_.FullName.Substring($Source.Length).TrimStart("\")
        $target = Join-Path $Destination $relative

        if (-not (Test-Path -LiteralPath $target)) {
            $problems.Add("누락: $relative")
            return
        }

        $targetItem = Get-Item -LiteralPath $target -Force
        if ($targetItem.Length -ne $_.Length) {
            $problems.Add("크기 불일치: $relative")
        }
    }

    if ($problems.Count -gt 0) {
        $preview = ($problems | Select-Object -First 20) -join [Environment]::NewLine
        throw "복사 검증 실패:`n$preview"
    }
}

function New-SafeJunction {
    param(
        [string]$LinkPath,
        [string]$TargetPath
    )

    New-Item -ItemType Junction -Path $LinkPath -Target $TargetPath | Out-Null

    if (-not (Test-IsJunction -Path $LinkPath)) {
        throw "정션 생성 확인 실패: $LinkPath"
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

Write-Host "=== HALAL 런타임 데이터 D 드라이브 이전 ===" -ForegroundColor Green
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

# data: 메일 다운로드, 수동/테스트 OCR, OCR export, 규칙 및 파일링 이력
# output: 수신 인증서, OCR 산출물, LHLN 출력
# cache: PMF 캐시
# db: 메일 본문/첨부 메타, OCR raw_text/result_json 등이 있는 SQLite DB
$runtimeFolders = @("data", "output", "cache", "db")
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$manifestRows = @()

foreach ($name in $runtimeFolders) {
    $source = Join-Path $BackendRoot $name
    $destination = Join-Path $DestinationRoot $name

    Write-Host ""
    Write-Host "[$name]" -ForegroundColor Magenta

    if (Test-IsJunction -Path $source) {
        $item = Get-Item -LiteralPath $source -Force
        Write-Host "이미 정션입니다. 건너뜁니다: $source -> $($item.Target)" -ForegroundColor Yellow

        $manifestRows += [PSCustomObject]@{
            name = $name
            source = $source
            destination = $destination
            backup = ""
            status = "ALREADY_JUNCTION"
        }
        continue
    }

    $backup = ""

    if (Test-Path -LiteralPath $source) {
        Copy-And-VerifyDirectory -Source $source -Destination $destination

        $backup = "$source.__onedrive_backup_$stamp"
        Rename-Item -LiteralPath $source -NewName (Split-Path -Leaf $backup)

        try {
            New-SafeJunction -LinkPath $source -TargetPath $destination
        }
        catch {
            if (Test-Path -LiteralPath $source) {
                Remove-Item -LiteralPath $source -Force
            }
            Rename-Item -LiteralPath $backup -NewName $name
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
Write-Host "1. .\scripts\verify_runtime_on_d.ps1"
Write-Host "2. 백엔드 실행 및 메일/OCR 1건 테스트"
Write-Host "3. 정상 확인 후 .\scripts\remove_onedrive_runtime_backups.ps1 -ConfirmDelete"
