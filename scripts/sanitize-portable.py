"""Remove DLLs accidentally resolved through unrelated development-tool PATH entries."""
import ast
import shutil
import sys
import importlib.util
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

root = Path(__file__).resolve().parents[1]
toc = ast.literal_eval((root / "build/portable/portable/Analysis-00.toc").read_text(encoding="utf-8"))
payload = (root / "dist/portable/AgentWorkbench/_internal").resolve()
allowed = [root.resolve(), Path(sys.base_prefix).resolve(), Path(sys.prefix).resolve(), Path(os.environ.get("SystemRoot", "C:/Windows")).resolve()]
removed = []
for group in toc:
    if not isinstance(group, list):
        continue
    for item in group:
        if not isinstance(item, tuple) or len(item) != 3 or item[2] not in ("BINARY", "EXTENSION"):
            continue
        destination, source, _ = item
        if any(Path(source).resolve().is_relative_to(base) for base in allowed):
            continue
        target = (payload / destination).resolve()
        if not target.is_relative_to(payload):
            raise ValueError("Unsafe target")
        if target.is_file():
            target.unlink()
            removed.append(destination)
for name in ("vcruntime140.dll", "vcruntime140_1.dll"):
    source = Path(sys.base_prefix) / name
    if source.exists():
        shutil.copy2(source, payload / name)
print("Removed unrelated host DLLs:", len(removed))
for package in ("latex2mathml", "rapidocr", "docling_parse"):
    for source, destination in collect_data_files(package):
        target = payload / destination
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target / Path(source).name)
# Recent torchvision wheels use _C_stable/image_stable rather than the hook's old names.
vision = Path(importlib.util.find_spec("torchvision").origin).parent
for source in vision.iterdir():
    if source.suffix.lower() in (".pyd", ".dll"):
        (payload / "torchvision").mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, payload / "torchvision" / source.name)
