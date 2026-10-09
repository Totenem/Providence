"""Convert the approved PNG artwork into a multi-size Windows ICO."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import struct
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter

root = Path(__file__).resolve().parents[1]
assets = root / 'providence' / 'assets'
app = QGuiApplication([])
artwork = QImage(str(assets / 'providence.png'))
assert not artwork.isNull(), 'The icon source PNG is missing'
frames = []
for size in (16, 24, 32, 48, 64, 128, 256):
    canvas = QImage(size, size, QImage.Format.Format_ARGB32)
    canvas.fill(Qt.GlobalColor.transparent)
    scaled = artwork.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
    painter = QPainter(canvas)
    painter.drawImage((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert canvas.save(buffer, 'PNG')
    frames.append((size, bytes(data)))
offset = 6 + 16 * len(frames)
directory = []
for size, data in frames:
    directory.append(struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0, 1, 32, len(data), offset))
    offset += len(data)
icon = struct.pack('<HHH', 0, 1, len(frames)) + b''.join(directory) + b''.join(data for _, data in frames)
(assets / 'providence.ico').write_bytes(icon)
print(f'Saved {assets / "providence.ico"} with {len(frames)} sizes')
