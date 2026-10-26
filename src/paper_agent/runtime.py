"""Keep this project's caches and temporary files inside its project directory."""

import os
import tempfile
from pathlib import Path
from paper_agent.paths import project_root


def configure_runtime():
    root = project_root()
    locations = {
        "HF_HOME": root / ".cache" / "huggingface",
        "HF_HUB_CACHE": root / ".cache" / "huggingface" / "hub",
        "HF_XET_CACHE": root / ".cache" / "huggingface" / "xet",
        "TORCH_HOME": root / ".cache" / "torch",
        "XDG_CACHE_HOME": root / ".cache",
        "UV_CACHE_DIR": root / ".cache" / "uv",
        "UV_PYTHON_INSTALL_DIR": root / ".runtime" / "python",
        "PIP_CACHE_DIR": root / ".cache" / "pip",
        "TEMP": root / "tmp",
        "TMP": root / "tmp",
    }
    for name, path in locations.items():
        path.mkdir(parents=True, exist_ok=True)
        os.environ[name] = str(path)
    # tempfile may already have cached a directory before this package is imported.
    tempfile.tempdir = str(root / "tmp")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    return {name: str(path) for name, path in locations.items()}
