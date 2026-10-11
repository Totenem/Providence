"""Local document previews: rendered PDF pages and formatted Word documents."""

from html import escape
from pathlib import Path
from functools import lru_cache
import re
from .documents import SUPPORTED, IMAGE_FORMATS, extract

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPainter, QColor, QTextCursor, QTextCharFormat
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


@lru_cache(maxsize=12)
def word_html(path, signature=None):
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
            rows = [
                "<tr>"
                + "".join(f"<td>{escape(cell.text)}</td>" for cell in row.cells)
                + "</tr>"
                for row in block.rows
            ]
            parts.append(
                '<table border="1" cellspacing="0" cellpadding="8">'
                + "".join(rows)
                + "</table>"
            )
    return (
        '<html><body style="font-family:Segoe UI;">' + "".join(parts) + "</body></html>"
    )


class DocumentPreview(QWidget):
    def __init__(self):
        super().__init__()
        self.path = None
        self.page = 0
        self.page_count = 0
        self.zoom = 1.0
        self.match = ""
        self.render_cache = {}
        self.ocr_payload = []
        self.image_source = None
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
        self.scroll.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
        )
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
        self.match = ""
        self.ocr_payload = []
        self.image_source = None
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
                raise ValueError(
                    "This file has moved or been deleted. Re-index its folder."
                )
            if self.path.suffix.lower() == ".pdf":
                import pymupdf

                with pymupdf.open(self.path) as document:
                    if document.needs_pass:
                        raise ValueError(
                            "This PDF needs a password. Open it in your PDF app."
                        )
                    self.page_count = len(document)
                self.page = max(0, min((page or 1) - 1, self.page_count - 1))
                self.zoom = 1.0
                self.render_pdf()
                self.stack.setCurrentIndex(2)
                self.toolbar.show()
            elif self.path.suffix.lower() == ".docx":
                stat = self.path.stat()
                self.paper.setHtml(
                    word_html(self.path, (stat.st_size, stat.st_mtime_ns))
                )
                self.stack.setCurrentIndex(1)
            elif self.path.suffix.lower() in IMAGE_FORMATS:
                pix = QPixmap(str(self.path))
                if pix.isNull():
                    raise ValueError("This image cannot be decoded")
                pix = pix.scaled(
                    1200,
                    1600,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.image_source = pix
                self.image.setPixmap(pix)
                self.image.setFixedSize(pix.width() + 48, pix.height() + 48)
                self.stack.setCurrentIndex(2)
            else:
                if self.path.suffix.lower() not in SUPPORTED:
                    raise ValueError(
                        "Content preview is unavailable for this file type"
                    )
                if self.path.stat().st_size > 5 * 1024 * 1024:
                    raise ValueError("This file is too large for an inline preview")
                text = '\n\n'.join(p.text for p in extract(self.path))
                if self.path.suffix.lower() == ".md":
                    from PySide6.QtGui import QTextDocument

                    self.paper.document().setMarkdown(
                        text, QTextDocument.MarkdownFeature.MarkdownDialectGitHub
                    )
                else:
                    self.paper.setPlainText(text)
                self.stack.setCurrentIndex(1)
        except Exception as error:
            self.empty.setText(
                f"Preview unavailable\n\n{error}\n\nUse Open file to view the original."
            )
            self.empty.setWordWrap(True)
            self.stack.setCurrentIndex(0)
            self.toolbar.hide()

    def render_pdf(self):
        import pymupdf

        if not self.path or self.path.suffix.lower() != ".pdf":
            return
        stat = self.path.stat()
        key = (
            str(self.path),
            stat.st_mtime_ns,
            self.page,
            self.scroll.width(),
            self.zoom,
            self.match,
        )
        if key in self.render_cache:
            image = self.render_cache[key]
        else:
            with pymupdf.open(self.path) as document:
                page = document[self.page]
                width = max(200, self.scroll.width() - 76)
                factor = min(width / page.rect.width * self.zoom, 3.0)
                pixmap = page.get_pixmap(
                    matrix=pymupdf.Matrix(factor, factor), alpha=False
                )
                image = QPixmap()
                image.loadFromData(pixmap.tobytes("png"))
                if self.match:
                    painter = QPainter(image)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(255, 202, 50, 100))
                    terms = [self.match] + re.findall(r"\w+", self.match)[:12]
                    from PySide6.QtCore import QRectF

                    for term in terms:
                        if len(term) < 2:
                            continue
                        for rect in page.search_for(term):
                            painter.drawRect(
                                QRectF(
                                    rect.x0 * factor,
                                    rect.y0 * factor,
                                    rect.width * factor,
                                    rect.height * factor,
                                )
                            )
                    painter.end()
            if len(self.render_cache) >= 12:
                self.render_cache.pop(next(iter(self.render_cache)))
            self.render_cache[key] = image
        self.image.setPixmap(image)
        self.overlay_ocr()
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

    def set_match(self, text):
        self.match = text
        if self.path and self.path.suffix.lower() == ".pdf":
            self.render_pdf()
        elif self.stack.currentIndex() == 1:
            self.paper.setExtraSelections([])
            if text:
                self.highlight(text)
        elif self.image_source is not None:
            self.image.setPixmap(self.image_source)
            self.overlay_ocr()

    def set_ocr(self, payload):
        self.ocr_payload = payload
        self.overlay_ocr()

    def overlay_ocr(self):
        if not self.match or not self.ocr_payload:
            return
        from PySide6.QtCore import QRectF

        image = self.image.pixmap().copy()
        if image.isNull():
            return
        painter = QPainter(image)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 202, 50, 100))
        terms = re.findall(r"\w+", self.match.casefold())
        for item in self.ocr_payload:
            if self.path.suffix.lower() == ".pdf" and item["page"] != self.page + 1:
                continue
            for region in item.get("regions", []):
                if any(
                    term in region["text"].casefold() for term in terms if len(term) > 1
                ):
                    x0, y0, x1, y1 = region["rect"]
                    painter.drawRect(
                        QRectF(
                            x0 * image.width(),
                            y0 * image.height(),
                            (x1 - x0) * image.width(),
                            (y1 - y0) * image.height(),
                        )
                    )
        painter.end()
        self.image.setPixmap(image)

    def highlight(self, text):
        from PySide6.QtWidgets import QTextEdit

        selections = []
        terms = [text] + re.findall(r"\w+", text)[:12]
        for term in terms:
            if len(term) < 2:
                continue
            cursor = QTextCursor(self.paper.document())
            while len(selections) < 500:
                cursor = self.paper.document().find(term, cursor)
                if cursor.isNull():
                    break
                selection = QTextEdit.ExtraSelection()
                selection.cursor = cursor
                selection.format = QTextCharFormat()
                selection.format.setBackground(QColor("#ffe18a"))
                selection.format.setForeground(QColor("#202a38"))
                selections.append(selection)
        self.paper.setExtraSelections(selections)

    def find(self, text):
        if not text:
            return
        self.set_match(text)
        if self.path and self.path.suffix.lower() == ".pdf":
            import pymupdf

            with pymupdf.open(self.path) as document:
                for step in range(1, self.page_count + 1):
                    index = (self.page + step) % self.page_count
                    if document[index].search_for(text):
                        self.page = index
                        break
                    if any(
                        item["page"] == index + 1
                        and text.casefold() in item["text"].casefold()
                        for item in self.ocr_payload
                    ):
                        self.page = index
                        break
            self.render_pdf()
        elif self.stack.currentIndex() == 1:
            if not self.paper.find(text):
                self.paper.moveCursor(QTextCursor.MoveOperation.Start)
                self.paper.find(text)
