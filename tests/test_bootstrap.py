import tempfile
import unittest
from pathlib import Path

from paper_agent.bootstrap import initialize_data, RESULTS
from paper_agent.memory.profile import load_profile


class BootstrapTests(unittest.TestCase):
    def test_fresh_install_creates_ten_classes_and_unknown_profile(self):
        with tempfile.TemporaryDirectory() as folder:
            data = initialize_data(Path(folder) / "new user data")
            self.assertEqual(set(RESULTS), {p.name for p in (data / "results").iterdir()})
            self.assertEqual([], load_profile(data / "results/1profile/current.json")["knowledge_mastery"])
            self.assertEqual([], list((data / "papers").iterdir()))

    def test_initialization_never_overwrites_existing_core_information(self):
        with tempfile.TemporaryDirectory() as folder:
            data = initialize_data(folder)
            path = data / "results/1profile/current.json"
            path.write_text("personal data retained", encoding="utf-8")
            initialize_data(folder)
            self.assertEqual("personal data retained", path.read_text(encoding="utf-8"))
