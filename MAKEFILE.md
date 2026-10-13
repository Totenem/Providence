# Providence Makefile guide

Run these commands from the repository root in PowerShell. The Makefile calls `scripts/release.ps1`; it does not change the application version or release notes for you.

## Requirements

- GNU Make: check with `make --version`. After installing it, close and reopen PowerShell so the updated PATH is loaded.
- Git: check with `git --version`.
- GitHub CLI for workflow commands: check with `gh --version`, then authenticate with `gh auth login`. Your account needs access to run this repository's workflows.
- Windows PowerShell, plus the repository's `.venv` and downloaded local models for `make test`. See [source setup](README.md#run-from-source).

## Commands

| Command | What it does |
|---|---|
| `make` or `make help` | Lists the available commands. |
| `make release-check` | Checks the local package version, release-summary file, version mentions in the readmes, and `git diff --check`. Warns about a development-draft notice. Does not run tests. |
| `make test` | Runs the full source test suite with offscreen/software Qt and offline model settings. No EXE or ZIP is built. |
| `make release-plan` | Prints the GitHub publication command. Does not contact GitHub, create a tag, build, or publish. |
| `make tag VERSION=1.0.2` | Creates and pushes `v1.0.2` from the current commit. The tag push starts GitHub source validation only. |
| `make release-build VERSION=1.0.2 CONFIRM_BUILD=1` | Starts the Windows workflow at the remote tag, builds/verifies the portable package, and saves the ZIP/checksum as an Actions artifact. Does not publish a release. |
| `make release VERSION=1.0.2 CONFIRM_BUILD=1 CONFIRM_PUBLISH=1` | Starts the workflow at the remote tag, runs source checks, builds/verifies the portable package, and publishes its ZIP/checksum on GitHub Releases. |
| `make release-status VERSION=1.0.2` | Lists the ten most recent Windows release workflow runs for that tag. Does not continuously watch them. |

`VERSION` defaults to the version in `pyproject.toml`. If supplied, it must match that version. Use `VERSION=1.0.2`, without the leading `v`; the helper supplies `v` for the tag.

The repository defaults to `Totenem/Providence`. For a fork, pass `REPO=owner/repository`. The tag command pushes to the local Git remote named `origin`; changing `REPO` does not change that remote. Check `git remote -v` before tagging a fork.

## Release sequence

The following example uses **1.0.2**. For a later release, replace every version-specific filename and command with the new version.

### 1. Prepare the version and notes

Update these together:

- `pyproject.toml`
- `README.md`
- `scripts/WINDOWS-README.txt`
- `docs/releases/1.0.2.md`
- Validation documentation and links relevant to the release.

Review the release summary and remove its `Development draft` notice when the notes are ready. Retain known limitations and recorded test results. Do not claim a successful packaged-app check before it has occurred.

### 2. Check and test

```powershell
make release-check VERSION=1.0.2
make test
make release-plan VERSION=1.0.2
```

Fix any failed checks or tests before continuing. A successful release plan is only a preview; it does not verify GitHub authentication, the remote tag, or packaging.

### 3. Commit and push the reviewed files

Inspect `git status` and your diff first. Stage the actual release changes, for example:

```powershell
git status
git diff
git add pyproject.toml README.md scripts/WINDOWS-README.txt docs/releases/1.0.2.md docs/1.0.2-validation.md MAKEFILE.md docs/RELEASING.md
git commit -m "Prepare Providence v1.0.2 release"
git push origin main
```

Include other reviewed implementation changes if needed. Do not stage local planning files, logs, indexes, model downloads, or generated builds. If everything is already committed and pushed, skip the commit commands.

### 4. Create the version tag

```powershell
make tag VERSION=1.0.2
```

Tagging requires a clean working tree. The helper refuses an existing local or remote tag and never replaces one. If the correct tag already exists on GitHub, skip this step. The tag contains the current commit; later changes on `main` do not change its contents.

A tag push runs source validation. **It does not attach a new application download.**

### 5. Build and publish

To authorize both the Windows package build and public release:

```powershell
make release VERSION=1.0.2 CONFIRM_BUILD=1 CONFIRM_PUBLISH=1
make release-status VERSION=1.0.2
```

Before dispatch, the helper checks the package version and release summary **at the remote tag**. The workflow repeats source tests, builds the portable app, verifies native Windows startup, and publishes:

- `Providence-win-x64.zip`, containing the portable app and bundled assets.
- `Providence-win-x64.zip.sha256`, containing the package checksum.
- Release notes combining the reviewed Markdown summary with GitHub-generated change notes.

Dispatching the workflow is not proof that it succeeded. Open the run in GitHub Actions, wait for the build and publish jobs to complete, then verify the matching tag, version, downloadable assets and checksum on the Releases page.

To build an artifact for review without publication, use:

```powershell
make release-build VERSION=1.0.2 CONFIRM_BUILD=1
```

Download it from the run's **Artifacts** section in GitHub Actions. Artifacts are retained for 14 days. A later `make release` starts a fresh workflow build; it does not promote the earlier artifact.

## Common errors

| Message/problem | What to do |
|---|---|
| `make` is not recognized | Close and reopen PowerShell after installing GNU Make. Check `make --version`, or use the PowerShell helper below. |
| GitHub CLI is missing or authentication fails | Install GitHub CLI, run `gh auth login`, and confirm access with `gh auth status`. |
| `Version must match pyproject.toml` | Use the package version, or update the release's version files together before committing. |
| Missing release summary | Create and review `docs/releases/<version>.md`, using the [template](docs/releases/TEMPLATE.md). |
| Development-draft notice blocks tagging | Review the summary, remove that notice, then commit and push the change. |
| Working tree is not clean | Inspect `git status` and commit your reviewed changes before tagging. |
| Tag already exists | Inspect the existing tag. If it is correct and already pushed, skip `make tag`. If it is correct but only local, push it with `git push origin v1.0.2`. Do not delete or move a published tag as a routine fix. |
| Remote tag is missing | Create/push the correct tag before dispatching the release workflow. A version-named commit or branch is not a version tag. |
| Remote tag still contains draft notes | Editing `main` does not update an existing tag. Inspect the tag's contents and decide the appropriate version/tag correction explicitly. |
| Build/publish confirmation is missing | Supply `CONFIRM_BUILD=1`; public publication also requires `CONFIRM_PUBLISH=1`. |
| Workflow failed | Read the failed job's logs in GitHub Actions and fix its reported cause. Do not assume a ZIP was published. |

## Without GNU Make

The same helper is available directly from PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/release.ps1 -Action help
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/release.ps1 -Action check -Version 1.0.2
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/release.ps1 -Action test
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/release.ps1 -Action release -Version 1.0.2 -DryRun
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/release.ps1 -Action tag -Version 1.0.2
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/release.ps1 -Action build -Version 1.0.2 -ConfirmBuild 1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/release.ps1 -Action release -Version 1.0.2 -ConfirmBuild 1 -ConfirmPublish 1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/release.ps1 -Action status -Version 1.0.2
```

Each line is a separate action, not a script to run all at once. Choose `build` for an artifact or `release` for publication.

For the workflow policy and release-note conventions, see [RELEASING.md](docs/RELEASING.md).
