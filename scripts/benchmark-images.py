"""Synthetic colour retrieval smoke test; not a personal-photo accuracy benchmark."""
import argparse
import json
import platform
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw
from providence.library_tools import ClipEmbedder, ImageLibrary, signature, clip_dir
from providence.store import Store


def peak_memory():
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in ('peak', 'working', 'paged_peak', 'paged', 'nonpaged_peak', 'nonpaged', 'pagefile', 'pagefile_peak')]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL('kernel32')
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL('psapi')
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return counters.peak / 1024**2
        return None
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024**2 if sys.platform == 'darwin' else 1024)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('docs/benchmarks/images.json'))
    args = parser.parse_args()
    root = Path('.artifacts/image-smoke/documents').resolve()
    root.mkdir(parents=True, exist_ok=True)
    store = Store(root.parent / 'data/index.sqlite3', 'image-smoke')
    store.clear_library()
    store.add_root(root)
    cases = [('sample-a.png', 'red'), ('sample-b.png', 'blue'), ('sample-c.png', 'green'), ('sample-d.png', 'yellow')]
    for name, colour in cases:
        path = root / name
        image = Image.new('RGB', (320, 240), 'white')
        ImageDraw.Draw(image).rectangle((65, 30, 255, 220), fill=colour)
        image.save(path)
        store.discover([(path, signature(path), path.stat().st_mtime, True)])
    model = ClipEmbedder()
    start = time.perf_counter()
    model.load()
    cold = time.perf_counter() - start
    library = ImageLibrary(store, model)
    start = time.perf_counter()
    report = library.update()
    indexing = time.perf_counter() - start
    trials = []
    for name, colour in cases:
        start = time.perf_counter()
        matches = library.search(f'a {colour} square on a white background')
        trials.append(dict(query=f'a {colour} square on a white background', expected=name,
                           first=Path(matches[0].path).name if matches else None,
                           seconds=time.perf_counter() - start))
    start = time.perf_counter()
    unchanged = library.update()
    result = dict(method='Synthetic colour/shape smoke test; no independent accuracy claim',
                  model=model.identity, platform=platform.platform(), cpu=platform.processor(),
                  weight_bytes=(clip_dir() / 'pytorch_model.bin').stat().st_size,
                  cold_load_seconds=cold, indexing_seconds=indexing, images_indexed=report['indexed'],
                  errors=report['errors'], unchanged_images=unchanged['unchanged'],
                  cached_refresh_seconds=time.perf_counter() - start,
                  hit_at_1=sum(trial['first'] == trial['expected'] for trial in trials) / len(trials),
                  peak_process_memory_mib=peak_memory(), trials=trials)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
