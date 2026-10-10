"""10k artificial, single-passage files: index/lookup scale, excluding AI encoding."""

from pathlib import Path
import json
import sys
import time
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from providence.engine import Engine
from providence.documents import Passage
from providence.store import Store


def main():
    base = Path(".artifacts/scale-benchmark")
    base.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(4821)
    vectors = rng.normal(size=(10000, 384)).astype(np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)

    class Encoder:
        identity = "synthetic-384-v1"

        def encode(self, texts):
            return [vectors[4821].tolist() for _ in texts]

    store = Store(base / "index.sqlite3", Encoder.identity)
    store.clear_library()
    start = time.monotonic()
    for start_row in range(0, 10000, 200):
        entries = []
        records = []
        for i in range(start_row, start_row + 200):
            path = (base / "documents" / f"file-{i:05}.txt").resolve()
            entries.append((path, (50, i, i), time.time(), True))
            records.append(
                (
                    path,
                    str(i),
                    [Passage("Artificial vector scale sample")],
                    [vectors[i]],
                    (50, i, i),
                )
            )
        store.discover(entries)
        store.replace_many(records)
    ingestion = time.monotonic() - start
    engine = Engine(store, Encoder())
    start = time.monotonic()
    engine.search("scale query", limit=20)
    cold = time.monotonic() - start
    timings = []
    for _ in range(50):
        start = time.monotonic()
        results = engine.search("scale query", limit=20)
        timings.append((time.monotonic() - start) * 1000)
        assert results[0].path.endswith("file-04821.txt")
    output = dict(
        documents=10000,
        passages=10000,
        dimensions=384,
        synthetic=True,
        excludes_ai_encoding=True,
        sqlite_ingestion_seconds=round(ingestion, 3),
        first_graph_build_and_lookup_seconds=round(cold, 3),
        warm_hybrid_lookup_p95_ms=round(float(np.percentile(timings, 95)), 3),
        sqlite_bytes=store.path.stat().st_size,
    )
    (base / "results.json").write_text(json.dumps(output, indent=2))
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
