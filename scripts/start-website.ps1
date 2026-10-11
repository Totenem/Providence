$ErrorActionPreference = 'Stop'
$websiteRoot = Split-Path -Parent $PSScriptRoot
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Install and start Docker Desktop with Linux containers first.' }
& docker compose -f (Join-Path $websiteRoot 'website/compose.yaml') up --build -d --wait
if ($LASTEXITCODE -ne 0) { throw 'Website container startup failed. Check Docker Desktop and the build output.' }
Write-Output 'Providence website: http://localhost:3000'
