from fixture_data import DATA
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paper_agent.agent.planning import Planner, PlanningError, ROOT


def response(name, args):
    return {"status": "completed", "output": [
        {"type": "reasoning", "id": "reasoning-test", "encrypted_content": "opaque", "summary": []},
        {"type": "function_call", "name": name, "arguments": json.dumps(args), "call_id": "call-test"}]}


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        self.paper = json.loads(next((DATA / "results/4papers").glob("*.json")).read_text(encoding="utf-8"))

    def plan(self):
        return {"part": "planning", "goal": "理解动作生成", "materials": [
            {"paper_id": self.paper["id"], "paper_content_id": self.paper["active_run_id"]}],
            "plan": [{"behavior": "reading", "description": "阅读方法，理解动作输入输出。"}, {"behavior": "verification", "description": "结束前验证理解。"}]}

    def test_read_then_submit_keeps_instructions_and_saves_only_plan(self):
        replies = iter([response("read_paper_pages", {"start": 2, "end": 2}), response("submit_plan", self.plan())])
        requests = []
        def model(history, instructions, **kwargs):
            requests.append((json.loads(json.dumps(history)), instructions, kwargs))
            return next(replies)
        result = Planner(data=DATA, generator=model, output_root=self.output).start(self.paper["id"], "理解动作生成")
        self.assertEqual("planned", result["status"])
        self.assertEqual(self.plan(), json.loads(Path(result["plan_path"]).read_text(encoding="utf-8")))
        self.assertEqual(requests[0][1], requests[1][1])
        self.assertIn("论文材料准备", requests[0][1])
        self.assertTrue(any(x.get("type") == "reasoning" for x in requests[1][0]))
        self.assertTrue(any(x.get("type") == "function_call_output" for x in requests[1][0]))

    def test_clarification_pauses_and_resumes_with_real_reply(self):
        planner = Planner(data=DATA, generator=lambda *a, **kw: response("ask_user", {"question": "需要公式推导吗？"}), output_root=self.output)
        result = planner.start(self.paper["id"], "理解动作生成")
        self.assertEqual("awaiting_user", result["status"])
        self.assertFalse((self.output / "results").exists())
        def model(history, *a, **kw):
            self.assertEqual({"user_reply": "先理解直觉"}, json.loads(history[-1]["output"]))
            return response("submit_plan", self.plan())
        resumed = Planner(data=DATA, generator=model, output_root=self.output).resume(result["run_id"], "先理解直觉")
        self.assertEqual("planned", resumed["status"])
        with self.assertRaises(PlanningError):
            planner.resume(result["run_id"], "再次回答")

    def test_bad_references_and_disabled_behavior_never_saved(self):
        for bad in ("reference", "behavior"):
            plan = self.plan()
            if bad == "reference":
                plan["materials"][0]["paper_content_id"] = "fake"
            else:
                plan["plan"][0]["behavior"] = "profile-change"
            with patch("paper_agent.agent.planning.MAX_CALLS", 2):
                result = Planner(data=DATA, generator=lambda *a, **kw: response("submit_plan", plan), output_root=self.output).start(self.paper["id"], "目标")
            self.assertEqual("budget_exhausted", result["status"])
            self.assertFalse((self.output / "results").exists())

    def test_incomplete_and_error_do_not_retry_or_save(self):
        result = Planner(data=DATA, generator=lambda *a, **kw: {"status": "incomplete"}, output_root=self.output).start(self.paper["id"], "目标")
        self.assertEqual("incomplete", result["status"])
        def failing(*a, **kw):
            raise RuntimeError("not a user-facing exception")
        with self.assertRaises(PlanningError):
            Planner(data=DATA, generator=failing, output_root=self.output).start(self.paper["id"], "目标")
        self.assertFalse((self.output / "results").exists())
