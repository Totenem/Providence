# Providence

Offline semantic search for PDF, TXT, DOCX and Markdown documents. Describe what you remember; Providence returns ranked files and matching passages. Run the native Windows desktop app or the Docker browser preview. Both include the offline model. Other formats, including legacy DOC, are skipped automatically.

## Run with Docker

Requires Docker Desktop running **Linux containers**. The first image build needs internet to download system dependencies, Python packages and the embedding model. After building, inference and document processing run offline. Compose puts the app on an internal Docker network with no external connectivity. A small TCP relay exposes only the desktop on localhost; it does not process documents or run inference.

```powershell
docker compose up -d --build
```

Open [Providence](http://localhost:6080/vnc.html?autoconnect=1&resize=remote). The **Initial indexing** screen asks you to **Add folder** (use `/documents` for the demo), then **Start indexing**. Once setup finishes, search for “the database proposal I wrote last semester.” Three demo documents are mounted by default. Indexing shows a percentage, processed-file count and current stage. The folder scan stays at 0% until the file total is known. **Stop indexing** stops between files or inference batches and keeps complete documents already saved. If any documents were saved, onboarding opens the library; otherwise you can start again. Re-indexing resumes without reprocessing unchanged documents. A partially embedded document is saved only after all its passages finish.

To share a real Windows folder without editing configuration, run:

```powershell
.\scripts\launch.ps1
```

The Windows folder picker selects the host folder to expose read-only to Docker. Onboarding inside Providence then lets you index `/documents` or selected subfolders. You can choose multiple subfolders by clicking **Add folder** again. To avoid the picker, use `scripts\launch.ps1 -DocumentsPath 'C:\Your\Folder'`; use `-Demo` for the bundled sample files. Python still runs only in Docker.

To search your own files, create `.env` beside `compose.yaml`:

```dotenv
PROVIDENCE_DOCUMENTS=C:/Users/Totem/Documents/my-search-folder
```

Then run `docker compose up -d --force-recreate` and select `/documents` in the app. The folder is mounted **read-only**. Only mounted folders are visible inside the container. Mount a parent folder to index multiple subfolders. Switching the shared host folder returns you to onboarding so you explicitly index the new selection. Providence never automatically scans the whole system. The native desktop app can select any folder your Windows account can read.

The model is baked into the image; the SQLite index persists in the `providence-data` Docker volume. **Re-index folders** updates changed files and removes deleted files after a completed scan. Unchanged files reuse their index using file size and timestamps; changed metadata triggers a content-hash check. Small documents share inference batches and database transactions. Overlapping selected folders are scanned once. Stopped runs preserve existing files and do not prune deletions. The Explorer-style library shows indexed files immediately, with folder navigation, a details list and a resizable preview pane. PDFs display actual rendered pages with page navigation and zoom. Word previews show formatted paragraphs and tables; exact pagination and embedded images require opening the original document. TXT previews show the complete file, and Markdown previews render headings, lists and formatting. In the Docker browser desktop, **View document** displays extracted text inside Providence; it does not launch applications on your Windows host.

```powershell
docker compose logs --tail 50 providence
docker compose stop
docker compose start
```

## Test inside Docker

```powershell
docker compose --profile test build tests
docker compose --profile test run --rm tests
```

The test container has no network. Tests cover extraction (including PDF pages and DOCX tables), chunk overlap, index persistence, changes and deletions, corrupt files, embedding compatibility, real-model semantic retrieval with network access blocked, and the desktop search/preview flow.

CLI commands are also available in the running app container:

```powershell
docker compose exec providence python -m providence index /documents
docker compose exec providence python -m providence search "database proposal"
```

## Scope and limitations

- Uses CPU inference with `all-MiniLM-L6-v2`, token-aware overlapping chunks, and normalized vectors stored in SQLite. Search scans chunk vectors and selects the strongest passage per file; this MVP is intended for modest personal libraries.
- PDF text extraction does not include OCR. Scanned/empty documents are reported, and password-protected or corrupt files do not prevent other files from indexing.
- DOCX extraction includes paragraphs and tables. Embedded images and headers/footers are not indexed.
- Similarity is a ranking score, not a probability that a result is correct. The model primarily targets English text.
- The index contains document text and is not encrypted. It stays in your local Docker volume or `%USERPROFILE%\.providence` for the Windows app.
- OCR, image/voice search, duplicate detection, RAG chat and native installer packaging remain future work.

The reference plan is in [Providence_Project_Plan.md](Providence_Project_Plan.md). Delivery includes a Docker preview and a portable Windows build.

## Windows executable

Download **Providence-win-x64.zip** from [GitHub Releases](https://github.com/Totenem/Providence/releases/latest) when a release is available. Release downloads include a SHA-256 checksum. Build outputs, local indexes, environments and test artifacts are excluded from Git; application source and the icon are included.

Extract `dist/Providence-win-x64.zip`, keep the entire **Providence** folder together, and double-click `Providence.exe`. The `_internal` folder contains Python, Qt, CPU inference libraries and the model. Users do not need to install Python or Docker. First-run onboarding lets you choose multiple Windows folders; indexing only reads selected folders and their subfolders. Double-click a file or use **Open file** to launch its Windows default application. **Show in Explorer** opens Windows File Explorer with the original file selected. Document and folder counts appear in the sidebar.

This is an unsigned portable test release. Signing and installer creation remain separate release steps. Logs are written to `%LOCALAPPDATA%\Providence\logs\providence.log`.

To rebuild on Windows, install Python 3.13 and run:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-windows.txt --extra-index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\python.exe -m pip install --no-deps -e .
.\scripts\build-windows.ps1
```

`scripts/build-windows.ps1` also copies the release README and license into the output folder. The Windows build environment is isolated in `.venv`; Docker uses its own virtual environment. The model runs through Transformers with masked mean pooling and normalization, matching its published inference recipe without training/scientific-library dependencies.

The build script downloads the pinned model when it is missing, embeds the app icon, and creates the portable ZIP and checksum. It needs internet for initial dependency and model downloads.

### Publishing a Windows release

After committing and pushing the source and `.github/workflows/windows-release.yml`, push a version tag:

```powershell
git tag v0.1.0
git push origin v0.1.0
```

The **Windows release** GitHub Actions workflow runs tests, builds the executable on Windows, checks native startup, and attaches the ZIP and checksum to a GitHub Release. Use a new version tag for each release. Running the workflow manually from the Actions page creates a downloadable build artifact without publishing a Release. No executable or ZIP needs to be committed to Git.

The build verifies that packaged application code matches the current source and excludes third-party ICU DLLs that conflict with Qt's Windows ICU API. Run `scripts/verify-desktop-windows.ps1` to test the actual Windows executable: it creates an isolated index, verifies the main window starts, and closes only that test instance.
