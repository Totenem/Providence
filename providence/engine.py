from dataclasses import dataclass, field, replace
from hashlib import file_digest
from pathlib import Path
import math
import os
import json
import time
import re
from threading import RLock, Event

from .documents import SUPPORTED, IMAGE_FORMATS, Passage, chunk, extract
from .store import Store
from .discovery import DEFAULT_EXCLUSIONS, excluded, walk_files
from .vector_index import VectorIndex
from .ocr import OCRWorker
from .search_evidence import identifiers, normalize_identifiers, word_found, explain


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
    reason: str = "Meaning"
    explanation: str = ""
    matched_words: tuple[str, ...] = ()


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
        self.model_lock = RLock()
        self.search_waiting = Event()
        self.vector_index = VectorIndex(store)
        self.ocr_worker = OCRWorker()
        self.store.recover()
        override = os.environ.get("PROVIDENCE_DATA_DIR")
        self.protected = (
            Path(override).resolve()
            if override
            else (
                self.store.path.parent.resolve()
                if self.store.path.parent.name == ".providence"
                else None
            )
        )

    def encode(self, texts, query=False):
        if query:
            self.search_waiting.set()
        elif self.search_waiting.is_set():
            time.sleep(0.02)
        try:
            with self.model_lock:
                return (
                    self.embedder.encode_queries(texts)
                    if query and hasattr(self.embedder, "encode_queries")
                    else self.embedder.encode(texts)
                )
        finally:
            if query:
                self.search_waiting.clear()

    def exclusions(self):
        return json.loads(
            self.store.setting("exclusions", json.dumps(DEFAULT_EXCLUSIONS))
        )

    def update_paths(
        self,
        paths,
        progress=lambda message: None,
        cancelled=lambda: False,
        ocr_yield=lambda: False,
    ):
        roots = self.store.roots()
        candidates = []
        for raw in paths:
            path = Path(raw)
            if not any(path.is_relative_to(root) for root in roots):
                continue
            if not path.exists():
                # Missing entries are removed only if their parent is accessible.
                if path.parent.is_dir():
                    self.store.forget(path)
                continue
            if excluded(path, self.exclusions(), self.protected):
                continue
            if path.is_file():
                candidates.append(path)
        available = [r for r in roots if r.is_dir()]
        return (
            self.index_many(
                available,
                progress,
                cancelled=cancelled,
                paths=candidates,
                ocr_yield=ocr_yield,
            )
            if available
            else []
        )

    def index(
        self,
        root: Path,
        progress=lambda message: None,
        force=False,
        cancelled=lambda: False,
    ):
        return self.index_many([root], progress, force, cancelled)[0]

    def index_many(
        self,
        roots,
        progress=lambda message: None,
        force=False,
        cancelled=lambda: False,
        paths=None,
        ocr_yield=lambda: False,
    ):
        roots = list(dict.fromkeys(Path(root).expanduser().resolve() for root in roots))
        for root in roots:
            if not root.is_dir():
                raise ValueError(f"Folder is unavailable: {root}")
        reports = {root: IndexReport() for root in roots}
        errors = {root: [] for root in roots}
        seen, owners = set(), {}
        # Scan parent selections once, even when a child folder is also selected.
        scans = [
            root
            for root in roots
            if not any(root != other and root.is_relative_to(other) for other in roots)
        ]
        progress(IndexProgress("Collecting · Discovering your files"))
        for root in roots:
            self.store.add_root(root)
        for root in scans if paths is None else []:
            if cancelled():
                break
            batch = []
            for path in walk_files(
                root, self.exclusions(), self.protected, cancelled, errors[root].append
            ):
                try:
                    signature = file_signature(path)
                    batch.append(
                        (
                            path,
                            signature,
                            path.stat().st_mtime,
                            path.suffix.lower() in SUPPORTED,
                        )
                    )
                    seen.add(str(path))
                    if path.suffix.lower() in SUPPORTED:
                        owners[path] = root
                    if len(batch) >= 100:
                        self.store.discover(batch)
                        batch = []
                        progress(
                            IndexProgress(
                                f"Collecting · {len(seen)} files found", total=len(seen)
                            )
                        )
                except OSError as error:
                    errors[root].append(error)
            self.store.discover(batch)
            progress(
                IndexProgress(f"Collecting · {len(seen)} files found", total=len(seen))
            )
        if paths is not None:
            batch = []
            for path in paths:
                try:
                    batch.append(
                        (
                            path,
                            file_signature(path),
                            path.stat().st_mtime,
                            path.suffix.lower() in SUPPORTED,
                        )
                    )
                    if path.suffix.lower() in SUPPORTED:
                        owners[path] = next(r for r in roots if path.is_relative_to(r))
                except OSError:
                    continue
            self.store.discover(batch)

        total, completed, reported_percent = len(owners), 0, 0
        snapshots = self.store.snapshots()
        pending, pending_size = [], 0

        def emit(stage, detail, partial=0, finished=False):
            nonlocal reported_percent
            percent = (
                100
                if finished
                else min(99, int(100 * (completed + partial) / max(total, 1)))
            )
            reported_percent = max(reported_percent, percent)
            progress(
                IndexProgress(f"{stage} · {detail}", reported_percent, completed, total)
            )

        def flush():
            nonlocal completed, pending_size
            if not pending:
                return
            texts = [
                passage.text for _, _, _, passages in pending for passage in passages
            ]
            passage_offsets, offset = [], 0
            for _, _, _, passages in pending:
                passage_offsets.append((offset, passages))
                offset += len(passages)
            vectors = []
            batch_size = 8 if self.store.setting("low_resource", "0") == "1" else 32
            for start in range(0, len(texts), batch_size):
                if cancelled():
                    break
                emit(
                    "Processing",
                    f"Creating search index · {len(pending)} files in this batch",
                    partial=sum(
                        min(max(start - offset, 0), len(passages)) / len(passages)
                        for offset, passages in passage_offsets
                    ),
                )
                batch = self.encode(texts[start : start + batch_size])
                if len(batch) != len(texts[start : start + batch_size]):
                    raise RuntimeError("Embedding count does not match passages")
                vectors.extend(normalized(vector) for vector in batch)
                if batch_size == 8:
                    time.sleep(0.05)
            records, offset, settled = [], 0, 0
            for path, digest, signature, passages in pending:
                # Keep only files whose complete embeddings have finished.
                if offset + len(passages) > len(vectors):
                    break
                file_vectors = vectors[offset : offset + len(passages)]
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
                self.store.state(
                    path,
                    "ready",
                    ocr=any(
                        p.ocr
                        for p in next(item[3] for item in pending if item[0] == path)
                    ),
                )
            completed += settled
            pending.clear()
            pending_size = 0
            emit("Indexing", f"{completed} of {total} files complete")

        # OCR-heavy formats run after ordinary documents, preserving quick initial results.
        for path in sorted(
            owners,
            key=lambda p: (
                p.suffix.lower() in IMAGE_FORMATS | {'.pdf'},
                str(p),
            ),
        ):
            if cancelled():
                break
            report = reports[owners[path]]
            emit("Processing", f"Reading {path.name}")
            try:
                signature = file_signature(path)
                catalog = self.store.file(path)
                force_ocr = bool(catalog and catalog["error"] == "force-ocr")
                if (
                    signature[0]
                    > int(self.store.setting("max_file_mb", "50")) * 1024 * 1024
                ):
                    raise ValueError("File exceeds the configured content size limit")
                saved = snapshots.get(str(path))
                if (
                    not force
                    and not force_ocr
                    and saved
                    and saved[0]
                    and saved[1:] == signature
                ):
                    report.unchanged += 1
                    if catalog and catalog["state"] == "pending":
                        self.store.state(
                            path,
                            "ready" if self.store.digest(path) else "empty",
                            ocr=bool(catalog["ocr"]),
                        )
                    completed += 1
                    emit("Indexing", f"Unchanged · {path.name}")
                    continue
                digest = content_digest(path)
                if not force and not force_ocr and saved and saved[0] == digest:
                    self.store.remember_signature(path, signature)
                    report.unchanged += 1
                    completed += 1
                    emit("Indexing", f"Unchanged · {path.name}")
                    continue
                self.store.state(path, "processing")
                if path.suffix.lower() in IMAGE_FORMATS | {'.pdf'}:
                    # Save native text before the OCR queue so it becomes searchable early.
                    flush()
                    if self.store.setting("ocr_enabled", "1") != "1":
                        if path.suffix.lower() != ".pdf":
                            self.store.state(
                                path, "ocr_pending", "OCR is paused in settings"
                            )
                            completed += 1
                            continue
                        payload = self.ocr_worker.read(
                            path, cancelled=cancelled, native_only=True
                        )
                        extracted = [
                            Passage(item["text"], item["page"]) for item in payload
                        ]
                    else:
                        key = self.ocr_worker.cache_key(digest, force_ocr)
                        payload = self.store.cached_ocr(key)
                        if payload is None:
                            self.store.state(path, "ocr_processing")
                            emit("OCR", f"Reading text · {path.name}")
                            payload = self.ocr_worker.read(
                                path, force_ocr, lambda: cancelled() or ocr_yield()
                            )
                            self.store.save_ocr(key, payload)
                        extracted = [
                            Passage(item["text"], item["page"], item["ocr"])
                            for item in payload
                        ]
                else:
                    extracted = extract(path)
                emit("Loading", f"Preparing local model · {path.name}")
                with self.model_lock:
                    passages = (
                        self.embedder.passages(extracted)
                        if hasattr(self.embedder, "passages")
                        else chunk(extracted)
                    )
                if not passages:
                    self.store.replace(path, digest, [], [])
                    self.store.state(
                        path,
                        "empty",
                        "No readable text was found",
                        ocr=any(p.ocr for p in extracted),
                    )
                    report.errors.append(f"{path}: no readable text was found")
                    completed += 1
                    continue
            except (RuntimeError, ImportError):
                raise
            except Exception as error:
                if ocr_yield() and path.suffix.lower() in IMAGE_FORMATS | {'.pdf'}:
                    self.store.state(
                        path, "ocr_pending", "Waiting for foreground file updates"
                    )
                    completed += 1
                    continue
                if not cancelled():
                    self.store.replace(path, "", [], [])
                self.store.state(
                    path, "pending" if cancelled() else "failed", str(error)
                )
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
            if not traversal_errors and not stopped and paths is None:
                reports[root].removed = self.store.prune(root, seen)
                self.store.prune_catalog(root, seen)
        if stopped:
            emit(
                "Stopped",
                f"{sum(report.indexed for report in reports.values())} documents saved · You can resume indexing later",
            )
        else:
            emit(
                "Indexing",
                f"Complete · {completed} of {total} files processed",
                finished=True,
            )
        return list(reports.values())

    def search(
        self,
        query: str,
        limit=100,
        progress=lambda message: None,
        filters=None,
        clues=None,
        cancelled=lambda: False,
    ):
        if not query.strip():
            return []
        query = query.strip()
        clues = clues or {}
        filters = dict(filters or {})
        remembered_folder = clues.get("folder", "")
        if remembered_folder:
            folder = Path(remembered_folder).resolve()
            if filters.get("root") and not folder.is_relative_to(
                Path(filters["root"]).resolve()
            ):
                raise ValueError(
                    "The remembered folder is outside the selected search location."
                )
            if not any(folder.is_relative_to(root) for root in self.store.roots()):
                raise ValueError("Choose a remembered folder within your library.")
            filters["root"] = folder
        if clues.get("suffix"):
            filters["suffix"] = clues["suffix"]
        if clues.get("days"):
            filters["days"] = max(1, int(clues["days"]))
        if clues.get("count"):
            limit = min(limit, max(1, min(1000, int(clues["count"]))))
        semantic_query = query
        if remembered_folder:
            semantic_query += f"\nRemembered context: a document in the {Path(remembered_folder).name} folder."
        if cancelled():
            return []
        progress(IndexProgress("Checking your search scope", percent=5))
        codes = identifiers(query)
        rows, _ = self.store.list_files(**filters, limit=1_000_000)
        eligible = {row["path"] for row in rows}
        if not eligible:
            progress(IndexProgress("No files in this scope", percent=100))
            return []
        if codes:
            progress(IndexProgress("Checking exact class and reference codes", percent=10))
            code_paths = self.store.identifier_paths(codes, cancelled)
            eligible = code_paths if eligible is None else eligible & code_paths
            if cancelled():
                return []
            if not eligible:
                progress(IndexProgress("No files match the requested codes", percent=100))
                return []
        best = {}
        ranks = {}

        def add(rows, reason, weight=1):
            seen = set()
            rank = 0
            for path, text, page, score in rows:
                if (eligible is not None and path not in eligible) or path in seen:
                    continue
                seen.add(path)
                rank += 1
                ranks[path] = ranks.get(path, 0) + weight / (60 + rank)
                previous = best.get(path)
                if (
                    not previous
                    or (
                        reason == "Meaning"
                        and previous.reason == "Meaning"
                        and score > previous.score
                    )
                    or reason != "Meaning"
                ):
                    best[path] = Result(path, text, page, score, reason)

        if self.store.count():
            progress(IndexProgress("Preparing the local search model", percent=15))
            vector = normalized(self.encode([semantic_query], query=True)[0])
            if cancelled():
                return []
            progress(IndexProgress("Finding matching passages", percent=55))
            rows = self.vector_index.search(vector, max(200, limit * 8), eligible)
            add(sorted(rows, key=lambda row: -row[3]), "Meaning")
        if cancelled():
            return []
        progress(IndexProgress("Checking exact words", percent=75))
        word_query, corrected = self.store.search_words(normalize_identifiers(query))
        words = word_query.split()
        text_reason = "Similar words" if corrected else "Text"
        word_limit = 1000 if eligible is not None else max(100, limit * 4)
        # All remembered words together are stronger evidence than one common word.
        if len(word_query.split()) > 1:
            add(
                self.store.lexical(word_query, word_limit, require_all=True),
                text_reason,
                weight=2,
            )
        add(
            self.store.lexical(word_query, word_limit),
            text_reason,
        )
        for path in self.store.names(
            query, 1000 if eligible is not None else max(100, limit * 4)
        ):
            if eligible is None or path in eligible:
                ranks[path] = ranks.get(path, 0) + 0.05
                previous = best.get(path)
                best[path] = Result(
                    path,
                    previous.text if previous else "",
                    previous.page if previous else None,
                    0.99,
                    "Filename"
                    if query.casefold() in Path(path).name.casefold()
                    else "Path",
                )
        if codes:
            for path in eligible:
                if all(word_found(word, path) for word in words):
                    in_filename = all(word_found(word, Path(path).name) for word in words)
                    ranks[path] = ranks.get(path, 0) + (0.05 if in_filename else 0.02)
                    previous = best.get(path)
                    best[path] = Result(
                        path, previous.text if previous else '',
                        previous.page if previous else None, .99,
                        'Filename' if in_filename else 'Path',
                    )
        if cancelled():
            return []
        progress(IndexProgress("Ranking your documents", percent=95))
        for path, result in best.items():
            reason, explanation, matched = explain(path, result.text, words, query, result.reason)
            best[path] = replace(
                result, reason=reason, explanation=explanation,
                matched_words=tuple(word for word in words if word in matched),
            )
            if codes and all(word in matched for word in words):
                ranks[path] += 0.04
        results = sorted(
            best.values(), key=lambda item: (-ranks[item.path], -item.score, item.path)
        )[:limit]
        if self.store.setting("reranker_enabled", "0") == "1" and results:
            # A small, deterministic local reranker. It is deliberately optional:
            # no model download or conversational generation is involved.
            query_terms = set(re.findall(r"\w+", query.casefold()))
            rescored = []
            for position, result in enumerate(results):
                evidence = set(re.findall(r"\w+", (Path(result.path).name + " " + result.text).casefold()))
                overlap = len(query_terms & evidence) / max(1, len(query_terms))
                score = ranks[result.path] + overlap * 0.08 + (0.02 if result.reason in {"Filename", "Path", "Text", "Similar words"} else 0)
                rescored.append((score, -position, result))
            results = [item[2] for item in sorted(rescored, reverse=True)]
        progress(IndexProgress("Search complete", percent=100))
        return results
