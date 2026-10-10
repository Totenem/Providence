$ErrorActionPreference = 'Stop'
$testRoot = Split-Path -Parent $PSScriptRoot
$testExecutable = Join-Path $testRoot 'dist\Providence\Providence.exe'
$testData = Join-Path $testRoot '.artifacts\desktop-smoke'
New-Item -ItemType Directory -Force -Path $testData | Out-Null
$previousData = $env:PROVIDENCE_DATA_DIR
$previousLocalAppData = $env:LOCALAPPDATA
$env:PROVIDENCE_DATA_DIR = $testData
$env:LOCALAPPDATA = $testData
$testProcess = $null
try {
    # Test the real Windows Qt platform with an isolated empty search index.
    $testProcess = Start-Process -FilePath $testExecutable -WindowStyle Hidden -PassThru
    $testDeadline = (Get-Date).AddSeconds(15)
    $verifiedTitle = ''
    while ((Get-Date) -lt $testDeadline) {
        $testProcess.Refresh()
        if ($testProcess.HasExited) { throw "Providence exited during startup: $($testProcess.ExitCode)" }
        if ($testProcess.MainWindowTitle -like 'Providence*Your files*') {
            $verifiedTitle = $testProcess.MainWindowTitle
            break
        }
        if ($testProcess.MainWindowTitle -like '*exception*') {
            throw 'The packaged application displayed a startup exception.'
        }
        Start-Sleep -Milliseconds 200
    }
    if (-not $verifiedTitle) { throw 'The packaged application did not create its main Windows window.' }
    Write-Output "Native startup verified: $verifiedTitle"
} finally {
    # Terminate only the isolated test process created by this script.
    if ($null -ne $testProcess) {
        $testProcess.Refresh()
        if (-not $testProcess.HasExited) { Stop-Process -Id $testProcess.Id }
    }
    $env:PROVIDENCE_DATA_DIR = $previousData
    $env:LOCALAPPDATA = $previousLocalAppData
}
