from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtCore import QObject, QMetaObject
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from threading import Event
import time

from providence.quick_ui import QuickWindow
from providence.engine import IndexProgress
from test_ui import app as app, finish, make_engine, library


def test_qml_onboarding_search_selection_and_settings(app, tmp_path):
    engine = make_engine(tmp_path)
    root = library(tmp_path)
    window = QuickWindow(engine, monitor=False)
    window.show()
    assert window.quick.status() == QQuickWidget.Status.Ready
    assert window.quick.rootObject() is not None
    assert window.quick.rootObject().childItems(), "QML must contain visible controls"
    c = window.controller
    c.add_pending_folder(root)
    window.bridge.action("start")
    finish(app, c)
    window.bridge.refresh()
    assert window.bridge.state["onboarded"]
    assert window.preview_panel.isVisible()
    assert window.bridge.rows[0]["name"] == "final_v3.txt"
    window.bridge.search("database")
    c.search()
    finish(app, c)
    window.bridge.select(0)
    assert "database proposal" in c.preview.toPlainText()
    assert window.bridge.rows[0]["match"]
    window.bridge.filter("type", c.type_filter.findData(".pdf"))
    finish(app, c)
    window.bridge.refresh()
    assert not window.bridge.rows
    window.bridge.action("clear")
    finish(app, c)
    window.bridge.panel(2)
    assert len(window.bridge.dialogs) == 1
    assert c.folders.isVisible() and c.model_combo.isVisible()
    c.theme_combo.setCurrentText("Dark")
    c.reduced_motion.setChecked(True)
    window.bridge.dialogs[0].reject()
    window.bridge.refresh()
    assert window.bridge.state["dark"] and window.bridge.state["reducedMotion"]
    assert c.pages.count() == 4
    window.bridge.panel(3)
    assert c.health_summary.isVisible()
    assert c.health_summary.text()
    assert c.health_empty.isVisible()
    window.bridge.dialogs[0].reject()
    assert c.pages.count() == 4
    window.close()


def test_typing_and_library_changes_never_search_without_submission(
    app, tmp_path, monkeypatch
):
    engine = make_engine(tmp_path)
    engine.store.set_setting("onboarding_complete", "1")
    calls = []

    def search(query, **kwargs):
        calls.append(query)
        return []

    monkeypatch.setattr(engine, "search", search)
    window = QuickWindow(engine, monitor=False)
    for query in ("d", "da", "dat", "data", "database"):
        window.bridge.search(query)
        QTest.qWait(40)
    assert calls == []
    QTest.qWait(800)
    finish(app, window.controller)
    assert calls == []
    window.controller.library_updated()
    window.bridge.filter("type", 1)
    QTest.qWait(800)
    assert calls == []
    window.bridge.search("a")
    QTest.qWait(800)
    assert calls == []
    window.bridge.submitSearch("a")
    finish(app, window.controller)
    assert calls == ["a"]
    window.bridge.search("database")
    window.bridge.submitSearch("database")
    finish(app, window.controller)
    QTest.qWait(800)
    assert calls == ["a", "database"]
    window.close()


def test_finishing_old_search_does_not_search_an_unsubmitted_draft(
    app, tmp_path, monkeypatch
):
    engine = make_engine(tmp_path)
    engine.store.set_setting("onboarding_complete", "1")
    calls = []
    entered, release = Event(), Event()

    def search(query, **kwargs):
        calls.append(query)
        if query == "original":
            entered.set()
            assert release.wait(8)
        return []

    monkeypatch.setattr(engine, "search", search)
    window = QuickWindow(engine, monitor=False)
    try:
        window.bridge.submitSearch("original")
        assert entered.wait(2)
        window.bridge.search("intermediate")
        QTest.qWait(100)
        assert not window.controller.pending_search
        window.bridge.submitSearch("intermediate")
        assert window.controller.pending_search
        window.bridge.search("latest query")
        release.set()
        finish(app, window.controller)
        QTest.qWait(100)
        assert calls == ["original"]
        QTest.qWait(800)
        assert calls == ["original"]
        window.bridge.submitSearch("latest query")
        finish(app, window.controller)
        assert calls == ["original", "latest query"]
    finally:
        release.set()
        finish(app, window.controller)
        window.close()


