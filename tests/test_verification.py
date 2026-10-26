from fixture_data import DATA
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paper_agent.agent.behavior import BehaviorRunner
from paper_agent.agent.planning import ROOT, PlanningError
from paper_agent.storage.behavior_records import RecordStore
from paper_agent.storage.json_files import write_json


def response(name, args):
    return {"status": "completed", "output": [{"type": "function_call", "name": name,
            "arguments": json.dumps(args), "call_id": "test-call"}]}


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paper = json.loads(next((DATA / "results/4papers").glob("*.json")).read_text(encoding="utf-8"))
        self.plan_id = "planning_" + "a" * 32
        self.plan = {"part": "planning", "goal": "理解动作输入与输出", "materials": [
            {"paper_id": self.paper["id"], "paper_content_id": self.paper["active_run_id"]}],
            "plan": [{"behavior": "verification", "description": "回答理解问题"}]}
        self.plan_path = self.root / "results/3learningnotes" / (self.plan_id + ".json")
        write_json(self.plan_path, self.plan)

    def runner(self, model):
        runner = BehaviorRunner(data=DATA, generator=model, output_root=self.root)
        # Read the fixture plan from isolated storage while reusing real material read methods.
        runner.data = self.root
        return runner

    def candidate(self, assessment="passed"):
        return {"plan_id": self.plan_id, "goal": self.plan["goal"], "assessment": assessment,
                "evaluations": [{"question_id": "q1", "assessment": "correct" if assessment == "passed" else "partial",
                                 "reference_answer": "图像和语言进入模型，输出连续动作。", "feedback": "本次回答的判断依据。"}],
                "summary": "本次理解验证", "sources": [], "unresolved_questions": []}

    def start(self, runner):
        # Only fixture core inputs differ; all paper reads still use the existing library.
        (self.root / "results/1profile").mkdir(parents=True, exist_ok=True)
        (self.root / "results/2knowledgeframework").mkdir(parents=True, exist_ok=True)
        (self.root / "results/1profile/current.json").write_bytes((DATA / "results/1profile/current.json").read_bytes())
        (self.root / "results/2knowledgeframework/knowledge.txt").write_text("AI", encoding="utf-8")
        return runner.start(self.paper["id"], "请验证理解", "verification", self.plan_id)

    def ask(self):
        return response("ask_verification_questions", {"questions": [{"question": "输入和输出是什么？", "goal": self.plan["goal"]}]})

    def save_result_fixture(self, runner, result):
        state = runner.load(result["run_id"])
        record = json.loads(Path(state["record_paths"][0]).read_text(encoding="utf-8"))
        path = self.root / "results/3learningnotes" / (state["plan_id"] + "." + result["run_id"] + ".result.json")
        value = {"part": "result", "plan_id": state["plan_id"], "goal_achieved": record["content"]["assessment"] == "passed",
                 "reason": "测试结果", "question_ids": ["q1"], "verification_record_id": record["id"],
                 "changes": [{"object_type": "paper", "object_id": state["paper_id"], "action": "used", "description": "论文"},
                             {"object_type": "paper_content", "object_id": state["parse_run_id"], "action": "used", "description": "内容"}]}
        write_json(path, value)
        write_json(self.root / "runs/reviews" / result["run_id"] / "state.json", {"result_path": str(path)})

    def test_answer_evaluate_finish_and_confirm_end(self):
        runner = self.runner(lambda *a, **kw: self.ask())
        result = self.start(runner)
        self.assertEqual("awaiting_user", result["status"])
        self.assertEqual("", result["verification_questions"][0]["user_answer"])
        runner.generator = lambda *a, **kw: response("propose_record", self.candidate())
        result = runner.resume(result["run_id"], "图像和语言输入，输出连续动作。")
        self.assertEqual("awaiting_finish", result["status"])
        saved = runner.finish(result["run_id"])
        self.assertEqual("awaiting_learning_decision", saved["status"])
        self.assertIn("是否结束", saved["learning_end_question"])
        self.assertEqual(saved, runner.finish(result["run_id"]))
        self.save_result_fixture(runner, saved)
        record = json.loads(Path(saved["record_paths"][0]).read_text(encoding="utf-8"))
        self.assertEqual("图像和语言输入，输出连续动作。", record["verification_questions"][0]["user_answer"])
        with patch.object(runner, "generator", side_effect=AssertionError("decision must be local")):
            ended = runner.decide(result["run_id"], "end")
        self.assertEqual("completed", ended["learning_status"])
        self.assertEqual(ended, runner.decide(result["run_id"], "end"))

    def test_no_answers_no_assessment_and_no_end_before_record(self):
        runner = self.runner(lambda *a, **kw: self.ask())
        result = self.start(runner)
        state = runner.load(result["run_id"])
        with self.assertRaises(ValueError):
            RecordStore(self.root, self.root, runner.library).validate_candidate(state, self.candidate())
        with self.assertRaises(PlanningError):
            runner.decide(result["run_id"], "end")

    def test_partial_answers_cannot_pass_and_end_is_early(self):
        runner = self.runner(lambda *a, **kw: self.ask())
        result = self.start(runner)
        runner.generator = lambda *a, **kw: response("propose_record", self.candidate("needs_more_learning"))
        result = runner.resume(result["run_id"], "我只知道输入是图像。")
        state = runner.load(result["run_id"])
        bad = self.candidate("needs_more_learning")
        bad["assessment"] = "passed"
        with self.assertRaises(ValueError):
            RecordStore(self.root, self.root, runner.library).validate_candidate(state, bad)
        saved = runner.finish(result["run_id"])
        self.save_result_fixture(runner, saved)
        self.assertEqual("ended_early", runner.decide(result["run_id"], "end")["learning_status"])

    def test_changed_plan_prevents_end_and_continue_is_not_completed(self):
        for choice in ("end", "continue"):
            runner = self.runner(lambda *a, **kw: self.ask())
            result = self.start(runner)
            runner.generator = lambda *a, **kw: response("propose_record", self.candidate())
            result = runner.resume(result["run_id"], "完整测试回答")
            saved = runner.finish(result["run_id"])
            self.save_result_fixture(runner, saved)
            if choice == "end":
                changed = {**self.plan, "goal": "修改后的目标"}
                write_json(self.plan_path, changed)
                with self.assertRaises(PlanningError):
                    runner.decide(result["run_id"], choice)
                write_json(self.plan_path, self.plan)
            else:
                self.assertEqual("learning", runner.decide(result["run_id"], choice)["learning_status"])

    def test_verification_requires_saved_plan(self):
        runner = BehaviorRunner(output_root=self.root)
        with self.assertRaises(PlanningError):
            runner.start(self.paper["id"], "验证", "verification")
