import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from paper_agent.paths import project_root


class PortablePathsTests(unittest.TestCase):
    def test_frozen_uses_executable_directory_not_internal_or_working_directory(self):
        with patch.object(sys, "frozen", True, create=True), patch.object(sys, "executable", str(Path("custom location") / "AgentWorkbench.exe")):
            self.assertEqual(Path("custom location").resolve(), project_root())

    def test_source_uses_checkout_root(self):
        with patch.object(sys, "frozen", False, create=True):
            self.assertTrue((project_root() / "pyproject.toml").is_file())
