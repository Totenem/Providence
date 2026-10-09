"""Native Windows entry point with logging for a windowed executable."""
import os
import sys
from pathlib import Path

if __name__ == "__main__":
    os.environ.pop("PROVIDENCE_CONTAINER", None)
    os.environ.pop("PROVIDENCE_LIBRARY_SOURCE", None)
    os.environ.pop("PROVIDENCE_MODEL_DIR", None)
    if getattr(sys, "frozen", False):
        # Give the pinned Windows taskbar entry its own application identity.
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Providence.Desktop")
        log_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Providence" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        if sys.stdout is None:
            sys.stdout = (log_dir / "providence.log").open("a", encoding="utf-8", buffering=1)
        if sys.stderr is None:
            sys.stderr = sys.stdout
    from providence.__main__ import main
    result = main()
    if result and getattr(sys, "frozen", False) and len(sys.argv) == 1:
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication([])
        QMessageBox.critical(None, "Providence could not start",
                             f"Startup failed. Details are in {log_dir / 'providence.log'}")
    raise SystemExit(result)
