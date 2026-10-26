"""Persistent coordinator: model chooses actions; code enforces state and budgets."""

import json
import re
from pathlib import Path
from uuid import uuid4

from jsonschema import Draft202012Validator

from paper_agent.agent.behavior import BehaviorRunner
from paper_agent.agent.planning import Planner, PlanningError, ROOT, BEHAVIORS, api_schema, object_schema
from paper_agent.agent.review import LearningReviewer
from paper_agent.models.client import generate_text
from paper_agent.storage.json_files import write_json

LABELS = {"reading": "阅读", "discussion": "探讨", "qa": "问答", "knowledge-recording": "知识记录", "verification": "理解验证"}

SELECTION_SCHEMA = object_schema({"behavior": {"enum": list(BEHAVIORS)},
                                  "request": {"type": "string", "minLength": 1},
                                  "reason": {"type": "string", "minLength": 1}})


def format_candidate(candidate):
    labels = {"scope": "阅读范围", "summary": "总结", "feedback": "反馈", "viewpoint": "观点",
              "key_points": "重点", "conclusions": "阶段结论", "disagreements": "分歧", "unresolved_questions": "遗留问题"}
    parts = []
    for key, label in labels.items():
        value = candidate.get(key)
        if value:
            parts.append(label + "：" + ("；".join(value) if isinstance(value, list) else value))
    for item in candidate.get("evaluations", []):
        parts.append(item["question_id"] + "：" + {"correct": "正确", "partial": "部分理解", "incorrect": "存在理解错误", "insufficient_evidence": "证据不足"}[item["assessment"]] + "\n反馈：" + item["feedback"] + "\n参考答案：" + item["reference_answer"])
    if "note" in candidate:
        parts.append("知识点：" + "、".join(c["name"] for c in candidate["concepts"]))
        parts.append(candidate["note"]["title"] + "\n" + candidate["note"]["content"])
    return "\n".join(parts)


