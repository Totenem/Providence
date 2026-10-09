from dataclasses import dataclass
from pathlib import Path
import re

SUPPORTED = {".pdf", ".docx", ".txt", ".md"}


@dataclass(frozen=True)
class Passage:
    text: str
    page: int | None = None


def extract(path: Path) -> list[Passage]:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        raw = path.read_bytes()
        encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        try:
            content = raw.decode(encoding)
        except UnicodeDecodeError:
            content = raw.decode("cp1252")
        return [Passage(content)]
    if suffix == ".pdf":
        import pymupdf
        with pymupdf.open(path) as doc:
            if doc.needs_pass:
                raise ValueError("Password-protected PDF")
            return [Passage(page.get_text(sort=True), i + 1) for i, page in enumerate(doc)]
    if suffix == ".docx":
        from docx import Document
        document = Document(path)
        texts = [paragraph.text for paragraph in document.paragraphs]
        texts.extend(" | ".join(cell.text for cell in row.cells)
                     for table in document.tables for row in table.rows)
        return [Passage("\n".join(texts))]
    raise ValueError(f"Unsupported file type: {suffix}")


def chunk(passages: list[Passage], words: int = 90, overlap: int = 20) -> list[Passage]:
    if not 0 <= overlap < words:
        raise ValueError("Overlap must be smaller than chunk size")
    result = []
    for passage in passages:
        tokens = re.findall(r"\S+", passage.text)
        for start in range(0, len(tokens), words - overlap):
            result.append(Passage(" ".join(tokens[start:start + words]), passage.page))
            if start + words >= len(tokens):
                break
    return result
