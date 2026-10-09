"""Compare the previous per-file inference loop with batched indexing locally."""
import json
import os
from pathlib import Path
import sys
import tempfile
from time import perf_counter

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
os.environ.setdefault("PROVIDENCE_MODEL_DIR", str(root / "build" / "model"))
os.environ.setdefault("HF_HOME", str(root / ".artifacts" / "hf-cache"))
from providence.documents import extract
from providence.embeddings import LocalEmbedder
from providence.engine import Engine, content_digest, normalized
from providence.store import Store

output = root / ".artifacts" / "indexing"
output.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(dir=output) as temporary:
    work = Path(temporary)
    documents = work / "Documents"
    documents.mkdir()
    for index in range(48):
        (documents / f"note-{index:03}.md").write_text(
            f"# Project {index}\n\n" + "Database proposal for a library with books, borrowers, loans and reservations. " * 4,
            encoding="utf-8")
    embedder = LocalEmbedder()
    embedder.encode(["Warm up the local model"])
    old_store = Store(work / "previous.sqlite3", embedder.identity)
    started = perf_counter()
    for path in sorted(documents.iterdir()):
        digest = content_digest(path)
        passages = embedder.passages(extract(path))
        vectors = [normalized(vector) for vector in embedder.encode([passage.text for passage in passages])]
        assert content_digest(path) == digest
        old_store.replace(path, digest, passages, vectors)
    previous = perf_counter() - started
    engine = Engine(Store(work / "batched.sqlite3", embedder.identity), embedder)
    started = perf_counter()
    report = engine.index(documents)
    batched = perf_counter() - started
    assert report.indexed == old_store.count() == 48
    started = perf_counter()
    report = engine.index(documents)
    unchanged = perf_counter() - started
    assert report.unchanged == 48
    result = {"files": 48, "model": embedder.identity, "previous_seconds": round(previous, 3),
              "batched_seconds": round(batched, 3), "speedup": round(previous / batched, 2),
              "unchanged_reindex_seconds": round(unchanged, 3),
              "note": "Synthetic short Markdown documents, warm CPU model; real folders vary."}
    (output / "benchmark.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
