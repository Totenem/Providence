"""Qt Quick library shell sharing the proven desktop services and rich preview."""

import json
import time
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer, QUrl, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import (
    QMainWindow,
    QSplitter,
    QDialog,
    QVBoxLayout,
    QScrollArea,
    QWidget,
    QLabel,
)

from .ui import Window, SLOW_SEARCH_SECONDS

# Native Windows controls ignore custom QML backgrounds during hover/open.
# Basic renders our own control delegates consistently on all platforms.
QQuickStyle.setStyle("Basic")


class LibraryBridge(QObject):
    changed = Signal()
    rowsChanged = Signal()

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._state = {}
        self._rows = []
        self._clue_session = None
        self._clue_folders = []
        self.dialogs = []
        self.refresh()
        self.timer = QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        controller.refresh_timer.timeout.connect(self.refresh_panels)

    def refresh_panels(self):
        if any(dialog.property("panelPage") == 3 for dialog in self.dialogs):
            self.controller.refresh_health()

    @Property("QVariantMap", notify=changed)
    def state(self):
        return self._state

    @Property("QVariantList", notify=rowsChanged)
    def rows(self):
        return self._rows

    def refresh(self):
        c = self.controller
        rows = []
        for row in c.file_model.rows:
            result = row.get("result")
            rows.append(
                dict(
                    path=row["path"],
                    name=row["name"],
                    kind=row["suffix"].lstrip(".").upper(),
                    status="Unavailable"
                    if not row.get("available", True)
                    else row["state"].replace("_", " "),
                    size=f"{row['size'] / 1024:,.0f} KB",
                    match=("Related" if result.reason == "Meaning" else result.reason)
                    if result else "",
                    explanation=result.explanation if result else "",
                )
            )
        roots = [str(p) for p in c.engine.store.roots()]
        pending = [
            c.onboarding_folders.item(i).text()
            for i in range(c.onboarding_folders.count())
        ]
        selected = c.current_row()
        crumbs = [dict(name="Library", path="")]
        if c.active_root:
            base = next(
                (r for r in c.engine.store.roots() if c.active_root.is_relative_to(r)),
                c.active_root,
            )
            parts = [base] + [
                base.joinpath(*c.active_root.relative_to(base).parts[:i])
                for i in range(1, len(c.active_root.relative_to(base).parts) + 1)
            ]
            crumbs += [dict(name=p.name or str(p), path=str(p)) for p in parts[-3:]]
        folders = (
            c.engine.store.children(str(c.active_root)) if c.active_root else roots
        )
        theme = c.theme_combo.currentText()
        dark = theme == "Dark" or (
            theme == "System" and c.palette().window().color().lightness() < 128
        )
        if rows != self._rows:
            self._rows = rows
            self.rowsChanged.emit()
        searching = bool(c.search_task) and (
            not c.search_cancel.is_set() or c.pending_search
        )
        elapsed = (
            int(time.monotonic() - c.search_started)
            if searching and c.search_started and not c.pending_search
            else 0
        )
        slow = searching and elapsed > SLOW_SEARCH_SECONDS and c.search_percent < 100
        if slow and self._clue_session != c.search_session:
            remembered = roots + ([str(c.active_root)] if c.active_root else [])
            for root in roots:
                remembered += c.engine.store.children(root)
            self._clue_folders = [dict(label="I have no clue", value="")] + [
                dict(label=path, value=path) for path in dict.fromkeys(remembered)
            ]
            self._clue_session = c.search_session
        state = dict(
            roots=roots,
            pending=pending,
            onboarded=c.onboarded,
            selected=selected["path"] if selected else "",
            query=c.query.text(),
            summary=c.summary.text(),
            status=c.status.text(),
            emptyMessage=c.results_empty.text(),
            count=c.count_label.text(),
            progress=c.busy_message.text(),
            phase=c.busy_title.text(),
            busy=c.busy_panel.isHidden() is False,
            pause=c.pause_button.text(),
            paging=c.page_label.text(),
            previous=c.previous_page.isEnabled(),
            next=c.next_page.isEnabled(),
            back=c.back_button.isEnabled(),
            forward=c.forward_button.isEnabled(),
            up=c.up_button.isEnabled(),
            crumbs=crumbs,
            folders=[dict(name=Path(p).name or p, path=p) for p in folders],
            feedback=c.onboarding_feedback.text(),
            dark=dark,
            reducedMotion=c.reduced_motion.isChecked(),
            search=dict(
                running=searching,
                pending=c.pending_search,
                percent=c.search_percent,
                phase=c.search_phase,
                elapsed=elapsed,
                slow=slow,
                session=c.search_session,
                helper=c.search_helpers[(elapsed // 5) % len(c.search_helpers)],
            ),
            clueFolders=self._clue_folders or [dict(label="I have no clue", value="")],
            filters={
                name: dict(
                    items=[combo.itemText(i) for i in range(combo.count())],
                    index=combo.currentIndex(),
                )
                for name, combo in self.filter_controls().items()
            },
        )
        if state != self._state:
            self._state = state
            self.changed.emit()

    def filter_controls(self):
        c = self.controller
        return dict(
            type=c.type_filter,
            status=c.state_filter,
            date=c.date_filter,
            size=c.size_filter,
            sort=c.sort_filter,
        )

    @Slot(str, int)
    def filter(self, name, index):
        combo = self.filter_controls().get(name)
        if combo and 0 <= index < combo.count():
            combo.setCurrentIndex(index)
        self.refresh()

    @Slot(str)
    def search(self, query):
        c = self.controller
        c.query.setText(query)
        c.edit_search()
        self.refresh()

    @Slot(str)
    def submitSearch(self, query):
        c = self.controller
        c.query.setText(query)
        c.search()
        self.refresh()

    @Slot("QVariantMap")
    def refineSearch(self, clues):
        self.controller.search_clues = dict(clues)
        self.controller.search()
        self.refresh()

    @Slot(str)
    def browse(self, path):
        self.controller.browse_library(path or None)
        self.refresh()

    @Slot(int)
    def select(self, index):
        c = self.controller
        if 0 <= index < len(c.file_model.rows):
            c.results.setCurrentIndex(c.file_model.index(index, 0))
        self.refresh()

    @Slot(str)
    def action(self, name):
        c = self.controller
        actions = dict(
            pause=c.toggle_pause,
            add=c.add_folder,
            choose=c.choose_onboarding_folder,
            drives=c.select_drives,
            start=c.start_onboarding,
            open=c.open_document,
            reveal=c.reveal_document,
            copy=c.copy_path,
            passage=c.copy_passage,
            retry=c.retry_current,
            clear=c.clear_filters,
            up=c.go_up,
            back=lambda: c.history_move(-1),
            forward=lambda: c.history_move(1),
            previous=lambda: c.page_move(-1),
            next=lambda: c.page_move(1),
        )
        if name in actions:
            actions[name]()
        self.refresh()

    @Slot(int)
    def removePending(self, index):
        c = self.controller
        c.onboarding_folders.setCurrentRow(index)
        c.remove_pending_folder()
        self.refresh()

    @Slot(int)
    def panel(self, page):
        """Reuse accessible native settings/health without duplicating state."""
        if page not in (2, 3):
            return
        c = self.controller
        widget = c.pages.widget(page)
        if widget is None:
            return
        c.navigate(page)
        dialog = QDialog(self.parent())
        dialog.setProperty("panelPage", page)
        dialog.setWindowTitle(
            "Providence · "
            + ("Locations and settings" if page == 2 else "Index health")
        )
        dialog.resize(980, 700)
        dialog.setMinimumSize(850, 600)
        dialog.setStyleSheet(c.styleSheet())
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 22, 22, 22)
        heading = QLabel("Locations & settings" if page == 2 else "Index health")
        heading.setObjectName("title")
        layout.addWidget(heading)
        scroll = QScrollArea(dialog)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        c.pages.removeWidget(widget)
        widget.setObjectName("settingsPage" if page == 2 else "healthPage")
        scroll.setWidget(widget)
        layout.addWidget(scroll)
        widget.show()
        self.dialogs.append(dialog)

        def restore():
            scroll.takeWidget()
            c.pages.insertWidget(page, widget)
            c.navigate(1 if c.onboarded else 0)
            self.dialogs.remove(dialog)
            dialog.deleteLater()
            self.refresh()

        dialog.finished.connect(restore)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.open()
        widget.show()

    @Slot(str)
    def tools(self, mode):
        if mode not in ('duplicates', 'images'):
            return
        from .library_tools_ui import LibraryToolsDialog
        for dialog in self.dialogs:
            if getattr(dialog, 'mode', None) == mode:
                dialog.raise_()
                return
        dialog = LibraryToolsDialog(self.controller, mode, self.parent())
        self.dialogs.append(dialog)
        dialog.finished.connect(lambda: self.dialogs.remove(dialog))
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.open()


class QuickWindow(QMainWindow):
    def __init__(self, engine, monitor=True):
        super().__init__()
        self.controller = Window(engine, monitor=monitor)
        self.setWindowTitle(self.controller.windowTitle())
        self.setWindowIcon(self.controller.windowIcon())
        self.resize(1450, 860)
        self.setMinimumSize(1080, 640)
        self.setAcceptDrops(True)
        self.bridge = LibraryBridge(self.controller, self)
        self.quick = QQuickWidget(self)
        self.quick.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self.quick.rootContext().setContextProperty("library", self.bridge)
        self.quick.setSource(
            QUrl.fromLocalFile(str(Path(__file__).with_name("qml") / "Library.qml"))
        )
        if self.quick.status() == QQuickWidget.Status.Error:
            raise RuntimeError(
                "\n".join(error.toString() for error in self.quick.errors())
            )
        self.preview_panel = self.controller.splitter.widget(1)
        self.preview_panel.setObjectName("previewPanel")
        self.preview_panel.layout().setContentsMargins(18, 20, 18, 18)
        self.preview_panel.layout().setSpacing(12)
        self.preview_panel.setMinimumWidth(340)
        self.preview_container = QWidget()
        preview_layout = QVBoxLayout(self.preview_container)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_layout.addWidget(self.preview_panel)
        self.splitter = QSplitter()
        self.splitter.addWidget(self.quick)
        self.splitter.addWidget(self.preview_container)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        self.setCentralWidget(self.splitter)
        saved = engine.store.setting("quick_pane_sizes", "[1000, 420]")
        try:
            self.splitter.setSizes(json.loads(saved))
        except (ValueError, TypeError):
            self.splitter.setSizes([1000, 420])
        self.bridge.changed.connect(self.sync)
        self.sync()
        for keys, action in [
            ("Alt+Left", "back"),
            ("Alt+Right", "forward"),
            ("Alt+Up", "up"),
            ("Ctrl+Shift+C", "copy"),
        ]:
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.activated.connect(lambda a=action: self.bridge.action(a))
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(
            self.controller.find_input.setFocus
        )

    def sync(self):
        self.preview_panel.setVisible(self.controller.onboarded)
        self.preview_container.setVisible(self.controller.onboarded)
        self.setStyleSheet(self.controller.styleSheet())
        for dialog in self.bridge.dialogs:
            dialog.setStyleSheet(self.controller.styleSheet())

    def dragEnterEvent(self, event):
        self.controller.dragEnterEvent(event)

    def dropEvent(self, event):
        self.controller.dropEvent(event)
        self.bridge.refresh()

    def closeEvent(self, event):
        working = [dialog for dialog in self.bridge.dialogs if getattr(dialog, 'worker', None)]
        if working:
            for dialog in working:
                dialog.close()
            event.ignore()
            QTimer.singleShot(200, self.close)
            return
        self.controller.closeEvent(event)
        if event.isAccepted():
            self.controller.engine.store.set_setting(
                "quick_pane_sizes", json.dumps(self.splitter.sizes())
            )
            self.bridge.timer.stop()
        else:
            QTimer.singleShot(200, self.close)
