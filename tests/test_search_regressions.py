from threading import Event
from pathlib import Path
import pytest
from PySide6.QtCore import QObject
from PySide6.QtTest import QTest
from providence.engine import Result
from providence.quick_ui import QuickWindow
from test_ui import app as app, make_engine, library, finish


def test_attendance_query_requires_class_code_and_explains_filename_match(tmp_path):
    engine = make_engine(tmp_path)
    root = tmp_path / 'documents'
    root.mkdir()
    samples = {
        'Attendance Report - 1-CS1.csv': 'Student,Date,Present\nExample Student,2026-09-02,Yes',
        'Attendance Report - 1CS4.csv': 'Attendance for 1CS4. Present students.',
        'Introduction.txt': 'City college of example. Attendance policy for all students.',
        '1CS1-notes.txt': 'Attendance policy: arrive on time for your class.',
        'records.txt': 'Attendance for class 1-CS1. Example Student was present.',
    }
    for name, text in samples.items():
        (root / name).write_text(text)
    engine.index(root)
    for query in ('attendance of 1cs1', 'attendace of 1cs1', 'attendance of 1-CS1', 'attendance of 1-CS-1'):
        results = engine.search(query)
        assert Path(results[0].path).name == 'Attendance Report - 1-CS1.csv'
        assert {Path(result.path).name for result in results} == {
            'Attendance Report - 1-CS1.csv', '1CS1-notes.txt', 'records.txt',
        }
        first = results[0]
        assert first.reason == 'Filename'
        assert 'Filename: attendance, 1cs1' in first.explanation
        assert 'of' not in first.matched_words
        if query.startswith('attendace'):
            assert 'Spelling fallback: attendance' in first.explanation
    engine.ocr_worker.close()


def test_absent_class_code_returns_no_matches_without_model_work(tmp_path, monkeypatch):
    engine = make_engine(tmp_path)
    root = library(tmp_path)
    (root / '1CS4.txt').write_text('Attendance for 1CS4')
    engine.index(root)
    def forbidden(*args, **kwargs):
        raise AssertionError('An absent required identifier must not start inference')
    monkeypatch.setattr(engine, 'encode', forbidden)
    assert engine.search('attendance of 1cs1') == []
    engine.ocr_worker.close()


def test_code_boundaries_scope_and_multiple_codes(tmp_path):
    engine = make_engine(tmp_path)
    root = tmp_path / 'documents'
    root.mkdir()
    target = root / '1_CS1.txt'
    target.write_text('Attendance for 2-CS2')
    (root / '1CS10.txt').write_text('Attendance for another class')
    other = root / 'other'
    other.mkdir()
    (other / '1CS1.txt').write_text('Attendance')
    engine.index(root)
    assert [r.path for r in engine.search('attendance 1cs1 2cs2')] == [str(target)]
    assert [r.path for r in engine.search('attendance 1cs1', filters={'root': other})] == [str(other / '1CS1.txt')]
    engine.ocr_worker.close()


def test_search_does_not_count_removed_catalog_entries(tmp_path):
    engine = make_engine(tmp_path)
    root = library(tmp_path)
    engine.index(root)
    with engine.store.connect() as db:
        db.execute('DELETE FROM files')
    assert engine.search('database') == []
    engine.ocr_worker.close()


def test_match_evidence_is_visible_in_narrow_results_and_preview(app, tmp_path):
    engine = make_engine(tmp_path)
    root = library(tmp_path)
    (root / 'Attendance - 1-CS1.csv').write_text('Student,Present\nExample Student,Yes')
    engine.index(root)
    engine.store.set_setting('onboarding_complete', '1')
    window = QuickWindow(engine, monitor=False)
    window.resize(1080, 640)
    window.show()
    try:
        window.bridge.submitSearch('attendace of 1cs1')
        finish(app, window.controller)
        window.bridge.refresh()
        QTest.qWait(50)
        row = window.bridge.rows[0]
        assert 'Filename: attendance, 1cs1' in row['explanation']
        items = [window.quick.rootObject()]
        evidence = None
        while items:
            item = items.pop()
            if item.objectName() == 'match-evidence-0':
                evidence = item
                break
            items.extend(item.childItems())
        assert evidence and evidence.property('visible') and evidence.property('width') > 0
        assert evidence.property('text') == row['explanation']
        assert 'Why this file: Filename: attendance, 1cs1' in window.controller.match_text.text()
    finally:
        window.close()


