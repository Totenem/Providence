# Providence contributor guide

## Product rules

- Providence is an offline, privacy-first Windows desktop file browser and search app. Keep AI inference, OCR, indexes, and document text local by default.
- Never change original files. Treat indexed files as read-only; previews, OCR, and embeddings write only to Providence data.
- Preserve the default exclusions for system folders, app data, caches, build outputs, reparse points, cloud placeholders, and inaccessible paths. New scopes must be explicit and editable.
- Search starts only when the user presses Enter or chooses Search. Typing, filter changes, file notifications, and a previous search finishing must never submit a new AI search.
- Search progress describes completed stages, not confidence or an ETA. If a search exceeds 20 seconds, offer optional clues: remembered folder, connected-file count, type, and date. Each clue defaults to unknown.
- Do not add a conversational LLM merely to use search clues. Clues must constrain or enrich local retrieval.

## Architecture

- `providence/` holds the application: discovery, extraction, OCR, embeddings, SQLite/FTS store, HNSW retrieval, background service, previews, and UI controllers.
- `providence/qml/` is the Qt Quick/QML library shell. Keep the app's visual language: Explorer-style browser, clear section separation, high-contrast controls, bounded custom dropdowns, padded previews, and responsive file rows.
- Rich previews and settings/index-health dialogs remain native Qt widgets. Keep their behavior and shared controllers aligned with QML.
- MiniLM is the lightweight profile; Qwen3-Embedding-0.6B is the stronger multilingual profile. Embedding changes require a separate compatible index. Do not claim a model is faster or more accurate without a documented measurement.
- OCR uses bundled RapidOCR/PP-OCRv6 for printed text in scanned PDFs and PNG/JPEG images. Preserve native PDF text, page references, caching, cancellation, and resource limits.

## Testing and validation

- Run the source suite before submitting behavior changes:

  ```powershell
  $env:QT_QPA_PLATFORM = "offscreen"
  $env:QT_QUICK_BACKEND = "software"
  $env:PROVIDENCE_MODEL_DIR = "$PWD/build/model"
  .\.venv\Scripts\python.exe -m pytest -q
  ```

- Pytest uses the disposable repository-root `pytest-tmp` directory. Do not move fixtures under AppData or Temp: discovery deliberately excludes those folders.
- For UI work, inspect light and dark themes and a narrow window. Use `scripts/preview-ui.py --public` for public screenshots; never publish paths, usernames, or real document contents.
- For retrieval or OCR changes, preserve offline tests and record quality, latency, memory, and limitations in the relevant validation documentation. Synthetic results are smoke tests, not production guarantees.

## Documentation and releases

- Keep the README public-facing: users, contributors, and researchers. Use fictional data in screenshots and examples.
- `Providence_Project_Plan.md` and `Providence_1.1.0_Roadmap.md` are local planning documents and intentionally ignored by Git. Update them when requested, but do not add them to releases or package source copies.
- Every release needs `docs/releases/<version>.md`. Update the package version, README, portable-app readme, and validation links together.
- A tag push runs source validation. Building the EXE/ZIP and publishing a GitHub Release require the user's explicit confirmation for that specific release. Do not build, package, publish, sign, or delete/retag releases without it.
- When publishing is approved, use the `Windows release` workflow for the exact version tag with both `confirm_build` and `confirm_publish` enabled. Verify the resulting ZIP, SHA-256 file, release notes, and GitHub Release assets.

## Working conventions

- Prefer focused, behavior-level tests over implementation-mirroring tests. Keep user changes intact and avoid broad formatting churn.
- Use `rg` for repository searches. Run targeted tests first, then the full suite when the change affects shared behavior.
- Do not include secrets, personal paths, local logs, generated build outputs, model downloads, indexes, or unrelated files in commits.
