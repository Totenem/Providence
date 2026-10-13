param(
    [ValidateSet('help', 'test', 'check', 'tag', 'build', 'release', 'status')]
    [string]$Action = 'help',
    [string]$Version = '',
    [string]$Repo = 'Totenem/Providence',
    [string]$ConfirmBuild = '0',
    [string]$ConfirmPublish = '0',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed (exit $LASTEXITCODE)." }
}

if ($Action -eq 'help') {
    Write-Output @'
make test                         Run source tests only
make release-check                Check local version and release documents
make release-plan                 Preview publication command; no remote changes
make tag                          Create/push v<version>; source validation only
make release-build CONFIRM_BUILD=1 Build a GitHub artifact without publishing
make release CONFIRM_BUILD=1 CONFIRM_PUBLISH=1
                                  Build and publish the ZIP/checksum on GitHub
make release-status               List workflow runs for this version tag

Version defaults to pyproject.toml. Override with VERSION=1.0.2.
Commit and push reviewed source/release notes before make tag.
Prerequisites: GNU Make, Windows PowerShell, Git, GitHub CLI (gh auth login).
Without make: powershell -File scripts/release.ps1 -Action help
'@
    exit 0
}

$packageVersion = [regex]::Match(
    (Get-Content -Raw -LiteralPath 'pyproject.toml'), '(?m)^version = "([^"]+)"\r?$'
).Groups[1].Value
if (-not $Version) { $Version = $packageVersion }
if ($Version -notmatch '^\d+\.\d+\.\d+$' -or $Version -ne $packageVersion) {
    throw "Version must match pyproject.toml ($packageVersion), for example -Version $packageVersion."
}
if ($Repo -notmatch '^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$') { throw 'Repo must be owner/name.' }
$tag = "v$Version"
$summary = "docs/releases/$Version.md"
if (-not (Test-Path -LiteralPath $summary)) { throw "Missing release summary: $summary" }
foreach ($document in @('README.md', 'scripts/WINDOWS-README.txt')) {
    if (-not (Get-Content -Raw -LiteralPath $document).Contains($Version)) {
        throw "$document must mention version $Version."
    }
}
if ($Action -eq 'test') {
    $env:QT_QPA_PLATFORM = 'offscreen'
    $env:QT_QUICK_BACKEND = 'software'
    $env:PROVIDENCE_MODEL_DIR = Join-Path $PWD 'build/model'
    $env:HF_HUB_OFFLINE = '1'
    $env:TRANSFORMERS_OFFLINE = '1'
    Invoke-Checked '.venv/Scripts/python.exe' @('-m', 'pytest', '-q')
    exit 0
}
if ($Action -eq 'check') {
    Invoke-Checked git @('diff', '--check')
    Write-Output "Version $Version and release documents checked."
    if ((Get-Content -Raw -LiteralPath $summary) -match '(?i)Development draft') {
        Write-Warning "Review $summary and remove the development-draft notice before tagging."
    }
    exit 0
}
if ($DryRun) {
    if ($Action -notin @('build', 'release')) { throw 'DryRun is supported for build/release only.' }
    $publish = if ($Action -eq 'release') { 'true' } else { 'false' }
    Write-Output "gh workflow run windows-release.yml --repo $Repo --ref $tag -f confirm_build=true -f confirm_publish=$publish"
    Write-Output 'Preview only. No tag, build, workflow dispatch, or publication was performed.'
    exit 0
}
if ($Action -in @('tag', 'build', 'release')) {
    if ((Get-Content -Raw -LiteralPath $summary) -match '(?i)Development draft') {
        throw "Review $summary and remove the development-draft notice before tagging/releasing."
    }
}
if ($Action -eq 'tag') {
    $changes = & git status --porcelain
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect the working tree.' }
    if ($changes) { throw 'Commit and push the reviewed source/release notes before tagging.' }
    $existing = & git tag --list $tag
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect tags.' }
    if ($existing) { throw "$tag already exists locally. Push it manually if needed; this helper never retags." }
    $remoteTag = & git ls-remote --tags origin "refs/tags/$tag"
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect remote tags.' }
    if ($remoteTag) { throw "$tag already exists remotely. This helper never replaces tags." }
    Invoke-Checked git @('tag', '-a', $tag, '-m', "Providence $Version")
    Invoke-Checked git @('push', 'origin', "refs/tags/$tag")
    Write-Output 'Tag pushed. GitHub source validation runs; no EXE/ZIP is built by a tag push.'
    exit 0
}
if ($Action -in @('build', 'release')) {
    if ($ConfirmBuild -ne '1') { throw 'Building requires CONFIRM_BUILD=1 (or -ConfirmBuild 1).' }
    if ($Action -eq 'release' -and $ConfirmPublish -ne '1') {
        throw 'Publishing requires CONFIRM_PUBLISH=1 (or -ConfirmPublish 1).'
    }
}
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw 'Install GitHub CLI and run gh auth login before using remote release commands.'
}
if ($Action -eq 'status') {
    Invoke-Checked gh @('run', 'list', '--repo', $Repo, '--workflow', 'windows-release.yml', '--branch', $tag, '--limit', '10')
    exit 0
}
# Inspect the remote tag's package and summary, not just the current checkout.
$tagPackage = & gh api "repos/$Repo/contents/pyproject.toml?ref=$tag" --jq '.content'
if ($LASTEXITCODE -ne 0) { throw "Remote tag $tag is missing/inaccessible. Run make tag first, or push your existing tag." }
$tagText = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String(($tagPackage -join '')))
if ($tagText -notmatch ('(?m)^version = "' + [regex]::Escape($Version) + '"\r?$')) {
    throw "Remote $tag does not contain package version $Version. No workflow dispatched."
}
$tagSummary = & gh api "repos/$Repo/contents/$summary`?ref=$tag" --jq '.content'
if ($LASTEXITCODE -ne 0) { throw "Remote $tag is missing its release summary." }
$tagNotes = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String(($tagSummary -join '')))
if ($tagNotes -match '(?i)Development draft') { throw "Remote $tag still contains draft release notes. No workflow dispatched." }
$publish = if ($Action -eq 'release') { 'true' } else { 'false' }
Invoke-Checked gh @('workflow', 'run', 'windows-release.yml', '--repo', $Repo, '--ref', $tag,
    '-f', 'confirm_build=true', '-f', "confirm_publish=$publish")
Write-Output "Workflow dispatched for $tag. Run make release-status to follow progress."
