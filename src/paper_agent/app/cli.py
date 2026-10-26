"""Minimal local CLI: python -m paper_agent --help."""

import argparse
import json
import logging
import sys
from pathlib import Path
from jsonschema import ValidationError

from paper_agent.ingestion.library import Library, LibraryError
from paper_agent.agent.planning import Planner, PlanningError
from paper_agent.agent.behavior import BehaviorRunner, KINDS_ALLOWED
from paper_agent.agent.review import LearningReviewer
from paper_agent.app.chat import run_chat
from paper_agent.memory.profile import ProfileError, load_profile
from paper_agent.models.client import ModelError, load_settings, smoke_test


def main():
    from paper_agent.paths import project_root
    root = project_root()
    parser = argparse.ArgumentParser(description="Import, extract and read local PDF papers.")
    parser.add_argument("--data", type=Path, default=root / "data")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Create missing data folders and blank core templates; never overwrite existing data.")
    imp = sub.add_parser("import")
    imp.add_argument("pdf", type=Path)
    imp.add_argument("--title")
    imp.add_argument("--source")
    sub.add_parser("list")
    chat = sub.add_parser("chat", help="One interactive learning session; model chooses behaviors.")
    chat.add_argument("paper", nargs="?", help="Registered paper ID or a local PDF path.")
    chat.add_argument("--goal")
    chat.add_argument("--resume", dest="session_id")
    chat.add_argument("--max-calls", type=int, default=40, help="Total API attempts for a new session, across revisions.")
    chat.add_argument("--backend", choices=("docling", "pdfplumber"), default="docling")
    plan = sub.add_parser("plan", help="Billable: model-led planning for an already prepared paper.")
    plan.add_argument("paper_id")
    plan.add_argument("--goal", required=True)
    resume = sub.add_parser("plan-resume", help="Billable: answer a planning clarification and continue.")
    resume.add_argument("run_id")
    resume.add_argument("--reply", required=True)
    behavior = sub.add_parser("behavior", help="Run one behavior; start/resume call the model, show/finish are local.")
    actions = behavior.add_subparsers(dest="behavior_action", required=True)
    start = actions.add_parser("start")
    start.add_argument("kind", choices=KINDS_ALLOWED)
    start.add_argument("paper_id")
    start.add_argument("--request", required=True)
    start.add_argument("--plan-id", help="Link this behavior to a learning plan; required for verification.")
    reply = actions.add_parser("reply")
    reply.add_argument("run_id")
    reply.add_argument("--text", required=True)
    decision = actions.add_parser("decide")
    decision.add_argument("run_id")
    decision.add_argument("--choice", choices=("end", "continue"), required=True)
    for action in ("show", "finish", "pause"):
        entry = actions.add_parser(action)
        entry.add_argument("run_id")
    review = sub.add_parser("learning-review", help="Billable: save learning result and generate a revised plan if needed.")
    review.add_argument("verification_run_id")
    profile = sub.add_parser("profile", help="Read the confirmed initial personal profile.")
    profile.add_argument("--fields", nargs="+", help="Select top-level profile fields.")
    profile.add_argument("--file", type=Path, help="Read an alternative local profile JSON.")
    sub.add_parser("model-config", help="Show non-secret settings; does not call the API.")
    sub.add_parser("model-test", help="Make one small, billable GPT connectivity request.")
    for name in ("show", "check", "parse", "read", "export"):
        command = sub.add_parser(name)
        command.add_argument("paper_id")
        if name == "parse":
            command.add_argument("--backend", choices=("docling", "pdfplumber"), default="docling")
            command.add_argument("--formula", action="store_true", help="Enable Docling formula model (extra download).")
        if name == "read":
            command.add_argument("--start", type=int, default=1)
            command.add_argument("--end", type=int)
        if name == "export":
            command.add_argument("--output", type=Path, default=root / "data" / "artifacts" / "exports")
    args = parser.parse_args()
    if args.command == "parse":
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        if args.command == "init":
            from paper_agent.bootstrap import initialize_data
            print(json.dumps({"ok": True, "data": str(initialize_data(args.data))}, ensure_ascii=False))
            return 0
        if args.command == "chat":
            if args.session_id and (args.paper or args.goal):
                parser.error("--resume cannot be combined with a new paper or goal")
            result = run_chat(args.data, args.paper, args.goal, args.session_id, args.max_calls, args.backend)
            return 1 if result["status"] == "blocked" else 0
        if args.command == "learning-review":
            result = LearningReviewer(args.data).start(args.verification_run_id)
            print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "behavior":
            runner = BehaviorRunner(args.data)
            action = args.behavior_action
            if action == "start":
                result = runner.start(args.paper_id, args.request, args.kind, args.plan_id)
            elif action == "decide":
                result = runner.decide(args.run_id, args.choice)
            elif action == "reply":
                result = runner.resume(args.run_id, args.text)
            else:
                result = getattr(runner, action)(args.run_id)
            if result.get("status") == "awaiting_finish":
                result = runner.show(result["run_id"])
            print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))
            return 0
        if args.command in ("plan", "plan-resume"):
            planner = Planner(args.data)
            result = planner.start(args.paper_id, args.goal) if args.command == "plan" else planner.resume(args.run_id, args.reply)
            print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))
            return 0
        if args.command in ("model-config", "model-test"):
            result = load_settings() if args.command == "model-config" else smoke_test()
            print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "profile":
            result = load_profile(args.file or args.data / "results/1profile/current.json", args.fields)
            print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))
            return 0
        lib = Library(args.data)
        if args.command == "import":
            result = lib.import_pdf(args.pdf, args.title, args.source)
        elif args.command == "list":
            result = lib.list_papers()
        elif args.command == "show":
            result = lib.get(args.paper_id)
        elif args.command == "check":
            result = lib.check(args.paper_id)
        elif args.command == "parse":
            result = lib.parse(args.paper_id, backend=args.backend, formula=args.formula)
        elif args.command == "read":
            result = lib.read(args.paper_id, args.start, args.end)
        else:
            result = lib.export(args.paper_id, args.output)
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))
        return 0
    except ValidationError as exc:
        print(json.dumps({"ok": False, "error": {"code": "invalid_record", "field": list(exc.absolute_path),
                                                 "message": "记录结构不符合约定，请检查对应 JSON 文件。"}}, ensure_ascii=False), file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print("已取消；没有自动重试。", file=sys.stderr)
        return 130
    except (LibraryError, ProfileError, ModelError, PlanningError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": {"code": getattr(exc, "code", "storage_error"),
                                                 "message": str(exc)}}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
