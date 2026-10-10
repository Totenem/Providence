import os
import socket

from providence.documents import Passage
from providence.embeddings import LocalEmbedder
from providence.engine import Engine
from providence.store import Store


def test_real_model_offline_retrieval(tmp_path, monkeypatch):
    def reject_network(*args, **kwargs):
        raise AssertionError("Offline search attempted a network connection")

    monkeypatch.setattr(socket, "create_connection", reject_network)
    monkeypatch.setattr(socket.socket, "connect", reject_network)
    embedder = LocalEmbedder()
    engine = Engine(Store(tmp_path / "index.sqlite3", embedder.identity), embedder)
    root = tmp_path / "documents"
    root.mkdir()
    (root / "final_v3.txt").write_text(
        "Last semester I proposed a PostgreSQL database for a library with tables for books and loans."
    )
    (root / "trip.txt").write_text(
        "A beach holiday with swimming and a hotel beside the ocean."
    )
    assert engine.index(root).indexed == 2
    assert engine.search("the database proposal I wrote last semester")[
        0
    ].path.endswith("final_v3.txt")
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"


def test_token_chunks_fit_model_limit():
    embedder = LocalEmbedder()
    passages = embedder.passages(
        [Passage("PostgreSQL database optimization " * 400, page=2)]
    )
    model = embedder.load()
    assert len(passages) > 1
    assert all(p.page == 2 for p in passages)
    assert all(
        len(model.tokenizer.encode(p.text)) <= model.max_seq_length for p in passages
    )
    assert passages[0].text.startswith("PostgreSQL database optimization")
