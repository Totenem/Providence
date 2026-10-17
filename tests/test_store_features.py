import json
import pytest
from providence.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "data" / "index.sqlite3", "test-model")


def test_favorites_and_saved_searches(store, tmp_path):
    path = tmp_path / "favorite.txt"
    path.write_text("local search")
    store.discover([(path, (path.stat().st_size, path.stat().st_mtime_ns, path.stat().st_ctime_ns), path.stat().st_mtime, True)])
    assert not store.is_favorite(path)
    assert store.favorite(path)
    assert store.is_favorite(path)
    rows, total = store.list_files(favorite=True)
    assert total == 1 and rows[0]["favorite"]
    assert not store.favorite(path)

    store.save_search("Local notes", "local search", {"suffix": ".txt"}, {"days": 7})
    saved = store.saved_searches()
    assert saved[0]["name"] == "Local notes"
    assert json.loads(saved[0]["filters"])["suffix"] == ".txt"
    store.delete_saved_search(saved[0]["id"])
    assert store.saved_searches() == []
