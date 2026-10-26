"""Read the confirmed initial profile without inference or database side effects."""

import json
from pathlib import Path
from paper_agent.paths import project_root


DEFAULT_PROFILE = project_root() / "data" / "results" / "1profile" / "current.json"


class ProfileError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def load_profile(path=None, fields=None):
    source = Path(path) if path is not None else DEFAULT_PROFILE
    try:
        profile = json.loads(source.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ProfileError("profile_not_found", f"Profile file not found: {source}") from exc
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ProfileError("invalid_profile", f"Profile is not valid UTF-8 JSON: {exc}") from exc
    required_types = {
        "profile_id": str, "revision": int, "sources": dict,
        "background": dict, "knowledge_background": dict,
        "learning_preferences": dict, "knowledge_mastery": list,
    }
    if not isinstance(profile, dict) or profile.get("schema_version") != 1:
        raise ProfileError("invalid_profile", "Expected a profile object with schema_version 1.")
    for name, expected in required_types.items():
        if type(profile.get(name)) is not expected:
            raise ProfileError("invalid_profile", f"Invalid or missing field: {name}")
    if not profile["profile_id"].strip() or profile["revision"] < 1:
        raise ProfileError("invalid_profile", "Profile ID must be nonempty and revision must be positive.")
    if fields is None:
        return profile
    missing = set(fields) - profile.keys()
    if missing:
        raise ProfileError("unknown_profile_field", "Unknown fields: " + ", ".join(sorted(missing)))
    selected = {name: profile[name] for name in fields}
    # A partial read still identifies its revision and supplies provenance definitions.
    for name in ("profile_id", "revision", "information_type", "sources"):
        if name in profile:
            selected[name] = profile[name]
    return selected
