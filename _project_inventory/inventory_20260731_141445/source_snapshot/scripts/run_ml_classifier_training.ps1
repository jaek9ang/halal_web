$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path `
    $projectRoot `
    '.venv\Scripts\python.exe'

$trainingScript = Join-Path `
    $projectRoot `
    'backend\scripts\ml_certificate_classifier\02_train_classifier.py'

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "프로젝트 .venv Python이 없습니다: $venvPython"
}

if (-not (Test-Path -LiteralPath $trainingScript)) {
    throw "학습 스크립트가 없습니다: $trainingScript"
}

$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

& $venvPython $trainingScript

if ($LASTEXITCODE -ne 0) {
    throw "모델 학습 실패. 종료코드: $LASTEXITCODE"
}

$runtimeRoot = `
    'D:\halal_web_runtime\certificate_classifier'

$latestTrainingPointer = Join-Path `
    $runtimeRoot `
    'reports\latest_model_training.txt'

if (Test-Path -LiteralPath $latestTrainingPointer) {
    $reportRoot = (
        Get-Content `
            -LiteralPath $latestTrainingPointer `
            -Raw
    ).Trim()

    if (Test-Path -LiteralPath $reportRoot) {
        $htmlReport = Join-Path `
            $reportRoot `
            '13_model_report.html'

        Start-Process explorer.exe $reportRoot

        if (Test-Path -LiteralPath $htmlReport) {
            Start-Process $htmlReport
        }
    }
}