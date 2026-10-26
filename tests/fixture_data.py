"""Synthetic, offline material fixtures; never read a developer's personal data."""
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from paper_agent.bootstrap import initialize_data
from paper_agent.ingestion.library import Library

_TEMP = tempfile.TemporaryDirectory(prefix="paper-agent-fixture-")
DATA = initialize_data(Path(_TEMP.name) / "data")
source = Path(_TEMP.name) / "synthetic.pdf"
source.write_bytes(b"%PDF-1.5\nSynthetic mocked parser fixture; not a research paper.")
library = Library(DATA)
paper_id = library.import_pdf(source, title="Synthetic VLA fixture")["paper"]["id"]
with patch("pdfplumber.open") as opened:
    opened.return_value.__enter__.return_value.pages = [
        SimpleNamespace(extract_text=lambda **kwargs: "Synthetic test text: image and language inputs produce continuous robot actions.")
        for _ in range(4)
    ]
    library.parse(paper_id, backend="pdfplumber")
