import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from paper_agent.ingestion.library import Library, LibraryError


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pdf = self.root / "sample.pdf"
        self.pdf.write_bytes(b"%PDF-1.5\nfixture")
        self.db = self.root / "data"
        self.lib = Library(self.db)

    def imported(self):
        return self.lib.import_pdf(self.pdf)["paper"]["id"]

    def assert_code(self, code, call):
        with self.assertRaises(LibraryError) as caught:
            call()
        self.assertEqual(code, caught.exception.code)

    def test_material_schema_rejects_invalid_metadata_without_orphan_pdf(self):
        with self.assertRaises(LibraryError) as caught:
            self.lib.import_pdf(self.pdf, title=123)
        self.assertEqual("invalid_material_record", caught.exception.code)
        self.assertFalse(list((self.db / "papers").glob("*.pdf")))
        self.assertFalse(self.lib.list_papers())

    def test_readiness_detects_missing_or_changed_material_without_writing(self):
        paper_id = self.imported()
        self.assertIn("content_not_ready", self.lib.check(paper_id)["issues"])
        with patch("pdfplumber.open") as opened:
            opened.return_value.__enter__.return_value.pages = [SimpleNamespace(extract_text=lambda **kw: "text")]
            self.lib.parse(paper_id)
        before = {p: p.read_bytes() for p in self.db.rglob("*") if p.is_file()}
        self.assertTrue(self.lib.check(paper_id)["ready"])
        self.assertEqual(before, {p: p.read_bytes() for p in self.db.rglob("*") if p.is_file()})
        paper = self.lib.get(paper_id)
        Path(paper["pdf_path"]).write_bytes(b"changed")
        self.assertIn("source_changed", self.lib.check(paper_id)["issues"])
        (self.lib.contents / paper_id / (paper["active_run_id"] + ".json")).unlink()
        self.assertIn("content_unreadable", self.lib.check(paper_id)["issues"])

    def test_duplicate_content_and_restart(self):
        first = self.imported()
        copy = self.root / "renamed.pdf"
        copy.write_bytes(self.pdf.read_bytes())
        second = self.lib.import_pdf(copy)
        self.assertTrue(second["duplicate"])
        self.assertEqual(first, second["paper"]["id"])
        self.assertEqual(1, len(Library(self.db).list_papers()))

    def test_invalid_inputs(self):
        self.assert_code("file_unreadable", lambda: self.lib.import_pdf(self.root / "missing.pdf"))
        bad = self.root / "bad.pdf"
        bad.write_text("not a PDF")
        self.assert_code("invalid_pdf", lambda: self.lib.import_pdf(bad))
        self.assert_code("not_found", lambda: self.lib.get("missing"))
        self.assert_code("not_ready", lambda: self.lib.read(self.imported()))

    def test_partial_pages_persist_and_reparse_has_stable_ids(self):
        paper_id = self.imported()
        pages = [SimpleNamespace(extract_text=lambda **kw: "first page"),
                 SimpleNamespace(extract_text=lambda **kw: "")]
        with patch("pdfplumber.open") as opened:
            opened.return_value.__enter__.return_value.pages = pages
            result = self.lib.parse(paper_id)
            self.assertEqual("partial", result["paper"]["status"])
            self.lib.parse(paper_id)
        content = Library(self.db).read(paper_id, 1, 2)["pages"]
        self.assertEqual(2, len(content))
        self.assertEqual(f"{paper_id}:page:1", content[0]["id"])
        self.assertEqual("first page", content[0]["text"])
        self.assertTrue(content[1]["warning"])
        self.assert_code("invalid_range", lambda: self.lib.read(paper_id, 0))

    def test_changed_source_and_corrupt_pdf_mark_failed(self):
        paper_id = self.imported()
        Path(self.lib.get(paper_id)["pdf_path"]).write_bytes(b"%PDF-1.5\nchanged")
        self.pdf.write_bytes(b"%PDF-1.5\nchanged")
        self.assert_code("source_changed", lambda: self.lib.parse(paper_id))
        self.assertEqual("failed", self.lib.get(paper_id)["status"])
        other_id = self.imported()
        self.assert_code("parse_failed", lambda: self.lib.parse(other_id))
        self.assertEqual("failed", self.lib.get(other_id)["status"])

    def test_docling_adapter_keeps_provenance_and_old_blocks(self):
        paper_id = self.imported()
        def converted(*args):
            return {"pages": [{"pdf_page": 1, "text": "left then right", "warning": None}],
                    "blocks": [{"pdf_page": 1, "order": 0, "type": "text", "text": "left",
                                "bbox": {"l": 10, "t": 20, "r": 30, "b": 40}}],
                    "limitations": ["test limitation"], "partial": False, "backend": "docling"}
        with patch("paper_agent.ingestion.docling_backend.convert", side_effect=converted):
            self.lib.parse(paper_id, backend="docling")
            first = self.lib.read(paper_id)
            self.lib.parse(paper_id, backend="docling")
        second = Library(self.db).read(paper_id)
        self.assertNotEqual(first["parse_run_id"], second["parse_run_id"])
        self.assertEqual("left then right", second["pages"][0]["text"])
        self.assertEqual(10, second["blocks"][0]["bbox"]["l"])
        self.assertEqual(["test limitation"], second["limitations"])
        self.assertEqual(2, len(list((self.lib.contents / paper_id).glob("*.json"))))


if __name__ == "__main__":
    unittest.main()
