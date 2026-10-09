from dataclasses import dataclass, field
from hashlib import file_digest
from pathlib import Path
import math
import os

from .documents import SUPPORTED, chunk, extract
from .store import Store


@dataclass
class IndexReport:
    indexed: int = 0
    unchanged: int = 0
    removed: int = 0
    errors: list[str] = field(default_factory=list)
    cancelled: bool = False


@dataclass(frozen=True)
class Result:
    path: str
    text: str
    page: int | None
    score: float


class IndexProgress(str):
    """A printable stage message with real indexing progress for the desktop."""
    def __new__(cls, message, percent=0, completed=0, total=0):
        value = super().__new__(cls, message)
        value.percent = percent
        value.completed = completed
        value.total = total
        return value


def file_signature(path):
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def content_digest(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def normalized(vector):
    norm = math.sqrt(sum(float(v) ** 2 for v in vector))
    if not norm or not math.isfinite(norm):
        raise ValueError("Invalid embedding vector")
    return [float(v) / norm for v in vector]


class Engine:
    def __init__(self, store: Store, embedder):
        self.store, self.embedder = store, embedder

    def index(self, root: Path, progress=lambda message: None, force=False, cancelled=lambda: False):
        return self.index_many([root], progress, force, cancelled)[0]

    def index_many(self, roots, progress=lambda message: None, force=False, cancelled=lambda: False):
        roots = list(dict.fromkeys(Path(root).expanduser().resolve() for root in roots))
        for root in roots:
            if not root.is_dir():
                raise ValueError(f"Folder is unavailable: {root}")
        reports = {root: IndexReport() for root in roots}
        errors = {root: [] for root in roots}
        seen, owners = set(), {}
        # Scan parent selections once, even when a child folder is also selected.
        scans = [root for root in roots if not any(root != other and root.is_relative_to(other) for other in roots)]
        progress(IndexProgress("Collecting · Finding PDF, TXT, DOCX and MD files"))
        for root in roots:
            self.store.add_root(root)
        for root in scans:
            if cancelled():
                break
            for directory, folders, files in os.walk(root, onerror=errors[root].append, followlinks=False):
                if cancelled():
                    break
                folders[:] = [folder for folder in folders if folder not in {".git", ".venv", "__pycache__", ".providence"}
                              and not (Path(directory) / folder).is_symlink()]
                for filename in sorted(files):
                    if cancelled():
                        break
                    path = Path(directory) / filename
                    if path.suffix.lower() not in SUPPORTED or path.is_symlink():
                        continue
                    seen.add(str(path))
                    owners[path] = root
                progress(IndexProgress(f"Collecting · {len(seen)} supported files found", total=len(seen)))

        total, completed, reported_percent = len(owners), 0, 0
        snapshots = self.store.snapshots()
        pending, pending_size = [], 0

        def emit(stage, detail, partial=0, finished=False):
            nonlocal reported_percent
            percent = 100 if finished else min(99, int(100 * (completed + partial) / max(total, 1)))
            reported_percent = max(reported_percent, percent)
            progress(IndexProgress(f"{stage} · {detail}", reported_percent, completed, total))

        def flush():
            nonlocal completed, pending_size
            if not pending:
                return
            texts = [passage.text for _, _, _, passages in pending for passage in passages]
            passage_offsets, offset = [], 0
            for _, _, _, passages in pending:
                passage_offsets.append((offset, passages))
                offset += len(passages)
            vectors = []
            for start in range(0, len(texts), 32):
                if cancelled():
                    break
                emit("Processing", f"Creating search index · {len(pending)} files in this batch",
                     partial=sum(min(max(start - offset, 0), len(passages)) / len(passages)
                                 for offset, passages in passage_offsets))
                batch = self.embedder.encode(texts[start:start + 32])
                if len(batch) != len(texts[start:start + 32]):
                    raise RuntimeError("Embedding count does not match passages")
                vectors.extend(normalized(vector) for vector in batch)
            records, offset, settled = [], 0, 0
            for path, digest, signature, passages in pending:
                # Keep only files whose complete embeddings have finished.
                if offset + len(passages) > len(vectors):
                    break
                file_vectors = vectors[offset:offset + len(passages)]
                offset += len(passages)
                settled += 1
                try:
                    if file_signature(path) != signature:
                        raise ValueError("File changed during indexing; retry")
                    records.append((path, digest, passages, file_vectors, signature))
                except OSError as error:
                    reports[owners[path]].errors.append(f"{path}: {error}")
                    self.store.replace(path, "", [], [])
                except ValueError as error:
                    reports[owners[path]].errors.append(f"{path}: {error}")
                    self.store.replace(path, "", [], [])
            emit("Indexing", f"Saving {len(records)} files")
            self.store.replace_many(records)
            for path, *_ in records:
                reports[owners[path]].indexed += 1
            completed += settled
            pending.clear()
            pending_size = 0
            emit("Indexing", f"{completed} of {total} files complete")

        for path in sorted(owners):
            if cancelled():
                break
            report = reports[owners[path]]
            emit("Processing", f"Reading {path.name}")
            try:
                signature = file_signature(path)
                saved = snapshots.get(str(path))
                if not force and saved and saved[0] and saved[1:] == signature:
                    report.unchanged += 1
                    completed += 1
                    emit("Indexing", f"Unchanged · {path.name}")
                    continue
                digest = content_digest(path)
                if not force and saved and saved[0] == digest:
                    self.store.remember_signature(path, signature)
                    report.unchanged += 1
                    completed += 1
                    emit("Indexing", f"Unchanged · {path.name}")
                    continue
                extracted = extract(path)
                emit("Loading", f"Preparing local model · {path.name}")
                passages = self.embedder.passages(extracted) if hasattr(self.embedder, "passages") else chunk(extracted)
                if not passages:
                    self.store.replace(path, digest, [], [])
                    report.errors.append(f"{path}: no extractable text (scanned PDFs need OCR)")
                    completed += 1
                    continue
            except (RuntimeError, ImportError):
                raise
            except Exception as error:
                self.store.replace(path, "", [], [])
                report.errors.append(f"{path}: {error}")
                completed += 1
                emit("Indexing", f"Skipped unreadable file · {path.name}")
                continue
            # Share inference batches across small files, with bounded pending work.
            if pending_size + len(passages) > 128:
                flush()
            pending.append((path, digest, signature, passages))
            pending_size += len(passages)
            if pending_size >= 128:
                flush()
        flush()
        stopped = cancelled()
        for root in roots:
            containing_scan = next(scan for scan in scans if root.is_relative_to(scan))
            traversal_errors = errors[containing_scan]
            reports[root].errors.extend(str(error) for error in traversal_errors)
            reports[root].cancelled = stopped
            if not traversal_errors and not stopped:
                reports[root].removed = self.store.prune(root, seen)
        if stopped:
            emit("Stopped", f"{sum(report.indexed for report in reports.values())} documents saved · You can resume indexing later")
        else:
            emit("Indexing", f"Complete · {completed} of {total} files processed", finished=True)
        return list(reports.values())

    def search(self, query: str, limit=20, progress=lambda message: None):
        if not query.strip() or not self.store.count():
            return []
        progress("Loading · Preparing the local search model")
        vector = normalized(self.embedder.encode([query.strip()])[0])
        progress("Processing · Finding matching passages")
        best = {}
        for path, text, page, candidate in self.store.vectors():
            if len(candidate) != len(vector):
                raise RuntimeError("Embedding dimensions differ; rebuild the index")
            score = sum(a * b for a, b in zip(vector, candidate))
            if path not in best or score > best[path].score:
                best[path] = Result(path, text, page, score)
        progress("Collecting · Ranking your documents")
        return sorted(best.values(), key=lambda item: (-item.score, item.path))[:limit]
