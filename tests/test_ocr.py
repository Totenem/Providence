import socket
from PIL import Image, ImageDraw, ImageFont
import pymupdf
import pytest
from providence.ocr import OCRWorker, _recognizer
from providence.engine import Engine
from providence.store import Store
from test_engine import TestEmbedder


def screenshot(path, text="DATABASE PROPOSAL 4821"):
    image = Image.new("RGB", (1100, 220), "white")
    draw = ImageDraw.Draw(image)
    if __import__("os").name == "nt":
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 48)
    else:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 48)
    draw.text((35, 65), text, font=font, fill="black")
    image.save(path)


def test_bundled_ocr_recognizes_without_network(tmp_path, monkeypatch):
    path = tmp_path / "screenshot.png"
    screenshot(path)

    def reject(*args, **kwargs):
        raise AssertionError("OCR attempted network access")

    monkeypatch.setattr(socket.socket, "connect", reject)
    monkeypatch.setattr(socket, "create_connection", reject)
    engine = _recognizer()
    output = engine(str(path))
    text = " ".join(output.txts).upper()
    assert "DATABASE" in text and "4821" in text


def test_scanned_pdf_and_image_cache_and_page_reference(tmp_path, monkeypatch):
    root = tmp_path / "documents"
    root.mkdir()
    image = root / "shot.png"
    screenshot(image)
    pdf = root / "scanned.pdf"
    with pymupdf.open() as doc:
        doc.new_page(width=1100, height=220).insert_image(
            pymupdf.Rect(0, 0, 1100, 220), filename=str(image)
        )
        doc.save(pdf)
    store = Store(tmp_path / "data" / "index.sqlite3", TestEmbedder.identity)
    engine = Engine(store, TestEmbedder())
    try:
        report = engine.index(root)
        assert not report.errors and report.indexed == 2
        result = next(r for r in engine.search("4821") if r.path == str(pdf))
        assert result.page == 1 and "DATABASE" in result.text.upper()
        assert store.file(pdf)["ocr"] == 1

        def forbidden(*args, **kwargs):
            raise AssertionError("Unchanged OCR reran")

        monkeypatch.setattr(engine.ocr_worker, "read", forbidden)
        assert engine.index(root).unchanged == 2
        # A forced re-embedding still reuses the OCR cache.
        assert engine.index(root, force=True).indexed == 2
    finally:
        engine.ocr_worker.close()


def test_mixed_pdf_preserves_native_text_without_duplicate_ocr(tmp_path):
    root = tmp_path / "documents"
    root.mkdir()
    image = tmp_path / "image.png"
    screenshot(image, "SCANNED INVOICE 9912")
    path = root / "mixed.pdf"
    with pymupdf.open() as doc:
        page = doc.new_page(width=1100, height=400)
        page.insert_text((35, 40), "Native database text", fontsize=18)
        page.insert_image(pymupdf.Rect(0, 100, 1100, 320), filename=str(image))
        doc.save(path)
    store = Store(tmp_path / "data" / "index.sqlite3", TestEmbedder.identity)
    engine = Engine(store, TestEmbedder())
    try:
        report = engine.index(root)
        assert not report.errors
        text = " ".join(row[1] for row in store.vectors())
        assert "Native database text" in text and "9912" in text
        assert text.count("Native database text") == 1
    finally:
        engine.ocr_worker.close()


def test_disabled_ocr_keeps_image_pending(tmp_path):
    root = tmp_path / "documents"
    root.mkdir()
    path = root / "shot.png"
    screenshot(path)
    store = Store(tmp_path / "data" / "index.sqlite3", TestEmbedder.identity)
    store.set_setting("ocr_enabled", "0")
    engine = Engine(store, TestEmbedder())
    engine.index(root)
    assert store.file(path)["state"] == "ocr_pending"
    assert engine.search("shot.png")[0].reason == "Filename"


def test_cancelled_ocr_preserves_pending_and_stops_worker(tmp_path):
    path = tmp_path / "shot.png"
    screenshot(path)
    worker = OCRWorker()
    with pytest.raises(ValueError, match="interrupted"):
        worker.read(path, cancelled=lambda: True)
    assert worker.process is None


def test_ocr_yields_to_new_ordinary_files_without_failure(tmp_path, monkeypatch):
    root = tmp_path / "documents"
    root.mkdir()
    image = root / "shot.png"
    screenshot(image)
    (root / "new.txt").write_text("database proposal")
    store = Store(tmp_path / "data" / "index.sqlite3", TestEmbedder.identity)
    engine = Engine(store, TestEmbedder())

    def interrupted(path, force, cancelled):
        assert cancelled()
        raise ValueError("OCR interrupted")

    monkeypatch.setattr(engine.ocr_worker, "read", interrupted)
    report = engine.index_many([root], ocr_yield=lambda: True)[0]
    assert not report.errors and report.indexed == 1
    assert store.file(image)["state"] == "ocr_pending"
    assert store.file(root / "new.txt")["state"] == "ready"
