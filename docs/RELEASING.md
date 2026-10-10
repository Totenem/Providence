# Releasing Providence

Each release needs a short summary for users, plus source validation and separately approved packaging. GitHub supplies the automatic pull-request list and contributor credits; no additional app or token is needed beyond the workflow's repository token.

1. Update `pyproject.toml`, the README version, and `scripts/WINDOWS-README.txt` together.
2. Write `docs/releases/<version>.md` describing the changes, fixes, validation, and known limits. Start from the [summary template](releases/TEMPLATE.md). Update any validation-document links.
3. Run the source tests and review the summary before committing and tagging `v<version>`. Pytest uses `.artifacts/pytest`, a dedicated disposable directory cleared before each run, so fixtures stay outside excluded AppData/Temp locations.
4. Push the approved version tag. The Windows release workflow checks that the tag matches the package version and that a summary exists, then runs source tests. A tag push does not build or publish binaries.
5. When packaging is explicitly approved, select that tag in Actions → Windows release → Run workflow and enable `confirm_build`. Leave `confirm_publish` off to keep the result as a workflow artifact.
6. When publication is also approved, run against the version tag with both inputs enabled. The workflow combines the checked-in summary with GitHub-generated notes and publishes the verified ZIP and checksum. Re-running publication refreshes the assets and notes for that tag.

Label pull requests `enhancement`, `feature`, `ui`, `bug`, `fix`, `documentation`, `research`, `dependencies`, or `maintenance` to organize generated notes. Unlabeled changes fall under Other changes; `skip-changelog` excludes a pull request. Direct commits may not produce descriptive pull-request entries, so keep the curated summary even when work is committed directly.

Release-note configuration lives in [`.github/release.yml`](../.github/release.yml). The workflow never generates a narrative from private planning files. Before publishing, confirm that images and examples contain only public or fictional data.

GitHub reference: [automatically generated release notes](https://docs.github.com/en/repositories/releasing-projects-on-github/automatically-generated-release-notes).
