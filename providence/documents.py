from dataclasses import dataclass
from pathlib import Path
import re

TEXT_FORMATS = {
    '.txt', '.md', '.markdown', '.rst', '.log', '.csv', '.tsv', '.json', '.jsonl',
    '.yaml', '.yml', '.toml', '.xml', '.ini', '.cfg', '.conf', '.sql',
    '.py', '.pyi', '.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs', '.java', '.kt',
    '.kts', '.c', '.h', '.cpp', '.hpp', '.cc', '.cs', '.go', '.rs', '.rb', '.php',
    '.swift', '.dart', '.r', '.sh', '.bash', '.ps1', '.bat', '.cmd', '.css',
    '.scss', '.sass', '.less', '.vue', '.svelte', '.qml', '.html', '.htm',
}
IMAGE_FORMATS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff'}
SUPPORTED = TEXT_FORMATS | IMAGE_FORMATS | {'.pdf', '.docx', '.xlsx', '.pptx'}
MAX_TEXT_BYTES = 10 * 1024 * 1024
MAX_EXTRACTED_CHARS = 2_000_000


def read_text(path):
    if path.stat().st_size > MAX_TEXT_BYTES:
        raise ValueError('Text file exceeds the 10 MB extraction limit')
    with path.open('rb') as stream:
        raw = stream.read(MAX_TEXT_BYTES + 1)
    if len(raw) > MAX_TEXT_BYTES:
        raise ValueError('Text file exceeds the 10 MB extraction limit')
    encoding = 'utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig'
    if encoding != 'utf-16' and b'\x00' in raw:
        raise ValueError('Binary content in a text file')
    try:
        return raw.decode(encoding)
    except UnicodeDecodeError:
        return raw.decode('cp1252')


def check_office_archive(path):
    from zipfile import ZipFile
    with ZipFile(path) as archive:
        if sum(item.file_size for item in archive.infolist()) > 100 * 1024 * 1024:
            raise ValueError('Office document exceeds the 100 MB expanded-size limit')


def spreadsheet_passages(path):
    from openpyxl import load_workbook
    check_office_archive(path)
    workbook = load_workbook(path, read_only=True, data_only=True, keep_links=False)
    passages, count = [], 0
    try:
        for sheet in workbook:
            # Ignore unreliable worksheet dimension declarations; stream real rows.
            sheet.reset_dimensions()
            lines = [f'Sheet: {sheet.title}']
            for number, row in enumerate(sheet.iter_rows(values_only=True, max_row=100_001), 1):
                if number > 100_000 or len(row) > 1000:
                    raise ValueError('Spreadsheet exceeds the row/column extraction limit')
                text = ' | '.join('' if value is None else str(value) for value in row)
                if not text.strip(' |'):
                    continue
                line = f'Row {number}: {text}'
                count += len(line)
                if count > MAX_EXTRACTED_CHARS:
                    raise ValueError('Spreadsheet exceeds the extracted-text limit')
                lines.append(line)
                if len(lines) >= 101:
                    passages.append(Passage('\n'.join(lines)))
                    lines = [f'Sheet: {sheet.title}']
            if len(lines) > 1:
                passages.append(Passage('\n'.join(lines)))
    finally:
        workbook.close()
    return passages


@dataclass(frozen=True)
class Passage:
    text: str
    page: int | None = None
    ocr: bool = False


def extract(path: Path) -> list[Passage]:
    suffix = path.suffix.lower()
    if suffix in TEXT_FORMATS:
        content = read_text(path)
        if suffix in {'.html', '.htm'}:
            from html.parser import HTMLParser

            class VisibleText(HTMLParser):
                def __init__(self):
                    super().__init__(convert_charrefs=True)
                    self.hidden = 0
                    self.parts = []

                def handle_starttag(self, tag, attrs):
                    if tag in {'script', 'style', 'noscript'}:
                        self.hidden += 1

                def handle_endtag(self, tag):
                    if tag in {'script', 'style', 'noscript'}:
                        self.hidden = max(0, self.hidden - 1)

                def handle_data(self, data):
                    if not self.hidden:
                        self.parts.append(data)

            parser = VisibleText()
            parser.feed(content)
            content = '\n'.join(parser.parts)
        return [Passage(content)]
    if suffix == '.xlsx':
        return spreadsheet_passages(path)
    if suffix == '.pptx':
        from pptx import Presentation
        check_office_archive(path)
        passages, count = [], 0
        for number, slide in enumerate(Presentation(path).slides, 1):
            parts = [shape.text for shape in slide.shapes if shape.has_text_frame]
            parts += [' | '.join(cell.text for cell in row.cells)
                      for shape in slide.shapes if shape.has_table for row in shape.table.rows]
            text = f'Slide {number}\n' + '\n'.join(parts)
            count += len(text)
            if count > MAX_EXTRACTED_CHARS:
                raise ValueError('Presentation exceeds the extracted-text limit')
            passages.append(Passage(text, number))
        return passages
    if suffix == ".pdf":
        import pymupdf

        with pymupdf.open(path) as doc:
            if doc.needs_pass:
                raise ValueError("Password-protected PDF")
            return [
                Passage(page.get_text(sort=True), i + 1) for i, page in enumerate(doc)
            ]
    if suffix == ".docx":
        from docx import Document

        check_office_archive(path)
        document = Document(path)
        texts = [paragraph.text for paragraph in document.paragraphs]
        texts.extend(
            " | ".join(cell.text for cell in row.cells)
            for table in document.tables
            for row in table.rows
        )
        return [Passage("\n".join(texts))]
    raise ValueError(f"Unsupported file type: {suffix}")


def chunk(passages: list[Passage], words: int = 90, overlap: int = 20) -> list[Passage]:
    if not 0 <= overlap < words:
        raise ValueError("Overlap must be smaller than chunk size")
    result = []
    for passage in passages:
        tokens = re.findall(r"\S+", passage.text)
        for start in range(0, len(tokens), words - overlap):
            result.append(
                Passage(
                    " ".join(tokens[start : start + words]), passage.page, passage.ocr
                )
            )
            if start + words >= len(tokens):
                break
    return result
