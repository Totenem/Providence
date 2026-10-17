"""Bundled offline OCR in a reusable, bounded subprocess (also isolates MuPDF)."""

import multiprocessing as mp
from pathlib import Path
import threading
import hashlib

OCR_ID = "rapidocr-3.10.0:PP-OCRv6-small:latin-mixed:2000px:v1"


def _recognizer():
    import rapidocr
    from rapidocr import RapidOCR

    root = Path(rapidocr.__file__).parent / "models"
    names = {
        "Det.model_path": "PP-OCRv6_det_small.onnx",
        "Rec.model_path": "PP-OCRv6_rec_small.onnx",
        "Cls.model_path": "ch_ppocr_mobile_v2.0_cls_mobile.onnx",
    }
    missing = [name for name in names.values() if not (root / name).is_file()]
    if missing:
        raise RuntimeError("Bundled OCR models missing: " + ", ".join(missing))
    return RapidOCR(
        params={
            **{key: str(root / name) for key, name in names.items()},
            "EngineConfig.onnxruntime.intra_op_num_threads": 2,
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
            "Global.max_side_len": 2000,
            "Global.log_level": "error",
        }
    )


def _run(pipe):
    engine = None
    while True:
        request = pipe.recv()
        if request is None:
            return
        path, force, native_only = request
        try:
            import pymupdf
            import numpy as np

            payload = []

            def recognize(image, page):
                nonlocal engine
                if engine is None:
                    engine = _recognizer()
                result = engine(image)
                texts = list(result.txts) if result.txts is not None else []
                boxes = result.boxes.tolist() if result.boxes is not None else []
                height, width = image.shape[:2]
                regions = [
                    {
                        "text": text,
                        "rect": [
                            min(p[0] for p in box) / width,
                            min(p[1] for p in box) / height,
                            max(p[0] for p in box) / width,
                            max(p[1] for p in box) / height,
                        ],
                    }
                    for text, box in zip(texts, boxes)
                ]
                return {
                    "text": "\n".join(texts),
                    "page": page,
                    "ocr": True,
                    "boxes": boxes,
                    "regions": regions,
                }

            if Path(path).suffix.lower() == ".pdf":
                with pymupdf.open(path) as document:
                    if document.needs_pass:
                        raise ValueError("Password-protected PDF")
                    if len(document) > 500:
                        raise ValueError(
                            "OCR page limit is 500; split this document to process it"
                        )
                    for i, page in enumerate(document):
                        text = page.get_text(sort=True)
                        # For mixed pages use only uncovered image regions to avoid duplicate text.
                        native = {
                            "text": text,
                            "page": i + 1,
                            "ocr": False,
                            "boxes": [],
                        }
                        if native_only:
                            payload.append(native)
                        elif force or not text.strip():
                            factor = min(
                                2.0, 2000 / max(page.rect.width, page.rect.height)
                            )
                            pix = page.get_pixmap(
                                matrix=pymupdf.Matrix(factor, factor),
                                colorspace=pymupdf.csRGB,
                                alpha=False,
                            )
                            image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                                pix.height, pix.width, 3
                            )
                            payload.append(recognize(image, i + 1))
                        else:
                            payload.append(native)
                            for block in page.get_text("dict")["blocks"]:
                                if block["type"] != 1:
                                    continue
                                rect = pymupdf.Rect(block["bbox"])
                                if rect.width < 80 or rect.height < 40:
                                    continue
                                # Embedded images have no native text; only OCR sizeable image regions.
                                factor = min(2.0, 2000 / max(rect.width, rect.height))
                                pix = page.get_pixmap(
                                    matrix=pymupdf.Matrix(factor, factor),
                                    clip=rect,
                                    colorspace=pymupdf.csRGB,
                                    alpha=False,
                                )
                                image = np.frombuffer(
                                    pix.samples, dtype=np.uint8
                                ).reshape(pix.height, pix.width, 3)
                                item = recognize(image, i + 1)
                                # Some PDFs overlay a native text layer on scans. Ignore covered text.
                                words = page.get_text("words", clip=rect)
                                if not words:
                                    for region in item["regions"]:
                                        x0, y0, x1, y1 = region["rect"]
                                        region["rect"] = [
                                            (rect.x0 + x0 * rect.width)
                                            / page.rect.width,
                                            (rect.y0 + y0 * rect.height)
                                            / page.rect.height,
                                            (rect.x0 + x1 * rect.width)
                                            / page.rect.width,
                                            (rect.y0 + y1 * rect.height)
                                            / page.rect.height,
                                        ]
                                    payload.append(item)
            else:
                from PIL import Image, ImageOps
                from .documents import register_image_plugins
                register_image_plugins()

                with Image.open(path) as image:
                    image = ImageOps.exif_transpose(image).convert("RGB")
                    image.thumbnail((2000, 2000))
                    payload.append(recognize(np.asarray(image), None))
            pipe.send((True, payload))
        except Exception as error:
            pipe.send((False, f"{type(error).__name__}: {error}"))


class OCRWorker:
    def __init__(self):
        self.process = None
        self.pipe = None
        self.lock = threading.RLock()

    def read(
        self, path, force=False, cancelled=lambda: False, timeout=90, native_only=False
    ):
        import time

        with self.lock:
            if self.process is None or not self.process.is_alive():
                context = mp.get_context("spawn")
                self.pipe, child = context.Pipe()
                self.process = context.Process(target=_run, args=(child,), daemon=True)
                self.process.start()
                child.close()
            self.pipe.send((str(path), force, native_only))
            started = time.monotonic()
            while not self.pipe.poll(0.1):
                if cancelled() or time.monotonic() - started > timeout:
                    self.close()
                    raise ValueError(
                        "OCR interrupted; retry to resume"
                        if cancelled()
                        else "OCR timed out; retry or split the document"
                    )
                if not self.process.is_alive():
                    self.close()
                    raise ValueError("OCR worker exited unexpectedly; retry this file")
            ok, payload = self.pipe.recv()
            if not ok:
                raise ValueError(payload)
            return payload

    def close(self):
        with self.lock:
            if self.process:
                if self.process.is_alive():
                    self.process.terminate()
                self.process.join(2)
            if self.pipe:
                self.pipe.close()
            self.process = self.pipe = None

    @staticmethod
    def cache_key(digest, force=False):
        return hashlib.sha256(f"{digest}:{OCR_ID}:{force}".encode()).hexdigest()
