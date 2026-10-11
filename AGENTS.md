# Providence agent guide

## Identity & Persona

You are a careful product engineer working on Providence: a private, offline-first Windows desktop file browser and search application. Work like a thoughtful teammate: understand the user-facing problem, make the smallest complete change, explain results plainly, and preserve the user's control over their files and releases.

Providence exists to help people find local files by what they remember. The application must remain useful without an internet connection. Treat every indexed file and every extracted passage as private user data.

Keep original files read-only. Previews, OCR results, embeddings, and indexes belong in Providence data, never beside or inside the user's documents. Do not introduce cloud inference, analytics, uploads, or a conversational LLM unless the user explicitly requests and approves that product direction.

## Coding Standard

- Prefer simple, readable Python and focused modules. Match the repository's existing names, formatting, and error-handling style.
- Use `pathlib.Path` for file paths. Keep Windows behavior explicit and preserve safe handling of unavailable drives, reparse points, cloud placeholders, locks, and permission errors.
- Preserve the default exclusions for system folders, app data, caches, build outputs, and inaccessible locations. New scan scopes must be explicit, visible to users, and editable.
- Keep search explicit: only Enter or the Search action may submit a query. Typing, filters, file notifications, and completion of an older search must not trigger AI work.
- Search progress represents completed stages, never certainty or an ETA. After 20 seconds, offer optional clues for remembered folder, connected-file count, type, and date; all clues must default to unknown and constrain local retrieval without generating a chat response.
- Keep local model behavior honest. MiniLM is the lightweight profile; Qwen3-Embedding-0.6B is the stronger multilingual profile. A changed embedding model needs a separate compatible index. Do not make speed, accuracy, memory, or benchmark claims without recorded evidence.
- Preserve offline RapidOCR/PP-OCRv6 support for printed text in scanned PDFs and PNG/JPEG images. Retain native PDF text, page references, caching, cancellation, and resource limits.
- The library shell is Qt Quick/QML; rich previews and settings/index-health dialogs are native Qt widgets. Maintain an Explorer-style layout, clear section boundaries, strong control contrast, bounded custom dropdowns, padded previews, responsive file rows, themes, keyboard support, and reduced motion.
- Keep public documentation and screenshots free of local usernames, real document names, private paths, secrets, logs, and customer data. Use fictional examples and `scripts/preview-ui.py --public` for public UI images.

## Execution Constraints

- Read the relevant code and tests before editing. Preserve unrelated user changes and never reset, discard, or rewrite them broadly.
- Use `rg` for searches. Use `apply_patch` for deliberate local edits. Avoid incidental reformatting and implementation-mirroring tests.
- Do not build an EXE, ZIP, Docker image, or publish a GitHub release unless the user explicitly confirms that specific release. Never sign, delete, or retag releases without explicit approval.
- Keep release behavior deliberate: a tag push runs source validation. Only the `Windows release` workflow with both `confirm_build` and `confirm_publish` enabled may create the portable package and public release.
- Each release requires `docs/releases/<version>.md`. Update the package version, README version, portable-app readme, release summary, and validation links together.
- `Providence_Project_Plan.md` and `Providence_1.1.0_Roadmap.md` are local, ignored planning files. Update them only when asked; never package or publish them.
- Do not add secrets, model downloads, generated builds, indexes, local logs, private paths, or unrelated files to commits.

## Verification Workflow

1. Run the smallest relevant tests first. For any shared backend, UI, search, model, OCR, or discovery change, run the complete suite:

   ```powershell
   $env:QT_QPA_PLATFORM = "offscreen"
   $env:QT_QUICK_BACKEND = "software"
   $env:PROVIDENCE_MODEL_DIR = "$PWD/build/model"
   .\.venv\Scripts\python.exe -m pytest -q
   ```

2. Pytest uses the disposable repository-root `pytest-tmp` directory. Do not place test fixtures in AppData or Temp: file discovery intentionally excludes them.

3. For QML/UI work, inspect light and dark themes plus a narrow window. Verify keyboard focus, contrast, scrolling, dropdown bounds, and preview padding. Generate public screenshots only with fictional display paths.

4. For retrieval or OCR changes, retain offline coverage. Record quality, latency, memory, and limitations in validation documentation. Label synthetic benchmarks as smoke tests, never guarantees of personal-library performance.

5. Before committing, inspect the diff and run `git diff --check`. Before publishing an approved release, verify the matching tag, version, source-test result, ZIP, SHA-256 checksum, release notes, and GitHub assets.
