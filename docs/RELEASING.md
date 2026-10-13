# Releasing Providence

Each release needs a short summary for users, plus source validation and separately approved packaging. GitHub supplies the automatic pull-request list and contributor credits; no additional app or token is needed beyond the workflow's repository token.

1. Update `pyproject.toml`, the README version, and `scripts/WINDOWS-README.txt` together.
2. Write `docs/releases/<version>.md` describing the changes, fixes, validation, and known limits. Start from the [summary template](releases/TEMPLATE.md). Update any validation-document links.
3. Run the source tests and review the summary before committing and tagging `v<version>`. Pytest uses `pytest-tmp`, a dedicated disposable repository directory cleared before each run, so fixtures stay outside excluded AppData/Temp locations.
4. Push the approved version tag. The Windows release workflow checks that the tag matches the package version and that a summary exists, then runs source tests. A tag push does not build or publish binaries.
5. When packaging is explicitly approved, select that tag in Actions → Windows release → Run workflow and enable `confirm_build`. Leave `confirm_publish` off to keep the result as a workflow artifact.
6. When publication is also approved, run against the version tag with both inputs enabled. The workflow combines the checked-in summary with GitHub-generated notes and publishes the verified ZIP and checksum. Re-running publication refreshes the assets and notes for that tag.

Label pull requests `enhancement`, `feature`, `ui`, `bug`, `fix`, `documentation`, `research`, `dependencies`, or `maintenance` to organize generated notes. Unlabeled changes fall under Other changes; `skip-changelog` excludes a pull request. Direct commits may not produce descriptive pull-request entries, so keep the curated summary even when work is committed directly.

## Makefile commands on Windows

The root [Makefile](../Makefile) uses Windows PowerShell and defaults to the version in `pyproject.toml`. Install GNU Make and GitHub CLI, then authenticate with `gh auth login`. Git must also be available. Run commands from the repository root:

```powershell
make release-check
make test
make release-plan
```

The check flags a development-draft summary. Review `docs/releases/<version>.md` and remove that notice before tagging; do not change the recorded validation results or invent a successful packaged-app check. Commit and push the reviewed files, including the Makefile/helper if desired. Then:

```powershell
make tag VERSION=1.0.2
make release VERSION=1.0.2 CONFIRM_BUILD=1 CONFIRM_PUBLISH=1
make release-status VERSION=1.0.2
```

`make tag` creates and pushes only the version tag. It refuses an uncommitted working tree or an existing local/remote tag; it never replaces tags or pushes the branch automatically. If you already have the correct tag, skip that command. A tag push runs source tests only.

`make release` explicitly authorizes both building and publishing through the existing Windows release workflow. It validates the version and release summary at the **remote tag** before dispatch. The workflow reruns source tests, builds/verifies the Windows package and publishes the ZIP plus SHA-256 checksum using the curated and generated notes. Use `make release-build VERSION=1.0.2 CONFIRM_BUILD=1` for a workflow artifact without publication. The helper does not alter versions or release notes automatically.

If GNU Make is unavailable, use the same helper directly:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/release.ps1 -Action check
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/release.ps1 -Action tag -Version 1.0.2
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/release.ps1 -Action release -Version 1.0.2 -ConfirmBuild 1 -ConfirmPublish 1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/release.ps1 -Action status -Version 1.0.2
```

GitHub CLI reference: [dispatching a workflow at a tag with explicit inputs](https://cli.github.com/manual/gh_workflow_run).

Release-note configuration lives in [`.github/release.yml`](../.github/release.yml). The workflow never generates a narrative from private planning files. Before publishing, confirm that images and examples contain only public or fictional data.

GitHub reference: [automatically generated release notes](https://docs.github.com/en/repositories/releasing-projects-on-github/automatically-generated-release-notes).
