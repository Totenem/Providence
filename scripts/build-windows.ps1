$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$buildPython = Join-Path $PWD '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $buildPython)) { throw 'The isolated Windows build environment (.venv) is missing.' }
if (-not (Test-Path -LiteralPath 'build\model\REVISION')) {
    & $buildPython 'docker/download_model.py' --destination 'build/model'
    if ($LASTEXITCODE -ne 0) { throw 'Downloading the fixed offline model failed.' }
}
& $buildPython -m PyInstaller --noconfirm Providence.spec
if ($LASTEXITCODE -ne 0) { throw 'Windows packaging failed.' }
& $buildPython 'scripts/verify-package.py'
if ($LASTEXITCODE -ne 0) { throw 'Packaged application differs from current source.' }
& $buildPython 'scripts/package-windows.py'
if ($LASTEXITCODE -ne 0) { throw 'Release ZIP packaging failed.' }
Write-Output 'Ready: dist\Providence\Providence.exe. Ship the entire Providence folder, including _internal.'
