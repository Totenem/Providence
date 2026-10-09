import time
from pathlib import Path

from PySide6.QtWidgets import QApplication

from providence.engine import Engine
from providence.store import Store
from providence.ui import Window
from test_engine import TestEmbedder


def test_window_search_preview_and_background_worker(tmp_path):
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "documents"
    root.mkdir()
    (root / "final_v3.txt").write_text("database proposal")
    engine = Engine(Store(tmp_path / "index.sqlite3", TestEmbedder.identity), TestEmbedder())
    engine.index(root)
    engine.store.set_setting("onboarding_complete", "1")
    window = Window(engine)
    window.show()
    window.query.setText("database")
    window.search()
    assert not window.search_button.isEnabled()
    assert window.busy_panel.isVisible()
    assert window.spinner.timer.isActive()
    assert window.busy_title.text() == "Loading"
    deadline = time.monotonic() + 10
    while window.task is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert window.task is None
    assert window.search_button.isEnabled()
    assert not window.busy_panel.isVisible()
    assert not window.spinner.timer.isActive()
    assert window.results.topLevelItemCount() == 1
    assert "database proposal" in window.preview.toPlainText()
    assert window.open_button.isEnabled()
    window.close()


def finish_task(app, window):
    deadline = time.monotonic() + 10
    while window.task is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert window.task is None


def test_onboarding_selects_indexes_and_persists(tmp_path):
    app = QApplication.instance() or QApplication([])
    engine = Engine(Store(tmp_path / "index.sqlite3", TestEmbedder.identity), TestEmbedder())
    root = tmp_path / "selected"
    root.mkdir()
    (root / "proposal.txt").write_text("database proposal")
    # A readable document outside the selection must remain unindexed.
    (tmp_path / "unselected.txt").write_text("private beach notes")
    window = Window(engine)
    window.show()
    assert window.pages.currentIndex() == 0
    assert not window.onboarding_continue.isEnabled()
    assert not window.home_nav.isEnabled()
    window.add_pending_folder(root)
    window.add_pending_folder(root)
    assert window.onboarding_folders.count() == 1
    window.start_onboarding()
    assert window.busy_panel.isVisible()
    assert window.busy_title.text() == "Collecting"
    assert not window.onboarding_add.isEnabled()
    finish_task(app, window)
    assert window.pages.currentIndex() == 1
    assert window.onboarded
    assert engine.store.count() == 1
    assert engine.store.setting("onboarding_complete") == "1"
    assert engine.store.roots() == [root.resolve()]
    assert not window.busy_panel.isVisible()
    window.close()
    reopened = Window(engine)
    assert reopened.pages.currentIndex() == 1
    reopened.close()


def test_onboarding_failure_is_recoverable(tmp_path):
    app = QApplication.instance() or QApplication([])
    engine = Engine(Store(tmp_path / "index.sqlite3", TestEmbedder.identity), TestEmbedder())
    window = Window(engine)
    window.show()
    window.add_pending_folder(tmp_path / "missing")
    window.start_onboarding()
    finish_task(app, window)
    assert not window.onboarded
    assert window.pages.currentIndex() == 0
    assert "unavailable" in window.onboarding_feedback.text()
    assert window.onboarding_continue.isEnabled()
    assert not window.spinner.timer.isActive()
    window.close()


def test_progress_messages_and_folder_removal(tmp_path):
    app = QApplication.instance() or QApplication([])
    engine = Engine(Store(tmp_path / "index.sqlite3", TestEmbedder.identity), TestEmbedder())
    root = tmp_path / "selected"
    root.mkdir()
    document = root / "a.txt"
    document.write_text("database")
    messages = []
    engine.index(root, progress=messages.append)
    assert any(message.startswith("Collecting") for message in messages)
    assert any(message.startswith("Loading") for message in messages)
    assert any(message.startswith("Processing") for message in messages)
    assert any(message.startswith("Indexing") for message in messages)
    engine.store.set_setting("onboarding_complete", "1")
    window = Window(engine)
    window.folders.setCurrentRow(0)
    window.remove_folder()
    finish_task(app, window)
    assert document.is_file()
    assert engine.store.count() == 0
    assert engine.store.roots() == []
    window.close()


def test_changing_shared_folder_requires_onboarding(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    engine = Engine(Store(tmp_path / "index.sqlite3", TestEmbedder.identity), TestEmbedder())
    engine.store.set_setting("onboarding_complete", "1")
    engine.store.set_setting("library_source", "C:/old-folder")
    monkeypatch.setenv("PROVIDENCE_LIBRARY_SOURCE", "C:/new-folder")
    window = Window(engine)
    assert not window.onboarded
    assert window.pages.currentIndex() == 0
    window.close()


def test_onboarding_only_keeps_selected_roots(tmp_path):
    app = QApplication.instance() or QApplication([])
    engine = Engine(Store(tmp_path / "index.sqlite3", TestEmbedder.identity), TestEmbedder())
    first, second = tmp_path / "first", tmp_path / "second"
    for root in (first, second):
        root.mkdir()
        (root / "a.txt").write_text("database")
        engine.index(root)
    window = Window(engine)
    window.show()
    window.onboarding_folders.clear()
    window.add_pending_folder(first)
    window.start_onboarding()
    finish_task(app, window)
    assert engine.store.roots() == [first.resolve()]
    assert engine.store.count() == 1
    assert (second / "a.txt").is_file()
    window.close()


def test_browse_preview_and_native_file_actions(tmp_path, monkeypatch):
    from PySide6.QtCore import Qt
    from providence.ui import QDesktopServices
    import providence.ui as ui

    app = QApplication.instance() or QApplication([])
    root = tmp_path / "library"
    root.mkdir()
    document = root / "proposal.txt"
    document.write_text("database proposal\nFull document ending")
    engine = Engine(Store(tmp_path / "index.sqlite3", TestEmbedder.identity), TestEmbedder())
    engine.index(root)
    engine.store.set_setting("onboarding_complete", "1")
    window = Window(engine)
    assert window.results.topLevelItemCount() == 1
    assert "Full document ending" in window.preview.toPlainText()
    assert window.reveal_button.isEnabled()
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toLocalFile()) or True)
    window.results.itemDoubleClicked.emit(window.results.currentItem(), 0)
    assert Path(opened[0]) == document
    revealed = []
    monkeypatch.setattr(ui.subprocess, "Popen", lambda args: revealed.append(args))
    if ui.os.name == "nt":
        window.reveal_document()
        assert revealed == [["explorer.exe", "/select,", str(document)]]
    window.browse_folder(window.folder_tree.item(0))
    assert window.results.topLevelItemCount() == 1
    assert window.location.text().endswith("library")
    document.unlink()
    window.open_document()
    assert "moved or been deleted" in window.status.text()
    window.close()


