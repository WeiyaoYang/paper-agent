"""PyInstaller entry and explicit offline checks (never invokes the model)."""
import json
import sys
from pathlib import Path


def portable_check():
    from paper_agent.paths import project_root
    from paper_agent.bootstrap import initialize_data
    from paper_agent.app.desktop import Window, configure_appearance
    from paper_agent.ingestion.library import Library
    from paper_agent.models.client import load_settings
    from PySide6.QtWidgets import QApplication
    root = project_root()
    report = root / "tmp/portable-check.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    result = {"frozen": bool(getattr(sys, "frozen", False)), "root": str(root), "ok": False}
    try:
        import tempfile
        with tempfile.TemporaryDirectory(prefix="portable-check-", dir=root / "tmp") as folder:
            data = initialize_data(Path(folder) / "data")
            assert len(list((data / "results").iterdir())) == 10
            settings = load_settings()
            result["model_config_loaded"] = bool(settings["model"])
            app = QApplication.instance() or QApplication([])
            configure_appearance(app)
            window = Window(data)
            window.show()
            app.processEvents()
            window.grab().save(str(root / "tmp/portable-welcome.png"))
            window.stack.setCurrentIndex(1)
            app.processEvents()
            window.grab().save(str(root / "tmp/portable-chat.png"))
            window.close()
            result["gui_rendered"] = True
            # Minimal real PDF, parsed with the bundled text parser.
            objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
                b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
                b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
            stream = b'BT /F1 16 Tf 72 720 Td (Portable Agent PDF import test) Tj ET'
            objects.append(b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream')
            pdf = b'%PDF-1.4\n'
            offsets = [0]
            for index, obj in enumerate(objects, 1):
                offsets.append(len(pdf))
                pdf += str(index).encode() + b' 0 obj\n' + obj + b'\nendobj\n'
            xref = len(pdf)
            pdf += b'xref\n0 6\n0000000000 65535 f \n' + b''.join(f'{o:010d} 00000 n \n'.encode() for o in offsets[1:])
            pdf += b'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n' + str(xref).encode() + b'\n%%EOF\n'
            source = Path(folder) / "sample.pdf"
            source.write_bytes(pdf)
            library = Library(data)
            paper = library.import_pdf(source)["paper"]
            library.parse(paper["id"], backend="pdfplumber")
            assert library.check(paper["id"])["ready"]
            result["pdf_import_parse"] = True
            from paper_agent.agent.session import LearningSession
            selections = []
            def tool(name, arguments):
                return {"status": "completed", "output": [{"type": "function_call", "call_id": "offline-check", "name": name, "arguments": json.dumps(arguments)}]}
            def offline_model(prompt, instructions, **kwargs):
                if "tools" not in kwargs:
                    if "question_ids" in kwargs["json_schema"]["properties"]:
                        return {"status": "completed", "text": json.dumps({"reason": "q1 supports the offline test goal.", "question_ids": ["q1"]})}
                    kind = "reading" if not selections else "verification"
                    selections.append(kind)
                    return {"status": "completed", "text": json.dumps({"behavior": kind, "request": "Offline test", "reason": "Offline test progression"})}
                context = json.loads(prompt[0]["content"])
                if any(t["name"] == "submit_plan" for t in kwargs["tools"]):
                    return tool("submit_plan", {"part": "planning", "goal": context["user_request"], "materials": [{"paper_id": paper["id"], "paper_content_id": library.get(paper["id"])["active_run_id"]}], "plan": [{"behavior": "reading", "description": "Read inputs and outputs"}, {"behavior": "verification", "description": "Verify understanding"}]})
                if context["kind"] == "reading":
                    return tool("propose_record", {"scope": "Offline check", "summary": "Explained inputs and outputs", "key_points": [], "sources": [], "unresolved_questions": []})
                if not any(item.get("type") == "function_call_output" for item in prompt):
                    return tool("ask_verification_questions", {"questions": [{"question": "What are the inputs and outputs?", "goal": context["learning_plan"]["goal"]}]})
                return tool("propose_record", {"plan_id": context["plan_id"], "goal": context["learning_plan"]["goal"], "assessment": "passed", "evaluations": [{"question_id": "q1", "assessment": "correct", "reference_answer": "Images and language in; actions out", "feedback": "Offline synthetic reply evaluated"}], "summary": "Offline synthetic test, not real mastery", "sources": [], "unresolved_questions": []})
            session = LearningSession(data, generator=offline_model)
            session.create(paper["id"], "Offline synthetic learning test")
            assert session.state["status"] == "waiting_save"
            session.reply("保存")
            assert session.state["status"] == "waiting_answer"
            session.reply("Synthetic reply: images and language in; actions out")
            session.reply("保存")
            assert session.state["status"] == "waiting_end"
            session.reply("结束")
            assert session.state["status"] == "completed"
            reopened = LearningSession(data, generator=offline_model)
            reopened.open(session.state["session_id"])
            assert reopened.state["status"] == "completed"
            result["offline_learning_save_reopen"] = True
            from docling.document_converter import DocumentConverter
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.datamodel.base_models import InputFormat
            result["docling_imported"] = True
            if "--check-docling" in sys.argv:
                library.parse(paper["id"], backend="docling")
                assert library.check(paper["id"])["ready"]
                result["docling_parse"] = True
            result["ok"] = True
    except Exception:
        import traceback
        result["error"] = traceback.format_exc()
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    # Windowed executables have no console streams; progress libraries still expect write().
    import os
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    import multiprocessing
    multiprocessing.freeze_support()
    if "--portable-check" in sys.argv:
        raise SystemExit(portable_check())
    try:
        from paper_agent.app.desktop import main
        main()
    except Exception:
        import ctypes
        from paper_agent.paths import project_root
        import traceback
        log = project_root() / "tmp/startup-error.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(traceback.format_exc(), encoding="utf-8")
        ctypes.windll.user32.MessageBoxW(None, "启动失败，错误详情已保存到 tmp/startup-error.log。请确认已解压整个目录到可写位置。", "Agent 工作台", 16)
