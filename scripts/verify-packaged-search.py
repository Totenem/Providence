"""Exercise bundled Qwen and OCR through the real frozen Windows executable."""

import os
from pathlib import Path
import sqlite3
import subprocess

from PIL import Image, ImageDraw, ImageFont
import pymupdf


root = Path(__file__).resolve().parents[1]
sample = root / '.artifacts' / 'packaged-qml-smoke'
documents = sample / 'documents'
documents.mkdir(parents=True, exist_ok=True)
(documents / 'notes.txt').write_text('Database project delivery reference 4821.', encoding='utf-8')
image = Image.new('RGB', (1100, 220), 'white')
ImageDraw.Draw(image).text((35, 65), 'DATABASE PROPOSAL 4821', fill='black',
                          font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 48))
image.save(documents / 'screenshot.png')
with pymupdf.open() as pdf:
    page = pdf.new_page(width=1100, height=220)
    page.insert_image(page.rect, filename=str(documents / 'screenshot.png'))
    pdf.save(documents / 'scanned.pdf')
environment = dict(os.environ, LOCALAPPDATA=str(sample))
environment.pop('PROVIDENCE_DATA_DIR', None)
environment.pop('PROVIDENCE_QWEN_DIR', None)
environment.pop('QT_QPA_PLATFORM', None)
environment.pop('QT_QUICK_BACKEND', None)
startup = subprocess.STARTUPINFO()
startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
startup.wShowWindow = 0
exe = root / 'dist/Providence/Providence.exe'
for arguments in [('index', str(documents)), ('search', '4821')]:
    result = subprocess.run([str(exe), '--data-dir', str(sample / 'data'), *arguments],
                            env=environment, startupinfo=startup, timeout=180)
    assert result.returncode == 0, f'Packaged command failed: {arguments}'
with sqlite3.connect(sample / 'data/index-qwen.sqlite3') as db:
    rows = db.execute('SELECT name,state,ocr FROM files ORDER BY name').fetchall()
    assert len(rows) == 3 and all(row[1] == 'ready' for row in rows), rows
    assert sum(row[2] for row in rows) == 2, rows
    texts = ' '.join(row[0] for row in db.execute('SELECT text FROM chunks'))
    assert '4821' in texts and 'DATABASE' in texts
log = (sample / 'Providence/logs/providence.log').read_text(encoding='utf-8')
assert 'scanned.pdf' in log and 'screenshot.png' in log, log[-2000:]
assert '"page": 1' in log, 'Search did not preserve scanned PDF page reference'
print('Packaged Qwen + PNG/PDF OCR + hybrid search verified: 3 ready files, 2 OCR files.')
