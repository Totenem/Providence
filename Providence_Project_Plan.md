# Providence
## Offline Semantic File Search Powered by Local AI

### Vision
Providence is a privacy-first desktop application that helps users find documents by describing what they remember instead of relying on filenames or folders. All AI inference runs entirely on the user's machine, ensuring searches continue to work even without an internet connection.

### Problem
People often remember the content of a document but not where they saved it or what they named it.

Example:
> "Find the database proposal I wrote last semester."

Providence returns the correct document even if it is named `final_v3.pdf`.

### Value Proposition
- 100% Offline
- Privacy-first
- Natural language search
- Fast semantic retrieval

### How It Works
1. Select one or more folders.
2. Providence extracts text from supported files.
3. Documents are chunked into smaller passages.
4. A local embedding model converts each chunk into vectors.
5. Vectors are stored locally in SQLite.
6. Users search using natural language.
7. The application returns the most relevant files with matching snippets.

### MVP Features
- Folder indexing
- PDF, DOCX and TXT support
- Local semantic search
- Search result previews
- Re-index documents
- Dark modern desktop UI

### Tech Stack
- Python
- PySide6
- Sentence Transformers (all-MiniLM-L6-v2 or ONNX equivalent)
- SQLite
- PyMuPDF
- python-docx
- PyInstaller

### Architecture
Documents
↓
Text Extraction
↓
Chunking
↓
Local Embedding Model
↓
SQLite Vector Store
↓
Semantic Search
↓
Relevant Results

### Build Plan
Hour 1: File ingestion
Hour 2: Text extraction & chunking
Hour 3: Local embeddings
Hour 4: Semantic search
Hour 5: Desktop UI
Hour 6: Demo polish

### Future Roadmap
- OCR support
- Image search
- Voice search
- Duplicate detection
- Local RAG chat over indexed documents

### Elevator Pitch
Providence is an offline AI-powered semantic search engine for personal files. Instead of remembering filenames, users simply describe what they are looking for, and Providence instantly finds the right document using local AI while keeping every file on the user's computer.
