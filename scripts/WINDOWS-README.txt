Providence 1.0.2 for Windows (64-bit)

1. Extract the entire Providence folder before running it.
2. Double-click Providence.exe. Docker and Python are not required.
3. Review the proposed local drives, or add selected folders, then click
   Start automatic indexing. Your library stays current while the app is open.
   Pause/resume indexing from the header; searches stay available.
4. Browse the file library, or describe a document to search.
   The first index/search loads the bundled model.

Keep Providence.exe and the _internal folder together. You can move the whole
Providence folder anywhere on your PC. The model is included and runs offline.

Providence discovers files inside the selected locations that your account can
read. System/application folders, caches, reparse points and cloud placeholders
are excluded. Adjust exclusions in Locations & settings. All discovered types
support filename search. Content search includes PDF, DOCX, XLSX, PPTX, CSV/TSV,
text, Markdown, common programming/configuration files, and supported images.
Bundled offline OCR reads scanned PDFs and screenshots. Originals are unchanged.

Duplicate review compares file contents and groups byte-identical copies without
deleting anything. Image search uses the local CLIP model to rank visual content.
Open Image search, click Update image index, then enter an English description
and press Enter or Search images. Repeat the update after images change.
Visual similarity is not confidence; unrelated descriptions can return images.
XLSX uses saved values without calculating formulas. PPTX previews show extracted
slide text/tables. TIFF image tools inspect the first frame only.

Manage locations, themes, exclusions and model choice in Locations & settings.
Index health shows pending work and file errors with retry controls. Select a file for a
large preview. PDFs show rendered pages with navigation and zoom; Word previews
show formatted text and tables. Open Word files for exact layout and images.
Double-click a file or use Open file for your Windows default application.
Show in Explorer opens the original file's folder with the file selected.

MiniLM uses less memory. The bundled Qwen 0.6B model improves multilingual retrieval
and uses more CPU and memory. Switching builds a separate index before activating it.
Indexes are stored at %USERPROFILE%\.providence (index.sqlite3 or index-qwen.sqlite3).
Indexes contain extracted text and are not encrypted. Settings includes a clear-index action.
Startup logs are stored at %LOCALAPPDATA%\Providence\logs\providence.log.

This is an unsigned test build. Code signing and an installer are not included.
Source and build instructions are in source/. Dependency licenses and the
bundled model's attribution are in third-party-licenses/.
