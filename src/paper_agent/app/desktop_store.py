"""Desktop organization and display history, separate from formal learning records."""
import json
from pathlib import Path
from uuid import uuid4

from paper_agent.storage.json_files import write_json


class DesktopStore:
    def __init__(self, data):
        self.data = Path(data)
        self.path = self.data / "runs/desktop/workspace.json"
        self.value = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {"folders": [], "chats": {}}

    def save(self):
        write_json(self.path, self.value)

    def folder(self, title):
        item = {"id": uuid4().hex, "title": title}
        self.value["folders"].append(item)
        self.save()
        return item

    def chats(self):
        result = []
        for path in (self.data / "runs/chats").glob("chat_*/state.json"):
            state = json.loads(path.read_text(encoding="utf-8"))
            result.append(state)
        return sorted(result, key=lambda s: self.data.joinpath("runs/chats", s["session_id"], "state.json").stat().st_mtime, reverse=True)

    def meta(self, state):
        return self.value["chats"].setdefault(state["session_id"], {"title": state["goal"][:36], "folder": None})

    def history(self, state):
        meta = self.meta(state)
        if "messages" not in meta:
            # Legacy terminal sessions have no unified chronological transcript.
            meta["messages"] = [{"role": "user", "text": state["goal"]}]
            meta["messages"] += [{"role": "assistant", "text": e} for e in state["events"]]
            if state.get("prompt") and state["status"].startswith("waiting_"):
                meta["messages"].append({"role": "assistant", "text": state["prompt"]})
            meta["event_count"] = len(state["events"])
            meta["last_prompt"] = state.get("prompt")
        return meta["messages"]

    def collect(self, state):
        messages = self.history(state)
        meta = self.meta(state)
        messages.extend({"role": "assistant", "text": e} for e in state["events"][meta.get("event_count", 0):])
        meta["event_count"] = len(state["events"])
        prompt = state.get("prompt")
        if state["status"].startswith("waiting_") and prompt and prompt != meta.get("last_prompt"):
            messages.append({"role": "assistant", "text": prompt})
        meta["last_prompt"] = prompt
        self.save()
