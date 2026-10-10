"""Filesystem notifications, durable pending work and periodic reconciliation."""

import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class LibraryService:
    def __init__(
        self,
        engine,
        progress=lambda value: None,
        changed=lambda: None,
        error=lambda text: None,
    ):
        self.engine = engine
        self.progress = progress
        self.changed = changed
        self.error = error
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.paused = threading.Event()
        self.dirty = {}
        self.lock = threading.Lock()
        self.reconcile = True
        self.force = False
        self.observer = None
        self.thread = None
        self.watched = ()
        self.busy = False
        self.urgent = threading.Event()

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(
            target=self.run, name="Providence library", daemon=True
        )
        self.thread.start()

    def event(self, event):
        if event.event_type in {"opened", "closed", "closed_no_write"}:
            return
        from .discovery import excluded

        if excluded(
            Path(event.src_path), self.engine.exclusions(), self.engine.protected
        ):
            return
        with self.lock:
            if event.is_directory:
                self.reconcile = True
            else:
                for path in (event.src_path, getattr(event, "dest_path", "")):
                    if path:
                        file = Path(path)
                        if excluded(
                            file, self.engine.exclusions(), self.engine.protected
                        ):
                            continue
                        self.dirty[path] = time.monotonic()
                        if file.is_file():
                            try:
                                from .engine import file_signature
                                from .documents import SUPPORTED

                                self.engine.store.discover(
                                    [
                                        (
                                            file,
                                            file_signature(file),
                                            file.stat().st_mtime,
                                            file.suffix.lower() in SUPPORTED,
                                        )
                                    ]
                                )
                            except OSError:
                                pass
                        if file.suffix.lower() not in {".pdf", ".png", ".jpg", ".jpeg"}:
                            self.urgent.set()
            if len(self.dirty) > 5000:
                self.dirty.clear()
                self.reconcile = True
        self.wake.set()

    def watches(self, roots):
        key = tuple(str(root) for root in roots)
        if key == self.watched:
            return
        if self.observer:
            self.observer.stop()
            self.observer.join(2)
        self.observer = Observer()
        handler = FileSystemEventHandler()
        handler.on_any_event = self.event
        for root in roots:
            if not any(root != other and root.is_relative_to(other) for other in roots):
                try:
                    self.observer.schedule(handler, str(root), recursive=True)
                except OSError as error:
                    self.error(
                        f"Notifications unavailable for {root}: {error}. Recovery scans remain enabled."
                    )
        self.observer.start()
        self.watched = key

    def request_scan(self, force=False):
        with self.lock:
            self.reconcile = True
            self.force = self.force or force
        self.wake.set()

    def set_paused(self, value):
        (self.paused.set if value else self.paused.clear)()
        self.wake.set()

    def run(self):
        last_scan = 0
        try:
            while not self.stop.is_set():
                self.wake.wait(0.5)
                self.wake.clear()
                if self.paused.is_set():
                    continue
                roots = self.engine.store.roots()
                available = [root for root in roots if root.is_dir()]
                self.watches(available)
                if not available:
                    continue
                now = time.monotonic()
                with self.lock:
                    full = self.reconcile or now - last_scan > 300
                    if full:
                        self.reconcile = False
                    force = self.force
                    self.force = False
                    paths = [
                        path for path, stamp in self.dirty.items() if now - stamp >= 0.8
                    ]
                    for path in paths:
                        self.dirty.pop(path, None)
                cancel = lambda: self.stop.is_set() or self.paused.is_set()
                if full or paths or self.engine.store.pending():
                    self.busy = True
                    try:
                        self.urgent.clear()
                        if full:
                            reports = self.engine.index_many(
                                available,
                                self.progress,
                                force,
                                cancel,
                                ocr_yield=self.urgent.is_set,
                            )
                            last_scan = now
                        else:
                            paths.extend(
                                str(path) for path in self.engine.store.pending()
                            )
                            # Do not spin on OCR files while OCR is disabled.
                            if self.engine.store.setting("ocr_enabled", "1") != "1":
                                paths = [
                                    p
                                    for p in paths
                                    if Path(p).suffix.lower()
                                    not in {".png", ".jpg", ".jpeg"}
                                ]
                            reports = self.engine.update_paths(
                                list(dict.fromkeys(paths)),
                                self.progress,
                                cancel,
                                ocr_yield=self.urgent.is_set,
                            )
                        if cancel():
                            self.reconcile = True
                        issues = [
                            message for report in reports for message in report.errors
                        ]
                        if issues:
                            self.error(issues[0])
                        self.changed()
                    except Exception as error:
                        self.error(str(error))
                        self.reconcile = True
                        # Back off without blocking shutdown or pause.
                        self.stop.wait(2)
                    finally:
                        self.busy = False
        finally:
            if self.observer:
                self.observer.stop()
                self.observer.join(3)
            self.engine.ocr_worker.close()

    def close(self, timeout=5):
        self.stop.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout)
        return not self.thread or not self.thread.is_alive()