class LearningSession:
    def __init__(self, data=None, *, generator=generate_text, notify=None):
        self.data = Path(data).resolve() if data else ROOT / "data"
        self.generator = generator
        self.state = None
        self.notify = notify or (lambda message: None)
        self.validator = Draft202012Validator(json.loads((ROOT / "schemas/chat-state.schema.json").read_text(encoding="utf-8")))

    def path(self, session_id):
        if not re.fullmatch(r"chat_[0-9a-f]{32}", session_id):
            raise PlanningError("invalid_session_id", "Invalid chat session ID.")
        return self.data / "runs/chats" / session_id / "state.json"

    def save(self):
        self.validator.validate(self.state)
        write_json(self.path(self.state["session_id"]), self.state)

    def event(self, text):
        self.state["events"].append(text)

    def model(self, *args, **kwargs):
        if self.state["model_calls"] >= self.state["max_calls"]:
            self.state.update(status="blocked", error="session_budget")
            self.save()
            raise PlanningError("session_budget", "Session model-call limit reached.")
        self.state["model_calls"] += 1
        self.notify("正在调用模型（" + str(self.state["model_calls"]) + "/" + str(self.state["max_calls"]) + "）……")
        self.state["in_flight"] = True
        self.save()
        try:
            result = self.generator(*args, **kwargs)
        except BaseException:
            # An interrupted/billed call is never silently replayed on resume.
            self.state["status"] = "blocked"
            self.state["error"] = "模型调用失败或被中断；未自动重试。请查看运行记录。"
            self.save()
            raise
        self.state["in_flight"] = False
        self.save()
        return result

    def planner(self):
        return Planner(self.data, generator=self.model)

    def behavior(self):
        return BehaviorRunner(self.data, generator=self.model)

    def create(self, paper_id, goal, max_calls=40):
        if type(max_calls) is not int or not 1 <= max_calls <= 200:
            raise PlanningError("invalid_budget", "max-calls must be an integer from 1 to 200.")
        if not isinstance(goal, str) or not goal.strip():
            raise PlanningError("empty_goal", "Provide a learning goal.")
        if not self.planner().library.check(paper_id)["ready"]:
            raise PlanningError("materials_not_ready", "Import and parse the paper first.")
        self.state = {"schema_version": 1, "session_id": "chat_" + uuid4().hex, "paper_id": paper_id, "goal": goal,
                      "phase": "planning", "status": "active", "plan_id": "planning_" + uuid4().hex,
                      "model_calls": 0, "max_calls": max_calls, "in_flight": False,
                      "events": [], "completed": [], "parked_runs": [], "inputs": []}
        self.save()
        return self.advance()

    def open(self, session_id):
        self.state = json.loads(self.path(session_id).read_text(encoding="utf-8"))
        self.validator.validate(self.state)
        if self.state.get("in_flight") or self.state.get("reply_pending") or self.state.get("selection_pending"):
            self.state.update(status="blocked", error="上次调用或提交被中断，不能自动重放。请检查运行记录后再处理。")
            self.save()
        elif self.state["status"] == "paused":
            self.state["status"] = "active"
            self.save()
        return self.advance()

    def context(self):
        """Supply bounded actual outputs, not generated claims about completed work."""
        records = []
        paths = {}
        for completed in self.state["completed"]:
            for path in completed.get("record_paths", []):
                record = json.loads(Path(path).read_text(encoding="utf-8"))
                paths[record["id"]] = path
                records.append({"id": record["id"], "plan_id": record.get("plan_id"),
                                "content_excerpt": json.dumps(record["content"], ensure_ascii=False)[:2500]})
        paused_dialogue = []
        for run_id in self.state.get("parked_runs", [])[-5:]:
            child = self.behavior().load(run_id)
            paused_dialogue.extend(child["messages"][-8:])
        return {"paused_dialogue": paused_dialogue[-20:], "original_goal": self.state["goal"], "records": records[-20:],
                "record_paths": paths, "user_inputs": self.state["inputs"][-20:]}

    def select(self):
        if self.state.pop("force_verification", False):
            choice = {"behavior": "verification", "request": "用户请求结束，请按本轮目标完成理解验证，等待真实回答。",
                      "reason": "结束前必须验证。"}
        elif self.state.get("requested_behavior"):
            choice = self.state.pop("requested_behavior")
        else:
            self.state["selection_pending"] = True
            self.save()
            plan = json.loads((self.data / "results/3learningnotes" / (self.state["plan_id"] + ".json")).read_text(encoding="utf-8"))
            instructions = (ROOT / "prompts/agent-policy.md").read_text(encoding="utf-8") + "\n\n" + (ROOT / "prompts/dispatch.md").read_text(encoding="utf-8")
            context = {"plan": plan, "history": self.context(),
                       "available_behaviors": [{"name": name, "description": (ROOT / "behaviors" / (name + ".md")).read_text(encoding="utf-8").split("## 输入")[0]}
                                               for name in BEHAVIORS]}
            response = self.model(json.dumps(context, ensure_ascii=False), instructions,
                                  config=ROOT / "config/planning.toml", json_schema=api_schema(SELECTION_SCHEMA),
                                  usage_path=self.data / "logs/model-usage.jsonl")
            path = self.path(self.state["session_id"]).parent / ("selection-" + str(self.state["model_calls"]) + ".json")
            write_json(path, response)
            if response["status"] != "completed":
                raise PlanningError("incomplete_selection", "Behavior selection was incomplete.")
            choice = json.loads(response["text"])
            Draft202012Validator(SELECTION_SCHEMA).validate(choice)
        self.state.pop("selection_pending", None)
        self.state.update(phase="behavior", active_run_id="behavior_" + uuid4().hex,
                          selected=choice, status="active")
        self.event("下一步：" + LABELS[choice["behavior"]] + "。" + choice["reason"])
        self.save()

    def accept_plan(self, result):
        if result["status"] == "awaiting_user":
            self.state.update(status="waiting_plan", prompt=result["question"])
        elif result["status"] == "planned":
            plan = json.loads(Path(result["plan_path"]).read_text(encoding="utf-8"))
            self.event("本次目标：" + plan["goal"] + "\n建议安排：\n" + "\n".join(str(i) + ". " + step["description"] for i, step in enumerate(plan["plan"], 1)))
            self.state.update(phase="selecting", status="active")
        else:
            raise PlanningError("planning_stopped", "Planning status: " + result["status"])
        self.save()

    def accept_behavior(self, result):
        if result["status"] == "awaiting_user":
            text = result.get("message", "")
            if result.get("question"):
                text += "\n\n" + result["question"]
            self.state.update(status="waiting_answer", prompt=text.strip())
        elif result["status"] == "awaiting_finish":
            candidate = self.behavior().show(result["run_id"])["candidate"]
            self.state.update(status="waiting_save", prompt="本行为拟保存的内容：\n" + format_candidate(candidate)
                              + "\n输入“保存”结束本行为，或输入补充意见继续讨论。")
        elif result["status"] in ("recorded", "awaiting_learning_decision"):
            if not any(item["run_id"] == result["run_id"] for item in self.state["completed"]):
                self.state["completed"].append(result)
            self.event("本行为记录已保存。")
            self.state.update(phase="reviewing" if result["kind"] == "verification" else "selecting", status="active")
        else:
            raise PlanningError("behavior_stopped", "Behavior status: " + result["status"])
        self.save()

    def advance(self):
        if self.state["status"] in ("blocked", "completed", "ended_early", "paused"):
            return self.state
        try:
            for _ in range(80):
                phase = self.state["phase"]
                if phase == "planning":
                    planner = self.planner()
                    path = planner.state_path(self.state["plan_id"])
                    if path.exists():
                        result = planner.result(json.loads(path.read_text(encoding="utf-8")))
                    else:
                        result = planner.start(self.state["paper_id"], self.state["goal"], run_id=self.state["plan_id"])
                    self.accept_plan(result)
                elif phase == "selecting":
                    self.select()
                elif phase == "behavior":
                    runner = self.behavior()
                    path = runner.state_path(self.state["active_run_id"])
                    if path.exists():
                        result = runner.result(runner.load(self.state["active_run_id"]))
                    else:
                        selected = self.state["selected"]
                        result = runner.start(self.state["paper_id"], selected["request"], selected["behavior"], self.state["plan_id"],
                                              run_id=self.state["active_run_id"], learning_context=self.context())
                    self.accept_behavior(result)
                elif phase == "reviewing":
                    review = LearningReviewer(self.data, generator=self.model).start(self.state["active_run_id"])
                    if review.get("result_path"):
                        result = json.loads(Path(review["result_path"]).read_text(encoding="utf-8"))
                        self.event("本轮结果：" + result["reason"])
                    if review["status"] == "passed":
                        self.state.update(phase="decision", status="waiting_end", prompt="本轮目标已通过验证。是否结束此次学习？输入“结束”或“继续”。")
                    elif review["status"] in ("replanned", "replan_awaiting_user"):
                        self.state.update(plan_id=review["next_plan_id"], phase="planning", status="active")
                        self.event("尚有理解缺口，已转入下一版规划。")
                    else:
                        raise PlanningError("review_stopped", "Review status: " + review["status"])
                    self.save()
                elif phase == "decision":
                    return self.state
                else:
                    raise PlanningError("invalid_phase", "Unknown session phase.")
                if self.state["status"].startswith("waiting_"):
                    return self.state
            raise PlanningError("transition_limit", "Too many automatic transitions.")
        except Exception as exc:
            self.state.update(status="blocked", error=self.state.get("error") or getattr(exc, "code", "invalid_state_or_storage"))
            self.save()
            return self.state

    def park_active(self):
        if self.state["phase"] == "behavior" and not any(x["run_id"] == self.state["active_run_id"] for x in self.state["completed"]):
            if self.state["active_run_id"] not in self.state["parked_runs"]:
                self.state["parked_runs"].append(self.state["active_run_id"])

    def reply(self, text):
        text = text.strip()
        if not text:
            return self.state
        if text in (":pause", ":quit"):
            self.state["status"] = "paused"
            self.save()
            return self.state
        if text == ":status":
            return self.state
        if text.startswith(":") and text not in (":end", ":save", ":stop") and not text.startswith(":do "):
            self.event("未知命令。可用 :pause、:status、:end、:stop、:do 行为 具体要求。")
            self.save()
            return self.state
        if self.state["status"] in ("blocked", "completed", "ended_early"):
            return self.state
        if text == ":save" and self.state["status"] != "waiting_save":
            self.event("当前没有待保存候选，请先完成交互或要求整理记录。")
            self.save()
            return self.state
        self.state["inputs"].append({"phase": self.state["phase"], "text": text})
        if text == ":stop":
            plan_path = self.planner().state_path(self.state["plan_id"])
            lineage = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else {}
            study_id = lineage.get("study_id", self.state["plan_id"])
            write_json(self.data / "runs/learning" / (study_id + ".json"),
                       {"study_id": study_id, "plan_id": self.state["plan_id"], "learning_status": "ended_early",
                        "user_decision": "stop_early", "reason": "用户明确提前结束；不将本轮标为验证通过。"})
            self.state.update(status="ended_early", phase="ended")
            self.event("已提前结束，实际进度保留；未将本轮标为通过。")
            self.save()
            return self.state
        if text == ":end" and self.state["phase"] == "decision":
            text = "结束"
        if text == ":end" and self.state["phase"] != "decision":
            if self.state["phase"] == "planning":
                self.event("请先完成目标澄清和规划，或输入 :pause 暂停。")
                self.save()
                return self.state
            self.park_active()
            self.state.update(force_verification=True, phase="selecting", status="active")
            self.save()
            return self.advance()
        if text.startswith(":do "):
            parts = text.split(" ", 2)
            if self.state["phase"] == "planning" or len(parts) < 3 or parts[1] not in BEHAVIORS:
                self.event("先完成规划。指定行为格式：:do reading 你的具体要求；仅允许五类学习行为。")
                self.save()
                return self.state
            self.park_active()
            self.state.update(requested_behavior={"behavior": parts[1], "request": parts[2], "reason": "用户指定。"}, phase="selecting", status="active")
            self.save()
            return self.advance()
        if self.state["phase"] == "decision":
            if text not in ("结束", "继续", "end", "continue"):
                self.state["prompt"] = "请输入“结束”或“继续”，也可以 :pause。"
                self.save()
                return self.state
            choice = "end" if text in ("结束", "end") else "continue"
            try:
                result = self.behavior().decide(self.state["active_run_id"], choice)
            except Exception as exc:
                self.state.update(status="blocked", error=getattr(exc, "code", "decision_failed"))
                self.save()
                return self.state
            if choice == "end":
                self.state.update(status=result["learning_status"], phase="ended")
                self.event("本次学习已结束，规划、结果与各行为记录均已保存。")
                self.save()
                return self.state
            self.state.update(status="active", phase="selecting")
            self.save()
            return self.advance()
        # Store a pending operation before touching a child's possibly billed state.
        self.state["reply_pending"] = True
        self.save()
        try:
            if self.state["phase"] == "planning":
                result = self.planner().resume(self.state["plan_id"], text)
                self.accept_plan(result)
            elif self.state["phase"] == "behavior":
                result = self.behavior().finish(self.state["active_run_id"]) if self.state["status"] == "waiting_save" and text in ("保存", ":save") else self.behavior().resume(self.state["active_run_id"], text)
                self.accept_behavior(result)
            else:
                raise PlanningError("not_waiting", "No user input expected here.")
            self.state.pop("reply_pending", None)
            self.save()
            return self.advance()
        except Exception as exc:
            self.state.update(status="blocked", error=getattr(exc, "code", "input_processing_failed"))
            self.save()
            return self.state
