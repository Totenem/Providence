import argparse
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description="Providence offline document search")
    parser.add_argument("--data-dir", type=Path, help="Location of the index and local model")
    commands = parser.add_subparsers(dest="command")
    indexing = commands.add_parser("index", help="Index a folder offline")
    indexing.add_argument("folder", type=Path)
    indexing.add_argument("--force", action="store_true")
    search = commands.add_parser("search", help="Search offline")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    if args.data_dir:
        os.environ["PROVIDENCE_DATA_DIR"] = str(args.data_dir.resolve())
    from .paths import data_dir
    try:
        from .embeddings import LocalEmbedder
        from .engine import Engine
        from .store import Store
        embedder = LocalEmbedder()
        engine = Engine(Store(data_dir() / "index.sqlite3", embedder.identity), embedder)
        if args.command == "index":
            report = engine.index(args.folder, lambda message: print(message, file=sys.stderr), args.force)
            print(json.dumps(vars(report), indent=2))
            return 1 if report.errors else 0
        if args.command == "search":
            if args.limit < 1:
                parser.error("--limit must be positive")
            print(json.dumps([vars(result) for result in engine.search(args.query, args.limit)], indent=2))
            return 0
        from .ui import launch
        return launch(engine)
    except Exception as error:
        print(f"Providence: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
