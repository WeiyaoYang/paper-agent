"""Writable portable home: source checkout or the directory next to the EXE."""
import sys
from pathlib import Path


def project_root():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]