def test_pdf_and_word_previews(tmp_path):
    import pymupdf
    from docx import Document
    from providence.preview import DocumentPreview

    app = QApplication.instance() or QApplication([])
    pdf = tmp_path / "two-pages.pdf"
    with pymupdf.open() as document:
        for text in ("First page", "Second page"):
            document.new_page().insert_text((72, 72), text)
        document.save(pdf)
    preview = DocumentPreview()
    preview.resize(640, 700)
    preview.load(pdf, page=2)
    assert preview.stack.currentIndex() == 2
    assert preview.page == 1
    assert not preview.image.pixmap().isNull()
    assert not preview.next.isEnabled()
    preview.turn(-1)
    assert preview.position.text() == "Page 1 of 2"
    preview.change_zoom(.2)
    assert preview.zoom == 1.2
    word = tmp_path / "formatted.docx"
    document = Document()
    document.add_heading("Project proposal", 1)
    document.add_paragraph().add_run("Bold statement").bold = True
    document.add_table(rows=1, cols=1).cell(0, 0).text = "Table content"
    document.save(word)
    preview.load(word)
    assert preview.stack.currentIndex() == 1
    assert "Table content" in preview.toPlainText()
    assert "font-weight:700" in preview.paper.toHtml()
    preview.load(tmp_path / "missing.pdf")
    assert preview.stack.currentIndex() == 0
    assert "moved or been deleted" in preview.empty.text()
    preview.close()


def test_onboarding_percentage_and_simple_copy(tmp_path):
    from PySide6.QtWidgets import QLabel
    from providence.engine import IndexProgress
    app = QApplication.instance() or QApplication([])
    engine = Engine(Store(tmp_path / "index.sqlite3", TestEmbedder.identity), TestEmbedder())
    window = Window(engine)
    assert window.page_title.text() == "Initial indexing"
    assert window.onboarding_continue.text() == "Start indexing"
    assert not any("Offline AI" in text.text() or "A little less" in text.text()
                   for text in window.findChildren(QLabel))
    window.set_progress(IndexProgress("Processing · Creating search index", 45, 9, 20))
    assert window.busy_bar.maximum() == 100
    assert window.busy_bar.value() == 45
    assert window.busy_percent.text() == "45%"
    assert window.busy_counts.text() == "9 of 20 files processed"
    window.set_progress("Loading · Preparing the local search model")
    assert window.busy_bar.maximum() == 0
    window.close()


def test_markdown_preview(tmp_path):
    from providence.preview import DocumentPreview
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "note.md"
    path.write_text("# Heading\n\n**Bold text**\n\n- List item")
    preview = DocumentPreview()
    preview.load(path)
    assert preview.stack.currentIndex() == 1
    assert "Heading" in preview.toPlainText()
    assert "**" not in preview.toPlainText()
    assert "font-weight:700" in preview.paper.toHtml()
    preview.close()


def test_stop_onboarding_opens_library_with_saved_documents(tmp_path):
    from threading import Event
    started, release = Event(), Event()
    app = QApplication.instance() or QApplication([])
    root = tmp_path / "documents"
    root.mkdir()
    for index in range(65):
        (root / f"file-{index:03}.txt").write_text("database proposal")
    class Stopping(TestEmbedder):
        def encode(self, texts):
            started.set()
            assert release.wait(5), "Test did not release the inference batch"
            return super().encode(texts)
    engine = Engine(Store(tmp_path / "index.sqlite3", TestEmbedder.identity), Stopping())
    window = Window(engine)
    window.show()
    window.add_pending_folder(root)
    window.start_onboarding()
    assert window.stop_button.isVisible()
    assert window.stop_button.isEnabled()
    deadline = time.monotonic() + 5
    while not started.is_set() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    assert started.is_set()
    window.stop_button.click()
    assert window.index_cancel.is_set()
    assert not window.stop_button.isEnabled()
    assert window.stop_button.text() == "Stopping…"
    release.set()
    finish_task(app, window)
    assert window.onboarded
    assert window.pages.currentIndex() == 1
    assert engine.store.count() == 32
    assert window.results.topLevelItemCount() == 32
    assert window.status.text().startswith("Indexing stopped")
    engine.embedder = TestEmbedder()
    window.reindex()
    finish_task(app, window)
    assert engine.store.count() == 65
    assert "33 indexed" in window.status.text()
    assert "32 unchanged" in window.status.text()
    window.close()
