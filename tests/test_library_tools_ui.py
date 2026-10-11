import time
from threading import Event

from PySide6.QtTest import QTest
from providence.quick_ui import QuickWindow
from test_ui import app as app, make_engine, library


def test_tools_only_start_explicitly_and_close_safely(app, tmp_path):
    engine = make_engine(tmp_path)
    root = library(tmp_path)
    (root / 'copy.txt').write_bytes((root / 'final_v3.txt').read_bytes())
    engine.index(root)
    engine.store.set_setting('onboarding_complete', '1')
    window = QuickWindow(engine, monitor=False)
    window.show()
    window.bridge.tools('duplicates')
    dialog = window.bridge.dialogs[-1]
    assert dialog.worker is None
    dialog.duplicates()
    deadline = time.monotonic() + 5
    while dialog.worker and time.monotonic() < deadline:
        QTest.qWait(10)
    assert dialog.worker is None
    assert dialog.results.topLevelItemCount() == 1
    dialog.reject()
    window.bridge.tools('images')
    dialog = window.bridge.dialogs[-1]
    dialog.query.setText('a beach')
    QTest.qWait(50)
    assert dialog.worker is None and dialog.images.embedder.model is None
    started, release = Event(), Event()

    def operation(_):
        started.set()
        release.wait(3)
        return []

    dialog.run(operation, dialog.show_images)
    while not started.is_set():
        QTest.qWait(10)
    dialog.reject()
    assert dialog.closing and dialog.cancelled.is_set()
    release.set()
    deadline = time.monotonic() + 5
    while window.bridge.dialogs and time.monotonic() < deadline:
        QTest.qWait(10)
    assert window.bridge.dialogs == []
    window.close()
