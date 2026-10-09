"""Local document previews: rendered PDF pages and formatted Word documents."""
from html import escape
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QScrollArea, QStackedWidget,
    QTextBrowser, QVBoxLayout, QWidget,
)


def word_html(path):
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    parts = []
    for block in Document(path).iter_inner_content():
        if isinstance(block, Paragraph):
            runs = []
            for run in block.runs:
                text = escape(run.text).replace("\n", "<br>")
                if run.bold:
                    text = f"<b>{text}</b>"
                if run.italic:
                    text = f"<i>{text}</i>"
                if run.underline:
                    text = f"<u>{text}</u>"
                runs.append(text)
            style = block.style.name if block.style else ""
            tag = "h1" if style == "Title" else "p"
            if style.startswith("Heading ") and style[-1:].isdigit():
                tag = f"h{min(int(style[-1]), 6)}"
            parts.append(f"<{tag}>{''.join(runs) or '&nbsp;'}</{tag}>")
        elif isinstance(block, Table):
            rows = ["<tr>" + "".join(f"<td>{escape(cell.text)}</td>" for cell in row.cells) + "</tr>"
                    for row in block.rows]
            parts.append('<table border="1" cellspacing="0" cellpadding="8">' + ''.join(rows) + '</table>')
    return '<html><body style="font-family:Segoe UI; color:#242927;">' + ''.join(parts) + '</body></html>'


class DocumentPreview(QWidget):
    def __init__(self):
        super().__init__()
        self.path = None
        self.page = 0
        self.page_count = 0
        self.zoom = 1.0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.stack = QStackedWidget()
        self.empty = QLabel("Select a file to preview\n\nPDF · Word · Text · Markdown")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setObjectName("muted")
        self.stack.addWidget(self.empty)
        self.paper = QTextBrowser()
        self.paper.setOpenExternalLinks(False)
        self.paper.setObjectName("paper")
        self.paper.document().setDocumentMargin(38)
        self.stack.addWidget(self.paper)
        self.scroll = QScrollArea()
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.image = QLabel()
        self.image.setContentsMargins(24, 24, 24, 24)
        self.scroll.setWidget(self.image)
        self.stack.addWidget(self.scroll)
        layout.addWidget(self.stack, 1)
        self.toolbar = QWidget()
        row = QHBoxLayout(self.toolbar)
        self.previous = QPushButton("‹")
        self.next = QPushButton("›")
        self.position = QLabel()
        self.minus = QPushButton("−")
        self.plus = QPushButton("+")
        self.scale = QLabel("100%")
        for button in (self.previous, self.next, self.minus, self.plus):
            button.setFixedWidth(38)
        self.previous.setAccessibleName("Previous PDF page")
        self.next.setAccessibleName("Next PDF page")
        self.minus.setAccessibleName("Zoom out")
        self.plus.setAccessibleName("Zoom in")
        self.previous.clicked.connect(lambda: self.turn(-1))
        self.next.clicked.connect(lambda: self.turn(1))
        self.minus.clicked.connect(lambda: self.change_zoom(-0.2))
        self.plus.clicked.connect(lambda: self.change_zoom(0.2))
        for widget in (self.previous, self.position, self.next):
            row.addWidget(widget)
        row.addStretch()
        for widget in (self.minus, self.scale, self.plus):
            row.addWidget(widget)
        layout.addWidget(self.toolbar)
        self.toolbar.hide()

    def clear(self):
        self.path = None
        self.image.clear()
        self.paper.clear()
        self.empty.setText("Select a file to preview\n\nPDF · Word · Text · Markdown")
        self.stack.setCurrentIndex(0)
        self.toolbar.hide()

    def load(self, path, page=None):
        self.clear()
        self.path = Path(path)
        try:
            if not self.path.is_file():
                raise ValueError("This file has moved or been deleted. Re-index its folder.")
            if self.path.suffix.lower() == ".pdf":
                import pymupdf
                with pymupdf.open(self.path) as document:
                    if document.needs_pass:
                        raise ValueError("This PDF needs a password. Open it in your PDF app.")
                    self.page_count = len(document)
                self.page = max(0, min((page or 1) - 1, self.page_count - 1))
                self.zoom = 1.0
                self.render_pdf()
                self.stack.setCurrentIndex(2)
                self.toolbar.show()
            elif self.path.suffix.lower() == ".docx":
                self.paper.setHtml(word_html(self.path))
                self.stack.setCurrentIndex(1)
            else:
                from .documents import extract
                text = extract(self.path)[0].text
                if self.path.suffix.lower() == ".md":
                    from PySide6.QtGui import QTextDocument
                    self.paper.document().setMarkdown(text, QTextDocument.MarkdownFeature.MarkdownDialectGitHub)
                else:
                    self.paper.setPlainText(text)
                self.stack.setCurrentIndex(1)
        except Exception as error:
            self.empty.setText(f"Preview unavailable\n\n{error}\n\nUse Open file to view the original.")
            self.empty.setWordWrap(True)
            self.stack.setCurrentIndex(0)
            self.toolbar.hide()

    def render_pdf(self):
        import pymupdf
        with pymupdf.open(self.path) as document:
            page = document[self.page]
            width = max(200, self.scroll.width() - 76)
            factor = min(width / page.rect.width * self.zoom, 3.0)
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(factor, factor), alpha=False)
            image = QPixmap()
            image.loadFromData(pixmap.tobytes("png"))
        self.image.setPixmap(image)
        self.image.setFixedSize(image.width() + 48, image.height() + 48)
        self.position.setText(f"Page {self.page + 1} of {self.page_count}")
        self.scale.setText(f"{self.zoom:.0%}")
        self.previous.setEnabled(self.page > 0)
        self.next.setEnabled(self.page + 1 < self.page_count)
        self.minus.setEnabled(self.zoom > 0.6)
        self.plus.setEnabled(self.zoom < 2.0)
        self.scroll.verticalScrollBar().setValue(0)

    def turn(self, delta):
        self.page = max(0, min(self.page + delta, self.page_count - 1))
        self.render_pdf()

    def change_zoom(self, delta):
        self.zoom = round(max(0.6, min(self.zoom + delta, 2.0)), 1)
        self.render_pdf()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.path and self.stack.currentIndex() == 2:
            try:
                self.render_pdf()
            except Exception as error:
                self.empty.setText(f"Preview unavailable\n\n{error}")
                self.stack.setCurrentIndex(0)
                self.toolbar.hide()

    def toPlainText(self):
        return self.paper.toPlainText()
