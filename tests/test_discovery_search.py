import json
import time
import os
from providence.engine import Engine
from providence.store import Store
from providence.background import LibraryService
from providence.discovery import excluded, DEFAULT_EXCLUSIONS
from test_engine import TestEmbedder


def test_clues_scope_model_context_result_count_and_stage_progress(tmp_path):
    queries = []

    class Recording(TestEmbedder):
        def encode_queries(self, texts):
            queries.extend(texts)
            return super().encode(texts)

    root = tmp_path / "documents"
    project = root / "project"
    project.mkdir(parents=True)
    recent = project / "recent.txt"
    recent.write_text("database project proposal")
    old = project / "old.txt"
    old.write_text("database old project")
    old_time = time.time() - 90 * 86400
    os.utime(old, (old_time, old_time))
    (project / "other.md").write_text("database other project")
    store = Store(tmp_path / "data/index.sqlite3", Recording.identity)
    engine = Engine(store, Recording())
    engine.index(root)
    progress = []
    results = engine.search(
        "database",
        clues=dict(folder=str(project), suffix=".txt", days=30, count=1),
        progress=progress.append,
    )
    assert [result.path for result in results] == [str(recent)]
    assert "project folder" in queries[-1]
    assert all(0 <= stage.percent <= 100 for stage in progress)
    assert [stage.percent for stage in progress] == sorted(
        stage.percent for stage in progress
    )
    assert progress[-1].percent == 100
    before = len(queries)
    assert engine.search("database", cancelled=lambda: True) == []
    assert len(queries) == before
    engine.ocr_worker.close()


def test_catalog_lists_all_types_before_embedding(tmp_path):
    root = tmp_path / "documents"
    root.mkdir()
    (root / "invoice-4821.bin").write_bytes(b"unknown")
    (root / "note.txt").write_text("database proposal")
    observed = []

    class Observing(TestEmbedder):
        def encode(self, texts):
            rows, total = store.list_files()
            observed.append((total, {r["state"] for r in rows}))
            return super().encode(texts)

    store = Store(tmp_path / "data" / "index.sqlite3", TestEmbedder.identity)
    engine = Engine(store, Observing())
    engine.index(root)
    assert observed == [(2, {"pending", "processing", "unsupported"})] or observed == [
        (2, {"processing", "unsupported"})
    ]
    assert engine.search("invoice-4821")[0].reason == "Filename"
    assert store.file(root / "invoice-4821.bin")["state"] == "unsupported"


def test_exact_identifiers_and_filters(tmp_path):
    root = tmp_path / "documents"
    root.mkdir()
    child = root / "percent_%"
    child.mkdir()
    (child / "record.txt").write_text("invoice number ZX92847 database proposal")
    (root / "other.md").write_text("database beach")
    store = Store(tmp_path / "data" / "index.sqlite3", TestEmbedder.identity)
    engine = Engine(store, TestEmbedder())
    engine.index(root)
    assert engine.search("ZX92847")[0].path == str(child / "record.txt")
    rows, total = store.list_files(root=child, suffix=".txt", min_size=5, max_size=1000)
    assert total == 1 and rows[0]["name"] == "record.txt"
    assert (
        len(engine.search("database", filters={"root": child, "suffix": ".txt"})) == 1
    )
    assert engine.search("database", filters={"suffix": ".pdf"}) == []


def test_exclusions_remove_catalog_and_content(tmp_path):
    root = tmp_path / "documents"
    root.mkdir()
    secret = root / "private"
    secret.mkdir()
    (secret / "secret.txt").write_text("database secrets")
    (root / "public.txt").write_text("beach")
    store = Store(tmp_path / "data" / "index.sqlite3", TestEmbedder.identity)
    engine = Engine(store, TestEmbedder())
    engine.index(root)
    store.set_setting("exclusions", json.dumps([*DEFAULT_EXCLUSIONS, "private"]))
    engine.index(root)
    assert store.file(secret / "secret.txt") is None
    assert store.count() == 1
    assert excluded(secret / "secret.txt", engine.exclusions())


def test_pending_recovery_retry_and_no_id_reuse(tmp_path):
    root = tmp_path / "documents"
    root.mkdir()
    path = root / "note.txt"
    path.write_text("database")
    store = Store(tmp_path / "data" / "index.sqlite3", TestEmbedder.identity)
    engine = Engine(store, TestEmbedder())
    engine.index(root)
    first = store.vector_records()[0][0]
    path.write_text("beach")
    engine.index(root)
    assert store.vector_records()[0][0] > first
    store.state(path, "processing")
    Engine(store, TestEmbedder())
    assert store.file(path)["state"] == "pending"
    store.state(path, "failed", "locked")
    assert not store.pending()
    store.retry(path)
    assert store.pending() == [path]
    engine.update_paths([path])
    assert store.file(path)["state"] == "ready"


def test_events_move_delete_and_disconnected_root(tmp_path):
    root = tmp_path / "documents"
    root.mkdir()
    path = root / "before.txt"
    path.write_text("database")
    store = Store(tmp_path / "data" / "index.sqlite3", TestEmbedder.identity)
    engine = Engine(store, TestEmbedder())
    engine.index(root)
    moved = root / "after.txt"
    path.rename(moved)
    engine.update_paths([path, moved])
    assert store.file(path) is None and store.file(moved)["state"] == "ready"
    disconnected = tmp_path / "disconnected"
    root.rename(disconnected)
    engine.update_paths([moved])
    assert store.file(moved) is not None


def test_hnsw_rebuild_tracks_changes_and_deletes(tmp_path):
    root = tmp_path / "documents"
    root.mkdir()
    path = root / "a.txt"
    path.write_text("database")
    store = Store(tmp_path / "data" / "index.sqlite3", TestEmbedder.identity)
    engine = Engine(store, TestEmbedder())
    engine.index(root)
    assert engine.search("database")[0].text == "database"
    path.write_text("beach vacation")
    engine.update_paths([path])
    assert engine.search("beach")[0].text == "beach vacation"
    path.unlink()
    engine.update_paths([path])
    assert engine.search("beach") == []


def test_service_pause_resume_and_reconciliation(tmp_path):
    root = tmp_path / "documents"
    root.mkdir()
    path = root / "note.txt"
    path.write_text("database")
    store = Store(tmp_path / "data" / "index.sqlite3", TestEmbedder.identity)
    engine = Engine(store, TestEmbedder())
    store.add_root(root)
    service = LibraryService(engine)
    service.set_paused(True)
    service.start()
    try:
        time.sleep(0.7)
        assert store.file(path) is None
        service.set_paused(False)
        deadline = time.monotonic() + 8
        while (
            not store.file(path) or store.file(path)["state"] != "ready"
        ) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert store.file(path)["state"] == "ready"
        # Simulate a missed notification. A requested recovery scan catches it.
        service.set_paused(True)
        added = root / "missed.txt"
        added.write_text("beach")
        service.request_scan()
        service.set_paused(False)
        deadline = time.monotonic() + 8
        while (
            not store.file(added) or store.file(added)["state"] != "ready"
        ) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert store.file(added)["state"] == "ready"
    finally:
        assert service.close()
