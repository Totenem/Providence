from pathlib import Path
import sys

from providence import paths


def source_locations(tmp_path, monkeypatch):
    monkeypatch.delenv('PROVIDENCE_MODEL_DIR', raising=False)
    monkeypatch.delattr(sys, 'frozen', raising=False)
    monkeypatch.setattr(paths, '__file__', str(tmp_path / 'providence' / 'paths.py'))
    monkeypatch.setattr(paths, 'data_dir', lambda: tmp_path / 'data')
    installed = tmp_path / 'data/models/all-MiniLM-L6-v2'
    bundled = tmp_path / 'build/model'
    bundled.mkdir(parents=True)
    (bundled / 'modules.json').write_text('[]')
    return installed, bundled


def test_source_model_uses_downloaded_build_without_environment_override(tmp_path, monkeypatch):
    installed, bundled = source_locations(tmp_path, monkeypatch)
    assert paths.model_dir() == bundled
    installed.mkdir(parents=True)
    (installed / 'modules.json').write_text('[]')
    assert paths.model_dir() == installed


def test_explicit_model_location_is_not_replaced_by_source_fallback(tmp_path, monkeypatch):
    source_locations(tmp_path, monkeypatch)
    explicit = tmp_path / 'custom-model'
    monkeypatch.setenv('PROVIDENCE_MODEL_DIR', str(explicit))
    assert paths.model_dir() == explicit


def test_packaged_model_location_does_not_use_source_fallback(tmp_path, monkeypatch):
    source_locations(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path / 'portable'), raising=False)
    assert paths.model_dir() == tmp_path / 'portable/models/all-MiniLM-L6-v2'
