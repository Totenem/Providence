"""Build-time only download; the application never fetches models at runtime."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from providence.paths import QWEN_ID, QWEN_REVISION
from huggingface_hub import snapshot_download
import importlib.util
import hashlib

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, default=Path("build/qwen"))
    destination = parser.parse_args().destination
    snapshot_download(
        QWEN_ID,
        revision=QWEN_REVISION,
        local_dir=str(destination),
        allow_patterns=["*.json", "*.txt", "README.md"],
        max_workers=4,
    )
    weights = destination / "model.safetensors"
    expected = "0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd"

    def valid():
        if not weights.exists() or weights.stat().st_size != 1191586416:
            return False
        with weights.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest() == expected

    if not valid():
        spec = importlib.util.spec_from_file_location(
            "download_model",
            Path(__file__).resolve().parents[1] / "docker" / "download_model.py",
        )
        downloader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(downloader)
        partial = destination / "weights.part"
        downloader.download_weights(
            f"https://huggingface.co/{QWEN_ID}/resolve/{QWEN_REVISION}/model.safetensors",
            partial,
            step=1024 * 1024,
            workers=24,
        )
        with partial.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                raise ValueError("Qwen weight checksum mismatch")
        partial.replace(weights)
    (destination / "REVISION").write_text(QWEN_REVISION + "\n")
    print("Pinned Qwen model ready:", destination)
