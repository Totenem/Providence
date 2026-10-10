import os
import sys
from pathlib import Path


MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
QWEN_ID = "Qwen/Qwen3-Embedding-0.6B"
QWEN_REVISION = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"


def data_dir() -> Path:
    override = os.environ.get("PROVIDENCE_DATA_DIR")
    base = Path(override) if override else Path.home() / ".providence"
    base.mkdir(parents=True, exist_ok=True)
    return base


def model_dir() -> Path:
    override = os.environ.get("PROVIDENCE_MODEL_DIR")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "models" / "all-MiniLM-L6-v2"
    return data_dir() / "models" / "all-MiniLM-L6-v2"


def qwen_dir() -> Path:
    override = os.environ.get("PROVIDENCE_QWEN_DIR")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "models" / "qwen-embedding-0.6b"
    bundled = Path(__file__).resolve().parents[1] / "build" / "qwen"
    return (
        bundled if bundled.is_dir() else data_dir() / "models" / "qwen-embedding-0.6b"
    )
