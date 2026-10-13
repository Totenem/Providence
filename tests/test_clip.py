import math
import socket

import pytest
from PIL import Image
from providence.library_tools import ClipEmbedder, clip_dir


def test_clip_image_and_text_encoding_are_offline(tmp_path, monkeypatch):
    if not (clip_dir() / 'REVISION').is_file():
        pytest.skip('Pinned CLIP assets not installed; run scripts/download-clip.py')
    monkeypatch.setenv('HF_HUB_OFFLINE', '1')
    monkeypatch.setenv('TRANSFORMERS_OFFLINE', '1')

    def reject(*args, **kwargs):
        raise AssertionError('Image search attempted network access')

    monkeypatch.setattr(socket.socket, 'connect', reject)
    monkeypatch.setattr(socket, 'create_connection', reject)
    path = tmp_path / 'red.png'
    Image.new('RGB', (320, 220), 'red').save(path)
    embedder = ClipEmbedder()
    image, text = embedder.image(path), embedder.text('a red square')
    assert len(image) == len(text) == 512
    for vector in (image, text):
        assert all(math.isfinite(value) for value in vector)
        assert sum(value * value for value in vector) == pytest.approx(1, abs=1e-5)
    assert embedder.text('a red square') == pytest.approx(text)


def test_missing_clip_assets_produce_setup_error(tmp_path, monkeypatch):
    monkeypatch.setenv('PROVIDENCE_CLIP_DIR', str(tmp_path))
    with pytest.raises(RuntimeError, match='model is missing'):
        ClipEmbedder().text('a beach')
