Providence for Windows (64-bit)

1. Extract the entire Providence folder before running it.
2. Double-click Providence.exe. Docker and Python are not required.
3. In Initial indexing, add one or more folders and click Start indexing.
   Stop indexing keeps complete documents already saved. Re-index to resume.
4. Browse the file library, or describe a document to search.
   The first index/search loads the bundled model.

Keep Providence.exe and the _internal folder together. You can move the whole
Providence folder anywhere on your PC. The model is included and runs offline.

Providence only indexes selected folders and their subfolders that your Windows
account can read. Only PDF, TXT, DOCX and MD are indexed; other formats, including
legacy DOC, are skipped automatically. Scanned PDFs require OCR, which
is not yet included. Original documents are never modified.

Manage your folders and re-index them from Indexed folders. Select a file for a
large preview. PDFs show rendered pages with navigation and zoom; Word previews
show formatted text and tables. Open Word files for exact layout and images.
Double-click a file or use Open file for your Windows default application.
Show in Explorer opens the original file's folder with the file selected.

Your index is stored at %USERPROFILE%\.providence\index.sqlite3.
Startup logs are stored at %LOCALAPPDATA%\Providence\logs\providence.log.

This is an unsigned test build. Code signing and an installer are not included.
Source and build instructions are in source/. Dependency licenses and the
bundled model's attribution are in third-party-licenses/.
