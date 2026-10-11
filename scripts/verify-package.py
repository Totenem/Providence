"""Verify that the executable contains the current application source code."""
from pathlib import Path
import types
import pefile

from PyInstaller.archive.readers import CArchiveReader


def code_signature(code):
    return (code.co_code, code.co_names, code.co_varnames, code.co_freevars,
            code.co_cellvars, code.co_argcount, code.co_posonlyargcount,
            code.co_kwonlyargcount, code.co_flags,
            tuple(code_signature(value) if isinstance(value, types.CodeType) else value
                  for value in code.co_consts))


root = Path(__file__).resolve().parents[1]
from providence.library_tools import CLIP_REVISION
assert (root / 'dist/Providence/_internal/models/clip-vit-base-patch32/REVISION').read_text().strip() == CLIP_REVISION, 'Packaged image model missing or stale'
executable = root / 'dist' / 'Providence' / 'Providence.exe'
with pefile.PE(str(executable)) as pe:
    assert any(entry.id == 14 for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries), 'Executable icon missing'
icon = Path('providence/assets/providence.ico')
assert (root / 'dist/Providence/_internal' / icon).read_bytes() == (root / icon).read_bytes(), 'Packaged icon is stale'
for qml in (root / 'providence/qml').glob('*.qml'):
    assert (root / 'dist/Providence/_internal/providence/qml' / qml.name).read_bytes() == qml.read_bytes(), 'Packaged QML is stale'
assert not (root / 'dist' / 'Providence' / '_internal' / 'icuuc.dll').exists(), (
    'Bundled ICU can shadow the Windows ICU API required by QtCore')
archive = CArchiveReader(str(root / 'dist' / 'Providence' / 'Providence.exe')).open_embedded_archive('PYZ.pyz')
count = 0
for source in sorted((root / 'providence').glob('*.py')):
    module = 'providence' if source.stem == '__init__' else f'providence.{source.stem}'
    saved = archive.extract(module)
    expected = compile(source.read_bytes(), str(source), 'exec', dont_inherit=True, optimize=0)
    assert code_signature(saved) == code_signature(expected), f'Executable has stale code: {module}'
    count += 1
print(f'Verified executable icon and {count} packaged application modules match current source.')
