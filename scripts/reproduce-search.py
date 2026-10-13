"""Fictional regression corpus for typo queries; never uses a personal index."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from providence.engine import Engine
from providence.embeddings import LocalEmbedder, QwenEmbedder
from providence.store import Store

root = Path('.artifacts/search-repro/documents').resolve()
root.mkdir(parents=True, exist_ok=True)
samples = {
    'student-record.txt': 'Scores for Delinquent Students. Academic grades and assessment scores for students with incomplete requirements. Mathematics 75, English 80.',
    'basketball.txt': 'Scores for basketball games. Final scores, league standings, sports results and team rankings.',
    'website.txt': 'A website for tracking scores in video games. Leaderboards for online gaming and tournament scores.',
    'accounts.txt': 'Delinquent accounts. Overdue payments, balances, interest charges and collection notices.',
    'travel.txt': 'Beach vacation itinerary. Hotel bookings, flights and travel plans.',
}
for name, text in samples.items():
    (root / name).write_text(text, encoding='utf-8')
for name, model in [('minilm', LocalEmbedder()), ('qwen', QwenEmbedder())]:
    store = Store(root.parent / f'{name}/index.sqlite3', model.identity)
    engine = Engine(store, model)
    try:
        engine.index(root)
        for query in ['Scores for deliquent', 'Scores for delinquent']:
            print(name, query, [(Path(r.path).name, r.reason, round(r.score, 3)) for r in engine.search(query)], flush=True)
    finally:
        engine.ocr_worker.close()
