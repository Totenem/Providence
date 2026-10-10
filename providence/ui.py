"""Desktop library with background indexing, virtual file lists and offline search."""

import json
import os
import subprocess
import time
import random
from datetime import datetime
from pathlib import Path
from threading import Event
from PySide6.QtCore import (
    Qt,
    QThread,
    QTimer,
    QUrl,
    Signal,
    QAbstractTableModel,
    QModelIndex,
    QPropertyAnimation,
)
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
    QKeySequence,
    QFontDatabase,
)
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QLineEdit,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QTableView,
    QAbstractItemView,
    QComboBox,
    QCheckBox,
    QPlainTextEdit,
    QListWidget,
    QListWidgetItem,
    QFileDialog,
    QMenu,
    QProgressBar,
    QGraphicsOpacityEffect,
    QFrame,
    QMessageBox,
)
from .engine import Engine, IndexProgress
from .background import LibraryService
from .discovery import default_roots
from .preview import DocumentPreview
from .paths import qwen_dir

SLOW_SEARCH_SECONDS = 20
SEARCH_HELPERS = (
    "I'll compare filenames, exact words, and meaning.",
    "You can keep browsing while I work.",
    "A remembered folder can make a broad search more focused.",
    "You don't need to remember the exact filename.",
    "If this takes a while, a file type or date can help narrow it down.",
)

LIGHT = dict(
    bg="#f4f6f8",
    panel="#ffffff",
    text="#202a38",
    muted="#596879",
    line="#dce3ea",
    field="#f7f9fb",
    hover="#eaf0f6",
    select="#dbeee6",
    accent="#147d59",
    on="#ffffff",
)
DARK = dict(
    bg="#111821",
    panel="#1a2430",
    text="#e7eef7",
    muted="#a9b8ca",
    line="#344253",
    field="#202d3b",
    hover="#2b3c4e",
    select="#244c40",
    accent="#63d9ac",
    on="#10251c",
)


def stylesheet(p):
    return f"""
    QWidget {{ color:{p["text"]};font-family:'Segoe UI','DejaVu Sans';font-size:13px; }}
    QMainWindow,QWidget#shell {{ background:{p["bg"]}; }}
    QWidget#sidebar,QFrame#card,QTableView,QTreeWidget,QListWidget {{ background:{p["panel"]}; }}
    QWidget#sidebar {{ border-right:1px solid {p["line"]}; }}
    QWidget#previewPanel {{ background:{p["panel"]};border:1px solid {p["line"]};border-radius:12px; }}
    QWidget#settingsPage,QWidget#healthPage {{ background:{p["panel"]}; }}
    QFrame#card {{ border:1px solid {p["line"]};border-radius:12px; }}
    QLabel {{ background:transparent; }}
    QLabel#brand {{ font-size:21px;font-weight:700; }}
    QLabel#title {{ font-size:26px;font-weight:600; }}
    QLabel#muted {{ color:{p["muted"]}; }}
    QLabel#badge {{ color:{p["accent"]};font-weight:600; }}
    QPushButton {{ background:{p["panel"]};border:1px solid {p["line"]};border-radius:7px;padding:8px 12px; }}
    QPushButton:hover {{ background:{p["hover"]}; }}
    QPushButton:pressed,QPushButton:checked {{ background:{p["select"]}; }}
    QPushButton:focus,QComboBox:focus,QTableView:focus,QTreeWidget:focus,QCheckBox:focus {{ border:2px solid {p["accent"]}; }}
    QPushButton:disabled {{ color:{p["muted"]}; }}
    QPushButton#primary {{ background:{p["accent"]};color:{p["on"]};font-weight:600; }}
    QPushButton#nav {{ text-align:left;border:none;padding:12px; }}
    QLineEdit,QComboBox,QPlainTextEdit {{ background:{p["field"]};border:1px solid {p["line"]};border-radius:7px;padding:8px; }}
    QLineEdit:focus,QPlainTextEdit:focus {{ border:2px solid {p["accent"]}; }}
    QComboBox QAbstractItemView,QMenu,QDialog {{ background:{p["panel"]};color:{p["text"]}; }}
    QTableView,QTreeWidget,QListWidget {{ border:1px solid {p["line"]};border-radius:8px;selection-background-color:{p["select"]};selection-color:{p["text"]}; }}
    QTableView::item:hover,QTreeWidget::item:hover,QListWidget::item:hover {{ background:{p["hover"]}; }}
    QHeaderView::section {{ background:{p["field"]};color:{p["muted"]};border:none;border-bottom:1px solid {p["line"]};padding:10px; }}
    QTreeWidget::item,QListWidget::item {{ padding:8px; }}
    QProgressBar {{ border:none;background:{p["line"]};min-height:5px;max-height:5px;border-radius:2px; }}
    QProgressBar::chunk {{ background:{p["accent"]}; }}
    QSplitter::handle {{ background:{p["line"]}; }}
    QTextBrowser#paper {{ background:{p["panel"]};color:{p["text"]};border:1px solid {p["line"]};font-size:15px; }}
    QScrollArea {{ border:none;background:{p["field"]}; }}
    QScrollBar:vertical {{ background:{p["field"]};width:10px;margin:0; }}
    QScrollBar:horizontal {{ background:{p["field"]};height:10px;margin:0; }}
    QScrollBar::handle {{ background:{p["line"]};border-radius:4px;min-height:28px;min-width:28px; }}
    QScrollBar::handle:hover {{ background:{p["muted"]}; }}
    QScrollBar::add-line,QScrollBar::sub-line {{ width:0;height:0; }}
    QScrollBar::add-page,QScrollBar::sub-page {{ background:transparent; }}
    """


def icon(kind, color="#64798e"):
    pix = QPixmap(48, 48)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(2, 2)
    p.setPen(QPen(QColor(color), 1.7))
    if kind == "folder":
        p.drawRoundedRect(3, 7, 18, 13, 2, 2)
        p.drawLine(4, 7, 4, 4)
        p.drawLine(4, 4, 11, 4)
        p.drawLine(11, 4, 14, 7)
    elif kind == "search":
        p.drawEllipse(4, 3, 12, 12)
        p.drawLine(14, 14, 21, 21)
    elif kind in {"back", "forward", "up"}:
        if kind == "up":
            p.drawLine(12, 20, 12, 4)
            p.drawLine(12, 4, 5, 11)
            p.drawLine(12, 4, 19, 11)
        else:
            a, b = (16, 7) if kind == "back" else (7, 16)
            p.drawLine(a, 4, b, 12)
            p.drawLine(b, 12, a, 20)
    elif kind == "settings":
        for y, x in ((6, 9), (12, 16), (18, 7)):
            p.drawLine(3, y, 21, y)
            p.drawEllipse(x - 2, y - 2, 4, 4)
    elif kind == "health":
        for a, b, c, d in (
            (3, 13, 7, 13),
            (7, 13, 10, 5),
            (10, 5, 14, 20),
            (14, 20, 17, 13),
            (17, 13, 21, 13),
        ):
            p.drawLine(a, b, c, d)
    else:
        p.drawRoundedRect(5, 3, 14, 18, 2, 2)
        for y in (9, 13, 17):
            p.drawLine(8, y, 16, y)
    p.end()
    return QIcon(pix)