def test_slow_search_offers_optional_clues_once_and_reports_progress(
    app, tmp_path, monkeypatch
):
    engine = make_engine(tmp_path)
    root = library(tmp_path)
    engine.index(root)
    engine.store.set_setting("onboarding_complete", "1")
    calls = []
    entered, release = Event(), Event()

    def search(query, **kwargs):
        calls.append((query, kwargs.get("clues")))
        kwargs["progress"](IndexProgress("Finding matching passages", percent=55))
        if len(calls) == 1:
            entered.set()
            assert release.wait(8)
        return []

    monkeypatch.setattr(engine, "search", search)
    window = QuickWindow(engine, monitor=False)
    window.show()
    try:
        window.bridge.submitSearch("database")
        assert entered.wait(2)
        app.processEvents()
        c = window.controller
        popup = window.quick.rootObject().findChild(QObject, "search-clues")
        c.search_started = time.monotonic() - 19
        window.bridge.refresh()
        app.processEvents()
        assert not window.bridge.state["search"]["slow"]
        assert not popup.property("visible")
        assert window.bridge.state["search"]["percent"] == 55
        c.search_started = time.monotonic() - 21
        window.bridge.refresh()
        app.processEvents()
        assert window.bridge.state["search"]["slow"]
        assert popup.property("visible")
        assert window.bridge.state["clueFolders"][0]["label"] == "I have no clue"
        QMetaObject.invokeMethod(popup, "close")
        window.bridge.refresh()
        app.processEvents()
        assert not popup.property("visible")
        window.bridge.refineSearch(
            dict(folder=str(root.resolve()), suffix=".txt", count=1, days=30)
        )
        release.set()
        finish(app, c)
        window.bridge.refresh()
        assert len(calls) == 2 and calls[1][1]["count"] == 1
        assert window.bridge.state["search"]["percent"] == 100
        assert not window.bridge.state["search"]["running"]
    finally:
        release.set()
        finish(app, window.controller)
        window.close()


def test_progress_and_selection_do_not_reset_qml_rows(app, tmp_path):
    engine = make_engine(tmp_path)
    root = library(tmp_path)
    engine.index(root)
    engine.store.set_setting("onboarding_complete", "1")
    window = QuickWindow(engine, monitor=False)
    changes = []
    window.bridge.rowsChanged.connect(lambda: changes.append(True))
    window.bridge.select(0)
    window.controller.set_progress("Updating files")
    window.bridge.refresh()
    assert not changes
    window.close()


def test_custom_dropdown_is_bounded_and_file_rows_fit(app, tmp_path):
    engine = make_engine(tmp_path)
    root = library(tmp_path)
    engine.index(root)
    engine.store.set_setting("onboarding_complete", "1")
    window = QuickWindow(engine, monitor=False)
    window.resize(1080, 640)
    window.show()
    for index in range(80):
        window.controller.type_filter.addItem(f"Extension {index}", f".ext{index}")
    window.bridge.refresh()
    app.processEvents()
    assert QQuickStyle.name() == "Basic"
    qml = window.quick.rootObject()
    popup = qml.findChild(QObject, "popup-type")
    assert popup is not None
    QMetaObject.invokeMethod(popup, "open")
    app.processEvents()
    assert popup.property("visible")
    assert 0 < popup.property("height") <= 310
    QMetaObject.invokeMethod(popup, "close")
    QTest.qWait(50)

    def visual_item(item, name):
        if item.objectName() == name:
            return item
        for child in item.childItems():
            found = visual_item(child, name)
            if found is not None:
                return found
        return None

    entry = visual_item(qml, "file-row-0")
    assert entry is not None
    row_layout = entry.childItems()[0]
    for item in row_layout.childItems():
        assert item.x() >= 0
        assert item.x() + item.width() <= row_layout.width() + 1
    assert window.preview_panel.layout().contentsMargins().left() >= 18
    assert window.preview_container.layout().contentsMargins().right() >= 12
    window.close()
