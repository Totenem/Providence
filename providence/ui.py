"""Desktop workspace and first-run folder selection."""
import math
import os
import subprocess
from threading import Event
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, QUrl, QRectF, Signal, Slot
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QIcon
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QSplitter, QStackedWidget, QTextEdit, QVBoxLayout, QWidget,
    QTreeWidget, QTreeWidgetItem, QAbstractItemView, QStyle,
)

from .engine import Engine, Result, IndexProgress
from .preview import DocumentPreview
from .paths import model_dir


STYLE = """
QWidget { color: #242927; font-family: 'Segoe UI', 'DejaVu Sans'; font-size: 13px; }
QMainWindow, QWidget#shell { background: #f3f4f3; }
QWidget#sidebar, QFrame#card { background: #ffffff; border-radius: 0px; }
QWidget#sidebar { border-right: 1px solid #dfe5e0; }
QTreeWidget { background: #ffffff; border: none; outline: none; }
QTreeWidget::item { height: 44px; border-bottom: 1px solid #edf0ed; }
QTreeWidget::item:selected { background: #e4f4e9; color: #245e3c; }
QTreeWidget::item:hover { background: #f1f7f3; }
QHeaderView::section { background: #f8faf8; color: #6f7772; padding: 10px; border: none; border-bottom: 1px solid #e0e6e1; }
QTextBrowser#paper { background: white; border: 1px solid #dfe5e0; border-radius: 0; font-size: 15px; }
QScrollArea { background: #e9ede9; border: none; }
QLabel { background: transparent; border: none; }
QLabel#brand { font-size: 19px; font-weight: 700; }
QLabel#title { font-size: 24px; font-weight: 600; }
QLabel#hero { font-size: 34px; font-weight: 600; }
QLabel#muted { color: #7c837f; }
QLabel#eyebrow { color: #6f7772; font-size: 11px; }
QLabel#metric { font-size: 28px; font-weight: 600; }
QLabel#badge { color: #2b8b54; background: #e4f6eb; border-radius: 7px; padding: 6px 10px; }
QLabel#error { color: #af493e; }
QPushButton { background: #ffffff; border: 1px solid #e4e7e4; border-radius: 8px; padding: 10px 15px; }
QPushButton:hover { background: #f2f6f3; border-color: #bddbc8; }
QPushButton:disabled { background: #f4f5f4; color: #a1a8a3; border-color: #eceeec; }
QPushButton#primary { background: #4fc47e; border: none; color: #123b23; font-weight: 600; }
QPushButton#primary:hover { background: #43b972; }
QPushButton#primary:disabled { background: #d3ecdc; color: #7ea28a; }
QPushButton#nav { text-align: left; border: none; background: transparent; padding: 12px 15px; }
QPushButton#nav:checked { background: #eff3ef; color: #26774a; font-weight: 600; }
QLineEdit { background: #f7f8f7; border: 1px solid #e7eae7; border-radius: 9px; padding: 13px; }
QLineEdit:focus { border: 1px solid #5dc88a; }
QListWidget, QTextEdit { background: #ffffff; border: none; border-radius: 8px; padding: 4px; }
QListWidget::item { padding: 14px 10px; border-bottom: 1px solid #f0f2f0; border-radius: 6px; }
QListWidget::item:selected { color: #245e3c; background: #eaf7ee; }
QListWidget::item:hover { background: #f5f9f6; }
QProgressBar { border: none; border-radius: 5px; background: #e8eee9; min-height: 10px; max-height: 10px; }
QProgressBar::chunk { background: #52c580; border-radius: 3px; }
QSplitter::handle { background: #f3f4f3; }
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: #d8dfd9; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


def label(text, name=None):
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(True)
    return widget


def card():
    frame = QFrame(objectName="card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(22, 20, 22, 20)
    layout.setSpacing(12)
    return frame, layout


class Spinner(QWidget):
    """Small animated spinner driven by the GUI event loop."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(26, 26)
        self.setAccessibleName("Operation in progress")
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.setInterval(70)
        self.timer.timeout.connect(self.advance)

    def advance(self):
        self.angle = (self.angle + 1) % 12
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(12):
            color = QColor("#40b972")
            color.setAlpha(45 + ((i - self.angle) % 12) * 18)
            painter.setBrush(color)
            angle = i * math.pi / 6
            painter.drawEllipse(QRectF(11 + 9 * math.cos(angle), 11 + 9 * math.sin(angle), 3.5, 3.5))


