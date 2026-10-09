"""Fetch a fixed, public model revision during image build only."""
from pathlib import Path
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import shutil
import time
import urllib.request

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
FILES = (
    "config.json", "config_sentence_transformers.json", "modules.json",
    "sentence_bert_config.json", "special_tokens_map.json", "tokenizer.json",
    "tokenizer_config.json", "vocab.txt", "1_Pooling/config.json", "README.md",
    "model.safetensors",
)

def download_weights(url, target):
    request = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(request, timeout=30) as response:
        size = int(response.headers["Content-Length"])
    step = 1024 * 1024
    ranges = [(start, min(start + step, size) - 1) for start in range(0, size, step)]

    def fetch(bounds):
        start, end = bounds
        for attempt in range(3):
            try:
                request = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})
                with urllib.request.urlopen(request, timeout=30) as response:
                    expected = f"bytes {start}-{end}/{size}"
                    if response.status != 206 or response.headers.get("Content-Range") != expected:
                        raise RuntimeError("Model host did not honor the requested byte range")
                    data = response.read(end - start + 2)
                    if len(data) != end - start + 1:
                        raise RuntimeError("Incomplete model download")
                return start, data
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2)

    with target.open("wb") as output, ThreadPoolExecutor(max_workers=8) as pool:
        output.truncate(size)
        futures = [pool.submit(fetch, bounds) for bounds in ranges]
        received = 0
        for future in as_completed(futures):
            start, data = future.result()
            output.seek(start)
            output.write(data)
            received += len(data)
            print(f"Model weights: {received:,}/{size:,} bytes", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Download Providence's fixed offline model")
    parser.add_argument("--destination", type=Path, default=Path("/opt/providence-model"))
    destination = parser.parse_args().destination
    for filename in FILES:
        target = destination / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://huggingface.co/{MODEL}/resolve/{REVISION}/{filename}"
        for attempt in range(3):
            try:
                print(f"Downloading {filename} (attempt {attempt + 1})", flush=True)
                if filename == "model.safetensors":
                    download_weights(url, target)
                else:
                    with urllib.request.urlopen(url, timeout=30) as response, target.open("wb") as output:
                        shutil.copyfileobj(response, output, length=1024 * 1024)
                print(f"Saved {filename}: {target.stat().st_size:,} bytes", flush=True)
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2)
    (destination / "REVISION").write_text(REVISION + "\n")


if __name__ == "__main__":
    main()
