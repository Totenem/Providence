param([string]$DocumentsPath, [switch]$Demo)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
if (-not $Demo) {
    if (-not $DocumentsPath) {
        Add-Type -AssemblyName System.Windows.Forms
        $picker = New-Object System.Windows.Forms.FolderBrowserDialog
        $picker.Description = 'Choose the folder Providence can access. You will select folders to index in the app next.'
        $picker.SelectedPath = [Environment]::GetFolderPath('MyDocuments')
        if ($picker.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
            $picker.Dispose()
            Write-Output 'No folder selected. Providence was not started.'
            exit 0
        }
        $DocumentsPath = $picker.SelectedPath
        $picker.Dispose()
    }
    $resolvedFolder = (Resolve-Path -LiteralPath $DocumentsPath).Path
    if (-not (Test-Path -LiteralPath $resolvedFolder -PathType Container)) { throw 'Choose an existing folder.' }
    $env:PROVIDENCE_DOCUMENTS = $resolvedFolder.Replace('\', '/')
} else {
    $env:PROVIDENCE_DOCUMENTS = (Join-Path $PWD 'demo-documents').Replace('\', '/')
}
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw 'Docker startup failed. Ensure Docker Desktop is running with Linux containers.' }
Write-Output 'Providence: http://localhost:6080/vnc.html?autoconnect=1&resize=remote'
