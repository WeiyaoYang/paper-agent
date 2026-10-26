from fixture_data import DATA
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from paper_agent.agent.behavior import BehaviorRunner
from paper_agent.agent.planning import ROOT, PlanningError
from paper_agent.agent.review import LearningReviewer
from paper_agent.storage.json_files import write_json


def call(name, args):
    return {"status": "completed", "output": [{"type": "function_call", "call_id": "call_test",
            "name": name, "arguments": json.dumps(args)}]}


class LearningReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        for folder in ("1profile", "2knowledgeframework", "4papers", "5papercontents"):
            shutil.copytree(DATA / "results" / folder, self.data / "results" / folder)
        self.paper = json.loads(next((self.data / "results/4papers").glob("*.json")).read_text(encoding="utf-8"))
        self.plan_id = "planning_" + "b" * 32
        self.plan = {"part": "planning", "goal": "理解原始目标：动作输入输出", "materials": [
            {"paper_id": self.paper["id"], "paper_content_id": self.paper["active_run_id"]}],
            "plan": [{"behavior": "reading", "description": "理解方法"}, {"behavior": "verification", "description": "验证输入输出"}]}
        write_json(self.data / "results/3learningnotes" / (self.plan_id + ".json"), self.plan)

    def verification(self, plan_id, passed):
        runner = BehaviorRunner(self.data, generator=lambda *a, **kw: call("ask_verification_questions", {
            "questions": [{"question": "输入输出是什么？", "goal": self.plan["goal"]}]}))
        result = runner.start(self.paper["id"], "验证本轮理解", "verification", plan_id)
        candidate = {"plan_id": plan_id, "goal": self.plan["goal"],
                     "assessment": "passed" if passed else "needs_more_learning",
                     "evaluations": [{"question_id": "q1", "assessment": "correct" if passed else "partial",
                                      "reference_answer": "图像语言输入、连续动作输出", "feedback": "依据真实测试回答判断"}],
                     "summary": "本轮判断", "sources": [], "unresolved_questions": [] if passed else ["动作输出理解不足"]}
        runner.generator = lambda *a, **kw: call("propose_record", candidate)
        result = runner.resume(result["run_id"], "完整回答" if passed else "只知道图像输入")
        return runner, runner.finish(result["run_id"])

    def model(self, reason="q1 显示动作输出理解仍需补充。"):
        calls = []
        def generate(prompt, instructions, **kwargs):
            calls.append(kwargs)
            if "json_schema" in kwargs:
                return {"status": "completed", "text": json.dumps({"reason": reason, "question_ids": ["q1"]})}
            self.assertIn("previous_learning_result", prompt[0]["content"])
            return call("submit_plan", self.plan)
        return generate, calls

    def test_failed_result_replans_then_passed_round_can_end(self):
        runner, verified = self.verification(self.plan_id, False)
        model, calls = self.model()
        reviewer = LearningReviewer(self.data, generator=model)
        review = reviewer.start(verified["run_id"])
        self.assertEqual("replanned", review["status"])
        first = json.loads(Path(review["result_path"]).read_text(encoding="utf-8"))
        self.assertFalse(first["goal_achieved"])
        self.assertIn("q1", first["reason"])
        next_id = review["next_plan_id"]
        lineage = json.loads((self.data / "runs/planning" / next_id / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(self.plan_id, lineage["previous_plan_id"])
        self.assertEqual(self.plan_id, lineage["study_id"])
        self.assertEqual(2, lineage["revision"])
        self.assertEqual(self.plan, json.loads((self.data / "results/3learningnotes" / (self.plan_id + ".json")).read_text(encoding="utf-8")))
        self.assertEqual(review, reviewer.start(verified["run_id"]))
        self.assertEqual(2, len(calls))
        second_runner, second_verified = self.verification(next_id, True)
        second_review = reviewer.start(second_verified["run_id"])
        self.assertEqual("passed", second_review["status"])
        self.assertNotIn("next_plan_id", second_review)
        self.assertTrue(Path(review["result_path"]).exists())
        self.assertEqual("completed", second_runner.decide(second_verified["run_id"], "end")["learning_status"])
        self.assertEqual(3, len(calls))

    def test_changes_include_only_linked_records_and_actual_material(self):
        candidate = {"scope": "摘要", "summary": "输入输出", "key_points": [], "sources": [], "unresolved_questions": []}
        runner = BehaviorRunner(self.data, generator=lambda *a, **kw: call("propose_record", candidate))
        linked = runner.start(self.paper["id"], "阅读", "reading", self.plan_id)
        linked = runner.finish(linked["run_id"])
        unlinked = runner.start(self.paper["id"], "独立阅读", "reading")
        unlinked = runner.finish(unlinked["run_id"])
        _, verified = self.verification(self.plan_id, True)
        model, _ = self.model("q1 支持本次目标已达到。")
        review = LearningReviewer(self.data, generator=model).start(verified["run_id"])
        result = json.loads(Path(review["result_path"]).read_text(encoding="utf-8"))
        ids = {item["object_id"] for item in result["changes"]}
        linked_id = json.loads(Path(linked["record_paths"][0]).read_text(encoding="utf-8"))["id"]
        unlinked_id = json.loads(Path(unlinked["record_paths"][0]).read_text(encoding="utf-8"))["id"]
        self.assertIn(linked_id, ids)
        self.assertNotIn(unlinked_id, ids)
        self.assertIn(self.paper["active_run_id"], ids)
        self.assertTrue(all(item["action"] in ("used", "created") for item in result["changes"]))

    def test_result_required_before_end(self):
        runner, verified = self.verification(self.plan_id, True)
        with self.assertRaises(PlanningError) as caught:
            runner.decide(verified["run_id"], "end")
        self.assertEqual("review_required", caught.exception.code)

    def test_nonexistent_question_reason_is_rejected_and_not_retried(self):
        _, verified = self.verification(self.plan_id, False)
        calls = []
        def model(*a, **kw):
            calls.append(1)
            return {"status": "completed", "text": json.dumps({"reason": "编造题号", "question_ids": ["q999"]})}
        reviewer = LearningReviewer(self.data, generator=model)
        with self.assertRaises(PlanningError):
            reviewer.start(verified["run_id"])
        repeated = reviewer.start(verified["run_id"])
        self.assertEqual("review_failed", repeated["status"])
        self.assertEqual(1, len(calls))
        self.assertFalse(list((self.data / "results/3learningnotes").glob("*.result.json")))

    def test_replan_failure_preserves_result_and_does_not_fake_next_plan(self):
        _, verified = self.verification(self.plan_id, False)
        def model(*a, **kw):
            if "json_schema" in kw:
                return {"status": "completed", "text": json.dumps({"reason": "q1 仍有缺口", "question_ids": ["q1"]})}
            raise RuntimeError("simulated connection failure")
        review = LearningReviewer(self.data, generator=model).start(verified["run_id"])
        self.assertEqual("replan_failed", review["status"])
        self.assertTrue(Path(review["result_path"]).exists())
        self.assertFalse((self.data / "results/3learningnotes" / (review["next_plan_id"] + ".json")).exists())
