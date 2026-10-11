"""Read-only duplicate review and offline visual retrieval over catalogued files."""

from array import array
from collections import defaultdict
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from threading import RLock
import json
import os
import sys

from .discovery import excluded, DEFAULT_EXCLUSIONS
from .documents import IMAGE_FORMATS

CLIP_ID = 'openai/clip-vit-base-patch32'
CLIP_REVISION = '3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268'


def clip_dir():
    if os.environ.get('PROVIDENCE_CLIP_DIR'):
        return Path(os.environ['PROVIDENCE_CLIP_DIR'])
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / 'models' / 'clip-vit-base-patch32'
    return Path(__file__).resolve().parents[1] / 'build' / 'clip'


def signature(path):
    stat = path.stat()
    return [stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]


def catalog_files(store, root=None):
    offset = 0
    while True:
        rows, total = store.list_files(root=root, offset=offset, limit=500)
        yield from rows
        offset += len(rows)
        if not rows or offset >= total:
            break


def file_scope(store):
    return store.roots(), json.loads(store.setting('exclusions', json.dumps(DEFAULT_EXCLUSIONS)))


def eligible_file(store, path, scope=None):
    roots, patterns = scope or file_scope(store)
    containing = [root for root in roots if path.is_relative_to(root)]
    if not containing:
        return False
    # A formerly ordinary parent folder may have become a junction or placeholder.
    root = max(containing, key=lambda item: len(item.parts))
    parts = [path, *(part for part in path.parents if part.is_relative_to(root))]
    return (not any(excluded(part, patterns, store.path.parent) for part in parts)
            and path.is_file())


@dataclass
class DuplicateReport:
    groups: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    checked: int = 0
    cancelled: bool = False


def find_duplicates(store, root=None, progress=lambda _: None, cancelled=lambda: False):
    """Hash equal-size candidates in chunks. Never remove, rename, or modify files."""
    from .engine import IndexProgress
    report = DuplicateReport()
    scope = file_scope(store)
    sizes = defaultdict(list)
    for row in catalog_files(store, root):
        if cancelled():
            report.cancelled = True
            return report
        path = Path(row['path'])
        try:
            if eligible_file(store, path, scope):
                sizes[path.stat().st_size].append(path)
        except OSError as error:
            report.errors.append(f'{path.name}: {error}')
    candidates = [path for paths in sizes.values() if len(paths) > 1 for path in paths]
    hashes = defaultdict(list)
    for index, path in enumerate(candidates):
        if cancelled():
            report.cancelled = True
            break
        try:
            if not eligible_file(store, path, scope):
                continue
            before = signature(path)
            digest = sha256()
            with path.open('rb') as stream:
                while block := stream.read(1024 * 1024):
                    if cancelled():
                        report.cancelled = True
                        return report
                    digest.update(block)
            if before != signature(path):
                raise ValueError('File changed during comparison; scan again')
            stat = path.stat()
            hashes[(before[0], digest.hexdigest())].append((path, (stat.st_dev, stat.st_ino), before))
            report.checked += 1
        except (OSError, ValueError) as error:
            report.errors.append(f'{path.name}: {error}')
        progress(IndexProgress(f'Comparing {path.name}', int(100 * (index + 1) / max(1, len(candidates)))))
    for (size, digest), matches in hashes.items():
        # Multiple hard links to one physical file are not duplicate disk copies.
        unique = {}
        for path, identity, saved in matches:
            try:
                if saved != signature(path) or not eligible_file(store, path, scope):
                    report.errors.append(f'{path.name}: Changed since comparison; scan again')
                    continue
                unique.setdefault(identity if identity[1] else str(path), str(path))
            except OSError as error:
                report.errors.append(f'{path.name}: {error}')
        if len(unique) > 1:
            report.groups.append(dict(size=size, digest=digest, paths=sorted(unique.values())))
    report.groups.sort(key=lambda group: -(group['size'] * (len(group['paths']) - 1)))
    return report


