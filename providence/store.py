from array import array
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import json
import time


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
                CREATE TABLE IF NOT EXISTS files (
                    path TEXT PRIMARY KEY, name TEXT NOT NULL, parent TEXT NOT NULL,
                    suffix TEXT NOT NULL, size INTEGER NOT NULL, modified REAL NOT NULL,
                    signature TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
                    error TEXT NOT NULL DEFAULT '', attempts INTEGER NOT NULL DEFAULT 0,
                    retry_at REAL NOT NULL DEFAULT 0, ocr INTEGER NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS files_parent ON files(parent);
                CREATE INDEX IF NOT EXISTS files_state ON files(state,retry_at);
                CREATE INDEX IF NOT EXISTS files_name ON files(name COLLATE NOCASE);
                CREATE INDEX IF NOT EXISTS files_modified ON files(modified DESC);
                CREATE INDEX IF NOT EXISTS files_size ON files(size DESC);
                CREATE INDEX IF NOT EXISTS files_suffix ON files(suffix);
                CREATE TABLE IF NOT EXISTS ocr_cache (
                    identity TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(text, path UNINDEXED, page UNINDEXED,
                    content='chunks', content_rowid='id', tokenize='unicode61');
                CREATE VIRTUAL TABLE IF NOT EXISTS chunk_terms USING fts5vocab(chunk_fts, 'row');
                CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
                    INSERT INTO chunk_fts(rowid,text,path,page) VALUES(new.id,new.text,new.path,new.page);
                END;
                CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
                    INSERT INTO chunk_fts(chunk_fts,rowid,text,path,page) VALUES('delete',old.id,old.text,old.path,old.page);
                END;
            """)
            if not db.execute(
                "SELECT 1 FROM metadata WHERE key='fts_initialized'"
            ).fetchone():
                db.execute("INSERT INTO chunk_fts(chunk_fts) VALUES('rebuild')")
                db.execute("INSERT INTO metadata VALUES('fts_initialized','1')")
            db.execute("INSERT OR IGNORE INTO metadata VALUES('vector_revision','0')")
            db.execute(
                "INSERT OR IGNORE INTO metadata SELECT 'chunk_sequence',COALESCE(MAX(id),0) FROM chunks"
            )
            # Migrate existing libraries into the metadata catalog without re-embedding.
            for (saved_path,) in db.execute(
                "SELECT path FROM documents WHERE path NOT IN (SELECT path FROM files)"
            ).fetchall():
                file = Path(saved_path)
                try:
                    stat = file.stat()
                    signature = json.dumps(
                        [stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]
                    )
                    state = (
                        "ready"
                        if db.execute(
                            "SELECT 1 FROM chunks WHERE path=?", (saved_path,)
                        ).fetchone()
                        else "pending"
                    )
                    db.execute(
                        "INSERT INTO files(path,name,parent,suffix,size,modified,signature,state) VALUES(?,?,?,?,?,?,?,?)",
                        (
                            saved_path,
                            file.name,
                            str(file.parent),
                            file.suffix.lower(),
                            stat.st_size,
                            stat.st_mtime,
                            signature,
                            state,
                        ),
                    )
                except OSError:
                    pass
            columns = {row[1] for row in db.execute("PRAGMA table_info(documents)")}
            for column in ("file_size", "mtime_ns", "ctime_ns"):
                if column not in columns:
                    db.execute(f"ALTER TABLE documents ADD COLUMN {column} INTEGER")
            saved = db.execute(
                "SELECT value FROM metadata WHERE key='model'"
            ).fetchone()
            if saved and saved[0] != identity:
                raise RuntimeError(
                    "Index uses a different embedding model. Use a new data directory."
                )
            db.execute(
                "INSERT OR IGNORE INTO metadata VALUES ('model', ?)", (identity,)
            )

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def roots(self):
        with self.connect() as db:
            return [
                Path(row[0])
                for row in db.execute("SELECT path FROM roots ORDER BY path")
            ]

    def add_root(self, root):
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO roots VALUES (?)", (str(root),))

    def setting(self, key, default=None):
        with self.connect() as db:
            row = db.execute(
                "SELECT value FROM metadata WHERE key=?", (key,)
            ).fetchone()
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
            removed = [
                path
                for path in paths
                if Path(path).is_relative_to(root)
                and not any(Path(path).is_relative_to(other) for other in remaining)
            ]
            db.executemany(
                "DELETE FROM documents WHERE path=?", [(path,) for path in removed]
            )
            catalog = [row[0] for row in db.execute("SELECT path FROM files")]
            db.executemany(
                "DELETE FROM files WHERE path=?",
                [
                    (p,)
                    for p in catalog
                    if Path(p).is_relative_to(root)
                    and not any(Path(p).is_relative_to(other) for other in remaining)
                ],
            )
            db.execute("DELETE FROM ocr_cache")
            self.bump(db)

    def clear_library(self):
        with self.connect() as db:
            db.execute("DELETE FROM documents")
            db.execute("DELETE FROM roots")
            db.execute("DELETE FROM files")
            db.execute("DELETE FROM ocr_cache")
            self.bump(db)

    def digest(self, path):
        with self.connect() as db:
            row = db.execute(
                "SELECT digest FROM documents WHERE path=?", (str(path),)
            ).fetchone()
            return row[0] if row else None

    def snapshots(self):
        with self.connect() as db:
            return {
                path: (digest, size, modified, created)
                for path, digest, size, modified, created in db.execute(
                    "SELECT path,digest,file_size,mtime_ns,ctime_ns FROM documents"
                )
            }

    def remember_signature(self, path, signature):
        with self.connect() as db:
            db.execute(
                "UPDATE documents SET file_size=?,mtime_ns=?,ctime_ns=? WHERE path=?",
                (*signature, str(path)),
            )

    def replace(self, path, digest, passages, vectors, signature=None):
        self.replace_many([(path, digest, passages, vectors, signature)])

    def replace_many(self, documents):
        for path, digest, passages, vectors, signature in documents:
            if len(passages) != len(vectors):
                raise ValueError("Embedding count does not match passages")
        with self.connect() as db:
            for path, digest, passages, vectors, signature in documents:
                db.execute("DELETE FROM documents WHERE path=?", (str(path),))
                db.execute(
                    "INSERT INTO documents(path,digest,file_size,mtime_ns,ctime_ns) VALUES (?,?,?,?,?)",
                    (str(path), digest, *(signature or (None, None, None))),
                )
                sequence = int(
                    db.execute(
                        "SELECT value FROM metadata WHERE key='chunk_sequence'"
                    ).fetchone()[0]
                )
                db.executemany(
                    "INSERT INTO chunks(id,path,text,page,vector) VALUES (?,?,?,?,?)",
                    [
                        (
                            sequence + i + 1,
                            str(path),
                            passage.text,
                            passage.page,
                            array("f", vector).tobytes(),
                        )
                        for i, (passage, vector) in enumerate(zip(passages, vectors))
                    ],
                )
                db.execute(
                    "UPDATE metadata SET value=? WHERE key='chunk_sequence'",
                    (str(sequence + len(passages)),),
                )
            self.bump(db)

    def prune(self, root, seen):
        with self.connect() as db:
            paths = [row[0] for row in db.execute("SELECT path FROM documents")]
            removed = [
                path
                for path in paths
                if Path(path).is_relative_to(root) and path not in seen
            ]
            db.executemany(
                "DELETE FROM documents WHERE path=?", [(path,) for path in removed]
            )
            self.bump(db)
            return len(removed)

    @staticmethod
    def bump(db):
        db.execute(
            "UPDATE metadata SET value=CAST(value AS INTEGER)+1 WHERE key='vector_revision'"
        )

    def discover(self, entries):
        """Persist metadata and pending work in bounded batches before AI processing."""
        with self.connect() as db:
            for path, signature, modified, supported in entries:
                path = Path(path)
                encoded = json.dumps(signature)
                saved = db.execute(
                    "SELECT signature FROM files WHERE path=?", (str(path),)
                ).fetchone()
                if saved and saved[0] == encoded:
                    if supported:
                        db.execute("UPDATE files SET state='pending' WHERE path=? AND state='unsupported'", (str(path),))
                    continue
                db.execute(
                    """INSERT INTO files(path,name,parent,suffix,size,modified,signature,state)
                    VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET size=excluded.size,
                    modified=excluded.modified,signature=excluded.signature,state=excluded.state,
                    error='',attempts=0,retry_at=0,ocr=0""",
                    (
                        str(path),
                        path.name,
                        str(path.parent),
                        path.suffix.lower(),
                        signature[0],
                        modified,
                        encoded,
                        "pending" if supported else "unsupported",
                    ),
                )

    def state(self, path, state, error="", ocr=False):
        with self.connect() as db:
            db.execute(
                """UPDATE files SET state=?,error=?,ocr=?,attempts=CASE WHEN ?='failed'
                THEN attempts+1 ELSE attempts END,retry_at=? WHERE path=?""",
                (
                    state,
                    str(error),
                    int(ocr),
                    state,
                    time.time() + 60 if state == "failed" else 0,
                    str(path),
                ),
            )

    def recover(self):
        with self.connect() as db:
            db.execute(
                "UPDATE files SET state='pending' WHERE state IN ('processing','ocr_processing')"
            )

    def pending(self, limit=128):
        with self.connect() as db:
            return [
                Path(row[0])
                for row in db.execute(
                    """SELECT path FROM files
                WHERE state IN ('pending','ocr_pending') OR (state='failed' AND attempts<3 AND retry_at<?)
                ORDER BY CASE WHEN suffix IN ('.png','.jpg','.jpeg','.webp','.bmp','.tif','.tiff') OR state='ocr_pending' THEN 1 ELSE 0 END,
                modified DESC LIMIT ?""",
                    (time.time(), limit),
                )
            ]

    def retry(self, path=None, force_ocr=False):
        with self.connect() as db:
            where, args = (
                ("path=?", [str(path)]) if path else ("state IN ('failed','empty')", [])
            )
            db.execute(
                f"UPDATE files SET state=?,attempts=0,retry_at=0,error=? WHERE {where}",
                ["pending", "force-ocr" if force_ocr else "", *args],
            )
            if path:
                db.execute("UPDATE documents SET digest='' WHERE path=?", (str(path),))

    def prune_catalog(self, root, seen):
        with self.connect() as db:
            paths = [row[0] for row in db.execute("SELECT path FROM files")]
            removed = [
                p for p in paths if Path(p).is_relative_to(root) and p not in seen
            ]
            db.executemany("DELETE FROM files WHERE path=?", [(p,) for p in removed])

    def forget(self, path):
        with self.connect() as db:
            db.execute("DELETE FROM files WHERE path=?", (str(path),))
            db.execute("DELETE FROM documents WHERE path=?", (str(path),))
            self.bump(db)

    def file(self, path):
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            row = db.execute(
                "SELECT * FROM files WHERE path=?", (str(path),)
            ).fetchone()
            return dict(row) if row else None

    def stats(self):
        with self.connect() as db:
            return dict(db.execute("SELECT state,COUNT(*) FROM files GROUP BY state"))

    def suffixes(self):
        with self.connect() as db:
            return [
                row[0]
                for row in db.execute(
                    "SELECT DISTINCT suffix FROM files WHERE suffix<>'' ORDER BY suffix"
                )
            ]

    def list_files(
        self,
        root=None,
        suffix="",
        state="",
        days=0,
        min_size=0,
        max_size=0,
        sort="name",
        offset=0,
        limit=200,
    ):
        clauses, args = [], []
        if root:
            # LIKE escapes ensure paths containing % or _ are literal.
            escaped = (
                str(root)
                .rstrip("/\\")
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            clauses.append("(parent=? OR path LIKE ? ESCAPE '\\')")
            args.extend(
                [
                    str(root),
                    escaped + ("\\\\" if __import__("os").name == "nt" else "/") + "%",
                ]
            )
        for column, value in (("suffix", suffix), ("state", state)):
            if value:
                clauses.append(f"{column}=?")
                args.append(value)
        if days:
            clauses.append("modified>=?")
            args.append(time.time() - days * 86400)
        if min_size:
            clauses.append("size>=?")
            args.append(min_size)
        if max_size:
            clauses.append("size<=?")
            args.append(max_size)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        order = {
            "name": "name COLLATE NOCASE,path",
            "date": "modified DESC,path",
            "size": "size DESC,path",
            "type": "suffix,name COLLATE NOCASE,path",
        }.get(sort, "name COLLATE NOCASE,path")
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            total = db.execute("SELECT COUNT(*) FROM files" + where, args).fetchone()[0]
            rows = db.execute(
                "SELECT * FROM files"
                + where
                + " ORDER BY "
                + order
                + " LIMIT ? OFFSET ?",
                [*args, limit, offset],
            )
            return [dict(row) for row in rows], total

    def children(self, root):
        with self.connect() as db:
            parents = [
                Path(row[0]) for row in db.execute("SELECT DISTINCT parent FROM files")
            ]
        root = Path(root)
        return sorted(
            {
                str(root / p.relative_to(root).parts[0])
                for p in parents
                if p != root and p.is_relative_to(root)
            },
            key=str.casefold,
        )

    def search_words(self, query):
        """Ignore filler words; expand only an unambiguous one-edit spelling error."""
        import re
        import string

        tokens = list(dict.fromkeys(re.findall(r"\w+", query.casefold())[:30]))
        filler = {'a', 'an', 'the', 'for', 'of', 'in', 'on', 'at', 'to', 'and', 'with'}
        words = [word for word in tokens if word not in filler] or tokens
        corrected = False
        attempts = 0
        name_terms = None
        with self.connect() as db:
            for index, word in enumerate(words):
                if not (5 <= len(word) <= 24 and word.isascii() and word.isalpha()):
                    continue
                if db.execute(
                    'SELECT 1 FROM chunk_fts WHERE chunk_fts MATCH ? LIMIT 1',
                    ('"' + word + '"',),
                ).fetchone():
                    continue
                if name_terms is None:
                    name_terms = {
                        term for (name,) in db.execute('SELECT name FROM files')
                        for term in re.findall(r'\w+', name.casefold().replace('_', ' '))
                    }
                if word in name_terms:
                    continue
                if attempts >= 8:
                    break
                attempts += 1
                splits = [(word[:i], word[i:]) for i in range(len(word) + 1)]
                variants = {left + right[1:] for left, right in splits if right}
                variants.update(
                    left + right[1] + right[0] + right[2:]
                    for left, right in splits if len(right) > 1
                )
                variants.update(
                    left + letter + right[1:]
                    for left, right in splits if right
                    for letter in string.ascii_lowercase
                )
                variants.update(
                    left + letter + right for left, right in splits
                    for letter in string.ascii_lowercase
                )
                variants = sorted(variants)
                matches = set(variants) & name_terms
                if len(matches) > 1:
                    continue
                for start in range(0, len(variants), 500):
                    batch = variants[start:start + 500]
                    matches.update(
                        row[0] for row in db.execute(
                            'SELECT term FROM chunk_terms WHERE term IN ('
                            + ','.join('?' for _ in batch) + ')', batch
                        )
                    )
                    if len(matches) > 1:
                        break
                if len(matches) == 1:
                    words[index] = next(iter(matches))
                    corrected = True
        return ' '.join(words), corrected

    def lexical(self, query, limit=100, require_all=False):
        import re

        tokens = re.findall(r"\w+", query, flags=re.UNICODE)
        if not tokens:
            return []
        expression = (" AND " if require_all else " OR ").join(
            '"' + token + '"' for token in tokens[:30]
        )
        with self.connect() as db:
            return db.execute(
                """SELECT path,text,page,bm25(chunk_fts) FROM chunk_fts
                WHERE chunk_fts MATCH ? ORDER BY bm25(chunk_fts) LIMIT ?""",
                (expression, limit),
            ).fetchall()

    def names(self, query, limit=100):
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        with self.connect() as db:
            return [
                row[0]
                for row in db.execute(
                    """SELECT path FROM files WHERE name LIKE ? ESCAPE '\\'
                OR path LIKE ? ESCAPE '\\' ORDER BY CASE WHEN lower(name)=lower(?) THEN 0 ELSE 1 END,name LIMIT ?""",
                    ("%" + escaped + "%", "%" + escaped + "%", query, limit),
                )
            ]

    def identifier_paths(self, codes, cancelled=lambda: False):
        from .search_evidence import identifier_pattern, identifier_expression

        patterns = [identifier_pattern(code) for code in codes]
        def matches(value):
            return all(pattern.search(value) for pattern in patterns)

        found = set()
        with self.connect() as db:
            for (path,) in db.execute('SELECT path FROM files'):
                if cancelled():
                    return set()
                if matches(path):
                    found.add(path)
            # Use indexed token candidates, then check boundaries/separators literally.
            expression = ' OR '.join(identifier_expression(code) for code in codes)
            for path, text in db.execute(
                'SELECT path,text FROM chunk_fts WHERE chunk_fts MATCH ?', (expression,)
            ):
                if cancelled():
                    return set()
                if matches(path + '\n' + text):
                    found.add(path)
        return found

    def chunks_by_ids(self, ids):
        if not ids:
            return []
        with self.connect() as db:
            return db.execute(
                "SELECT id,path,text,page FROM chunks WHERE id IN ("
                + ",".join("?" for _ in ids)
                + ")",
                [int(i) for i in ids],
            ).fetchall()

    def vector_records(self, with_paths=False):
        with self.connect() as db:
            return db.execute(
                "SELECT id,path,vector FROM chunks"
                if with_paths
                else "SELECT id,vector FROM chunks"
            ).fetchall()

    def cached_ocr(self, identity):
        with self.connect() as db:
            row = db.execute(
                "SELECT payload FROM ocr_cache WHERE identity=?", (identity,)
            ).fetchone()
            return json.loads(row[0]) if row else None

    def save_ocr(self, identity, payload):
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO ocr_cache VALUES(?,?)",
                (identity, json.dumps(payload)),
            )

    def count(self):
        with self.connect() as db:
            return db.execute("SELECT COUNT(DISTINCT path) FROM chunks").fetchone()[0]

    def documents(self):
        with self.connect() as db:
            return [
                row[0]
                for row in db.execute(
                    "SELECT DISTINCT path FROM chunks ORDER BY path COLLATE NOCASE"
                )
            ]

    def vectors(self):
        with self.connect() as db:
            for path, text, page, blob in db.execute(
                "SELECT path,text,page,vector FROM chunks"
            ):
                vector = array("f")
                vector.frombytes(blob)
                yield path, text, page, vector
