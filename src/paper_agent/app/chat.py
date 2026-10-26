"""One terminal conversation, with process-level exclusion and recoverable sessions."""

import os
from contextlib import contextmanager
from pathlib import Path

from paper_agent.agent.planning import PlanningError
from paper_agent.agent.session import LearningSession
from paper_agent.ingestion.library import Library


@contextmanager
def chat_lock(data):
    path = Path(data) / "runs/chats/.active.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if path.stat().st_size == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise PlanningError("chat_busy", "Another chat is using this data directory.") from None
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def read_turn(read=input):
    lines = []
    while True:
        line = read("你 > " if not lines else "... ")
        if not lines and (line.startswith(":") or line in ("保存", "结束", "继续", "end", "continue")):
            return line
        if line == ".":
            return "\n".join(lines)
        lines.append(line)


def interact(session, read=input, emit=print):
    emit("回答可写多行，单独一行 . 提交；输入“保存”确认候选记录。")
    emit(":pause 暂停并退出；:status 查看状态；:end 请求验证后结束；:stop 明确提前退出（不算通过）；:do reading 具体要求 可指定行为。")
    shown = 0
    try:
        while True:
            state = session.state
            for event in state["events"][shown:]:
                emit(event)
            shown = len(state["events"])
            if state["status"] in ("paused", "blocked", "completed", "ended_early"):
                if state["status"] == "blocked":
                    emit("运行已停止：" + str(state.get("error", "unknown")) + "。现场已保留，不会自动重放请求。")
                elif state["status"] == "paused":
                    emit("已暂停。")
                emit("会话编号：" + state["session_id"])
                if state["status"] == "paused":
                    emit("恢复命令：.\\scripts\\run.ps1 chat --resume " + state["session_id"])
                return state
            emit(state.get("prompt", "请回答。"))
            text = read_turn(read)
            if text == ":status":
                emit("阶段：" + {"planning": "制定规划", "selecting": "选择下一步", "behavior": "学习交流", "reviewing": "学习复盘", "decision": "等待结束决定", "ended": "已结束"}[state["phase"]] + "；本次模型调用：" + str(state["model_calls"]) + "/" + str(state["max_calls"]))
                continue
            session.reply(text)
    except (EOFError, KeyboardInterrupt):
        # Submitted child data stays intact; in-flight calls are detected and blocked on reopen.
        session.state["status"] = "paused"
        session.save()
        emit("已暂停；已提交内容保留，当前尚未提交的文字未保存。")
        emit("恢复命令：.\\scripts\\run.ps1 chat --resume " + session.state["session_id"])
        return session.state


def run_chat(data, paper=None, goal=None, resume=None, max_calls=40, backend="docling", read=input, emit=print):
    from paper_agent.bootstrap import initialize_data
    initialize_data(data)
    with chat_lock(data):
        session = LearningSession(data, notify=emit)
        emit("模型调用会发送本次所需论文、画像和框架到 OpenAI 官方 API，并产生费用。")
        if resume:
            session.open(resume)
        else:
            library = Library(data)
            if not paper:
                papers = library.list_papers()
                if len(papers) == 1:
                    paper = papers[0]["id"]
                    emit("使用论文：" + papers[0]["title"])
                else:
                    for index, item in enumerate(papers, 1):
                        emit(str(index) + ". " + item["title"])
                    selected = read("选择论文序号，或输入本地 PDF 路径 > ").strip().strip('"')
                    paper = papers[int(selected) - 1]["id"] if selected.isdecimal() and 1 <= int(selected) <= len(papers) else selected
            path = Path(paper)
            if path.is_file():
                paper = library.import_pdf(path)["paper"]["id"]
            check = library.check(paper)
            if not check["ready"]:
                if any(issue != "content_not_ready" for issue in check["issues"]):
                    raise PlanningError("materials_not_ready", "Material needs repair: " + ", ".join(check["issues"]))
                emit("正在解析论文……")
                library.parse(paper, backend=backend)
            goal = goal or read("本次希望理解什么？可以先用不精确的描述 > ")
            emit("正在准备学习规划……")
            session.create(paper, goal, max_calls)
        return interact(session, read=read, emit=emit)
