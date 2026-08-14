param(
    [switch]$Recreate,
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvDir = Join-Path $ProjectRoot ".venv"
$Requirements = Join-Path $ProjectRoot "backend\requirements.txt"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"

Set-Location $ProjectRoot

Write-Host "=== Halal Web .venv setup ===" -ForegroundColor Cyan

function Test-PythonInterpreter {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Executable
    )

    if (-not (Test-Path $Executable)) {
        return $null
    }

    try {
        $result = & $Executable -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}|{sys.executable}')" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $result) {
            return $null
        }

        $parts = "$result".Trim().Split("|", 2)
        if ($parts.Count -ne 2) {
            return $null
        }

        $version = [version]$parts[0]

        # 현재 프로젝트는 Python 3.10~3.12를 지원 대상으로 둔다.
        if ($version.Major -ne 3 -or $version.Minor -lt 10 -or $version.Minor -gt 12) {
            return $null
        }

        return [PSCustomObject]@{
            Version = $version
            Path = $parts[1]
        }
    }
    catch {
        return $null
    }
}

function Find-CompatiblePython {
    param(
        [string]$ExplicitPath = ""
    )

    $candidates = New-Object System.Collections.Generic.List[string]

    if ($ExplicitPath) {
        $candidates.Add($ExplicitPath)
    }

    # Python Launcher가 있으면 실제 Python 실행 경로를 얻는다.
    $pyCommand = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCommand) {
        foreach ($versionTag in @("3.12", "3.11", "3.10")) {
            try {
                $resolved = & $pyCommand.Source "-$versionTag" -c "import sys; print(sys.executable)" 2>$null
                if ($LASTEXITCODE -eq 0 -and $resolved) {
                    $candidates.Add("$resolved".Trim())
                }
            }
            catch {
                # 다음 후보를 확인한다.
            }
        }
    }

    # 일반적인 Windows 독립 설치 경로.
    foreach ($path in @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
        "C:\Program Files\Python312\python.exe",
        "C:\Program Files\Python311\python.exe",
        "C:\Program Files\Python310\python.exe"
    )) {
        $candidates.Add($path)
    }

    # PATH의 python/python3도 확인하되 WindowsApps 실행 별칭은 제외한다.
    foreach ($commandName in @("python", "python3")) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue
        if ($command -and $command.Source -notmatch "\\WindowsApps\\") {
            $candidates.Add($command.Source)
        }
    }

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        $tested = Test-PythonInterpreter -Executable $candidate
        if ($tested) {
            return $tested
        }
    }

    return $null
}

if ($env:CONDA_PREFIX) {
    Write-Host "현재 Conda 환경이 활성화되어 있습니다: $env:CONDA_PREFIX" -ForegroundColor Yellow
    Write-Host "새 .venv는 Conda 환경과 별도로 생성합니다." -ForegroundColor Yellow
}

if (-not (Test-Path $Requirements)) {
    throw "requirements.txt를 찾지 못했습니다: $Requirements"
}

if ($Recreate -and (Test-Path $VenvDir)) {
    Write-Host "기존 .venv 삭제 중..." -ForegroundColor Yellow
    Remove-Item $VenvDir -Recurse -Force
}

if (-not (Test-Path $PythonExe)) {
    $basePython = Find-CompatiblePython -ExplicitPath $PythonPath

    if (-not $basePython) {
        throw @"
호환 가능한 독립 Python 3.10~3.12를 찾지 못했습니다.

권장 설치:
  winget install -e --id Python.Python.3.12

설치 후 PowerShell과 VS Code를 완전히 다시 열고:
  python --version
  where.exe python

을 확인한 다음 이 스크립트를 다시 실행하세요.

특정 Python 경로를 직접 지정할 수도 있습니다:
  .\scripts\setup_venv.ps1 -PythonPath "C:\경로\python.exe"
"@
    }

    Write-Host "선택한 Python: $($basePython.Path)" -ForegroundColor Green
    Write-Host "버전: $($basePython.Version)" -ForegroundColor Green

    & $basePython.Path -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) {
        throw ".venv 생성에 실패했습니다."
    }
}

if (-not (Test-Path $PythonExe)) {
    throw ".venv Python 실행파일이 생성되지 않았습니다: $PythonExe"
}

& $PythonExe -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) {
    throw "pip 기본 도구 업그레이드에 실패했습니다."
}

& $PythonExe -m pip install -r $Requirements
if ($LASTEXITCODE -ne 0) {
    throw "requirements.txt 설치에 실패했습니다."
}

$LocalEnvExample = Join-Path $ProjectRoot "scripts\local_env.ps1.example"
$LocalEnv = Join-Path $ProjectRoot "scripts\local_env.ps1"

if ((Test-Path $LocalEnvExample) -and -not (Test-Path $LocalEnv)) {
    Copy-Item $LocalEnvExample $LocalEnv
    Write-Host "scripts\local_env.ps1을 생성했습니다. Git 추적 대상에서 제외됩니다." -ForegroundColor Green
}

& $PythonExe -m pip freeze |
    Set-Content -Encoding UTF8 (Join-Path $ProjectRoot "backend\requirements.lock.txt")

Write-Host ""
Write-Host "가상환경 생성 완료" -ForegroundColor Green
Write-Host "Python: $PythonExe"
& $PythonExe --version

Write-Host ""
Write-Host "다음 단계:"
Write-Host "  1. VS Code: Python: Select Interpreter -> .venv\Scripts\python.exe"
Write-Host "  2. .\scripts\run_backend.ps1"
