"""Explicit, cancellable library tools. Originals are always read-only."""
from pathlib import Path
from threading import Event

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QTreeWidget, QTreeWidgetItem, QProgressBar, QSplitter, QPlainTextEdit,
)
from .library_tools import ImageLibrary, find_duplicates
from .preview import DocumentPreview
from .ui import Task


class LibraryToolsDialog(QDialog):
    def __init__(self, controller, mode, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.controller, self.mode = controller, mode
        self.scope = controller.active_root
        self.worker = None
        self.cancelled = Event()
        self.closing = False
        self.images = ImageLibrary(controller.engine.store) if mode == 'images' else None
        self.setWindowTitle('Providence · ' + ('Image search' if self.images else 'Duplicate review'))
        self.setStyleSheet(controller.styleSheet())
        self.resize(1050, 740)
        self.setMinimumSize(780, 560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        heading = QLabel('Find an image by what you remember' if self.images else 'Review identical copies')
        heading.setObjectName('title')
        layout.addWidget(heading)
        description = QLabel(
            'Describe a scene in English. Update the local image index first; repeat after files change. '
            'Results are visual similarities, not confidence scores.' if self.images else
            'Compare file contents, even when names differ. Only byte-identical copies are grouped. '
            'No file is changed or deleted.'
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        scope = QLabel('Location: ' + (str(self.scope) if self.scope else 'All selected library locations'))
        scope.setWordWrap(True)
        layout.addWidget(scope)
        controls = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText('A beach at sunset, a blue bicycle, a handwritten diagram…')
        self.query.setAccessibleName('Describe an image')
        self.query.setVisible(bool(self.images))
        controls.addWidget(self.query, 1)
        self.submit = QPushButton('Search images' if self.images else 'Compare files')
        self.submit.setObjectName('primary')
        self.submit.clicked.connect(self.search if self.images else self.duplicates)
        self.query.returnPressed.connect(self.search)
        controls.addWidget(self.submit)
        self.update_button = QPushButton('Update image index')
        self.update_button.setVisible(bool(self.images))
        self.update_button.clicked.connect(self.update_images)
        controls.addWidget(self.update_button)
        self.stop = QPushButton('Cancel')
        self.stop.setEnabled(False)
        self.stop.clicked.connect(self.cancelled.set)
        controls.addWidget(self.stop)
        layout.addLayout(controls)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.status = QLabel('Ready when you are.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.errors = QPlainTextEdit()
        self.errors.setReadOnly(True)
        self.errors.setAccessibleName('Skipped files and reasons')
        self.errors.setMaximumHeight(100)
        self.errors.hide()
        layout.addWidget(self.errors)
        splitter = QSplitter()
        self.results = QTreeWidget()
        self.results.setHeaderLabels(['File / group', 'Location'])
        self.results.setColumnWidth(0, 280)
        self.results.currentItemChanged.connect(self.select)
        splitter.addWidget(self.results)
        self.preview = DocumentPreview()
        splitter.addWidget(self.preview)
        splitter.setSizes([580, 400])
        layout.addWidget(splitter, 1)
        self.open_button = QPushButton('Open selected file')
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self.open_file)
        layout.addWidget(self.open_button)

    def selected_path(self):
        item = self.results.currentItem()
        return item.data(0, Qt.ItemDataRole.UserRole) if item else None

    def select(self, *_):
        path = self.selected_path()
        self.open_button.setEnabled(bool(path))
        if path:
            self.preview.load(path)
        else:
            self.preview.clear()

    def open_file(self):
        path = self.selected_path()
        if path and Path(path).is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def run(self, operation, handler):
        if self.worker:
            return
        self.cancelled.clear()
        self.errors.clear()
        self.errors.hide()
        self.results.clear()
        self.preview.clear()
        self.submit.setEnabled(False)
        self.update_button.setEnabled(False)
        self.stop.setEnabled(True)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.status.setText('Working locally…')
        self.worker = Task(operation, self)
        self.worker.progress.connect(self.show_progress)
        self.worker.success.connect(handler)
        self.worker.failure.connect(lambda message: self.status.setText('Needs attention: ' + message))
        self.worker.finished.connect(self.done_work)
        self.worker.start()

    def show_progress(self, message):
        self.status.setText(str(message))
        if hasattr(message, 'percent'):
            self.progress.setRange(0, 100)
            self.progress.setValue(message.percent)

    def done_work(self):
        self.worker.deleteLater()
        self.worker = None
        self.submit.setEnabled(True)
        self.update_button.setEnabled(True)
        self.stop.setEnabled(False)
        self.progress.hide()
        if self.cancelled.is_set():
            self.status.setText('Cancelled. Completed image entries are kept; originals are unchanged.')
        if self.closing:
            self.close()

    def duplicates(self):
        self.run(lambda progress: find_duplicates(self.controller.engine.store, self.scope, progress, self.cancelled.is_set), self.show_duplicates)

    def show_duplicates(self, report):
        copies = sum(len(group['paths']) - 1 for group in report.groups)
        # Bound widgets while reporting the full scan count.
        for group in report.groups[:500]:
            parent = QTreeWidgetItem([f"{len(group['paths'])} identical copies · {group['size']:,} bytes each", 'SHA-256 content match'])
            self.results.addTopLevelItem(parent)
            for path in group['paths']:
                child = QTreeWidgetItem([Path(path).name, str(Path(path).parent)])
                child.setData(0, Qt.ItemDataRole.UserRole, path)
                parent.addChild(child)
        self.results.expandAll()
        self.status.setText(f'{len(report.groups)} groups · {copies} extra copies · {report.checked} files compared. '
                            f'{len(report.errors)} files skipped. Showing up to 500 groups.')
        if report.errors:
            self.errors.setPlainText('\n'.join(report.errors[:100]))
            self.errors.show()

    def update_images(self):
        self.run(lambda progress: self.images.update(self.scope, progress, self.cancelled.is_set),
                 self.show_image_update)

    def show_image_update(self, report):
        self.status.setText(f"{report['indexed']} images indexed · {report['unchanged']} unchanged · {len(report['errors'])} skipped. Enter a description to search.")
        if report['errors']:
            self.errors.setPlainText('\n'.join(report['errors'][:100]))
            self.errors.show()

    def search(self):
        if not self.images or not self.query.text().strip():
            return
        query = self.query.text().strip()
        self.run(lambda _: self.images.search(query, self.scope, cancelled=self.cancelled.is_set), self.show_images)

    def show_images(self, results):
        for index, result in enumerate(results, 1):
            item = QTreeWidgetItem([f'{index}. {Path(result.path).name}', str(Path(result.path).parent)])
            item.setData(0, Qt.ItemDataRole.UserRole, result.path)
            self.results.addTopLevelItem(item)
        self.status.setText(f'{len(results)} images ranked by visual similarity.' if results else
                            'No current image entries. Update the image index for this location first.')

    def closeEvent(self, event):
        if self.worker:
            self.closing = True
            self.cancelled.set()
            self.status.setText('Finishing the current operation before closing…')
            event.ignore()
        else:
            super().closeEvent(event)

    def reject(self):
        if self.worker:
            self.close()
        else:
            super().reject()
