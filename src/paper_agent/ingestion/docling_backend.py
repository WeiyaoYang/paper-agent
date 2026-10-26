"""Docling adapter. Keep vendor output alongside our normalized blocks."""

import json
import logging
from importlib.metadata import version
from pathlib import Path


LIMITATIONS = [
    "Layout and reading order are model predictions; verify important passages against the PDF.",
    "PDF page numbers are 1-based; printed page labels are not inferred.",
    "Picture regions and captions are located, not semantically interpreted.",
    "OCR is disabled for this born-digital PDF pipeline; scans require another configuration.",
]


def normalize(document, path):
    """Use model reading order, but do not duplicate cross-page paragraphs."""
    import pdfplumber

    blocks = []
    page_text = {number: [] for number in sorted(document.pages)}
    with pdfplumber.open(path) as pdf:
        for order, (item, level) in enumerate(document.iterate_items()):
            provenance = getattr(item, "prov", [])
            if not provenance:
                continue
            label = getattr(item.label, "value", str(item.label))
            full_text = getattr(item, "text", "")
            if label == "table":
                full_text = item.export_to_markdown(doc=document)
            crosses_pages = len({p.page_no for p in provenance}) > 1
            for location in provenance:
                text, text_source, warning = full_text, "docling", None
                bbox = location.bbox.model_dump(mode="json")
                if crosses_pages and label not in ("table", "picture", "formula"):
                    # Docling's cleaned text can have stale char offsets after dehyphenation.
                    # For cross-page text, read only the provenance region from the source PDF.
                    page = pdf.pages[location.page_no - 1]
                    if bbox["coord_origin"] == "BOTTOMLEFT":
                        top, bottom = page.height - bbox["t"], page.height - bbox["b"]
                    else:
                        top, bottom = bbox["t"], bbox["b"]
                    region = (max(0, bbox["l"]), max(0, top), min(page.width, bbox["r"]), min(page.height, bottom))
                    text = page.crop(region).extract_text(x_tolerance_ratio=0.2) or ""
                    text_source = "pdf_region_at_docling_provenance"
                    warning = "Cross-page paragraph localized from PDF region; line breaks and hyphenation may remain."
                elif len(provenance) > 1 and label not in ("table", "picture", "formula"):
                    start, end = location.charspan
                    text = full_text[start:end]
                    if end > len(full_text):
                        warning = "Docling character span exceeds normalized text; verify region."
                elif crosses_pages:
                    warning = "Structured item spans pages; content may repeat. Verify original."
                block = {"vendor_ref": item.self_ref, "order": order, "level": level,
                         "type": label, "text": text, "pdf_page": location.page_no,
                         "bbox": bbox, "charspan": list(location.charspan),
                         "text_source": text_source, "warning": warning}
                blocks.append(block)
                if label == "picture":
                    rendered = "<!-- picture: see original PDF region -->"
                elif label == "formula" and not text.strip():
                    rendered = "[Formula region: text unavailable; inspect original PDF.]"
                elif label == "section_header":
                    rendered = "## " + text
                else:
                    rendered = text
                if rendered.strip():
                    page_text[location.page_no].append(rendered)
    pages = [{"pdf_page": n, "text": "\n\n".join(parts),
              "warning": None if any(b["text"].strip() for b in blocks if b["pdf_page"] == n)
              else "No readable text on this page; inspect original."}
             for n, parts in page_text.items()]
    return pages, blocks


def convert(path, output, formula=False):
    logging.getLogger(__name__).info("Loading Docling (OCR off, tables on, formulas %s)", formula)
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions()
    options.do_ocr = False
    options.do_table_structure = True
    options.do_formula_enrichment = formula
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
    result = converter.convert(Path(path))
    state = getattr(result.status, "value", str(result.status))
    if state not in ("success", "partial_success"):
        raise RuntimeError(f"Docling conversion status: {state}; errors: {result.errors}")
    document = result.document
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    raw = output / "docling.json"
    raw.write_text(json.dumps(document.export_to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "document.md").write_text(document.export_to_markdown(), encoding="utf-8")
    pages, blocks = normalize(document, path)
    warnings = list(LIMITATIONS)
    if not formula:
        warnings.append("Formula enrichment is disabled; formula regions may contain raw or incomplete text.")
    else:
        warnings.append("Formula LaTeX is model-generated and must be checked against the original.")
    errors = [str(error) for error in result.errors]
    return {"pages": pages, "blocks": blocks, "limitations": warnings,
            "partial": state == "partial_success", "errors": errors,
            "backend": "docling", "backend_version": version("docling"),
            "options": {"ocr": False, "table_structure": True, "formula_enrichment": formula},
            "artifacts": {"raw_json": str(raw.resolve()), "markdown": str((output / 'document.md').resolve())}}
