"""Finish the portable distribution and create a ZIP with a SHA-256 checksum."""
from importlib.metadata import distributions
from pathlib import Path
import hashlib
import shutil
import zipfile

root = Path(__file__).resolve().parents[1]
release = root / "dist" / "Providence"
assert (release / "Providence.exe").is_file(), "Build Providence.spec first"
shutil.copy2(root / "LICENSE", release / "LICENSE.txt")
shutil.copy2(root / "scripts" / "WINDOWS-README.txt", release / "README.txt")

# Include license notices from the isolated build environment, preserving paths.
licenses = release / "third-party-licenses"
inventory = []
for dist in distributions():
    name = dist.metadata["Name"]
    if name.lower() in {"pytest", "pyinstaller", "pyinstaller-hooks-contrib", "providence-search"}:
        continue
    inventory.append(f"{name} {dist.version}")
    for file in dist.files or []:
        relative = Path(str(file))
        lowered = str(file).lower()
        if ".dist-info/" not in lowered or not any(word in lowered for word in ("license", "copying", "notice")):
            continue
        source = dist.locate_file(file)
        if source.is_file():
            target = licenses / name / Path(*relative.parts[1:])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
licenses.mkdir(exist_ok=True)
(licenses / "BUILD-DEPENDENCIES.txt").write_text("\n".join(sorted(inventory)) + "\n", encoding="utf-8")
shutil.copy2(root / "build/model/README.md", licenses / "MODEL-CARD.md")
shutil.copy2(root / 'build/qwen/README.md', licenses / 'QWEN-MODEL-CARD.md')
# The bundled model is Apache-2.0; Transformers includes the full license text.
apache = next((licenses / "transformers").rglob("LICENSE"))
shutil.copy2(apache, licenses / "MODEL-LICENSE-Apache-2.0.txt")
python_license = Path(__import__("sys").base_prefix) / "LICENSE.txt"
if python_license.exists():
    shutil.copy2(python_license, licenses / "PYTHON-LICENSE.txt")

# Source and build recipe accompany the portable distribution.
source = release / "source"
source.mkdir(exist_ok=True)
shutil.copytree(root / "providence", source / "providence", dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
for filename in ("launcher.py", "Providence.spec", "pyproject.toml", "requirements-windows.txt", "README.md", "LICENSE"):
    shutil.copy2(root / filename, source / filename)
source_scripts = source / "scripts"
source_scripts.mkdir(exist_ok=True)
shutil.copytree(root/'docs',source/'docs',dirs_exist_ok=True)
shutil.copytree(root/'tests',source/'tests',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
for filename in ('benchmark-search.py','benchmark-vectors.py','preview-ui.py','verify-packaged-search.py'):
    shutil.copy2(root/'scripts'/filename,source_scripts/filename)
for filename in ("build-windows.ps1", "package-windows.py", "prepare-icon.py", "verify-package.py", "verify-desktop-windows.ps1", "WINDOWS-README.txt", "download-qwen.py"):
    shutil.copy2(root / "scripts" / filename, source_scripts / filename)
(source / "docker").mkdir(exist_ok=True)
shutil.copy2(root / "docker" / "download_model.py", source / "docker" / "download_model.py")

archive = root / "dist" / "Providence-win-x64.zip"
files = sorted(path for path in release.rglob("*") if path.is_file())
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as output:
    for index, file in enumerate(files):
        output.write(file, file.relative_to(release.parent))
        if index % 250 == 0:
            print(f"Packaging {index + 1}/{len(files)} files", flush=True)
with zipfile.ZipFile(archive) as output:
    assert output.testzip() is None, "Archive verification failed"
digest = hashlib.file_digest(archive.open("rb"), "sha256").hexdigest()
archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
print(f"Ready: {archive} ({archive.stat().st_size / 1024**2:.1f} MB)", flush=True)