@pytest.mark.parametrize('reasons, expected', [
    ([], 'No files found for “scores for deliquent” in this search scope.'),
    (['Meaning'], 'No word or filename matches for “scores for deliquent”. Showing 1 potentially related file.'),
    (['Text', 'Meaning'], 'Results for “scores for deliquent” · 1 word/filename match · 1 potentially related file'),
])
def test_search_status_explains_empty_and_related_results(app, tmp_path, monkeypatch, reasons, expected):
    engine = make_engine(tmp_path)
    root = library(tmp_path)
    (root / 'students.txt').write_text('Student scores')
    engine.index(root)
    engine.store.set_setting('onboarding_complete', '1')
    results = [Result(str(path.resolve()), 'Student scores', None, .5, reason)
               for path, reason in zip(sorted(root.iterdir()), reasons)]
    monkeypatch.setattr(engine, 'search', lambda *args, **kwargs: results)
    window = QuickWindow(engine, monitor=False)
    window.show()
    window.bridge.submitSearch('scores for deliquent')
    finish(app, window.controller)
    window.bridge.refresh()
    QTest.qWait(50)
    assert window.bridge.state['status'] == expected
    empty = window.quick.rootObject().findChild(QObject, 'results-empty')
    assert empty.property('visible') == (not reasons)
    if not reasons:
        assert expected in empty.property('text')
    if 'Meaning' in reasons:
        assert any(row['match'] == 'Related' for row in window.bridge.rows)
    window.bridge.search('')
    assert 'scores for deliquent' not in window.bridge.state['emptyMessage']
    window.close()


def test_misspelled_score_query_prioritizes_all_remembered_words(tmp_path, monkeypatch):
    engine = make_engine(tmp_path)
    root = tmp_path / 'documents'
    root.mkdir()
    samples = {
        'student.txt': 'Scores for delinquent students. Academic grades and scores.',
        'games.txt': 'Scores for basketball games and scores for video games.',
        'accounts.txt': 'Delinquent accounts and overdue payments.',
        'travel.txt': 'Reservations for a beach holiday.',
    }
    for name, text in samples.items():
        (root / name).write_text(text)
    engine.index(root)
    # Deliberately misleading semantic order: lexical evidence must still win.
    monkeypatch.setattr(engine.vector_index, 'search', lambda *args: [
        (str((root / name).resolve()), samples[name], None, .9 - i * .1)
        for i, name in enumerate(reversed(samples))
    ])
    for query in ('Scores for deliquent', 'Scores for delinquent'):
        results = engine.search(query)
        assert Path(results[0].path).name == 'student.txt'
        assert next(r for r in results if Path(r.path).name == 'travel.txt').reason == 'Meaning'
    assert engine.search('Scores for deliquent')[0].reason == 'Similar words'
    assert [Path(row[0]).name for row in engine.store.lexical('scores delinquent', require_all=True)] == ['student.txt']
    engine.ocr_worker.close()


def test_spelling_fallback_preserves_exact_and_ambiguous_words(tmp_path):
    engine = make_engine(tmp_path)
    root = library(tmp_path)
    (root / 'spelling.txt').write_text('tickets ticker delinquent')
    engine.index(root)
    assert engine.store.search_words('scores for deliquent') == ('scores delinquent', True)
    assert engine.store.search_words('tickets') == ('tickets', False)
    assert engine.store.search_words('ticket') == ('ticket', False)
    assert engine.store.search_words('for') == ('for', False)
    assert engine.store.search_words('" OR *') == ('or', False)
    engine.ocr_worker.close()


def test_failed_search_clears_previous_results_and_searching_label(app, tmp_path, monkeypatch):
    engine = make_engine(tmp_path)
    engine.index(library(tmp_path))
    engine.store.set_setting('onboarding_complete', '1')
    window = QuickWindow(engine, monitor=False)
    window.bridge.submitSearch('database')
    finish(app, window.controller)
    assert window.controller.search_results
    failures = []
    monkeypatch.setattr(window.controller, 'show_error', failures.append)
    def failed(*args, **kwargs):
        raise RuntimeError('Model unavailable')
    monkeypatch.setattr(engine, 'search', failed)
    window.bridge.submitSearch('another query')
    finish(app, window.controller)
    window.bridge.refresh()
    assert failures == ['Model unavailable']
    assert window.controller.summary.text() == 'Search failed'
    assert window.controller.search_results == []
    assert not window.bridge.rows and not window.bridge.state['search']['running']
    window.close()


def test_discarded_result_cannot_leave_searching_label(app, tmp_path, monkeypatch):
    engine = make_engine(tmp_path)
    engine.store.set_setting('onboarding_complete', '1')
    entered, release = Event(), Event()
    def search(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return []
    monkeypatch.setattr(engine, 'search', search)
    window = QuickWindow(engine, monitor=False)
    try:
        window.bridge.submitSearch('original')
        assert entered.wait(2)
        window.controller.query.setText('changed draft')
        release.set()
        finish(app, window.controller)
        window.bridge.refresh()
        assert window.controller.summary.text() != 'Searching…'
        assert not window.bridge.state['search']['running']
        assert window.controller.search_button.isEnabled()
    finally:
        release.set()
        finish(app, window.controller)
        window.close()
