"""Cached HNSW candidate lookup; SQLite remains the recoverable source of truth."""

from threading import RLock
import numpy as np


class VectorIndex:
    def __init__(self, store):
        self.store = store
        self.revision = None
        self.index = None
        self.lock = RLock()
        self.scoped = {}
        self.records = []

    def search(self, vector, count=100, eligible=None):
        from usearch.index import Index

        with self.lock:
            revision = self.store.setting("vector_revision", "0")
            if revision != self.revision:
                records = self.store.vector_records(with_paths=True)
                self.records = records
                self.scoped.clear()
                self.index = None
                if records:
                    vectors = np.stack(
                        [
                            np.frombuffer(blob, dtype=np.float32)
                            for _, _, blob in records
                        ]
                    )
                    if vectors.shape[1] != len(vector):
                        raise RuntimeError(
                            "Embedding dimensions differ; rebuild the index"
                        )
                    self.index = Index(
                        ndim=len(vector),
                        metric="cos",
                        dtype="f32",
                        expansion_search=128,
                    )
                    self.index.add(
                        np.array([key for key, _, _ in records], dtype=np.uint64),
                        vectors,
                        threads=2,
                    )
                self.revision = revision
            index = self.index
            if eligible is not None:
                scope = frozenset(eligible)
                if scope not in self.scoped:
                    records = [
                        (key, blob) for key, path, blob in self.records if path in scope
                    ]
                    scoped = None
                    if records:
                        scoped = Index(
                            ndim=len(vector),
                            metric="cos",
                            dtype="f32",
                            expansion_search=128,
                        )
                        scoped.add(
                            np.array([key for key, _ in records], dtype=np.uint64),
                            np.stack(
                                [
                                    np.frombuffer(blob, dtype=np.float32)
                                    for _, blob in records
                                ]
                            ),
                            threads=2,
                        )
                    if len(self.scoped) >= 3:
                        self.scoped.pop(next(iter(self.scoped)))
                    self.scoped[scope] = scoped
                index = self.scoped[scope]
            if index is None:
                return []
            matches = index.search(
                np.asarray(vector, dtype=np.float32), min(count, len(index)), threads=1
            )
            scores = {
                int(key): max(-1.0, min(1.0, 1 - float(distance)))
                for key, distance in zip(matches.keys, matches.distances)
            }
            return [
                (path, text, page, scores[key])
                for key, path, text, page in self.store.chunks_by_ids(list(scores))
            ]
