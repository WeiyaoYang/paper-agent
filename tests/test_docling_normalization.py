import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from paper_agent.ingestion.docling_backend import normalize


def location(page, start, end):
    bbox = SimpleNamespace(model_dump=lambda **kw: {
        "l": 10, "t": 90, "r": 90, "b": 10, "coord_origin": "BOTTOMLEFT"})
    return SimpleNamespace(page_no=page, charspan=(start, end), bbox=bbox)


def item(ref, text, locations, label="text"):
    return SimpleNamespace(self_ref=ref, text=text, label=label, prov=locations)


class NormalizationTests(unittest.TestCase):
    def test_cross_page_paragraph_does_not_leak_or_duplicate(self):
        # Deliberately invalid character offsets: vendor normalization can make them stale.
        paragraph = item("#/texts/1", "joined across pages", [location(1, 0, 100), location(2, 101, 200)])
        document = SimpleNamespace(pages={1: None, 2: None}, iterate_items=lambda: iter([(paragraph, 0)]))
        first, second = MagicMock(height=100, width=100), MagicMock(height=100, width=100)
        first.crop.return_value.extract_text.return_value = "only first page"
        second.crop.return_value.extract_text.return_value = "only second page"
        with patch("pdfplumber.open") as opened:
            opened.return_value.__enter__.return_value.pages = [first, second]
            pages, blocks = normalize(document, "unused.pdf")
        self.assertEqual("only first page", pages[0]["text"])
        self.assertEqual("only second page", pages[1]["text"])
        self.assertEqual([1, 2], [b["pdf_page"] for b in blocks])
        first.crop.assert_called_once_with((10, 10, 90, 90))

    def test_two_regions_on_same_page_are_not_repeated(self):
        paragraph = item("#/texts/1", "left right", [location(1, 0, 4), location(1, 5, 10)])
        document = SimpleNamespace(pages={1: None}, iterate_items=lambda: iter([(paragraph, 0)]))
        with patch("pdfplumber.open"):
            pages, blocks = normalize(document, "unused.pdf")
        self.assertEqual("left\n\nright", pages[0]["text"])
        self.assertEqual(["left", "right"], [b["text"] for b in blocks])

    def test_missing_formula_is_explicit_not_invented(self):
        formula = item("#/texts/1", "", [location(1, 0, 0)], label="formula")
        document = SimpleNamespace(pages={1: None}, iterate_items=lambda: iter([(formula, 0)]))
        with patch("pdfplumber.open"):
            pages, blocks = normalize(document, "unused.pdf")
        self.assertIn("text unavailable", pages[0]["text"])
        self.assertEqual("", blocks[0]["text"])
        self.assertIsNotNone(pages[0]["warning"])
