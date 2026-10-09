from array import array
from contextlib import contextmanager
from pathlib import Path
import sqlite3


class Store:
    def __init__(self, path: Path, identity: str):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS roots (path TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS documents (
                    path TEXT PRIMARY KEY, digest TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY, path TEXT NOT NULL REFERENCES documents(path) ON DELETE CASCADE,
                    text TEXT NOT NULL, page INTEGER, vector BLOB NOT NULL);
                CREATE INDEX IF NOT EXISTS chunks_path ON chunks(path);
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(documents)")}
            for column in ("file_size", "mtime_ns", "ctime_ns"):
                if column not in columns:
                    db.execute(f"ALTER TABLE documents ADD COLUMN {column} INTEGER")
            saved = db.execute("SELECT value FROM metadata WHERE key='model'").fetchone()
            if saved and saved[0] != identity:
                raise RuntimeError("Index uses a different embedding model. Use a new data directory.")
            db.execute("INSERT OR IGNORE INTO metadata VALUES ('model', ?)", (identity,))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def roots(self):
        with self.connect() as db:
            return [Path(row[0]) for row in db.execute("SELECT path FROM roots ORDER BY path")]

    def add_root(self, root):
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO roots VALUES (?)", (str(root),))

    def setting(self, key, default=None):
        with self.connect() as db:
            row = db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
            return row[0] if row else default

    def set_setting(self, key, value):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)", (key, value))

    def remove_root(self, root):
        root = Path(root)
        with self.connect() as db:
            db.execute("DELETE FROM roots WHERE path=?", (str(root),))
            remaining = [Path(row[0]) for row in db.execute("SELECT path FROM roots")]
            paths = [row[0] for row in db.execute("SELECT path FROM documents")]
            removed = [path for path in paths if Path(path).is_relative_to(root)
                       and not any(Path(path).is_relative_to(other) for other in remaining)]
            db.executemany("DELETE FROM documents WHERE path=?", [(path,) for path in removed])

    def clear_library(self):
        with self.connect() as db:
            db.execute("DELETE FROM documents")
            db.execute("DELETE FROM roots")

    def digest(self, path):
        with self.connect() as db:
            row = db.execute("SELECT digest FROM documents WHERE path=?", (str(path),)).fetchone()
            return row[0] if row else None

    def snapshots(self):
        with self.connect() as db:
            return {path: (digest, size, modified, created)
                    for path, digest, size, modified, created in db.execute(
                        "SELECT path,digest,file_size,mtime_ns,ctime_ns FROM documents")}

    def remember_signature(self, path, signature):
        with self.connect() as db:
            db.execute("UPDATE documents SET file_size=?,mtime_ns=?,ctime_ns=? WHERE path=?",
                       (*signature, str(path)))

    def replace(self, path, digest, passages, vectors, signature=None):
        self.replace_many([(path, digest, passages, vectors, signature)])

    def replace_many(self, documents):
        for path, digest, passages, vectors, signature in documents:
            if len(passages) != len(vectors):
                raise ValueError("Embedding count does not match passages")
        with self.connect() as db:
            for path, digest, passages, vectors, signature in documents:
                db.execute("DELETE FROM documents WHERE path=?", (str(path),))
                db.execute("INSERT INTO documents(path,digest,file_size,mtime_ns,ctime_ns) VALUES (?,?,?,?,?)",
                           (str(path), digest, *(signature or (None, None, None))))
                db.executemany("INSERT INTO chunks(path,text,page,vector) VALUES (?,?,?,?)", [
                    (str(path), passage.text, passage.page, array('f', vector).tobytes())
                    for passage, vector in zip(passages, vectors)
                ])

    def prune(self, root, seen):
        with self.connect() as db:
            paths = [row[0] for row in db.execute("SELECT path FROM documents")]
            removed = [path for path in paths if Path(path).is_relative_to(root) and path not in seen]
            db.executemany("DELETE FROM documents WHERE path=?", [(path,) for path in removed])
            return len(removed)

    def count(self):
        with self.connect() as db:
            return db.execute("SELECT COUNT(DISTINCT path) FROM chunks").fetchone()[0]

    def documents(self):
        with self.connect() as db:
            return [row[0] for row in db.execute("SELECT DISTINCT path FROM chunks ORDER BY path COLLATE NOCASE")]

    def vectors(self):
        with self.connect() as db:
            for path, text, page, blob in db.execute("SELECT path,text,page,vector FROM chunks"):
                vector = array('f')
                vector.frombytes(blob)
                yield path, text, page, vector