class Task(QThread):
    success = Signal(object)
    failure = Signal(str)
    progress = Signal(object)

    def __init__(self, operation, parent):
        super().__init__(parent)
        self.operation = operation

    def run(self):
        try:
            self.success.emit(self.operation(self.progress.emit))
        except Exception as error:
            self.failure.emit(str(error))


class Window(QMainWindow):
    def __init__(self, engine: Engine):
        super().__init__()
        self.engine = engine
        self.task = None
        self._onboarding_job = False
        self.index_cancel = Event()
        self._indexing_job = False
        self.library_source = os.environ.get("PROVIDENCE_LIBRARY_SOURCE", "")
        self.source_changed = self.engine.store.setting("library_source", "") != self.library_source
        self.onboarded = (self.engine.store.setting("onboarding_complete") == "1"
                          and self.engine.store.setting("library_source", "") == self.library_source)
        self.setWindowTitle("Providence · File library")
        self.setWindowIcon(QIcon(str(Path(__file__).with_name('assets') / 'providence.ico')))
        self.resize(1440, 900)
        self.setMinimumSize(940, 650)
        self.setStyleSheet(STYLE)
        shell = QWidget(objectName="shell")
        self.setCentralWidget(shell)
        outer = QHBoxLayout(shell)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QWidget(objectName="sidebar")
        sidebar.setFixedWidth(205)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 23, 16, 20)
        side.setSpacing(7)
        side.addWidget(label("◈  Providence", "brand"))
        side.addWidget(label("Your private file library", "muted"))
        side.addSpacing(30)
        self.home_nav = QPushButton("▤   All documents", objectName="nav")
        self.folder_nav = QPushButton("▧   Indexed folders", objectName="nav")
        for button in (self.home_nav, self.folder_nav):
            button.setCheckable(True)
            side.addWidget(button)
        self.home_nav.clicked.connect(lambda: self.navigate(1))
        self.folder_nav.clicked.connect(lambda: self.navigate(2))
        side.addSpacing(24)
        side.addWidget(label("PINNED FOLDERS", "eyebrow"))
        self.folder_tree = QListWidget()
        self.folder_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.folder_tree.setAccessibleName("Browse indexed folders")
        self.folder_tree.itemClicked.connect(self.browse_folder)
        side.addWidget(self.folder_tree, 1)
        side.addStretch()
        self.count_label = label("", "muted")
        side.addWidget(self.count_label)
        side.addSpacing(15)
        side.addWidget(label("Your files stay on your device.", "muted"))
        outer.addWidget(sidebar)

        body = QVBoxLayout()
        body.setContentsMargins(20, 20, 20, 12)
        body.setSpacing(12)
        header = QHBoxLayout()
        self.page_title = label("Initial indexing", "title")
        header.addWidget(self.page_title, 1)
        body.addLayout(header)

        self.busy_panel, busy_layout = card()
        busy_layout.setContentsMargins(18, 12, 18, 12)
        busy_row = QHBoxLayout()
        self.spinner = Spinner()
        busy_row.addWidget(self.spinner)
        busy_text = QVBoxLayout()
        self.busy_title = label("Collecting", "brand")
        self.busy_percent = label("0%", "brand")
        self.busy_counts = label("Finding supported files…", "muted")
        self.busy_message = label("Preparing your documents…", "muted")
        busy_text.addWidget(self.busy_title)
        busy_text.addWidget(self.busy_message)
        busy_text.addWidget(self.busy_counts)
        busy_row.addLayout(busy_text, 1)
        busy_row.addWidget(self.busy_percent)
        self.stop_button = QPushButton("Stop indexing")
        self.stop_button.clicked.connect(self.stop_indexing)
        busy_row.addWidget(self.stop_button)
        busy_layout.addLayout(busy_row)
        self.busy_bar = QProgressBar()
        self.busy_bar.setRange(0, 0)
        self.busy_bar.setTextVisible(False)
        busy_layout.addWidget(self.busy_bar)
        self.busy_panel.hide()
        body.addWidget(self.busy_panel)

        self.pages = QStackedWidget()
        body.addWidget(self.pages, 1)
        self.build_onboarding()
        self.build_search()
        self.build_folders()
        self.status = label("Ready · All processing happens on this device.", "muted")
        body.addWidget(self.status)
        outer.addLayout(body, 1)
        self.controls = [self.home_nav, self.folder_nav, self.add_button, self.reindex_button,
                         self.remove_button, self.search_button, self.query, self.onboarding_add,
                         self.onboarding_remove, self.onboarding_continue, self.open_button,
                         self.reveal_button, self.folder_tree, self.all_button]
        self.refresh_library()
        for root in self.engine.store.roots():
            self.add_pending_folder(root)
        self.navigate(1 if self.onboarded else 0)
        if self.onboarded:
            self.browse_library()

    def build_onboarding(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.addWidget(label("Select the folders to index. Subfolders are included.", "muted"))
        selection, select = card()
        row = QHBoxLayout()
        row.addWidget(label("Folders to index", "brand"), 1)
        formats = label("PDF  ·  TXT  ·  DOCX  ·  MD", "muted")
        formats.setWordWrap(False)
        row.addWidget(formats)
        select.addLayout(row)
        self.onboarding_folders = QListWidget()
        self.onboarding_folders.setMinimumHeight(110)
        self.onboarding_folders.setMaximumHeight(260)
        self.onboarding_folders.setAccessibleName("Selected folders for initial indexing")
        select.addWidget(self.onboarding_folders, 1)
        self.onboarding_empty = label("No folders selected. Use Add folder to choose a location.", "muted")
        select.addWidget(self.onboarding_empty)
        buttons = QHBoxLayout()
        self.onboarding_add = QPushButton("+ Add folder")
        self.onboarding_add.clicked.connect(self.choose_onboarding_folder)
        self.onboarding_remove = QPushButton("Remove selected")
        self.onboarding_remove.clicked.connect(self.remove_pending_folder)
        buttons.addWidget(self.onboarding_add)
        buttons.addWidget(self.onboarding_remove)
        buttons.addStretch()
        self.onboarding_continue = QPushButton("Start indexing", objectName="primary")
        self.onboarding_continue.clicked.connect(self.start_onboarding)
        buttons.addWidget(self.onboarding_continue)
        select.addLayout(buttons)
        hint = ("In this Docker preview, choose /documents or a subfolder. To use a Windows folder, start scripts/launch.ps1 and choose it in the Windows folder picker."
                if os.environ.get("PROVIDENCE_CONTAINER") else
                "Only PDF, TXT, DOCX and MD files are indexed. Other file types are skipped. Original files are never modified.")
        select.addWidget(label(hint, "muted"))
        self.onboarding_feedback = label("", "error")
        select.addWidget(self.onboarding_feedback)
        layout.addWidget(selection)
        layout.addStretch(1)
        self.pages.addWidget(page)
        self.update_pending_controls()

    def build_search(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        address = QHBoxLayout()
        self.all_button = QPushButton("↑  All documents")
        self.all_button.clicked.connect(self.browse_library)
        address.addWidget(self.all_button)
        self.location = label("Library  ›  All documents", "muted")
        address.addWidget(self.location, 1)
        self.query = QLineEdit()
        self.query.setPlaceholderText("Search by name, topic, or what you remember…")
        self.query.setAccessibleName("Describe a document")
        self.query.returnPressed.connect(self.search)
        address.addWidget(self.query, 2)
        self.search_button = QPushButton("Search", objectName="primary")
        self.search_button.clicked.connect(self.search)
        address.addWidget(self.search_button)
        layout.addLayout(address)
        commands = QHBoxLayout()
        commands.setContentsMargins(0, 12, 0, 12)
        add = QPushButton("+ Add folder")
        add.clicked.connect(self.add_folder)
        refresh = QPushButton("↻ Re-index")
        refresh.clicked.connect(self.reindex)
        commands.addWidget(add)
        commands.addWidget(refresh)
        self.library_commands = [add, refresh]
        commands.addStretch()
        view_hint = label("Details view  ·  Preview pane", "muted")
        view_hint.setWordWrap(False)
        commands.addWidget(view_hint)
        layout.addLayout(commands)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(6)
        files = QWidget()
        files_layout = QVBoxLayout(files)
        files_layout.setContentsMargins(0, 0, 0, 0)
        self.summary = label("All indexed documents", "muted")
        files_layout.addWidget(self.summary)
        self.results = QTreeWidget()
        self.results.setColumnCount(4)
        self.results.setHeaderLabels(["Name", "Type", "Modified", "Match"])
        self.results.setRootIsDecorated(False)
        self.results.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results.setSortingEnabled(False)
        self.results.setColumnWidth(0, 250)
        self.results.setColumnWidth(1, 65)
        self.results.setColumnWidth(2, 110)
        self.results.setAccessibleName("Matching documents")
        self.results.currentItemChanged.connect(self.preview_result)
        self.results.itemDoubleClicked.connect(lambda *_: self.open_document())
        files_layout.addWidget(self.results, 1)
        self.results_empty = label("No documents here yet. Add a folder to get started.", "muted")
        files_layout.addWidget(self.results_empty)
        self.splitter.addWidget(files)
        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(18, 0, 0, 0)
        preview_layout.setSpacing(10)
        self.preview_title = label("Preview", "brand")
        preview_layout.addWidget(self.preview_title)
        self.preview_meta = label("Select a document from the library", "muted")
        preview_layout.addWidget(self.preview_meta)
        self.preview = DocumentPreview()
        preview_layout.addWidget(self.preview, 1)
        self.match_text = label("", "muted")
        self.match_text.setMaximumHeight(68)
        preview_layout.addWidget(self.match_text)
        actions = QHBoxLayout()
        self.open_button = QPushButton("View document" if os.environ.get("PROVIDENCE_CONTAINER") else "Open file", objectName="primary")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self.open_document)
        self.reveal_button = QPushButton("Show in Explorer")
        self.reveal_button.setEnabled(False)
        self.reveal_button.setVisible(not os.environ.get("PROVIDENCE_CONTAINER"))
        self.reveal_button.clicked.connect(self.reveal_document)
        actions.addWidget(self.open_button)
        actions.addWidget(self.reveal_button)
        preview_layout.addLayout(actions)
        preview_layout.addWidget(label("Double-click a file to open it", "muted"))
        self.splitter.addWidget(preview_panel)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([560, 640])
        layout.addWidget(self.splitter, 1)
        self.pages.addWidget(page)

    def display_files(self, results, ranked=False):
        self.results.clear()
        for result in results:
            path = Path(result.path)
            try:
                modified = datetime.fromtimestamp(path.stat().st_mtime).strftime("%d %b %Y")
            except OSError:
                modified = "Unavailable"
            item = QTreeWidgetItem([path.name, path.suffix[1:].upper(), modified,
                                   f"{result.score:.3f}" if ranked else "—"])
            item.setData(0, Qt.ItemDataRole.UserRole, result)
            item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
            item.setToolTip(0, str(path))
            self.results.addTopLevelItem(item)
        self.results_empty.setVisible(not results)
        self.summary.setText(f"{len(results)} documents" + ("  ·  Ranked by relevance" if ranked else "  ·  Select to preview"))
        if results:
            self.results.setCurrentItem(self.results.topLevelItem(0))

    def browse_library(self, root=None):
        if self.task is not None:
            return
        self.query.clear()
        self.active_root = Path(root) if root else None
        self.location.setText(f"Library  ›  {Path(root).name}" if root else "Library  ›  All documents")
        files = self.engine.store.documents()
        if root:
            files = [path for path in files if Path(path).is_relative_to(Path(root))]
        self.display_files([Result(path, "", None, 0) for path in files])

    def browse_folder(self, item):
        self.navigate(1)
        self.browse_library(item.data(Qt.ItemDataRole.UserRole))

    def build_folders(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        panel, content = card()
        content.addWidget(label("Your search starts with your folders", "title"))
        content.addWidget(label("Only the folders listed here are indexed. Add folders when you need them, and re-index after your files change.", "muted"))
        self.folders = QListWidget()
        self.folders.setAccessibleName("Indexed folders")
        content.addWidget(self.folders, 1)
        buttons = QHBoxLayout()
        self.add_button = QPushButton("+ Add folder", objectName="primary")
        self.add_button.clicked.connect(self.add_folder)
        self.reindex_button = QPushButton("Re-index folders")
        self.reindex_button.clicked.connect(self.reindex)
        self.remove_button = QPushButton("Remove from library")
        self.remove_button.clicked.connect(self.remove_folder)
        for button in (self.add_button, self.reindex_button, self.remove_button):
            buttons.addWidget(button)
        buttons.addStretch()
        content.addLayout(buttons)
        content.addWidget(label("Removing a folder only removes its search index. Original documents stay where they are.", "muted"))
        layout.addWidget(panel, 1)
        self.pages.addWidget(page)

    def navigate(self, page):
        if not self.onboarded:
            page = 0
        self.pages.setCurrentIndex(page)
        self.page_title.setText(["Initial indexing", "Documents", "Indexed folders"][page])
        self.home_nav.setChecked(page == 1)
        self.folder_nav.setChecked(page == 2)
        self.home_nav.setEnabled(self.onboarded and self.task is None)
        self.folder_nav.setEnabled(self.onboarded and self.task is None)

    def refresh_library(self):
        self.folders.clear()
        roots = self.engine.store.roots()
        for root in roots:
            item = QListWidgetItem(f"{root.name or root}\n{root}")
            item.setData(Qt.ItemDataRole.UserRole, str(root))
            self.folders.addItem(item)
        count = self.engine.store.count()
        self.count_label.setText(f"{count} documents · {len(roots)} folders")
        self.folder_tree.clear()
        for root in roots:
            item = QListWidgetItem(root.name or str(root))
            item.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
            item.setData(Qt.ItemDataRole.UserRole, str(root))
            item.setToolTip(str(root))
            self.folder_tree.addItem(item)

    def pick_folder(self):
        initial = "/documents" if os.environ.get("PROVIDENCE_CONTAINER") else str(Path.home() / "Documents")
        folder = QFileDialog.getExistingDirectory(self, "Choose a folder to index", initial)
        if folder and os.environ.get("PROVIDENCE_CONTAINER") and not Path(folder).resolve().is_relative_to(Path("/documents")):
            self.status.setText("Choose /documents or one of its subfolders. Use the Windows launcher to share another host folder.")
            return ""
        return folder

    def add_pending_folder(self, root):
        root = str(Path(root).resolve())
        existing = [self.onboarding_folders.item(i).data(Qt.ItemDataRole.UserRole)
                    for i in range(self.onboarding_folders.count())]
        if root not in existing:
            item = QListWidgetItem(root)
            item.setData(Qt.ItemDataRole.UserRole, root)
            self.onboarding_folders.addItem(item)
        self.update_pending_controls()

    def update_pending_controls(self):
        count = self.onboarding_folders.count()
        self.onboarding_continue.setEnabled(count > 0 and self.task is None)
        self.onboarding_remove.setEnabled(count > 0 and self.task is None)
        self.onboarding_empty.setVisible(count == 0)

    @Slot()
    def choose_onboarding_folder(self):
        folder = self.pick_folder()
        if folder:
            self.add_pending_folder(folder)

    @Slot()
    def remove_pending_folder(self):
        row = self.onboarding_folders.currentRow()
        if row >= 0:
            self.onboarding_folders.takeItem(row)
        self.update_pending_controls()

    @Slot()
    def start_onboarding(self):
        roots = [Path(self.onboarding_folders.item(i).data(Qt.ItemDataRole.UserRole))
                 for i in range(self.onboarding_folders.count())]
        if not roots or self.task is not None:
            return
        self._onboarding_job = True
        self.onboarding_feedback.clear()
        def build(progress):
            if self.source_changed:
                self.engine.store.clear_library()
            reports = self.engine.index_many(roots, progress, cancelled=self.index_cancel.is_set)
            errors = [error for report in reports for error in report.errors]
            if not any(report.cancelled for report in reports) and (not errors or any(report.indexed + report.unchanged for report in reports)):
                for previous in self.engine.store.roots():
                    if previous not in roots:
                        self.engine.store.remove_root(previous)
            return reports
        self.start_task(build, self.index_finished, IndexProgress("Collecting · Finding supported files in your selected folders"))

    def start_task(self, operation, handler, message="Processing · Working on your request"):
        if self.task is not None:
            return
        for control in self.controls + self.library_commands:
            control.setEnabled(False)
        self.index_cancel.clear()
        self._indexing_job = isinstance(message, IndexProgress)
        self.stop_button.setVisible(self._indexing_job)
        self.stop_button.setEnabled(self._indexing_job)
        self.stop_button.setText("Stop indexing")
        self.busy_panel.show()
        self.spinner.timer.start()
        self.set_progress(message)
        self.task = Task(operation, self)
        self.task.progress.connect(self.set_progress)
        self.task.success.connect(handler)
        self.task.failure.connect(self.show_error)
        self.task.finished.connect(self.task_finished)
        self.task.start()

    @Slot(object)
    def set_progress(self, message):
        stage, separator, detail = message.partition(" · ")
        self.busy_title.setText(stage)
        self.busy_message.setText(detail if separator else message)
        self.status.setText("Stopping indexing after the current batch…"
                            if self._indexing_job and self.index_cancel.is_set() else message)
        if isinstance(message, IndexProgress):
            self.busy_bar.setRange(0, 100)
            self.busy_bar.setValue(message.percent)
            self.busy_percent.setText(f"{message.percent}%")
            self.busy_percent.show()
            self.busy_counts.setText(f"{message.completed:,} of {message.total:,} files processed"
                                     if stage != "Collecting" else f"{message.total:,} supported files found · Scanning folders")
            self.busy_counts.show()
        else:
            self.busy_bar.setRange(0, 0)
            self.busy_percent.hide()
            self.busy_counts.hide()

    @Slot()
    def stop_indexing(self):
        if self.task is None or not self._indexing_job:
            return
        self.index_cancel.set()
        self.stop_button.setEnabled(False)
        self.stop_button.setText("Stopping…")
        self.status.setText("Stopping after the current batch. Documents already saved will remain searchable.")

    @Slot()
    def task_finished(self):
        task, self.task = self.task, None
        task.deleteLater()
        self.spinner.timer.stop()
        self.busy_panel.hide()
        self._indexing_job = False
        for control in self.controls + self.library_commands:
            control.setEnabled(True)
        self.open_button.setEnabled(self.results.currentItem() is not None)
        self.reveal_button.setEnabled(self.results.currentItem() is not None)
        self.update_pending_controls()
        self.refresh_library()
        self.navigate(self.pages.currentIndex())

    @Slot(str)
    def show_error(self, message):
        self.status.setText(f"Could not complete this operation: {message}")
        if self._onboarding_job:
            self.onboarding_feedback.setText(message + " Choose an accessible folder and try again.")
        self._onboarding_job = False

    @Slot()
    def add_folder(self):
        folder = self.pick_folder()
        if folder:
            self._onboarding_job = False
            self.start_task(lambda progress: [self.engine.index(Path(folder), progress, cancelled=self.index_cancel.is_set)], self.index_finished,
                            IndexProgress("Collecting · Finding supported files in the selected folder"))

    @Slot()
    def remove_folder(self):
        if self.task is not None:
            return
        current = self.folders.currentItem()
        if current:
            root = current.data(Qt.ItemDataRole.UserRole)
            self.start_task(lambda progress: self.engine.store.remove_root(root), self.folder_removed,
                            "Processing · Removing the folder from your search index")

    @Slot(object)
    def folder_removed(self, result):
        self.results.clear()
        self.preview.clear()
        self.results_empty.show()
        self.display_files([Result(path, "", None, 0) for path in self.engine.store.documents()])
        self.status.setText("Folder removed from the library. Your original files are unchanged.")

    @Slot()
    def reindex(self):
        roots = self.engine.store.roots()
        if not roots:
            self.status.setText("Add a folder first.")
            return
        self._onboarding_job = False
        self.start_task(lambda progress: self.engine.index_many(roots, progress, cancelled=self.index_cancel.is_set),
                        self.index_finished, IndexProgress("Collecting · Checking your indexed folders"))

    @Slot(object)
    def index_finished(self, reports):
        self.results.clear()
        self.preview.clear()
        errors = [error for report in reports for error in report.errors]
        stopped = any(report.cancelled for report in reports)
        self.status.setText(("Indexing stopped" if stopped else "Library updated") + f" · {sum(r.indexed for r in reports)} indexed · "
                            f"{sum(r.unchanged for r in reports)} unchanged · {sum(r.removed for r in reports)} removed"
                            + (f" · {len(errors)} issues" if errors else ""))
        self.summary.setText("Library updated. Describe a document to search.")
        self.results_empty.show()
        if self._onboarding_job:
            if (self.engine.store.count() > 0 if stopped else not errors or any(report.indexed + report.unchanged for report in reports)):
                self.engine.store.set_setting("onboarding_complete", "1")
                self.engine.store.set_setting("library_source", self.library_source)
                self.onboarded = True
                self.source_changed = False
                self.navigate(1)
            elif stopped:
                self.onboarding_feedback.setText("Indexing stopped before any documents were saved. Start indexing to resume.")
            else:
                self.onboarding_feedback.setText("No searchable text was found. Choose a folder containing PDF, TXT, DOCX or MD files.")
        self._onboarding_job = False
        self.display_files([Result(path, "", None, 0) for path in self.engine.store.documents()])
        if stopped:
            self.summary.setText("Indexing stopped · Saved documents are ready · Re-index to resume")
        if errors:
            self.status.setToolTip("\n".join(errors))
        else:
            self.status.setToolTip("")

    @Slot()
    def search(self):
        if not self.onboarded or self.task is not None:
            return
        query = self.query.text().strip()
        if not query:
            self.status.setText("Enter a description to search.")
            return
        self.summary.setText("Searching your library…")
        self.start_task(lambda progress: self.engine.search(query, progress=progress), self.search_finished,
                        "Loading · Preparing the local search model")

    @Slot(object)
    def search_finished(self, results):
        self.location.setText("Library  ›  Search results")
        self.display_files(results, ranked=True)
        self.results_empty.setText("No matching documents. Try another description or add a folder.")
        self.status.setText("Search complete · Match is a ranking score, not a confidence percentage.")

    def preview_result(self, current, previous):
        enabled = current is not None and self.task is None
        self.open_button.setEnabled(enabled)
        self.reveal_button.setEnabled(enabled)
        self.preview.clear()
        self.match_text.clear()
        self.preview_title.setText("Preview")
        self.preview_meta.setText("Select a document from the library")
        if current:
            result = current.data(0, Qt.ItemDataRole.UserRole)
            path = Path(result.path)
            self.preview_title.setText(path.name)
            self.preview_title.setToolTip(path.name)
            self.preview_meta.setText(str(path.parent))
            self.preview_meta.setToolTip(str(path))
            self.preview.load(path, result.page)
            if result.text:
                self.match_text.setText("MATCHING PASSAGE · " + result.text[:220].replace("\n", " "))
                self.match_text.setToolTip(result.text)
            if path.suffix.lower() == ".docx" and self.task is None:
                self.status.setText("Word preview · Formatting and tables shown; open the file for original page layout and images.")

    @Slot()
    def reveal_document(self):
        if self.task is not None:
            return
        item = self.results.currentItem()
        if not item:
            return
        path = Path(item.data(0, Qt.ItemDataRole.UserRole).path)
        if not path.is_file():
            self.show_error("This document has moved or been deleted. Re-index its folder.")
            return
        try:
            if os.name == "nt":
                subprocess.Popen(["explorer.exe", "/select,", str(path)])
            elif not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent))):
                self.show_error("Could not open this folder.")
        except OSError as error:
            self.show_error(str(error))

    @Slot()
    def open_document(self):
        if self.task is not None:
            return
        item = self.results.currentItem()
        if item:
            path = Path(item.data(0, Qt.ItemDataRole.UserRole).path)
            if not path.is_file():
                self.show_error("This document has moved or been deleted. Re-index its folder.")
            elif os.environ.get("PROVIDENCE_CONTAINER"):
                from .documents import extract
                def read(progress):
                    progress(f"Processing · Reading {path.name}")
                    return extract(path)
                self.start_task(read, self.show_document, "Loading · Opening the document")
            elif not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
                self.show_error("No application could open this document.")

    @Slot(object)
    def show_document(self, passages):
        dialog = QDialog(self)
        dialog.setWindowTitle("Document text")
        dialog.resize(800, 600)
        layout = QVBoxLayout(dialog)
        content = QTextEdit()
        content.setReadOnly(True)
        content.setPlainText("\n\n".join((f"Page {p.page}\n" if p.page else "") + p.text for p in passages))
        layout.addWidget(content)
        self.status.setText("Document loaded")
        dialog.exec()

    def closeEvent(self, event):
        if self.task is not None:
            self.status.setText("Processing is still running. Wait for it to finish before closing.")
            event.ignore()
        else:
            event.accept()


def launch(engine):
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Providence")
    app.setWindowIcon(QIcon(str(Path(__file__).with_name('assets') / 'providence.ico')))
    window = Window(engine)
    window.show()
    return app.exec()
