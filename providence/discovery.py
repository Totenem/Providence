"""Read-only file discovery with explicit scope, exclusions and reparse safeguards."""

import fnmatch
import os
from pathlib import Path

DEFAULT_EXCLUSIONS = (
    "Windows",
    "Program Files",
    "Program Files (x86)",
    "ProgramData",
    "$Recycle.Bin",
    "System Volume Information",
    "Recovery",
    "AppData",
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".providence",
    ".cache",
    "Cache",
    "Caches",
    "Temp",
    "tmp",
    "build",
    "dist",
    "pagefile.sys",
    "swapfile.sys",
    "hiberfil.sys",
    "*.sqlite3",
    "*.sqlite3-*",
)


def default_roots():
    if os.environ.get("PROVIDENCE_CONTAINER"):
        return [Path("/documents")]
    override = os.environ.get("PROVIDENCE_SCAN_ROOTS")
    if override:
        return [Path(p) for p in override.split(os.pathsep) if p]
    if os.name == "nt":
        import ctypes

        mask = ctypes.windll.kernel32.GetLogicalDrives()
        return [
            Path(f"{chr(65 + i)}:/")
            for i in range(26)
            if mask & (1 << i)
            and ctypes.windll.kernel32.GetDriveTypeW(f"{chr(65 + i)}:\\") == 3
        ]
    return [Path.home()]


def excluded(path, patterns, data_path=None):
    path = Path(path)
    if data_path and (path == data_path or path.is_relative_to(data_path)):
        return True
    for pattern in patterns:
        pattern = pattern.strip()
        if not pattern:
            continue
        if any(
            fnmatch.fnmatchcase(part.casefold(), pattern.casefold())
            for part in path.parts
        ):
            return True
        if Path(pattern).is_absolute() and (
            path == Path(pattern) or path.is_relative_to(Path(pattern))
        ):
            return True
    try:
        stat = path.lstat()
        # Reparse points include junctions and cloud placeholders. Do not hydrate them.
        if path.is_symlink() or getattr(stat, "st_file_attributes", 0) & (
            0x4 | 0x400 | 0x1000 | 0x40000 | 0x400000
        ):
            return True
    except OSError:
        return False
    return False


def walk_files(root, patterns, data_path, cancelled, onerror):
    for directory, folders, files in os.walk(root, followlinks=False, onerror=onerror):
        if cancelled():
            return
        folders[:] = [
            name
            for name in folders
            if not excluded(Path(directory) / name, patterns, data_path)
        ]
        for name in files:
            if cancelled():
                return
            path = Path(directory) / name
            if not excluded(path, patterns, data_path):
                yield path
