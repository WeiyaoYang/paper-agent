from fixture_data import DATA
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from paper_agent.memory.profile import ProfileError, load_profile


DEFAULT_PROFILE = DATA / "results/1profile/current.json"


class ProfileTests(unittest.TestCase):
    def test_partial_read_preserves_unknown_mastery_and_source(self):
        before = DEFAULT_PROFILE.read_bytes()
        result = load_profile(DEFAULT_PROFILE, fields=["knowledge_mastery", "learning_preferences"])
        self.assertEqual([], result["knowledge_mastery"])
        self.assertIn("sources", result)
        self.assertNotIn("background", result)
        self.assertEqual(before, DEFAULT_PROFILE.read_bytes())

    def test_invalid_profile_and_unknown_field_fail_explicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text("not json", encoding="utf-8")
            with self.assertRaises(ProfileError) as error:
                load_profile(path)
            self.assertEqual("invalid_profile", error.exception.code)
        with self.assertRaises(ProfileError) as error:
            load_profile(DEFAULT_PROFILE, fields=["made_up_ability"])
        self.assertEqual("unknown_profile_field", error.exception.code)

    def test_profile_cli_does_not_create_material_store(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "unused-data"
            result = subprocess.run(
                [sys.executable, "-m", "paper_agent", "--data", str(database),
                 "profile", "--file", str(DEFAULT_PROFILE), "--fields", "knowledge_mastery"],
                capture_output=True, encoding="utf-8", check=True,
            )
            self.assertEqual([], json.loads(result.stdout)["result"]["knowledge_mastery"])
            self.assertFalse(database.exists())
