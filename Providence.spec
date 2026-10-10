# Native Windows one-folder distribution, with the offline model included.
from PyInstaller.utils.hooks import collect_data_files, copy_metadata, collect_submodules
from PyInstaller.config import CONF
from hashlib import sha256
from pathlib import Path

source_root = Path(SPECPATH)

datas = collect_data_files('transformers') + copy_metadata('transformers')
datas += [('build/model', 'models/all-MiniLM-L6-v2')]
for model_file in (source_root / 'build/qwen').rglob('*'):
    relative=model_file.relative_to(source_root / 'build/qwen')
    if model_file.is_file() and '.cache' not in relative.parts:
        datas.append((str(model_file),str(Path('models/qwen-embedding-0.6b')/relative.parent)))
datas += collect_data_files('rapidocr',includes=['*.yaml','models/*.onnx'])
datas += copy_metadata('rapidocr') + copy_metadata('usearch')
datas += [(str(source_root / 'providence' / 'assets'), 'providence/assets')]
datas += [(str(source_root / 'providence' / 'qml'), 'providence/qml')]
hiddenimports = ['transformers.models.bert.modeling_bert', 'transformers.models.bert.tokenization_bert',
                 'transformers.models.qwen3.modeling_qwen3','watchdog.observers.read_directory_changes',
                 'usearch.index']
hiddenimports += collect_submodules('rapidocr')

a = Analysis(['launcher.py'], pathex=[], binaries=[], datas=datas,
             hiddenimports=hiddenimports, hookspath=[], hooksconfig={},
             runtime_hooks=[], excludes=['tkinter', 'matplotlib', 'IPython', 'pytest',
                                        'sentence_transformers', 'sklearn', 'scipy', '__main__'])
# Qt's Windows ICU imports target the OS-provided ICU API. An unrelated ICU
# from tools on PATH (for example Poppler) uses versioned exports and shadows
# that API when collected into _internal, preventing QtCore from loading.
if __import__('sys').platform == 'win32':
    a.binaries = [entry for entry in a.binaries
                  if Path(entry[0]).name.lower() not in {'icuuc.dll', 'icuin.dll'}
                  and not Path(entry[0]).name.lower().startswith('icudt')]
# PyInstaller adds __main__ to exclusions internally; listing it above keeps
# subsequent dependency analyses cached. A content-based archive name also
# prevents an archive built during edits from masking newer application code.
app_sources = sorted((source_root / 'providence').glob('*.py')) + [source_root / 'launcher.py']
source_revision = sha256(b''.join(path.read_bytes() for path in app_sources)).hexdigest()[:16]
pyz = PYZ(a.pure, name=str(Path(CONF['workpath']) / f'PYZ-{source_revision}.pyz'))
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Providence',
          icon=str(source_root / 'providence' / 'assets' / 'providence.ico'),
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='Providence')
