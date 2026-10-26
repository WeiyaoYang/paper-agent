"""Validate and persist behavior records; models never assign official IDs."""

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker

from paper_agent.storage.json_files import write_json
from paper_agent.paths import project_root

ROOT = project_root()
KINDS = {"verification": ("verification-record", "7qarecords", "verify"),
         "reading": ("reading-record", "6readingrecords", "read"),
         "qa": ("qa-record", "7qarecords", "qa"),
         "discussion": ("discussion-record", "8discussionrecords", "discussion")}


def schema(name):
    return json.loads((ROOT / "schemas" / (name + ".schema.json")).read_text(encoding="utf-8"))


def normalize(value):
    return " ".join(value.split()).casefold()


def check_sources(content, state, library):
    """Check exact references and excerpts, not the truth of a paraphrase."""
    if library.get(state["paper_id"])["active_run_id"] != state["parse_run_id"]:
        raise ValueError("The paper version changed.")
    if not library.check(state["paper_id"])["ready"]:
        raise ValueError("The paper material is no longer ready.")
    for source in content.get("sources", []):
        if not normalize(source["quote"]):
            raise ValueError("Source quotes cannot be blank.")
        if source["paper_id"] != state["paper_id"] or source["paper_content_id"] != state["parse_run_id"]:
            raise ValueError("Source must belong to the selected paper and version.")
        page = source["pdf_page"]
        if page not in state["read_pages"]:
            raise ValueError("Read the cited page before submitting a source.")
        material = library.read(state["paper_id"], page, page)
        if source["block_id"] is None:
            texts = [p["text"] for p in material["pages"]]
        else:
            texts = [b["text"] for b in material["blocks"] if b["id"] == source["block_id"]]
        if not any(normalize(source["quote"]) in normalize(text) for text in texts):
            raise ValueError("Source quote was not found at the cited location.")


def find_concepts(data, query, limit=20):
    records = []
    for path in (Path(data) / "results/10knowledgepoints").glob("*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        content = record["content"]
        if normalize(query) in normalize(" ".join([content["name"], *content["aliases"]])):
            records.append(record)
    return records if limit is None else records[:limit]


class RecordStore:
    def __init__(self, output, data, library):
        self.output, self.data, self.library = Path(output), Path(data), library

    def envelope(self, state, content, prefix):
        record = {"schema_version": 1, "id": prefix + "_" + uuid4().hex,
                "run_id": state["run_id"], "paper_id": state["paper_id"],
                "paper_content_id": state["parse_run_id"],
                "created_at": datetime.now(timezone.utc).isoformat(), "content": content}
        if state.get("plan_id"):
            record["plan_id"] = state["plan_id"]
        return record

    def validate_candidate(self, state, candidate):
        if state["kind"] in KINDS:
            name = KINDS[state["kind"]][0]
            Draft202012Validator(schema(name)["properties"]["content"]).validate(candidate)
            check_sources(candidate, state, self.library)
            if state["kind"] == "verification":
                self.validate_verification(state, candidate)
        else:
            Draft202012Validator(schema("knowledge-recording")).validate(candidate)
            check_sources(candidate["note"], state, self.library)

    def validate_verification(self, state, candidate):
        if candidate["plan_id"] != state["plan_id"] or candidate["goal"] != state["learning_goal"]:
            raise ValueError("Verification must reference the supplied plan and goal exactly.")
        questions = state.get("verification_questions", [])
        if not questions or any(not q.get("user_answer", "").strip() for q in questions):
            raise ValueError("Ask questions and wait for actual answers before assessment.")
        ids = [q["id"] for q in questions]
        assessed = [e["question_id"] for e in candidate["evaluations"]]
        if len(assessed) != len(set(assessed)) or set(assessed) != set(ids):
            raise ValueError("Assess every actual question exactly once.")
        if candidate["assessment"] == "passed" and any(e["assessment"] != "correct" for e in candidate["evaluations"]):
            raise ValueError("Cannot pass with partial, incorrect, or insufficient answers.")

    def save(self, state, candidate):
        self.validate_candidate(state, candidate)
        pending = []
        if state["kind"] in KINDS:
            name, folder, prefix = KINDS[state["kind"]]
            record = self.envelope(state, candidate, prefix)
            record["messages"] = state["messages"]
            if state["kind"] == "verification":
                record["verification_questions"] = state["verification_questions"]
            pending.append((name, folder, record))
        else:
            concept_ids, labels = [], set()
            for concept in candidate["concepts"]:
                key = normalize(concept["name"])
                if key in labels:
                    raise ValueError("Duplicate concept names in candidate.")
                labels.add(key)
                matches = [rec for rec in find_concepts(self.data, concept["name"], limit=None)
                           if key in {normalize(v) for v in [rec["content"]["name"], *rec["content"]["aliases"]]}]
                if len(matches) > 1:
                    raise ValueError("Ambiguous existing concept; clarify before recording.")
                if matches:
                    concept_ids.append(matches[0]["id"])
                    continue
                content = {**concept, "related_ids": [], "verification_status": "unverified"}
                record = self.envelope(state, content, "concept")
                pending.append(("knowledge-point", "10knowledgepoints", record))
                concept_ids.append(record["id"])
            content = {**candidate["note"], "concept_ids": list(dict.fromkeys(concept_ids)),
                       "author": "agent", "verification_status": "unverified"}
            pending.append(("knowledge-note", "9knowledgenotes", self.envelope(state, content, "note")))
        for name, _, record in pending:
            Draft202012Validator(schema(name), format_checker=FormatChecker()).validate(record)
        written = []
        try:
            for _, folder, record in pending:
                path = self.output / "results" / folder / (record["id"] + ".json")
                write_json(path, record)
                written.append(path)
        except OSError:
            # Roll back this batch on ordinary write failures, never remove existing records.
            for path in written:
                path.unlink(missing_ok=True)
            raise
        return [str(path.resolve()) for path in written]
