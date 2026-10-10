import socket
import time
import pytest
from providence.embeddings import QwenEmbedder, LocalEmbedder
from providence.paths import qwen_dir
from providence.engine import Engine
from providence.store import Store

pytestmark = pytest.mark.skipif(
    not (qwen_dir() / "REVISION").exists(),
    reason="Pinned Qwen build assets not present",
)


def test_qwen_offline_multilingual_retrieval(tmp_path, monkeypatch):
    def reject(*args, **kwargs):
        raise AssertionError("Qwen attempted network access")

    monkeypatch.setattr(socket.socket, "connect", reject)
    monkeypatch.setattr(socket, "create_connection", reject)
    root = tmp_path / "documents"
    root.mkdir()
    (root / "first.txt").write_text(
        "A monthly household budget allocates money for rent, groceries, electricity and emergency savings."
    )
    (root / "second.txt").write_text(
        "A recipe for chocolate banana bread lists ripe bananas, cocoa powder and flour."
    )
    model = QwenEmbedder()
    engine = Engine(
        Store(tmp_path / "data" / "index-qwen.sqlite3", model.identity), model
    )
    assert engine.index(root).indexed == 2
    assert engine.search("buwanang badyet ng pamilya")[0].path.endswith("first.txt")
    assert len(model.encode_queries(["household budget"])[0]) == 1024


def test_model_switch_builds_separate_index_and_retains_original(tmp_path):
    from PySide6.QtWidgets import QApplication
    from providence.ui import Window

    app = QApplication.instance() or QApplication([])
    root = tmp_path / "documents"
    root.mkdir()
    (root / "note.txt").write_text("A household budget for rent and groceries.")
    model = LocalEmbedder()
    original = Store(tmp_path / "data" / "index.sqlite3", model.identity)
    engine = Engine(original, model)
    engine.index(root)
    original.set_setting("onboarding_complete", "1")
    window = Window(engine, monitor=False)
    window.model_combo.setCurrentIndex(1)
    window.switch_model()
    # The original library remains active and browsable while rebuilding.
    assert window.engine is engine and window.query.isEnabled()
    deadline = time.monotonic() + 30
    while window.task and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)
    assert window.task is None
    assert isinstance(window.engine.embedder, QwenEmbedder)
    assert window.engine.store.path != original.path and original.count() == 1
    assert (original.path.parent / "active-model.txt").read_text() == "qwen"
    assert window.file_model.rowCount() == 1
    window.close()
