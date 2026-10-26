"""Create a learning-result part from saved evidence, then replan on failure."""

import json
from pathlib import Path
from uuid import uuid4

from jsonschema import Draft202012Validator

from paper_agent.agent.behavior import BehaviorRunner
from paper_agent.agent.planning import Planner, PlanningError, ROOT, api_schema, object_schema
from paper_agent.models.client import generate_text
from paper_agent.storage.behavior_records import RecordStore, schema
from paper_agent.storage.json_files import write_json

REASON_SCHEMA = object_schema({"reason": {"type": "string", "minLength": 1},
                               "question_ids": {"type": "array", "minItems": 1,
                                                "items": {"type": "string", "minLength": 1}}})


class LearningReviewer:
    def __init__(self, data=None, *, generator=generate_text, output_root=None):
        self.data = Path(data) if data else ROOT / "data"
        self.output = Path(output_root) if output_root else self.data
        self.generator = generator

    def runner(self):
        return BehaviorRunner(self.data, generator=self.generator, output_root=self.output)

    def changes(self, state, verification):
        entries = {("paper", state["paper_id"]): {"object_type": "paper", "object_id": state["paper_id"],
                   "action": "used", "description": "本轮使用的论文登记。"},
                   ("paper_content", state["parse_run_id"]): {"object_type": "paper_content", "object_id": state["parse_run_id"],
                   "action": "used", "description": "本轮实际采用的论文内容版本。"}}
        folders = {"6readingrecords": "reading_record", "7qarecords": "qa_record",
                   "8discussionrecords": "discussion_record", "9knowledgenotes": "knowledge_note",
                   "10knowledgepoints": "knowledge_point"}
        used_concepts = set()
        for folder, kind in folders.items():
            paths = {p.resolve() for base in {self.data, self.output} for p in (base / "results" / folder).glob("*.json")}
            for path in sorted(paths):
                record = json.loads(path.read_text(encoding="utf-8"))
                if record.get("plan_id") != state["plan_id"] and record.get("id") != verification["id"]:
                    continue
                if record.get("paper_id") != state["paper_id"] or record.get("paper_content_id") != state["parse_run_id"]:
                    raise PlanningError("record_mismatch", "A linked record belongs to another material version.")
                entries[(kind, record["id"])] = {"object_type": kind, "object_id": record["id"],
                                                "action": "created", "description": "本轮实际创建的正式记录。"}
                if kind == "knowledge_note":
                    used_concepts.update(record["content"]["concept_ids"])
        for cid in sorted(used_concepts):
            if ("knowledge_point", cid) not in entries:
                if not any((base / "results/10knowledgepoints" / (cid + ".json")).exists() for base in {self.data, self.output}):
                    raise PlanningError("missing_concept", "A linked knowledge point does not exist.")
                entries[("knowledge_point", cid)] = {"object_type": "knowledge_point", "object_id": cid,
                                                      "action": "used", "description": "本轮笔记引用的已有知识点，未修改原记录。"}
        return list(entries.values())

    def start(self, verification_run_id):
        runner = self.runner()
        verification_state = runner.load(verification_run_id)
        if verification_state["kind"] != "verification" or verification_state["status"] not in ("awaiting_learning_decision", "recorded"):
            raise PlanningError("verification_required", "Save a verification record before reviewing learning.")
        runner.check_plan(verification_state)
        review_path = self.output / "runs/reviews" / verification_run_id / "state.json"
        if review_path.exists():
            previous = json.loads(review_path.read_text(encoding="utf-8"))
            if previous.get("next_plan_id") and previous["status"].startswith("replan_") and previous["status"] != "replan_failed":
                planner = Planner(self.data, generator=self.generator, output_root=self.output)
                path = planner.state_path(previous["next_plan_id"])
                if path.exists():
                    current = json.loads(path.read_text(encoding="utf-8"))
                    previous.update(status="replanned" if current["status"] == "planned" else "replan_" + current["status"], next_planning=planner.result(current))
                    write_json(review_path, previous)
            return previous  # Never replay a potentially billed request.
        verification = json.loads(Path(verification_state["record_paths"][0]).read_text(encoding="utf-8"))
        RecordStore(self.output, self.data, runner.library).validate_candidate(verification_state, verification["content"])
        plan_id = verification_state["plan_id"]
        plan = json.loads((self.data / "results/3learningnotes" / (plan_id + ".json")).read_text(encoding="utf-8"))
        changes = self.changes(verification_state, verification)
        lineage_path = self.data / "runs/planning" / plan_id / "state.json"
        lineage = json.loads(lineage_path.read_text(encoding="utf-8")) if lineage_path.exists() else {}
        review = {"verification_run_id": verification_run_id, "plan_id": plan_id,
                  "study_id": lineage.get("study_id", plan_id), "revision": lineage.get("revision", 1),
                  "status": "generating_reason"}
        write_json(review_path, review)
        inputs = {"plan": plan, "verification": verification, "actual_changes": changes}
        write_json(review_path.parent / "inputs.json", inputs)
        try:
            response = self.generator(json.dumps(inputs, ensure_ascii=False),
                                      (ROOT / "prompts/agent-policy.md").read_text(encoding="utf-8") + "\n\n" +
                                      (ROOT / "prompts/learning-review.md").read_text(encoding="utf-8") + "\n当前仅输出复盘 JSON，不调用行为、不执行后续学习。",
                                      config=ROOT / "config/planning.toml", json_schema=api_schema(REASON_SCHEMA),
                                      usage_path=self.output / "logs/model-usage.jsonl")
            write_json(review_path.parent / "response.json", response)
            if response["status"] != "completed":
                raise PlanningError("incomplete_review", "Review output is incomplete; no automatic retry.")
            reason = json.loads(response["text"])
            Draft202012Validator(REASON_SCHEMA).validate(reason)
            asked = {q["id"] for q in verification_state["verification_questions"]}
            cited = reason["question_ids"]
            gaps = {e["question_id"] for e in verification["content"]["evaluations"] if e["assessment"] != "correct"}
            if not reason["reason"].strip() or len(cited) != len(set(cited)) or not set(cited) <= asked or not gaps <= set(cited):
                raise PlanningError("invalid_reason", "Reason must cite actual questions and cover identified gaps.")
            runner.check_plan(verification_state)
            result = {"part": "result", "plan_id": plan_id,
                      "goal_achieved": verification["content"]["assessment"] == "passed",
                      **reason, "verification_record_id": verification["id"], "changes": changes}
            Draft202012Validator(schema("learning-result")).validate(result)
            result_path = self.output / "results/3learningnotes" / (plan_id + "." + verification_run_id + ".result.json")
            write_json(result_path, result)
            review.update(status="passed" if result["goal_achieved"] else "result_saved", result_path=str(result_path.resolve()))
            write_json(review_path, review)
        except Exception as exc:
            review.update(status="review_failed", error_code=getattr(exc, "code", "invalid_review_or_storage"))
            write_json(review_path, review)
            raise PlanningError(review["error_code"], "Learning review stopped; inspect runs/reviews. No automatic retry.") from None
        if result["goal_achieved"]:
            review["message"] = "本轮目标已通过验证。请选择是否结束学习。"
            write_json(review_path, review)
            return review
        next_id = "planning_" + uuid4().hex
        review.update(status="replanning", next_plan_id=next_id)
        write_json(review_path, review)
        feedback = {"plan_id": plan_id, "study_id": review["study_id"], "next_revision": review["revision"] + 1,
                    "previous_plan": plan, "learning_result": result, "verification": verification}
        try:
            next_result = Planner(self.data, generator=self.generator, output_root=self.output).start(
                verification_state["paper_id"], plan["goal"], feedback=feedback, run_id=next_id)
            review.update(status="replanned" if next_result["status"] == "planned" else "replan_" + next_result["status"],
                          next_planning=next_result, message="按新版规划补缺后，再次执行理解验证；等待用户真实参与，不自动代答。")
        except Exception as exc:
            review.update(status="replan_failed", error_code=getattr(exc, "code", "replan_error"),
                          message="本轮结果已保存，新版规划失败；未自动重试。")
        write_json(review_path, review)
        return review
