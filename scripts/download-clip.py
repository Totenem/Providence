"""Explicit setup download; image search itself is strictly offline."""
import argparse
from pathlib import Path
import sys
import hashlib
import importlib.util

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from providence.library_tools import CLIP_ID, CLIP_REVISION
from huggingface_hub import snapshot_download

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--destination', type=Path, default=Path('build/clip'))
    target = parser.parse_args().destination
    snapshot_download(CLIP_ID, revision=CLIP_REVISION, local_dir=target,
                      allow_patterns=['*.json', '*.txt', 'README.md'])
    weights = target / 'pytorch_model.bin'
    expected = 'a63082132ba4f97a80bea76823f544493bffa8082296d62d71581a4feff1576f'
    def valid(path):
        if not path.is_file():
            return False
        with path.open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest() == expected
    if not valid(weights):
        spec = importlib.util.spec_from_file_location('download_model', Path(__file__).resolve().parents[1] / 'docker/download_model.py')
        downloader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(downloader)
        partial = target / 'weights.part'
        downloader.download_weights(f'https://huggingface.co/{CLIP_ID}/resolve/{CLIP_REVISION}/pytorch_model.bin', partial, workers=24)
        if not valid(partial):
            raise ValueError('CLIP weight checksum mismatch')
        partial.replace(weights)
    (target / 'REVISION').write_text(CLIP_REVISION + '\n')
    print('Pinned offline image model ready:', target)
