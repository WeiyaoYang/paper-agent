"""Build from the source root; resources are copied explicitly by build-portable.ps1."""
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, copy_metadata

root = Path(SPECPATH).parent
datas, binaries, hiddenimports = [], [], []
for package in ("docling", "docling_core", "docling_ibm_models", "transformers", "pypdfium2"):
    package_data, package_binaries, package_imports = collect_all(package)
    datas += package_data
    binaries += package_binaries
    hiddenimports += package_imports
for package in ("docling", "transformers", "torch", "torchvision", "openai", "jsonschema", "pdfplumber"):
    datas += copy_metadata(package)
analysis = Analysis([str(root / "scripts/portable_entry.py")], pathex=[str(root / "src")],
    binaries=binaries, datas=datas, hiddenimports=hiddenimports,
    hookspath=[], runtime_hooks=[], excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "IPython", "pytest", "tkinter", "tensorboard", "tensorflow", "jax", "flax"],
    noarchive=False)
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name="AgentWorkbench", debug=False,
    bootloader_ignore_signals=False, strip=False, upx=False, console=False)
collect = COLLECT(exe, analysis.binaries, analysis.datas, strip=False, upx=False, name="AgentWorkbench")
