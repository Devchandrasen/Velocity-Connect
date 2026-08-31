param(
    [string]$EnvironmentPath = "..\velocity-connect-analysis-env",
    [string]$TestReport = "..\velocity-connect-clean-tests.xml"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$environmentFullPath = [System.IO.Path]::GetFullPath(
    (Join-Path $projectRoot $EnvironmentPath)
)
if (Test-Path -LiteralPath $environmentFullPath) {
    throw "Refusing to reuse an existing environment: $environmentFullPath"
}

$runtime = & py -3.12 -c "import platform,sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}|{platform.architecture()[0]}')"
if ($LASTEXITCODE -ne 0 -or $runtime.Trim() -ne "3.12.10|64bit") {
    throw "Expected exact CPython 3.12.10 64-bit runtime; found '$runtime'."
}

py -3.12 -m venv $environmentFullPath
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.12 virtual-environment creation failed."
}
$python = Join-Path $environmentFullPath "Scripts\python.exe"
& $python -m pip install --require-hashes -r (
    Join-Path $projectRoot "environment\requirements-hashed-win-py312.txt"
)
if ($LASTEXITCODE -ne 0) {
    throw "Locked dependency installation failed."
}
& $python -m pip check
if ($LASTEXITCODE -ne 0) {
    throw "Installed environment failed pip check."
}
$testReportFullPath = [System.IO.Path]::GetFullPath(
    (Join-Path $projectRoot $TestReport)
)
$testReportParent = Split-Path -Parent $testReportFullPath
if (-not (Test-Path -LiteralPath $testReportParent)) {
    New-Item -ItemType Directory -Path $testReportParent | Out-Null
}
$env:PYTHONDONTWRITEBYTECODE = "1"
Push-Location $projectRoot
try {
    & $python -m pytest -q -p no:cacheprovider --junitxml $testReportFullPath
} finally {
    Pop-Location
}
if ($LASTEXITCODE -ne 0) {
    throw "Project tests failed in the clean environment."
}

[pscustomobject]@{
    status = "complete"
    python = $python
    runtime = $runtime.Trim()
    pip = (& $python -m pip --version)
    test_report = $testReportFullPath
}