def label(text="", name=None):
    w = QLabel(text)
    w.setWordWrap(True)
    if name:
        w.setObjectName(name)
    return w


def button(text, callback=None, kind=None, primary=False):
    w = QPushButton(text)
    if primary:
        w.setObjectName("primary")
    if kind:
        w.setIcon(icon(kind))
    if callback:
        w.clicked.connect(callback)
    return w


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


def size_text(value):
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024


class FileModel(QAbstractTableModel):
    HEADERS = ["Name", "Type", "Modified", "Size", "Status / Match"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []

    def replace(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if (
            role == Qt.ItemDataRole.DisplayRole
            and orientation == Qt.Orientation.Horizontal
        ):
            return self.HEADERS[section]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        if role in (Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.AccessibleTextRole):
            return row["path"] + "\n" + row.get("error", "")
        if role == Qt.ItemDataRole.DecorationRole and index.column() == 0:
            return icon("file")
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        result = row.get("result")
        return [
            row["name"],
            row["suffix"].lstrip(".").upper() or "FILE",
            datetime.fromtimestamp(row["modified"]).strftime("%d %b %Y"),
            size_text(row["size"]),
            "Unavailable"
            if not row.get("available", True)
            else result.reason
            if result
            else row["state"].replace("_", " ").title(),
        ][index.column()]


class Window(QMainWindow):
    background_progress = Signal(object)
    background_changed = Signal()
    background_error = Signal(str)

    def __init__(self, engine: Engine, monitor=True):
        super().__init__()
        self.engine = engine
        self.monitor = monitor
        if os.name == "nt" and not QFontDatabase.families():
            # Headless/restricted font discovery can fail even though the fonts are readable.
            for name in (
                "segoeui.ttf",
                "segoeuib.ttf",
                "segoeuisl.ttf",
                "seguisym.ttf",
            ):
                QFontDatabase.addApplicationFont(
                    str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name)
                )
        self.task = None
        self.search_task = None
        self.index_cancel = Event()
        self._indexing_job = False
        self.active_root = None
        self.history = [None]
        self.history_position = 0
        self.offset = 0
        self.total = 0
        self.search_results = None
        self.search_generation = 0
        self._closing = False
        self.pending_search = False
        self.search_cancel = Event()
        self.search_clues = {}
        self.search_started = None
        self.search_percent = 0
        self.search_phase = ""
        self.search_helpers = list(SEARCH_HELPERS)
        self.search_session = 0
        self._preview_key = None
        self.library_source = os.environ.get("PROVIDENCE_LIBRARY_SOURCE", "")
        self.source_changed = (
            engine.store.setting("library_source", "") != self.library_source
        )
        self.onboarded = (
            engine.store.setting("onboarding_complete") == "1"
            and not self.source_changed
        )
        self.setWindowTitle("Providence 1.1 · Your files, within reach")
        self.setWindowIcon(
            QIcon(str(Path(__file__).with_name("assets") / "providence.ico"))
        )
        self.resize(1380, 860)
        self.setMinimumSize(980, 640)
        self.setAcceptDrops(True)
        shell = QWidget(objectName="shell")
        self.setCentralWidget(shell)
        outer = QHBoxLayout(shell)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        sidebar = QWidget(objectName="sidebar")
        sidebar.setFixedWidth(220)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 24, 18, 18)
        side.addWidget(label("Providence", "brand"))
        side.addWidget(label("Your files, within reach", "muted"))
        side.addSpacing(24)
        self.home_nav = button("Library", lambda: self.navigate(1), "folder")
        self.folder_nav = button(
            "Locations && settings", lambda: self.navigate(2), "settings"
        )
        self.health_nav = button("Index health", lambda: self.navigate(3), "health")
        for nav in (self.home_nav, self.folder_nav, self.health_nav):
            nav.setObjectName("nav")
            nav.setCheckable(True)
            side.addWidget(nav)
        side.addSpacing(16)
        side.addWidget(label("LOCATIONS", "muted"))
        self.folder_tree = QTreeWidget()
        self.folder_tree.setHeaderHidden(True)
        self.folder_tree.setColumnCount(1)
        self.folder_tree.setAccessibleName("Browse library folders")
        self.folder_tree.itemClicked.connect(self.browse_folder)
        self.folder_tree.itemExpanded.connect(self.expand_folder)
        side.addWidget(self.folder_tree, 1)
        self.count_label = label("", "muted")
        side.addWidget(self.count_label)
        side.addWidget(label("Local processing · Private by default", "muted"))
        outer.addWidget(sidebar)
        body = QVBoxLayout()
        body.setContentsMargins(24, 22, 24, 14)
        body.setSpacing(14)
        header = QHBoxLayout()
        self.page_title = label("Welcome to Providence", "title")
        header.addWidget(self.page_title, 1)
        self.pause_button = button("Pause indexing", self.toggle_pause)
        header.addWidget(self.pause_button)
        body.addLayout(header)
        self.busy_panel = QFrame(objectName="card")
        busy = QHBoxLayout(self.busy_panel)
        self.busy_title = label("Discovering", "badge")
        busy.addWidget(self.busy_title)
        self.busy_message = label("", "muted")
        busy.addWidget(self.busy_message, 1)
        self.busy_counts = label("", "muted")
        busy.addWidget(self.busy_counts)
        self.busy_percent = label("", "badge")
        busy.addWidget(self.busy_percent)
        self.stop_button = button("Pause", self.stop_indexing)
        busy.addWidget(self.stop_button)
        self.busy_bar = QProgressBar()
        self.busy_bar.setTextVisible(False)
        body.addWidget(self.busy_panel)
        body.addWidget(self.busy_bar)
        self.busy_panel.hide()
        self.busy_bar.hide()
        self.pages = QStackedWidget()
        body.addWidget(self.pages, 1)
        self.build_onboarding()
        self.build_search()
        self.build_settings()
        self.build_health()
        self.status = label("Ready · All processing happens on this device.", "muted")
        body.addWidget(self.status)
        outer.addLayout(body, 1)
        self.service = LibraryService(
            engine,
            self.background_progress.emit,
            self.background_changed.emit,
            self.background_error.emit,
        )
        if engine.store.setting("paused", "0") == "1":
            self.service.set_paused(True)
            self.pause_button.setText("Resume indexing")
        self.background_progress.connect(self.set_progress)
        self.background_changed.connect(self.library_updated)
        self.background_error.connect(self.show_error)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(1500)
        self.refresh_timer.timeout.connect(self.tick)
        self.refresh_timer.start()
        self.query.textEdited.connect(lambda: self.edit_search())
        self.apply_theme()
        self.restore_layout()
        self.shortcuts()
        self.refresh_library()
        for root in engine.store.roots():
            self.add_pending_folder(root)
        if not engine.store.roots() and monitor:
            for root in default_roots():
                self.add_pending_folder(root)
        self.navigate(1 if self.onboarded else 0)
        if self.onboarded:
            self.browse_library()
            if monitor:
                QTimer.singleShot(200, self.service.start)

    def build_onboarding(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(18)
        layout.addWidget(
            label("Find files by their name—or by what you remember.", "title")
        )
        layout.addWidget(
            label(
                "Review your locations once. Providence then keeps them up to date automatically.",
                "muted",
            )
        )
        self.onboarding_folders = QListWidget()
        self.onboarding_folders.setAccessibleName("Locations to discover")
        layout.addWidget(self.onboarding_folders, 1)
        self.onboarding_empty = label(
            "Add a folder or choose your local drives.", "muted"
        )
        layout.addWidget(self.onboarding_empty)
        row = QHBoxLayout()
        self.onboarding_add = button(
            "Add folder", self.choose_onboarding_folder, "folder"
        )
        self.onboarding_remove = button("Remove selected", self.remove_pending_folder)
        self.onboarding_continue = button(
            "Start automatic indexing", self.start_onboarding, primary=True
        )
        for w in (
            self.onboarding_add,
            self.onboarding_remove,
            button("Use local drives", self.select_drives),
            self.onboarding_continue,
        ):
            row.addWidget(w)
        layout.addLayout(row)
        layout.addWidget(
            label(
                "All discovered file types can be found by name. PDF, Word, text, Markdown and PNG/JPEG text also support content search. System folders, caches and cloud placeholders are skipped. Adjust exclusions in settings.",
                "muted",
            )
        )
        if os.environ.get("PROVIDENCE_CONTAINER"):
            layout.addWidget(
                label("Docker can see only mounted files under /documents.", "muted")
            )
        self.onboarding_feedback = label("")
        layout.addWidget(self.onboarding_feedback)
        self.pages.addWidget(page)
        self.update_pending_controls()

    def build_search(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        address = QHBoxLayout()
        self.back_button = button("", lambda: self.history_move(-1), "back")
        self.back_button.setAccessibleName("Back")
        self.forward_button = button("", lambda: self.history_move(1), "forward")
        self.forward_button.setAccessibleName("Forward")
        self.up_button = button("", self.go_up, "up")
        self.up_button.setAccessibleName("Parent folder")
        for w in (self.back_button, self.forward_button, self.up_button):
            address.addWidget(w)
        self.breadcrumbs = QWidget()
        self.crumb_row = QHBoxLayout(self.breadcrumbs)
        self.crumb_row.setContentsMargins(0, 0, 0, 0)
        address.addWidget(self.breadcrumbs, 1)
        self.location = label("Library", "muted")
        self.location.hide()
        self.query = QLineEdit()
        self.query.setPlaceholderText("Filename, exact words, or what you remember…")
        self.query.setClearButtonEnabled(True)
        self.query.setAccessibleName("Search library")
        self.query.returnPressed.connect(self.search)
        address.addWidget(self.query, 2)
        self.search_button = button("Search", self.search, "search", True)
        address.addWidget(self.search_button)
        layout.addLayout(address)
        filters = QHBoxLayout()
        self.type_filter = self.combo(
            "Filter file type",
            [
                ("All types", ""),
                ("PDF", ".pdf"),
                ("Word", ".docx"),
                ("Text", ".txt"),
                ("Markdown", ".md"),
                ("PNG", ".png"),
                ("JPEG", ".jpg"),
                ("JPEG (.jpeg)", ".jpeg"),
            ],
        )
        self.state_filter = self.combo(
            "Filter indexing status",
            [
                ("All statuses", ""),
                ("Content ready", "ready"),
                ("Pending", "pending"),
                ("OCR processing", "ocr_processing"),
                ("Filename only", "unsupported"),
                ("Failed", "failed"),
                ("No text", "empty"),
            ],
        )
        self.date_filter = self.combo(
            "Filter modified date",
            [
                ("Any date", 0),
                ("Last 7 days", 7),
                ("Last 30 days", 30),
                ("Last year", 365),
            ],
        )
        self.size_filter = self.combo(
            "Filter file size",
            [
                ("Any size", (0, 0)),
                ("Under 1 MB", (0, 1024**2)),
                ("1–10 MB", (1024**2, 10 * 1024**2)),
                ("Over 10 MB", (10 * 1024**2, 0)),
            ],
        )
        self.sort_filter = self.combo(
            "Sort files",
            [
                ("Relevance", "relevance"),
                ("Name", "name"),
                ("Newest", "date"),
                ("Largest", "size"),
                ("Type", "type"),
            ],
        )
        for w in (
            self.type_filter,
            self.state_filter,
            self.date_filter,
            self.size_filter,
            self.sort_filter,
        ):
            filters.addWidget(w)
            w.currentIndexChanged.connect(self.filters_changed)
        filters.addWidget(button("Clear filters", self.clear_filters))
        layout.addLayout(filters)
        self.filter_chips = QWidget()
        self.chips_row = QHBoxLayout(self.filter_chips)
        self.chips_row.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.filter_chips)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(5)
        left = QWidget()
        files = QVBoxLayout(left)
        files.setContentsMargins(0, 0, 10, 0)
        self.summary = label("", "muted")
        files.addWidget(self.summary)
        self.results = QTableView()
        self.file_model = FileModel(self)
        self.results.setModel(self.file_model)
        self.results.setShowGrid(False)
        self.results.verticalHeader().hide()
        self.results.verticalHeader().setDefaultSectionSize(42)
        self.results.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.results.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results.horizontalHeader().setStretchLastSection(True)
        self.results.setAccessibleName("Files and search matches")
        self.results.selectionModel().currentRowChanged.connect(self.preview_result)
        self.results.doubleClicked.connect(lambda _: self.open_document())
        self.results.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.results.customContextMenuRequested.connect(self.context_menu)
        self.results.horizontalHeader().sectionClicked.connect(self.column_sort)
        files.addWidget(self.results, 1)
        self.results_empty = label(
            "Your files will appear here as they are discovered.", "muted"
        )
        files.addWidget(self.results_empty)
        paging = QHBoxLayout()
        self.previous_page = button("Previous", lambda: self.page_move(-1))
        self.next_page = button("Next", lambda: self.page_move(1))
        self.page_label = label("", "muted")
        paging.addWidget(self.previous_page)
        paging.addWidget(self.page_label, 1)
        paging.addWidget(self.next_page)
        files.addLayout(paging)
        self.splitter.addWidget(left)
        right = QWidget()
        pre = QVBoxLayout(right)
        pre.setContentsMargins(10, 0, 0, 0)
        self.preview_title = label("Preview", "brand")
        pre.addWidget(self.preview_title)
        self.preview_meta = label("Select a file", "muted")
        pre.addWidget(self.preview_meta)
        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("Find within preview…")
        self.find_input.setAccessibleName("Find within document preview")
        self.find_input.returnPressed.connect(
            lambda: self.preview.find(self.find_input.text())
        )
        pre.addWidget(self.find_input)
        self.preview = DocumentPreview()
        pre.addWidget(self.preview, 1)
        self.match_text = label("", "muted")
        self.match_text.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.match_text.setMaximumHeight(85)
        pre.addWidget(self.match_text)
        actions = QGridLayout()
        self.open_button = button("Open file", self.open_document, primary=True)
        self.reveal_button = button("Show in Explorer", self.reveal_document)
        self.reveal_button.setVisible(not os.environ.get("PROVIDENCE_CONTAINER"))
        actions.addWidget(self.open_button, 0, 0)
        actions.addWidget(self.reveal_button, 0, 1)
        actions.addWidget(button("Copy passage", self.copy_passage), 1, 0, 1, 2)
        pre.addLayout(actions)
        self.splitter.addWidget(right)
        self.splitter.setSizes([620, 530])
        layout.addWidget(self.splitter, 1)
        self.pages.addWidget(page)

    @staticmethod
    def combo(name, items):
        w = QComboBox()
        w.setAccessibleName(name)
        for text, value in items:
            w.addItem(text, value)
        return w

    def build_settings(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(
            label(
                "Locations update automatically. Add or remove locations to change your scope.",
                "muted",
            )
        )
        self.folders = QListWidget()
        self.folders.setAccessibleName("Indexed locations")
        self.folders.setMaximumHeight(130)
        layout.addWidget(self.folders)
        row = QHBoxLayout()
        self.add_button = button("Add folder", self.add_folder, "folder", True)
        self.remove_button = button("Remove location", self.remove_folder)
        self.reindex_button = button("Recovery scan", self.reindex)
        for w in (self.add_button, self.remove_button, self.reindex_button):
            row.addWidget(w)
        row.addStretch()
        layout.addLayout(row)
        prefs = QHBoxLayout()
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["System", "Light", "Dark"])
        self.theme_combo.setAccessibleName("Color theme")
        self.theme_combo.setCurrentText(self.engine.store.setting("theme", "System"))
        self.theme_combo.currentTextChanged.connect(self.theme_changed)
        prefs.addWidget(label("Theme"))
        prefs.addWidget(self.theme_combo)
        self.reduced_motion = QCheckBox("Reduce motion")
        self.reduced_motion.setChecked(
            self.engine.store.setting("reduced_motion", "0") == "1"
        )
        self.reduced_motion.toggled.connect(
            lambda v: self.engine.store.set_setting("reduced_motion", "1" if v else "0")
        )
        prefs.addWidget(self.reduced_motion)
        self.low_resource = QCheckBox("Low-resource mode")
        self.low_resource.setChecked(
            self.engine.store.setting("low_resource", "0") == "1"
        )
        self.low_resource.toggled.connect(
            lambda v: self.engine.store.set_setting("low_resource", "1" if v else "0")
        )
        prefs.addWidget(self.low_resource)
        self.ocr_enabled = QCheckBox("Offline OCR")
        self.ocr_enabled.setChecked(
            self.engine.store.setting("ocr_enabled", "1") == "1"
        )
        self.ocr_enabled.toggled.connect(self.ocr_changed)
        prefs.addWidget(self.ocr_enabled)
        prefs.addStretch()
        layout.addLayout(prefs)
        models = QHBoxLayout()
        models.addWidget(label("Search model"))
        self.model_combo = self.combo(
            "Local search model",
            [
                ("MiniLM · low memory", "minilm"),
                ("Qwen 0.6B · stronger retrieval", "qwen"),
            ],
        )
        self.model_combo.setCurrentIndex(
            1 if "Qwen/" in self.engine.embedder.identity else 0
        )
        models.addWidget(self.model_combo, 1)
        self.model_button = button("Build and switch model", self.switch_model)
        models.addWidget(self.model_button)
        layout.addLayout(models)
        layout.addWidget(
            label(
                "Changing models builds a separate index while your current library stays searchable.",
                "muted",
            )
        )
        layout.addWidget(
            label("Excluded folder names, patterns or absolute paths (one per line)")
        )
        self.exclusions = QPlainTextEdit("\n".join(self.engine.exclusions()))
        self.exclusions.setAccessibleName("Excluded file and folder patterns")
        layout.addWidget(self.exclusions, 1)
        layout.addWidget(button("Save exclusions", self.save_exclusions))
        layout.addWidget(button("Clear all local search indexes", self.clear_indexes))
        layout.addWidget(
            label(
                "Exclusions affect discovery and search; originals remain unchanged. Files over 50 MB are listed by name and reported as too large for content processing.",
                "muted",
            )
        )
        self.pages.addWidget(page)

    def build_health(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self.health_summary = label("", "title")
        layout.addWidget(self.health_summary)
        self.health_details = label("", "muted")
        layout.addWidget(self.health_details)
        self.health_files = QListWidget()
        self.health_files.setAccessibleName("Files needing attention")
        layout.addWidget(self.health_files, 1)
        self.health_empty = label(
            "No files need attention.\nNew indexing issues will appear here.", "muted"
        )
        self.health_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.health_empty, 1)
        self.health_empty.hide()
        row = QHBoxLayout()
        row.addWidget(button("Retry failed files", self.retry_failed))
        row.addWidget(button("Retry selected with OCR", self.force_selected_ocr))
        row.addStretch()
        layout.addLayout(row)
        layout.addWidget(
            label(
                "Files on unavailable drives remain in your library. Reconnect the drive to resume.",
                "muted",
            )
        )
        self.pages.addWidget(page)

    def shortcuts(self):
        for keys, action in [
            ("Ctrl+L", lambda: self.query.setFocus()),
            ("Ctrl+F", lambda: self.find_input.setFocus()),
            ("Alt+Left", lambda: self.history_move(-1)),
            ("Alt+Right", lambda: self.history_move(1)),
            ("Alt+Up", self.go_up),
            ("Ctrl+Shift+C", self.copy_path),
            ("Escape", lambda: self.query.clear()),
        ]:
            s = QShortcut(QKeySequence(keys), self)
            s.activated.connect(action)
        QApplication.instance().styleHints().colorSchemeChanged.connect(
            lambda _: self.apply_theme()
        )

    def theme_changed(self, value):
        self.engine.store.set_setting("theme", value)
        self.apply_theme()

    def apply_theme(self):
        choice = self.engine.store.setting("theme", "System")
        dark = choice == "Dark" or (
            choice == "System"
            and QApplication.instance().styleHints().colorScheme()
            == Qt.ColorScheme.Dark
        )
        self.setStyleSheet(stylesheet(DARK if dark else LIGHT))

    def restore_layout(self):
        self.splitter.setSizes(
            json.loads(self.engine.store.setting("pane_sizes", "[620,530]"))
        )
        for i, width in enumerate(
            json.loads(
                self.engine.store.setting("column_widths", "[240,60,110,80,150]")
            )[:5]
        ):
            self.results.setColumnWidth(i, max(40, int(width)))

    def navigate(self, page):
        if not self.onboarded:
            page = 0
        changed = self.pages.currentIndex() != page
        self.pages.setCurrentIndex(page)
        self.page_title.setText(
            [
                "Welcome to Providence",
                "Library",
                "Locations & settings",
                "Index health",
            ][page]
        )
        for i, nav in enumerate((self.home_nav, self.folder_nav, self.health_nav), 1):
            nav.setEnabled(self.onboarded)
            nav.setChecked(page == i)
        if changed and not self.reduced_motion.isChecked():
            if hasattr(self, "animation"):
                self.animation.stop()
            effect = QGraphicsOpacityEffect(self.pages)
            self.pages.setGraphicsEffect(effect)
            self.animation = QPropertyAnimation(effect, b"opacity", self)
            self.animation.setDuration(140)
            self.animation.setStartValue(0.65)
            self.animation.setEndValue(1)
            self.animation.start()
        if page == 3:
            self.refresh_health()

    def refresh_library(self):
        roots = self.engine.store.roots()
        selected = self.folders.currentItem()
        selected_path = selected.data(Qt.ItemDataRole.UserRole) if selected else None
        self.folders.clear()
        for root in roots:
            item = QListWidgetItem(str(root))
            item.setData(Qt.ItemDataRole.UserRole, str(root))
            self.folders.addItem(item)
            if str(root) == selected_path:
                self.folders.setCurrentItem(item)
        current = [
            self.folder_tree.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole)
            for i in range(self.folder_tree.topLevelItemCount())
        ]
        if current != [str(r) for r in roots]:
            self.folder_tree.clear()
            for root in roots:
                item = QTreeWidgetItem([root.name or str(root)])
                item.setIcon(0, icon("folder"))
                item.setData(0, Qt.ItemDataRole.UserRole, str(root))
                item.setToolTip(0, str(root))
                item.addChild(QTreeWidgetItem(["Loading…"]))
                self.folder_tree.addTopLevelItem(item)
        stats = self.engine.store.stats()
        existing = {
            self.type_filter.itemData(i) for i in range(self.type_filter.count())
        }
        self.type_filter.blockSignals(True)
        for suffix in self.engine.store.suffixes():
            if suffix not in existing:
                self.type_filter.addItem(suffix.lstrip(".").upper(), suffix)
        self.type_filter.blockSignals(False)
        self.count_label.setText(
            f"{sum(stats.values()):,} files\n{stats.get('ready', 0):,} content ready"
        )

    def expand_folder(self, item):
        root = item.data(0, Qt.ItemDataRole.UserRole)
        if not root:
            return
        item.takeChildren()
        for path in self.engine.store.children(root):
            child = QTreeWidgetItem([Path(path).name])
            child.setIcon(0, icon("folder"))
            child.setData(0, Qt.ItemDataRole.UserRole, path)
            child.setToolTip(0, path)
            child.addChild(QTreeWidgetItem(["Loading…"]))
            item.addChild(child)

    def browse_folder(self, item, column=0):
        root = item.data(0, Qt.ItemDataRole.UserRole)
        if root:
            self.navigate(1)
            self.browse_library(root)

    def filters(self):
        minimum, maximum = self.size_filter.currentData()
        return dict(
            root=self.active_root,
            suffix=self.type_filter.currentData(),
            state=self.state_filter.currentData(),
            days=self.date_filter.currentData(),
            min_size=minimum,
            max_size=maximum,
        )

    def filters_changed(self):
        self.offset = 0
        self.update_chips()
        if self.query.text().strip():
            self.edit_search()
            self.search_results = None
            self.load_files()
            self.status.setText("Filters updated · Press Search to apply them.")
        else:
            self.load_files()

    def clear_filters(self):
        for w in (
            self.type_filter,
            self.state_filter,
            self.date_filter,
            self.size_filter,
        ):
            w.blockSignals(True)
            w.setCurrentIndex(0)
            w.blockSignals(False)
        self.filters_changed()

    def update_chips(self):
        while self.chips_row.count():
            item = self.chips_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for combo in (
            self.type_filter,
            self.state_filter,
            self.date_filter,
            self.size_filter,
        ):
            if combo.currentIndex():
                self.chips_row.addWidget(
                    button(
                        combo.currentText() + " ×",
                        lambda checked=False, c=combo: c.setCurrentIndex(0),
                    )
                )
        self.chips_row.addStretch()

    def browse_library(self, root=None, remember=True):
        if isinstance(root, bool):
            root = None
        self.search_generation += 1
        self.search_cancel.set()
        self.pending_search = False
        self.search_percent = 0
        self.search_clues = {}
        self.query.clear()
        self.search_results = None
        self.active_root = Path(root) if root else None
        self.offset = 0
        if remember and self.history[self.history_position] != self.active_root:
            self.history = self.history[: self.history_position + 1] + [
                self.active_root
            ]
            self.history_position += 1
        self.update_breadcrumbs()
        self.load_files()

    def update_breadcrumbs(self):
        while self.crumb_row.count():
            item = self.crumb_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.crumb_row.addWidget(button("Library", lambda: self.browse_library()))
        if self.active_root:
            base = next(
                (
                    r
                    for r in self.engine.store.roots()
                    if self.active_root.is_relative_to(r)
                ),
                self.active_root,
            )
            parts = [base] + [
                base.joinpath(*self.active_root.relative_to(base).parts[:i])
                for i in range(1, len(self.active_root.relative_to(base).parts) + 1)
            ]
            for path in parts[-3:]:
                self.crumb_row.addWidget(label("›", "muted"))
                self.crumb_row.addWidget(
                    button(
                        path.name or str(path),
                        lambda checked=False, p=path: self.browse_library(p),
                    )
                )
        self.crumb_row.addStretch()
        self.location.setText(
            "Library" + (" › " + self.active_root.name if self.active_root else "")
        )
        self.back_button.setEnabled(self.history_position > 0)
        self.forward_button.setEnabled(self.history_position + 1 < len(self.history))
        self.up_button.setEnabled(self.active_root is not None)

    def history_move(self, delta):
        position = self.history_position + delta
        if 0 <= position < len(self.history):
            self.history_position = position
            self.browse_library(self.history[position], remember=False)

    def go_up(self):
        if self.active_root:
            parent = self.active_root.parent
            self.browse_library(
                parent
                if parent != self.active_root
                and any(parent.is_relative_to(r) for r in self.engine.store.roots())
                else None
            )

    def load_files(self):
        if self.search_results is not None:
            rows = []
            for result in self.search_results:
                row = self.engine.store.file(result.path)
                if row:
                    row["result"] = result
                    rows.append(row)
            order = self.sort_filter.currentData()
            if order != "relevance":
                rows.sort(
                    key=lambda r: (
                        -r["modified"]
                        if order == "date"
                        else -r["size"]
                        if order == "size"
                        else r["suffix"]
                        if order == "type"
                        else r["name"].casefold()
                    )
                )
            self.total = len(rows)
            rows = rows[self.offset : self.offset + 200]
        else:
            rows, self.total = self.engine.store.list_files(
                **self.filters(),
                sort=self.sort_filter.currentData(),
                offset=self.offset,
            )
        unavailable = [root for root in self.engine.store.roots() if not root.is_dir()]
        for row in rows:
            row["available"] = not any(
                Path(row["path"]).is_relative_to(root) for root in unavailable
            )
        selected = self.current_row()
        selected_path = selected["path"] if selected else None
        self.file_model.replace(rows)
        self.results_empty.setVisible(not rows)
        self.summary.setText(
            f"{self.total:,} files"
            + (
                " · Search results"
                if self.search_results is not None
                else " · Updates automatically"
            )
        )
        self.previous_page.setEnabled(self.offset > 0)
        self.next_page.setEnabled(self.offset + 200 < self.total)
        self.page_label.setText(
            f"{self.offset + 1 if rows else 0}–{self.offset + len(rows)} of {self.total:,}"
        )
        if rows:
            self.results.setCurrentIndex(
                self.file_model.index(
                    next(
                        (i for i, r in enumerate(rows) if r["path"] == selected_path), 0
                    ),
                    0,
                )
            )
        else:
            self.preview.clear()
            self._preview_key = None
            self.open_button.setEnabled(False)
            self.reveal_button.setEnabled(False)

    def page_move(self, direction):
        self.offset = max(0, self.offset + direction * 200)
        self.load_files()

    def column_sort(self, column):
        self.sort_filter.setCurrentIndex(
            self.sort_filter.findData(
                {0: "name", 1: "type", 2: "date", 3: "size", 4: "relevance"}[column]
            )
        )

    def current_row(self):
        index = self.results.currentIndex()
        return (
            self.file_model.rows[index.row()]
            if index.isValid() and index.row() < len(self.file_model.rows)
            else None
        )

    def preview_result(self, current, previous=QModelIndex()):
        row = self.current_row()
        self.open_button.setEnabled(bool(row))
        self.reveal_button.setEnabled(bool(row))
        if not row:
            return
        path = Path(row["path"])
        result = row.get("result")
        self.preview_title.setText(path.name)
        self.preview_meta.setText(
            str(path.parent) + " · " + row["state"].replace("_", " ")
        )
        self.preview_meta.setToolTip(row.get("error", ""))
        key = (
            str(path),
            row["modified"],
            row["size"],
            result.page if result else None,
            self.query.text().strip(),
        )
        if key == self._preview_key:
            return
        self._preview_key = key
        self.preview.load(path, result.page if result else None)
        self.preview.set_match(self.query.text().strip() if result else "")
        digest = self.engine.store.digest(path)
        if digest and row["ocr"]:
            payload = (
                self.engine.store.cached_ocr(self.engine.ocr_worker.cache_key(digest))
                or []
            )
            self.preview.set_ocr(payload)
        passage = result.text if result else ""
        self.match_text.setText(
            (result.reason + " match · " if result else "")
            + passage[:300].replace("\n", " ")
        )
        self.match_text.setToolTip(passage)

    def edit_search(self):
        """Typing changes the draft only; searching always needs submission."""
        self.search_generation += 1
        self.pending_search = False
        self.search_cancel.set()
        self.search_clues = {}
        self.search_percent = 0
        query = self.query.text().strip()
        if not query:
            self.search_results = None
            self.load_files()
            return
        self.status.setText("Press Enter or Search when you're ready.")
        self.summary.setText(
            "Press Search to update results"
            if self.search_results is not None
            else f"{self.total:,} files · Ready to search"
        )

    def search_progress(self, message, generation):
        if generation != self.search_generation or self.search_cancel.is_set():
            return
        self.search_percent = max(
            self.search_percent, min(99, int(getattr(message, "percent", 0)))
        )
        self.search_phase = str(message)

    def search(self):
        if self._closing:
            return
        if not self.onboarded:
            return
        query = self.query.text().strip()
        if not query:
            self.search_results = None
            self.load_files()
            return
        if self.search_task:
            self.search_generation += 1
            self.search_cancel.set()
            self.pending_search = True
            self.search_phase = "Waiting for the previous search to finish"
            self.search_percent = 0
            return
        self.search_generation += 1
        generation = self.search_generation
        filters = self.filters()
        clues = dict(self.search_clues)
        cancellation = Event()
        self.search_cancel = cancellation
        self.search_started = time.monotonic()
        self.search_percent = 0
        self.search_phase = "Starting your search"
        self.search_session += 1
        random.shuffle(self.search_helpers)
        self.summary.setText("Searching…")
        self.search_button.setEnabled(False)
        self.search_task = Task(
            lambda progress: self.engine.search(
                query,
                limit=1000,
                filters=filters,
                clues=clues,
                progress=progress,
                cancelled=cancellation.is_set,
            ),
            self,
        )
        self.search_task.progress.connect(
            lambda message: self.search_progress(message, generation)
        )
        self.search_task.success.connect(
            lambda results: (
                self.search_finished(results, generation)
                if query == self.query.text().strip() and filters == self.filters()
                else None
            )
        )
        self.search_task.failure.connect(
            lambda message: self.search_failed(message, generation)
        )
        self.search_task.finished.connect(self.search_done)
        self.search_task.start()

    def search_finished(self, results, generation=None):
        if generation is not None and generation != self.search_generation:
            return
        self.search_results = results
        self.search_percent = 100
        self.search_phase = "Search complete"
        self.offset = 0
        self.load_files()
        self.status.setText("Search complete · Filename, text and meaning combined.")
        self.results_empty.setText(
            "No matches in this scope. Try fewer filters or another description."
        )

    def search_failed(self, message, generation):
        if generation == self.search_generation:
            self.search_percent = 0
            self.search_phase = "Search needs attention"
            self.show_error(message)

    def search_done(self):
        self.search_task.deleteLater()
        self.search_task = None
        self.search_button.setEnabled(True)
        if self.pending_search:
            self.pending_search = False
            # Only an explicit submission can queue another search.
            self.search()

    def pick_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Choose a location",
            "/documents"
            if os.environ.get("PROVIDENCE_CONTAINER")
            else str(Path.home() / "Documents"),
        )
        if (
            folder
            and os.environ.get("PROVIDENCE_CONTAINER")
            and not Path(folder).resolve().is_relative_to(Path("/documents"))
        ):
            self.show_error("Docker can index only /documents or mounted subfolders.")
            return ""
        return folder

    def add_pending_folder(self, root):
        root = str(Path(root).resolve())
        if root not in [
            self.onboarding_folders.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.onboarding_folders.count())
        ]:
            item = QListWidgetItem(root)
            item.setData(Qt.ItemDataRole.UserRole, root)
            self.onboarding_folders.addItem(item)
        self.update_pending_controls()

    def update_pending_controls(self):
        count = self.onboarding_folders.count()
        self.onboarding_continue.setEnabled(bool(count) and not self.task)
        self.onboarding_remove.setEnabled(bool(count))
        self.onboarding_empty.setVisible(not count)

    def choose_onboarding_folder(self):
        folder = self.pick_folder()
        if folder:
            self.add_pending_folder(folder)

    def select_drives(self):
        for root in default_roots():
            self.add_pending_folder(root)

    def remove_pending_folder(self):
        row = self.onboarding_folders.currentRow()
        if row >= 0:
            self.onboarding_folders.takeItem(row)
        self.update_pending_controls()

    def start_onboarding(self):
        roots = [
            Path(self.onboarding_folders.item(i).data(Qt.ItemDataRole.UserRole))
            for i in range(self.onboarding_folders.count())
        ]
        if not roots or self.task:
            return
        if any(not r.is_dir() for r in roots):
            self.onboarding_feedback.setText(
                "A selected folder is unavailable. Choose an accessible location."
            )
            return
        if self.source_changed:
            self.engine.store.clear_library()
        for root in self.engine.store.roots():
            if root not in roots:
                self.engine.store.remove_root(root)
        for root in roots:
            self.engine.store.add_root(root)
        self.engine.store.set_setting("onboarding_complete", "1")
        self.engine.store.set_setting("library_source", self.library_source)
        self.onboarded = True
        self.source_changed = False
        self.navigate(1)
        self.refresh_library()
        self.browse_library()
        if self.monitor:
            self.service.start()
        else:
            self.reindex()

    def add_folder(self):
        folder = self.pick_folder()
        if folder:
            self.engine.store.add_root(Path(folder).resolve())
            self.refresh_library()
            if self.monitor:
                self.service.request_scan()
            else:
                self.reindex()

    def remove_folder(self):
        item = self.folders.currentItem()
        if item:
            if self.service.busy or self.task:
                self.service.set_paused(True)
                QTimer.singleShot(200, self.remove_folder)
                return
            self.engine.store.remove_root(item.data(Qt.ItemDataRole.UserRole))
            self.refresh_library()
            self.browse_library()
            self.service.set_paused(False)
            self.service.request_scan()

    def reindex(self):
        if self.monitor:
            self.service.request_scan()
            return
        roots = [r for r in self.engine.store.roots() if r.is_dir()]
        if roots:
            self.start_task(
                lambda progress: self.engine.index_many(
                    roots, progress, cancelled=self.index_cancel.is_set
                ),
                self.index_finished,
            )

    def start_task(
        self,
        operation,
        handler,
        message=IndexProgress("Collecting · Checking your library"),
    ):
        if self.task:
            return
        self.index_cancel.clear()
        self._indexing_job = True
        self.set_progress(message)
        self.task = Task(operation, self)
        self.task.progress.connect(self.set_progress)
        self.task.success.connect(handler)
        self.task.failure.connect(self.show_error)
        self.task.finished.connect(self.task_finished)
        self.task.start()

    def task_finished(self):
        self.task.deleteLater()
        self.task = None
        self._indexing_job = False
        self.busy_panel.hide()
        self.busy_bar.hide()
        self.stop_button.setEnabled(True)
        self.library_updated()

    def index_finished(self, reports):
        self.status.setText(
            f"Library updated · {sum(r.indexed for r in reports)} indexed · {sum(r.unchanged for r in reports)} unchanged"
        )
        if any(r.cancelled for r in reports):
            self.status.setText("Indexing paused · Completed files remain searchable")
        self.library_updated()

    def set_progress(self, message):
        if self._closing:
            return
        stage, _, detail = str(message).partition(" · ")
        self.busy_panel.show()
        self.busy_bar.show()
        self.busy_title.setText(stage)
        self.busy_message.setText(detail)
        if isinstance(message, IndexProgress):
            self.busy_bar.setRange(0, 100)
            self.busy_bar.setValue(message.percent)
            self.busy_percent.setText(f"{message.percent}%")
            self.busy_counts.setText(f"{message.completed:,} / {message.total:,}")
        else:
            self.busy_bar.setRange(0, 0)
            self.busy_percent.clear()
            self.busy_counts.clear()

    def toggle_pause(self):
        value = not self.service.paused.is_set()
        self.service.set_paused(value)
        self.engine.store.set_setting("paused", "1" if value else "0")
        self.pause_button.setText("Resume indexing" if value else "Pause indexing")
        self.stop_button.setEnabled(not value)
        if value and self.task:
            self.index_cancel.set()
        self.status.setText(
            "Indexing paused · Search remains available"
            if value
            else "Automatic indexing resumed"
        )

    def stop_indexing(self):
        self.index_cancel.set()
        self.service.set_paused(True)
        self.pause_button.setText("Resume indexing")
        self.stop_button.setEnabled(False)
        self.engine.store.set_setting("paused", "1")

    def tick(self):
        if self._closing:
            return
        self.refresh_library()
        if (self.service.busy or self.task) and not self.query.text().strip():
            self.load_files()
        if self.pages.currentIndex() == 3:
            self.refresh_health()
        if not self.service.busy and not self.task:
            self.busy_panel.hide()
            self.busy_bar.hide()

    def library_updated(self):
        self.refresh_library()
        if not self.query.text().strip():
            self.load_files()
        else:
            self.status.setText(
                "Library updated · Press Search to refresh your results."
            )

    def refresh_health(self):
        selected = self.health_files.currentItem()
        selected_path = selected.data(Qt.ItemDataRole.UserRole) if selected else None
        stats = self.engine.store.stats()
        self.health_summary.setText(
            f"{sum(stats.values()):,} files discovered · {stats.get('ready', 0):,} searchable by content"
        )
        self.health_details.setText(
            " · ".join(
                f"{state.replace('_', ' ')}: {count:,}"
                for state, count in sorted(stats.items())
            )
            + "\nModel: "
            + self.engine.embedder.identity.split("@")[0]
        )
        self.health_files.clear()
        for state in ("failed", "empty", "ocr_pending"):
            rows, _ = self.engine.store.list_files(state=state, limit=100)
            for row in rows:
                item = QListWidgetItem(row["name"] + "\n" + row["error"])
                item.setData(Qt.ItemDataRole.UserRole, row["path"])
                item.setToolTip(row["path"])
                self.health_files.addItem(item)
                if row["path"] == selected_path:
                    self.health_files.setCurrentItem(item)
        self.health_files.setVisible(self.health_files.count() > 0)
        self.health_empty.setVisible(self.health_files.count() == 0)
        unavailable = [str(r) for r in self.engine.store.roots() if not r.is_dir()]
        if unavailable:
            self.health_details.setText(
                self.health_details.text() + "\nUnavailable: " + ", ".join(unavailable)
            )

    def retry_failed(self):
        self.engine.store.retry()
        self.service.wake.set()
        if not self.monitor:
            self.reindex()

    def force_selected_ocr(self):
        item = self.health_files.currentItem()
        if item:
            path = item.data(Qt.ItemDataRole.UserRole)
            if Path(path).suffix.lower() not in {".pdf", ".png", ".jpg", ".jpeg"}:
                self.show_error("Force OCR applies to PDFs and PNG/JPEG images.")
                return
            self.engine.store.retry(path, force_ocr=True)
            self.service.wake.set()
            if not self.monitor:
                self.reindex()

    def save_exclusions(self):
        self.engine.store.set_setting(
            "exclusions",
            json.dumps(
                [
                    p.strip()
                    for p in self.exclusions.toPlainText().splitlines()
                    if p.strip()
                ]
            ),
        )
        self.service.request_scan()
        self.status.setText("Exclusions saved · Updating library scope")
        if not self.monitor:
            self.reindex()

    def clear_indexes(self):
        answer = QMessageBox.question(
            self,
            "Clear local indexes",
            "Remove Providence’s library and cached document text for both models? Original files remain unchanged.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.service.set_paused(True)
        self.index_cancel.set()
        self._clear_indexes_when_idle()

    def _clear_indexes_when_idle(self):
        if self.service.busy or self.task or self.search_task:
            QTimer.singleShot(200, self._clear_indexes_when_idle)
            return
        from .store import Store
        from .embeddings import LocalEmbedder, QwenEmbedder

        for name, identity in [
            ("index.sqlite3", LocalEmbedder.identity),
            ("index-qwen.sqlite3", QwenEmbedder.identity),
        ]:
            path = self.engine.store.path.parent / name
            if path.exists():
                store = Store(path, identity)
                store.clear_library()
                store.set_setting("onboarding_complete", "0")
        self.engine.store.clear_library()
        self.engine.store.set_setting("onboarding_complete", "0")
        self.onboarded = False
        self.search_results = None
        self.onboarding_folders.clear()
        self.update_pending_controls()
        self.refresh_library()
        self.browse_library()
        self.navigate(0)
        self.status.setText("Local indexes cleared · Original files unchanged")

    def ocr_changed(self, value):
        self.engine.store.set_setting("ocr_enabled", "1" if value else "0")
        self.service.request_scan()

    def switch_model(self):
        profile = self.model_combo.currentData()
        if (profile == "qwen") == (
            "Qwen/" in self.engine.embedder.identity
        ) or self.task:
            return
        if profile == "qwen" and not (qwen_dir() / "REVISION").exists():
            self.show_error(
                "Qwen assets are missing. Run scripts/download-qwen.py during setup, then try again."
            )
            return
        from .embeddings import LocalEmbedder, QwenEmbedder
        from .store import Store

        embedder = QwenEmbedder() if profile == "qwen" else LocalEmbedder()
        target = self.engine.store.path.parent / (
            "index-qwen.sqlite3" if profile == "qwen" else "index.sqlite3"
        )
        replacement = Engine(Store(target, embedder.identity), embedder)
        roots = self.engine.store.roots()
        for key in (
            "exclusions",
            "theme",
            "reduced_motion",
            "ocr_enabled",
            "low_resource",
            "library_source",
            "onboarding_complete",
        ):
            value = self.engine.store.setting(key)
            if value is not None:
                replacement.store.set_setting(key, value)
        for previous in replacement.store.roots():
            if previous not in roots:
                replacement.store.remove_root(previous)

        def build(progress):
            reports = replacement.index_many(
                [r for r in roots if r.is_dir()],
                progress,
                cancelled=self.index_cancel.is_set,
            )
            if any(r.errors for r in reports):
                raise ValueError(
                    "New model build has issues. Current model retained; inspect files and retry."
                )
            return replacement

        def switched(new_engine):
            if self.index_cancel.is_set():
                new_engine.ocr_worker.close()
                return
            self.service.close()
            self.engine = new_engine
            self.service = LibraryService(
                new_engine,
                self.background_progress.emit,
                self.background_changed.emit,
                self.background_error.emit,
            )
            (new_engine.store.path.parent / "active-model.txt").write_text(
                profile, encoding="utf-8"
            )
            if self.monitor:
                self.service.start()
            self.status.setText("Search model switched · Previous model index retained")
            self.browse_library()

        self.start_task(
            build, switched, IndexProgress("Loading · Building the new model index")
        )

    def show_error(self, message):
        self.status.setText("Needs attention · " + str(message))
        self.status.setToolTip(str(message))

    def open_document(self):
        row = self.current_row()
        if not row:
            return
        path = Path(row["path"])
        if not path.is_file():
            self.show_error(
                "This file has moved or been deleted. The library will update automatically."
            )
            return
        if os.environ.get("PROVIDENCE_CONTAINER"):
            self.preview.load(path)
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            self.show_error("No application could open this file.")

    def reveal_document(self):
        row = self.current_row()
        if not row:
            return
        path = Path(row["path"])
        if not path.is_file():
            self.show_error("This file has moved or been deleted.")
            return
        try:
            if os.name == "nt":
                subprocess.Popen(["explorer.exe", "/select,", str(path)])
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
        except OSError as error:
            self.show_error(str(error))

    def copy_path(self):
        row = self.current_row()
        if row:
            QApplication.clipboard().setText(row["path"])

    def copy_passage(self):
        row = self.current_row()
        result = row.get("result") if row else None
        if result:
            QApplication.clipboard().setText(result.text)

    def context_menu(self, position):
        index = self.results.indexAt(position)
        if index.isValid():
            self.results.setCurrentIndex(index)
        if not self.current_row():
            return
        menu = QMenu(self)
        for text, action in [
            ("Open file", self.open_document),
            ("Show in Explorer", self.reveal_document),
            ("Copy path", self.copy_path),
            ("Copy passage", self.copy_passage),
            ("Retry content indexing", self.retry_current),
        ]:
            menu.addAction(text, action)
        menu.exec(self.results.viewport().mapToGlobal(position))

    def retry_current(self):
        row = self.current_row()
        if row:
            self.engine.store.retry(row["path"])
            self.service.wake.set()
        if row and not self.monitor:
            self.reindex()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(
            Path(url.toLocalFile()).is_dir() for url in event.mimeData().urls()
        ):
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.is_dir() and (
                not os.environ.get("PROVIDENCE_CONTAINER")
                or path.resolve().is_relative_to(Path("/documents"))
            ):
                if self.onboarded:
                    self.engine.store.add_root(path.resolve())
                else:
                    self.add_pending_folder(path)
        self.refresh_library()
        self.service.request_scan()
        event.acceptProposedAction()

    def closeEvent(self, event):
        self._closing = True
        self.pending_search = False
        self.search_cancel.set()
        self.index_cancel.set()
        self.service.stop.set()
        self.service.wake.set()
        if self.task or self.search_task or not self.service.close(timeout=0.1):
            self.status.setText("Finishing the current batch before closing…")
            event.ignore()
            QTimer.singleShot(200, self.close)
            return
        self.refresh_timer.stop()
        self.search_cancel.set()
        self.engine.ocr_worker.close()
        self.engine.store.set_setting("pane_sizes", json.dumps(self.splitter.sizes()))
        self.engine.store.set_setting(
            "column_widths", json.dumps([self.results.columnWidth(i) for i in range(5)])
        )
        event.accept()


def launch(engine):
    from .quick_ui import QuickWindow

    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Providence")
    window = QuickWindow(engine)
    window.show()
    return app.exec()
