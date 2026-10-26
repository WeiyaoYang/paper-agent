from fixture_data import DATA
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paper_agent.agent.planning import ROOT, PlanningError
from paper_agent.agent.session import LearningSession
from paper_agent.app.chat import read_turn, interact, chat_lock, run_chat


def call(name, args):
    return {"status": "completed", "output": [{"type": "function_call", "call_id": "test_call",
            "name": name, "arguments": json.dumps(args)}]}


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        for folder in ("1profile", "2knowledgeframework", "4papers", "5papercontents"):
            shutil.copytree(DATA / "results" / folder, self.data / "results" / folder)
        self.paper = json.loads(next((self.data / "results/4papers").glob("*.json")).read_text(encoding="utf-8"))
        self.calls = []
        self.selections = 0

    def model(self, prompt, instructions, **kwargs):
        self.calls.append(kwargs)
        if "tools" not in kwargs:
            context = json.loads(prompt)
            if "question_ids" in kwargs["json_schema"]["properties"]:
                return {"status": "completed", "text": json.dumps({"reason": "q1 的真实回复支持本轮判断。", "question_ids": ["q1"]})}
            kind = ("reading", "verification", "qa", "verification")[min(self.selections, 3)]
            self.selections += 1
            return {"status": "completed", "text": json.dumps({"behavior": kind, "request": "围绕本轮目标开展" + kind, "reason": "根据实际进展选择。"})}
        names = {tool["name"] for tool in kwargs["tools"]}
        context = json.loads(prompt[0]["content"])
        if "submit_plan" in names:
            return call("submit_plan", {"part": "planning", "goal": context["user_request"],
                        "materials": [{"paper_id": self.paper["id"], "paper_content_id": self.paper["active_run_id"]}],
                        "plan": [{"behavior": "reading", "description": "理解原目标"}, {"behavior": "verification", "description": "检验理解"}]})
        kind = context["kind"]
        outputs = [x for x in prompt if x.get("type") == "function_call_output"]
        if not outputs:
            if kind == "verification":
                return call("ask_verification_questions", {"questions": [{"question": "输入输出是什么？", "goal": context["learning_plan"]["goal"]}]})
            return call("talk_to_user", {"message": "结合论文解释输入输出。", "question": "你如何理解？"})
        if kind == "verification":
            answer = json.loads(outputs[-1]["output"])["user_reply"]
            passed = "不会" not in answer
            return call("propose_record", {"plan_id": context["plan_id"], "goal": context["learning_plan"]["goal"],
                        "assessment": "passed" if passed else "needs_more_learning",
                        "evaluations": [{"question_id": "q1", "assessment": "correct" if passed else "insufficient_evidence",
                                         "reference_answer": "图像语言输入、连续动作输出", "feedback": "按实际回答评估"}],
                        "summary": "本轮验证", "sources": [], "unresolved_questions": []})
        if kind == "reading":
            return call("propose_record", {"scope": "方法", "summary": "理解输入输出", "key_points": [], "sources": [], "unresolved_questions": []})
        return call("propose_record", {"summary": "问答补缺", "feedback": "结合真实回复反馈", "sources": [], "unresolved_questions": []})

    def new(self, budget=40):
        session = LearningSession(self.data, generator=self.model)
        session.create(self.paper["id"], "理解动作输入输出", budget)
        return session

    def test_complete_learning_failed_review_replan_pause_and_pass(self):
        session = self.new()
        self.assertEqual("waiting_answer", session.state["status"])
        self.assertEqual("reading", session.state["selected"]["behavior"])
        session.reply("我的阅读理解")
        self.assertEqual("waiting_save", session.state["status"])
        session.reply("保存")
        self.assertEqual("verification", session.state["selected"]["behavior"])
        session.reply("我不会")
        session.reply("保存")
        self.assertEqual("qa", session.state["selected"]["behavior"])
        original_count = len(self.calls)
        original_session_id = session.state["session_id"]
        session.reply(":pause")
        session = LearningSession(self.data, generator=self.model)
        session.open(original_session_id)
        self.assertEqual(original_count, len(self.calls))
        session.reply("完整的补缺回答")
        session.reply("保存")
        session.reply("完整回答：图像语言输入，连续动作输出。")
        session.reply("保存")
        self.assertEqual("waiting_end", session.state["status"])
        before = len(self.calls)
        session.reply("结束")
        self.assertEqual("completed", session.state["status"])
        self.assertEqual(before, len(self.calls))
        results = list((self.data / "results/3learningnotes").glob("*.result.json"))
        self.assertEqual(2, len(results))
        self.assertEqual({True, False}, {json.loads(p.read_text(encoding="utf-8"))["goal_achieved"] for p in results})
        states = [json.loads(p.read_text(encoding="utf-8")) for p in (self.data / "runs/planning").glob("*/state.json")]
        self.assertEqual({1, 2}, {s["revision"] for s in states})
        self.assertEqual(1, len({s["study_id"] for s in states}))
        root_state = json.loads(next((self.data / "runs/learning").glob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual("completed", root_state["learning_status"])

    def test_user_end_request_cannot_skip_verification(self):
        session = self.new()
        session.reply(":end")
        self.assertEqual("verification", session.state["selected"]["behavior"])
        self.assertEqual("waiting_answer", session.state["status"])
        self.assertEqual(1, len(session.state["parked_runs"]))
        self.assertFalse((self.data / "runs/learning").exists())

    def test_user_can_override_behavior_without_losing_pending_dialogue(self):
        session = self.new()
        session.reply(":do qa 先帮我解释术语")
        self.assertEqual("qa", session.state["selected"]["behavior"])
        self.assertEqual(1, len(session.state["parked_runs"]))
        context = session.context()
        self.assertTrue(context["paused_dialogue"])

    def test_global_call_limit_and_interrupted_run_do_not_replay(self):
        session = self.new(2)
        self.assertEqual("blocked", session.state["status"])
        self.assertEqual(2, len(self.calls))
        reopened = LearningSession(self.data, generator=self.model)
        reopened.open(session.state["session_id"])
        self.assertEqual(2, len(self.calls))
        session = self.new()
        count = len(self.calls)
        session.state["in_flight"] = True
        session.save()
        reopened.open(session.state["session_id"])
        self.assertEqual("blocked", reopened.state["status"])
        self.assertEqual(count, len(self.calls))

    def test_multiline_input_and_eof_pause(self):
        lines = iter(["第一行", "第二行", "."])
        self.assertEqual("第一行\n第二行", read_turn(lambda _: next(lines)))
        session = self.new()
        output = []
        def eof(_):
            raise EOFError()
        interact(session, read=eof, emit=output.append)
        self.assertEqual("paused", session.state["status"])
        self.assertTrue(any("恢复命令" in message for message in output))

    def test_unknown_commands_are_local_and_early_exit_never_passes(self):
        session = self.new()
        before = len(self.calls)
        session.reply(":unknown")
        self.assertEqual(before, len(self.calls))
        session.reply(":stop")
        self.assertEqual("ended_early", session.state["status"])
        self.assertEqual(before, len(self.calls))
        learning = json.loads(next((self.data / "runs/learning").glob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual("ended_early", learning["learning_status"])

    def test_bad_selector_output_stops_without_replaying(self):
        real = self.model
        def bad(prompt, instructions, **kwargs):
            if "tools" not in kwargs and "behavior" in kwargs["json_schema"]["properties"]:
                return {"status": "completed", "text": json.dumps({"behavior": "profile-change", "request": "bad", "reason": "bad"})}
            return real(prompt, instructions, **kwargs)
        session = LearningSession(self.data, generator=bad)
        session.create(self.paper["id"], "学习目标")
        self.assertEqual("blocked", session.state["status"])
        count = session.state["model_calls"]
        session.open(session.state["session_id"])
        self.assertEqual(count, session.state["model_calls"])

    def test_terminal_frontend_runs_whole_session_without_copying_ids(self):
        answers = iter(["阅读后的理解", ".", "保存", "我不会", ".", "保存",
                        "补缺后的回答", ".", "保存", "完整回答", ".", "保存", "结束"])
        output = []
        def factory(data, notify):
            return LearningSession(data, generator=self.model, notify=notify)
        with patch("paper_agent.app.chat.LearningSession", side_effect=factory):
            state = run_chat(self.data, self.paper["id"], "理解动作输入输出", read=lambda _: next(answers), emit=output.append)
        self.assertEqual("completed", state["status"])
        self.assertTrue(any("本轮结果" in line for line in output))
        self.assertTrue(any("下一步" in line for line in output))

    def test_chat_lock_excludes_another_writer_and_releases(self):
        with chat_lock(self.data):
            with self.assertRaises(PlanningError):
                with chat_lock(self.data):
                    pass
        with chat_lock(self.data):
            pass
