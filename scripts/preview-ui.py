"""Render the actual Qt UI to PNGs for repeatable visual verification."""

from pathlib import Path
import sys
import shutil
import time
from threading import Event
import argparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication, QLabel, QListWidget, QTreeWidget
from PySide6.QtCore import QObject, QMetaObject
from providence.embeddings import LocalEmbedder
from providence.engine import Engine
from providence.store import Store
from providence.quick_ui import QuickWindow

PUBLIC_DEMO = False
DEMO_DOCUMENTS = ""


def settle(app):
    deadline = time.monotonic() + 0.3
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)


def capture(window, target):
    """Render public screenshots with fictional display paths, without editing images."""
    if not PUBLIC_DEMO:
        window.grab().save(str(target))
        return

    def public_value(value):
        if isinstance(value, str):
            return value.replace(DEMO_DOCUMENTS, "Demo/Documents")
        if isinstance(value, dict):
            return {key: public_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [public_value(item) for item in value]
        return value

    bridge = window.bridge
    state, rows = bridge._state, bridge._rows
    texts = [(label, label.text()) for label in window.findChildren(QLabel)]
    texts += [
        (listing.item(i), listing.item(i).text())
        for listing in window.findChildren(QListWidget)
        for i in range(listing.count())
    ]
    bridge.timer.stop()
    window.controller.refresh_timer.stop()
    try:
        bridge._state, bridge._rows = public_value(state), public_value(rows)
        for label, text in texts:
            label.setText(public_value(text))
        bridge.rowsChanged.emit()
        bridge.changed.emit()
        settle(QApplication.instance())
        assert window.grab().save(str(target))
    finally:
        bridge._state, bridge._rows = state, rows
        for label, text in texts:
            label.setText(text)
        bridge.rowsChanged.emit()
        bridge.changed.emit()
        bridge.timer.start()
        window.controller.refresh_timer.start()


def search_screenshots(app, window, engine, root):
    original = engine.search
    entered, release = Event(), Event()

    def paused(query, **kwargs):
        notify = kwargs["progress"]

        def progress(stage):
            notify(stage)
            if getattr(stage, "percent", 0) == 55:
                entered.set()
                release.wait(8)

        kwargs["progress"] = progress
        return original(query, **kwargs)

    engine.search = paused
    try:
        window.bridge.submitSearch("database proposal")
        deadline = time.monotonic() + 20
        while not entered.is_set() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        assert entered.is_set()
        settle(app)
        capture(window, root / "search-progress-dark.png")
        window.controller.search_started = time.monotonic() - 21
        window.bridge.refresh()
        settle(app)
        capture(window, root / "search-clues-dark.png")
    finally:
        release.set()
        deadline = time.monotonic() + 8
        while window.controller.search_task and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        engine.search = original


def capture_tool(window, dialog, target):
    texts = [(label, label.text()) for label in dialog.findChildren(QLabel)]
    cells = []
    for tree in dialog.findChildren(QTreeWidget):
        pending = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
        while pending:
            item = pending.pop()
            pending.extend(item.child(i) for i in range(item.childCount()))
            cells.extend((item, column, item.text(column)) for column in range(tree.columnCount()))
    try:
        if PUBLIC_DEMO:
            for label, text in texts:
                label.setText(text.replace(DEMO_DOCUMENTS, 'Demo/Documents'))
            for item, column, text in cells:
                item.setText(column, text.replace(DEMO_DOCUMENTS, 'Demo/Documents'))
        settle(QApplication.instance())
        assert dialog.grab().save(str(target))
    finally:
        for label, text in texts:
            label.setText(text)
        for item, column, text in cells:
            item.setText(column, text)


def tool_screenshots(app, window, engine, documents, output):
    from PIL import Image, ImageDraw
    from providence.library_tools import find_duplicates, clip_dir
    for name in ('invoice-original.csv', 'invoice-copy.csv'):
        (documents / name).write_text('Invoice,Amount\nZX92847,125\n', encoding='utf-8')
    for name, colour in [('image-a.png', 'red'), ('image-b.png', 'blue')]:
        image = Image.new('RGB', (320, 240), 'white')
        ImageDraw.Draw(image).rectangle((65, 30, 255, 220), fill=colour)
        image.save(documents / name)
    engine.store.set_setting('ocr_enabled', '0')
    engine.index(documents)
    window.bridge.refresh()
    for theme in ('Light', 'Dark'):
        window.controller.theme_combo.setCurrentText(theme)
        window.bridge.tools('duplicates')
        dialog = window.bridge.dialogs[-1]
        dialog.show_duplicates(find_duplicates(engine.store))
        dialog.results.setCurrentItem(dialog.results.topLevelItem(0).child(0))
        capture_tool(window, dialog, output / f'duplicates-{theme.lower()}.png')
        dialog.reject()
        window.bridge.tools('images')
        dialog = window.bridge.dialogs[-1]
        dialog.query.setText('A red square on a white background')
        if (clip_dir() / 'REVISION').is_file():
            dialog.show_image_update(dialog.images.update())
            dialog.show_images(dialog.images.search(dialog.query.text()))
            dialog.results.setCurrentItem(dialog.results.topLevelItem(0))
        capture_tool(window, dialog, output / f'images-{theme.lower()}.png')
        dialog.reject()


def main():
    global PUBLIC_DEMO, DEMO_DOCUMENTS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--public",
        action="store_true",
        help="Render demo paths instead of local filesystem paths",
    )
    parser.add_argument("--output", type=Path, default=Path(".artifacts/ui-preview"))
    args = parser.parse_args()
    PUBLIC_DEMO = args.public
    root = Path(".artifacts/ui-preview")
    root.mkdir(parents=True, exist_ok=True)
    documents = root / "documents"
    documents.mkdir(exist_ok=True)
    DEMO_DOCUMENTS = str(documents.resolve())
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    shutil.copytree("demo-documents", documents, dirs_exist_ok=True)
    embedder = LocalEmbedder()
    engine = Engine(Store(root / "data" / "index.sqlite3", embedder.identity), embedder)
    engine.index(documents)
    engine.store.set_setting("onboarding_complete", "1")
    app = QApplication([])
    window = QuickWindow(engine, monitor=False)
    window.controller.theme_combo.setCurrentText("Light")
    window.bridge.refresh()
    window.splitter.setSizes([1000, 420])
    window.show()
    settle(app)
    capture(window, output / "library-light.png")
    window.controller.theme_combo.setCurrentText("Dark")
    window.bridge.refresh()
    settle(app)
    capture(window, output / "library-dark.png")
    for index in range(60):
        window.controller.type_filter.addItem(f"Extension {index}", f".preview{index}")
    window.bridge.refresh()
    popup = window.quick.rootObject().findChild(QObject, "popup-type")
    QMetaObject.invokeMethod(popup, "open")
    settle(app)
    capture(window, output / "dropdown-dark.png")
    QMetaObject.invokeMethod(popup, "close")
    window.bridge.panel(2)
    settle(app)
    window.bridge.dialogs[0].grab().save(str(root / "settings-dark.png"))
    window.bridge.dialogs[0].resize(850, 600)
    settle(app)
    window.bridge.dialogs[0].grab().save(str(root / "settings-small.png"))
    window.bridge.dialogs[0].reject()
    search_screenshots(app, window, engine, output)
    window.bridge.panel(3)
    settle(app)
    window.bridge.dialogs[0].grab().save(str(root / "health-dark.png"))
    window.bridge.dialogs[0].reject()
    window.resize(1080, 640)
    settle(app)
    capture(window, output / "library-small.png")
    tool_screenshots(app, window, engine, documents, output)
    window.close()
    engine.ocr_worker.close()


if __name__ == "__main__":
    main()
