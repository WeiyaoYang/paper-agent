"""Initialize a fresh checkout without copying or overwriting personal data."""
from pathlib import Path
from paper_agent.paths import project_root

ROOT = project_root()
RESULTS = ("1profile", "2knowledgeframework", "3learningnotes", "4papers", "5papercontents",
           "6readingrecords", "7qarecords", "8discussionrecords", "9knowledgenotes", "10knowledgepoints")


def initialize_data(data=None):
    data = Path(data) if data else ROOT / "data"
    for folder in RESULTS:
        (data / "results" / folder).mkdir(parents=True, exist_ok=True)
    for folder in ("papers", "artifacts", "runs", "logs"):
        (data / folder).mkdir(parents=True, exist_ok=True)
    for source, destination in (("profile.json", "results/1profile/current.json"),
                                ("knowledge.txt", "results/2knowledgeframework/knowledge.txt")):
        target = data / destination
        if not target.exists():
            # Exclusive creation protects existing core data, including concurrent initialization.
            try:
                with target.open("xb") as stream:
                    stream.write((ROOT / "templates" / source).read_bytes())
            except FileExistsError:
                pass
    return data.resolve()