class ClipEmbedder:
    identity = f'{CLIP_ID}@{CLIP_REVISION}'

    def __init__(self):
        self.model = None
        self.lock = RLock()

    def load(self):
        if self.model is not None:
            return
        directory = clip_dir()
        if not (directory / 'REVISION').is_file():
            raise RuntimeError('The local image-search model is missing. Use a release with the image model, or run scripts/download-clip.py during source setup.')
        if (directory / 'REVISION').read_text().strip() != CLIP_REVISION:
            raise RuntimeError('The image-search model revision does not match this app')
        from transformers import CLIPModel, AutoTokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(directory, local_files_only=True)
        self.model = CLIPModel.from_pretrained(directory, local_files_only=True).eval()

    def image(self, path):
        import numpy as np
        import torch
        from PIL import Image, ImageOps
        with self.lock, torch.inference_mode():
            self.load()
            with Image.open(path) as source:
                if source.width * source.height > 40_000_000:
                    raise ValueError('Image exceeds 40 megapixels')
                image = ImageOps.exif_transpose(source).convert('RGB')
                image = ImageOps.fit(image, (224, 224), method=Image.Resampling.BICUBIC)
                pixels = np.asarray(image, dtype=np.float32) / 255
            pixels = (pixels - [0.48145466, 0.4578275, 0.40821073]) / [0.26862954, 0.26130258, 0.27577711]
            tensor = torch.from_numpy(pixels.astype(np.float32).transpose(2, 0, 1)).unsqueeze(0)
            vector = self.model.visual_projection(self.model.vision_model(pixel_values=tensor).pooler_output)
            return self.normalized(vector[0].tolist())

    def text(self, query):
        import torch
        with self.lock, torch.inference_mode():
            self.load()
            tokens = self.tokenizer([query], return_tensors='pt', padding=True, truncation=True, max_length=77)
            vector = self.model.text_projection(self.model.text_model(**tokens).pooler_output)
            return self.normalized(vector[0].tolist())

    @staticmethod
    def normalized(vector):
        import math
        norm = math.sqrt(sum(v * v for v in vector))
        if not norm or not math.isfinite(norm):
            raise ValueError('Invalid visual vector')
        return [v / norm for v in vector]


class ImageLibrary:
    def __init__(self, store, embedder=None):
        self.store = store
        self.embedder = embedder or ClipEmbedder()
        with store.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS image_vectors (
                path TEXT PRIMARY KEY REFERENCES files(path) ON DELETE CASCADE,
                signature TEXT NOT NULL, model TEXT NOT NULL, vector BLOB NOT NULL)''')

    def update(self, root=None, progress=lambda _: None, cancelled=lambda: False):
        from .engine import IndexProgress
        rows = [row for row in catalog_files(self.store, root) if row['suffix'] in IMAGE_FORMATS]
        scope = file_scope(self.store)
        report = dict(indexed=0, unchanged=0, errors=[], cancelled=False)
        for index, row in enumerate(rows):
            if cancelled():
                report['cancelled'] = True
                break
            path = Path(row['path'])
            try:
                if not eligible_file(self.store, path, scope):
                    continue
                before = signature(path)
                if before[0] > 50 * 1024 * 1024:
                    raise ValueError('Image exceeds 50 MB')
                encoded = json.dumps(before)
                with self.store.connect() as db:
                    saved = db.execute('SELECT signature,model FROM image_vectors WHERE path=?', (str(path),)).fetchone()
                if saved == (encoded, self.embedder.identity):
                    report['unchanged'] += 1
                else:
                    vector = self.embedder.image(path)
                    if cancelled():
                        report['cancelled'] = True
                        break
                    if signature(path) != before:
                        raise ValueError('Image changed during indexing')
                    with self.store.connect() as db:
                        db.execute('INSERT OR REPLACE INTO image_vectors VALUES(?,?,?,?)',
                                   (str(path), encoded, self.embedder.identity, array('f', vector).tobytes()))
                    report['indexed'] += 1
            except RuntimeError:
                raise
            except (OSError, ValueError) as error:
                report['errors'].append(f'{path.name}: {error}')
                with self.store.connect() as db:
                    db.execute('DELETE FROM image_vectors WHERE path=?', (str(path),))
            progress(IndexProgress(f'Reading image {index + 1} of {len(rows)}', int(100 * (index + 1) / max(1, len(rows)))))
        return report

    def search(self, query, root=None, limit=100, cancelled=lambda: False):
        from .engine import Result
        if not query.strip() or cancelled():
            return []
        vector = self.embedder.text(query)
        scope = file_scope(self.store)
        matches = []
        with self.store.connect() as db:
            records = db.execute('SELECT path,signature,vector FROM image_vectors WHERE model=?', (self.embedder.identity,))
            for raw, saved, blob in records:
                if cancelled():
                    return []
                path = Path(raw)
                if root and not path.is_relative_to(root):
                    continue
                try:
                    if not eligible_file(self.store, path, scope) or json.loads(saved) != signature(path):
                        continue
                except OSError:
                    continue
                values = array('f')
                values.frombytes(blob)
                if len(values) != len(vector):
                    continue
                score = sum(a * b for a, b in zip(vector, values))
                matches.append(Result(raw, 'Visual similarity, not a confidence percentage', None, score, 'Image'))
        return sorted(matches, key=lambda item: (-item.score, item.path))[:limit]
