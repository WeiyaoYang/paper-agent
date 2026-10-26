from fixture_data import DATA
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator, ValidationError

from paper_agent.agent.behavior import BehaviorRunner
from paper_agent.agent.planning import ROOT, PlanningError
from paper_agent.storage.behavior_records import RecordStore, schema


def response(name, args):
    return {"status": "completed", "output": [{"type": "function_call", "name": name,
            "arguments": json.dumps(args), "call_id": "call_test"}]}


class BehaviorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        self.paper = json.loads(next((DATA / "results/4papers").glob("*.json")).read_text(encoding="utf-8"))

    def candidate(self, kind):
        common = {"sources": [], "unresolved_questions": []}
        return {
            "reading": {"scope": "摘要", "summary": "解释了模型输入输出。", "key_points": ["连续动作"], **common},
            "qa": {"summary": "进行了真实问答", "feedback": "部分理解，仍需区分两类输入。", **common},
            "discussion": {"viewpoint": "基础模型是否能泛化？", "conclusions": ["材料证据有限。"], "disagreements": [], **common},
            "knowledge-recording": {"concepts": [{"name": "flow matching", "aliases": ["流匹配"], "classification": ["生成模型"]}],
                                    "note": {"title": "流匹配直觉", "content": "一种连续生成方法的待验证解释。", **common}}
        }[kind]

    def propose(self, kind):
        runner = BehaviorRunner(data=DATA, generator=lambda *a, **kw: response("propose_record", self.candidate(kind)), output_root=self.output)
        return runner, runner.start(self.paper["id"], "请围绕这篇论文帮助我学习", kind)

    def test_four_behaviors_preview_then_commit_without_another_model_call(self):
        for kind in ("reading", "qa", "discussion", "knowledge-recording"):
            runner, result = self.propose(kind)
            self.assertEqual("awaiting_finish", result["status"])
            self.assertFalse(runner.show(result["run_id"]).get("record_paths"))
            with patch.object(runner, "generator", side_effect=AssertionError("finish must be local")):
                saved = runner.finish(result["run_id"])
            self.assertEqual("recorded", saved["status"])
            self.assertEqual(saved, runner.finish(result["run_id"]))
            self.assertEqual(2 if kind == "knowledge-recording" else 1, len(saved["record_paths"]))
            for path in saved["record_paths"]:
                record = json.loads(Path(path).read_text(encoding="utf-8"))
                if kind != "knowledge-recording":
                    self.assertEqual("user", record["messages"][0]["role"])
                else:
                    self.assertEqual("unverified", record["content"]["verification_status"])

    def test_actual_dialogue_survives_restart_and_candidate_can_be_revised(self):
        runner = BehaviorRunner(data=DATA, generator=lambda *a, **kw: response("talk_to_user", {"message": "请用自己的话解释动作生成。", "question": "输入是什么？"}), output_root=self.output)
        result = runner.start(self.paper["id"], "检验我的理解", "qa")
        self.assertEqual("awaiting_user", result["status"])
        self.assertEqual(result, runner.pause(result["run_id"]))
        runner = BehaviorRunner(data=DATA, generator=lambda *a, **kw: response("propose_record", self.candidate("qa")), output_root=self.output)
        result = runner.resume(result["run_id"], "我认为输入是图像和语言。")
        self.assertEqual("awaiting_finish", result["status"])
        self.assertEqual("我认为输入是图像和语言。", runner.show(result["run_id"])["messages"][-1]["text"])
        result = runner.resume(result["run_id"], "先保留我不确定的部分。")
        saved = runner.finish(result["run_id"])
        record = json.loads(Path(saved["record_paths"][0]).read_text(encoding="utf-8"))
        self.assertEqual(4, len(record["messages"]))

    def test_false_citations_and_disabled_behavior_cannot_write_records(self):
        runner = BehaviorRunner(data=DATA, generator=lambda *a, **kw: response("propose_record", self.candidate("reading")), output_root=self.output)
        result = runner.start(self.paper["id"], "阅读摘要", "reading")
        state = runner.load(result["run_id"])
        bad = self.candidate("reading")
        bad["sources"] = [{"paper_id": self.paper["id"], "paper_content_id": self.paper["active_run_id"],
                           "pdf_page": 1, "block_id": None, "quote": "invented nonexistent quotation"}]
        with self.assertRaises(ValueError):
            RecordStore(self.output, DATA, runner.library).save(state, bad)
        with self.assertRaises(PlanningError):
            runner.start(self.paper["id"], "修改画像", "profile-change")
        self.assertFalse((self.output / "results").exists())

    def test_exact_material_citation_and_concept_reuse(self):
        runner, result = self.propose("knowledge-recording")
        state = runner.load(result["run_id"])
        store = RecordStore(self.output, self.output, runner.library)
        candidate = self.candidate("knowledge-recording")
        text = runner.library.read(self.paper["id"], 1, 1)["pages"][0]["text"][:50]
        candidate["note"]["sources"] = [{"paper_id": self.paper["id"], "paper_content_id": self.paper["active_run_id"],
                                          "pdf_page": 1, "block_id": None, "quote": text}]
        first = store.save(state, candidate)
        second = store.save(state, candidate)
        self.assertEqual(2, len(first))
        self.assertEqual(1, len(second))
        self.assertEqual(1, len(list((self.output / "results/10knowledgepoints").glob("*.json"))))

    def test_knowledge_batch_write_failure_rolls_back_new_files(self):
        runner, result = self.propose("knowledge-recording")
        state = runner.load(result["run_id"])
        from paper_agent.storage.json_files import write_json
        count = []
        def failing(path, value):
            count.append(path)
            if len(count) == 2:
                raise OSError("simulated disk full")
            write_json(path, value)
        with patch("paper_agent.storage.behavior_records.write_json", side_effect=failing):
            with self.assertRaises(OSError):
                RecordStore(self.output, DATA, runner.library).save(state, self.candidate("knowledge-recording"))
        self.assertFalse(list((self.output / "results").rglob("*.json")))

    def test_full_record_reader_is_limited_to_supplied_record_ids(self):
        original, result = self.propose("reading")
        saved = original.finish(result["run_id"])
        record = json.loads(Path(saved["record_paths"][0]).read_text(encoding="utf-8"))
        replies = iter([response("read_learning_record", {"record_id": record["id"]}),
                        response("propose_record", self.candidate("reading"))])
        histories = []
        def model(history, *a, **kw):
            histories.append(json.loads(json.dumps(history)))
            return next(replies)
        runner = BehaviorRunner(data=DATA, generator=model, output_root=self.output)
        outcome = runner.start(self.paper["id"], "查看本次已有记录", "reading", learning_context={"record_paths": {record["id"]: saved["record_paths"][0]}})
        self.assertEqual("awaiting_finish", outcome["status"])
        returned = json.loads(histories[1][-1]["output"])
        self.assertEqual(record["id"], returned["id"])
        with self.assertRaises(ValueError):
            runner.extra_tool(runner.load(outcome["run_id"]), {"name": "read_learning_record"}, {"record_id": "../../config/.env.local"})

    def test_all_new_schemas_are_valid_and_reject_unknown_fields(self):
        for name in ("reading-record", "qa-record", "discussion-record", "knowledge-note", "knowledge-point", "knowledge-recording"):
            Draft202012Validator.check_schema(schema(name))
        content = self.candidate("reading")
        content["made_up_field"] = True
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema("reading-record")["properties"]["content"]).validate(content)
