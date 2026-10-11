$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$buildPython = Join-Path $PWD '.venv\Scripts\python.exe'
$buildWorkspace = [IO.Path]::GetFullPath($PWD.Path)
$buildTarget = [IO.Path]::GetFullPath((Join-Path $buildWorkspace 'dist\Providence'))
if (-not $buildTarget.StartsWith($buildWorkspace + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Build output must stay inside this workspace.'
}
foreach ($buildOutputPath in @((Join-Path $buildWorkspace 'dist'), $buildTarget)) {
    if ((Test-Path -LiteralPath $buildOutputPath) -and ((Get-Item -LiteralPath $buildOutputPath).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Refusing to replace a linked build output directory.'
    }
}
if (-not (Test-Path -LiteralPath $buildPython)) { throw 'The isolated Windows build environment (.venv) is missing.' }
if (-not (Test-Path -LiteralPath 'build\model\REVISION')) {
    & $buildPython 'docker/download_model.py' --destination 'build/model'
    if ($LASTEXITCODE -ne 0) { throw 'Downloading the fixed offline model failed.' }
}
if (-not (Test-Path -LiteralPath 'build\qwen\REVISION')) {
    & $buildPython 'scripts/download-qwen.py' --destination 'build/qwen'
    if ($LASTEXITCODE -ne 0) { throw 'Downloading the fixed Qwen model failed.' }
}
if (-not (Test-Path -LiteralPath 'build\clip\REVISION')) {
    & $buildPython 'scripts/download-clip.py'
    if ($LASTEXITCODE -ne 0) { throw 'Downloading the fixed image model failed.' }
}
& $buildPython -m PyInstaller --noconfirm Providence.spec
if ($LASTEXITCODE -ne 0) { throw 'Windows packaging failed.' }
& $buildPython 'scripts/verify-package.py'
if ($LASTEXITCODE -ne 0) { throw 'Packaged application differs from current source.' }
& $buildPython 'scripts/package-windows.py'
if ($LASTEXITCODE -ne 0) { throw 'Release ZIP packaging failed.' }
Write-Output 'Ready: dist\Providence\Providence.exe. Ship the entire Providence folder, including _internal.'
