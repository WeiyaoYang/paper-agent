"""Persistent paper registry and page extraction. No model calls required."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from paper_agent.storage.json_files import write_json
from paper_agent.paths import project_root


LIMITATIONS = [
    "Text extraction only: figures, tables and equations are not reliably reconstructed.",
    "PDF page numbers are 1-based; printed page labels and sections are not inferred.",
    "Multi-column reading order may be incorrect; verify against the PDF.",
    "No OCR: scanned pages may have no extracted text.",
]


class LibraryError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def now():
    return datetime.now(timezone.utc).isoformat()


class Library:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.papers = self.directory / "results" / "4papers"
        self.contents = self.directory / "results" / "5papercontents"
        self.papers.mkdir(parents=True, exist_ok=True)

    def _save(self, path, value):
        from jsonschema import Draft202012Validator, ValidationError
        schema_name = "paper" if path.parent == self.papers else "paper-content"
        schema_path = project_root() / "schemas" / (schema_name + ".schema.json")
        try:
            Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8"))).validate(value)
        except ValidationError as exc:
            raise LibraryError("invalid_material_record", "Material does not match its schema: " + str(list(exc.absolute_path))) from None
        write_json(path, value)

    def import_pdf(self, path, title=None, source=None):
        import shutil
        path = Path(path).resolve()
        try:
            with path.open("rb") as stream:
                if b"%PDF-" not in stream.read(1024):
                    raise LibraryError("invalid_pdf", "File has no PDF header.")
                stream.seek(0)
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
        except OSError as exc:
            raise LibraryError("file_unreadable", str(exc)) from exc
        for paper in self.list_papers():
            if paper["sha256"] == digest:
                return {"duplicate": True, "paper": paper}
        paper_id = "paper_" + uuid4().hex
        destination = self.directory / "papers" / (paper_id + ".pdf")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        stamp = now()
        paper = dict(id=paper_id, sha256=digest, title=title or path.stem, source=source,
                     pdf_path=str(destination), status="unprocessed", page_count=None, error=None,
                     created_at=stamp, updated_at=stamp, revision=1, active_run_id=None)
        try:
            self._save(self.papers / (paper_id + ".json"), paper)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return {"duplicate": False, "paper": paper}

    def get(self, paper_id):
        if not paper_id.startswith("paper_") or not paper_id[6:].isalnum():
            raise LibraryError("not_found", "Unknown paper.")
        path = self.papers / (paper_id + ".json")
        if not path.exists():
            raise LibraryError("not_found", f"Unknown paper: {paper_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def list_papers(self):
        return sorted([json.loads(p.read_text(encoding="utf-8")) for p in self.papers.glob("*.json")],
                      key=lambda v: (v["created_at"], v["id"]))

    def check(self, paper_id):
        """Inspect existing material without writing, reparsing or model calls."""
        paper = self.get(paper_id)
        issues = []
        path = Path(paper["pdf_path"])
        try:
            with path.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != paper["sha256"]:
                    issues.append("source_changed")
        except OSError:
            issues.append("pdf_unreadable")
        if paper["status"] not in ("completed", "partial"):
            issues.append("content_not_ready")
        else:
            try:
                content = self.read(paper_id, 1, paper["page_count"])
                if content["paper_id"] != paper_id or content["parse_run_id"] != paper["active_run_id"]:
                    issues.append("content_reference_mismatch")
                if [p["pdf_page"] for p in content["pages"]] != list(range(1, paper["page_count"] + 1)):
                    issues.append("pages_incomplete")
                if not any(p["text"].strip() for p in content["pages"]):
                    issues.append("no_readable_text")
            except (OSError, ValueError, KeyError, TypeError, LibraryError):
                issues.append("content_unreadable")
        return {"paper_id": paper_id, "parse_run_id": paper["active_run_id"],
                "ready": not issues, "issues": issues,
                "warning": "Readiness checks do not verify extraction accuracy or semantic completeness."}

    def parse(self, paper_id, backend="pdfplumber", formula=False):
        if backend not in ("pdfplumber", "docling"):
            raise LibraryError("invalid_backend", "Choose pdfplumber or docling.")
        if formula and backend != "docling":
            raise LibraryError("invalid_options", "Formula enrichment requires Docling.")
        paper = self.get(paper_id)
        if paper["status"] == "processing":
            raise LibraryError("busy", "Paper is already being processed.")
        paper.update(status="processing", error=None, updated_at=now(), revision=paper["revision"] + 1)
        self._save(self.papers / (paper_id + ".json"), paper)
        try:
            import pdfplumber

            path = Path(paper["pdf_path"])
            with path.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != paper["sha256"]:
                    raise LibraryError("source_changed", "PDF changed after import; import the new file separately.")
            pages = []
            run_id = "parse_" + uuid4().hex
            metadata = {"backend": backend, "limitations": LIMITATIONS, "blocks": [], "partial": False}
            if backend == "docling":
                from paper_agent.ingestion.docling_backend import convert

                try:
                    metadata = convert(path, self.directory / "artifacts" / "docling" / paper_id / run_id, formula)
                except ImportError as exc:
                    raise LibraryError("dependency_missing", "Install the docling extra in this Python environment.") from exc
                pages = [(f"{paper_id}:page:{p['pdf_page']}", paper_id, p["pdf_page"], p["text"], p["warning"])
                         for p in metadata.pop("pages")]
            else:
                with pdfplumber.open(path) as pdf:
                    for number, page in enumerate(pdf.pages, 1):
                        warning = None
                        try:
                            text = page.extract_text(layout=False) or ""
                            if not text.strip():
                                warning = "No text extracted; OCR or manual review may be needed."
                        except Exception as exc:
                            text, warning = "", f"Page extraction failed: {exc}"
                        pages.append((f"{paper_id}:page:{number}", paper_id, number, text, warning))
            if not pages:
                raise LibraryError("parse_failed", "PDF has no pages.")
            status = "partial" if metadata["partial"] or any(p[4] for p in pages) else "completed"
            blocks = metadata.pop("blocks")
            content = {"paper_id": paper_id, "pdf_path": paper["pdf_path"], "parse_run_id": run_id,
                       "pages": [dict(zip(("id", "paper_id", "pdf_page", "text", "warning"), page)) for page in pages],
                       "blocks": [{"id": f"{run_id}:block:{i}", **block} for i, block in enumerate(blocks)],
                       "parse": metadata, "limitations": metadata["limitations"]}
            self._save(self.contents / paper_id / (run_id + ".json"), content)
            paper.update(status=status, page_count=len(pages), updated_at=now(), active_run_id=run_id,
                         revision=paper["revision"] + 1)
            self._save(self.papers / (paper_id + ".json"), paper)
            return {"paper": self.get(paper_id), "parse": metadata, "block_count": len(blocks),
                    "page_warnings": [{"pdf_page": p[2], "warning": p[4]} for p in pages if p[4]]}
        except (Exception, KeyboardInterrupt) as exc:
            paper.update(status="failed", error=str(exc), updated_at=now(), revision=paper["revision"] + 1)
            self._save(self.papers / (paper_id + ".json"), paper)
            if isinstance(exc, LibraryError):
                raise
            if isinstance(exc, KeyboardInterrupt):
                raise
            raise LibraryError("parse_failed", str(exc)) from exc

    def read(self, paper_id, start=1, end=None):
        paper = self.get(paper_id)
        if paper["status"] not in ("completed", "partial"):
            raise LibraryError("not_ready", f"Paper status is {paper['status']}; parse it first.")
        end = start if end is None else end
        if not (1 <= start <= end <= paper["page_count"]):
            raise LibraryError("invalid_range", f"Choose pages 1 through {paper['page_count']}.")
        path = self.contents / paper_id / (paper["active_run_id"] + ".json")
        content = json.loads(path.read_text(encoding="utf-8"))
        content["pages"] = [p for p in content["pages"] if start <= p["pdf_page"] <= end]
        content["blocks"] = [b for b in content["blocks"] if start <= b["pdf_page"] <= end]
        content["pdf_path"] = paper["pdf_path"]
        return content

    def export(self, paper_id, directory):
        paper = self.get(paper_id)
        content = self.read(paper_id, 1, paper["page_count"])
        path = Path(directory) / f"{paper_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"paper": paper, **content}, ensure_ascii=False, indent=2), encoding="utf-8")
        markdown = path.with_suffix(".md")
        markdown.write_text("# " + paper["title"] + "\n\n" + "\n\n".join(
            f"## PDF page {page['pdf_page']}\n\n{page['text']}" for page in content["pages"]
        ), encoding="utf-8")
        return {"export_path": str(path.resolve()), "markdown_path": str(markdown.resolve())}
