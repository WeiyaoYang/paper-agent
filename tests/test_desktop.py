import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt, QMimeData, QUrl, QPoint
from PySide6.QtGui import QDragEnterEvent
from PySide6.QtWidgets import QApplication

from paper_agent.app.desktop import Window, Job
from paper_agent.app.desktop_store import DesktopStore
from paper_agent.ingestion.library import Library
from paper_agent.storage.json_files import write_json


class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name) / "data"

    def state(self):
        return {"session_id": "chat_" + "a" * 32, "goal": "测试目标", "paper_id": "paper_test",
                "events": ["已有规划"], "status": "waiting_answer", "prompt": "请回答", "model_calls": 2, "max_calls": 40}

    def test_transcript_persists_and_does_not_duplicate(self):
        store = DesktopStore(self.data)
        state = self.state()
        store.collect(state)
        store.history(state).append({"role": "user", "text": "第一行\n第二行"})
        state["events"].append("答案已收到")
        state["prompt"] = "待保存"
        state["status"] = "waiting_save"
        store.collect(state)
        count = len(store.history(state))
        store.collect(state)
        self.assertEqual(count, len(store.history(state)))
        reloaded = DesktopStore(self.data)
        self.assertIn("第一行\n第二行", [m["text"] for m in reloaded.history(state)])

    def test_local_import_copies_deduplicates_and_preserves_source(self):
        path = Path(self.tmp.name) / "input.pdf"
        path.write_bytes(b"%PDF-1.5\nfixture")
        results = []
        errors = []
        job = Job(self.data, "import", [str(path)])
        job.done.connect(results.append)
        job.failed.connect(errors.append)
        job.run()
        self.assertFalse(errors)
        paper = results[0]["papers"][0]
        self.assertEqual(paper["source"], str(path.resolve()))
        self.assertEqual(Path(paper["pdf_path"]).parent, self.data / "papers")
        self.assertTrue(Library(self.data).import_pdf(path)["duplicate"])

    def test_window_actions_folders_and_no_api_on_browsing(self):
        state = self.state()
        write_json(self.data / "runs/chats" / state["session_id"] / "state.json", state)
        window = Window(self.data)
        window.stack.setCurrentIndex(1)
        window.selected = state["session_id"]
        window.render()
        self.assertTrue(window.save_button.isHidden())
        state["status"] = "waiting_save"
        write_json(self.data / "runs/chats" / state["session_id"] / "state.json", state)
        window.render()
        self.assertFalse(window.save_button.isHidden())
        folder = window.store.folder("机械臂")
        window.store.meta(state)["folder"] = folder["id"]
        window.refresh_tree()
        self.assertEqual(window.tree.topLevelItem(0).text(0), "文件夹")
        self.assertEqual(window.tree.topLevelItem(1).text(0), "最近")
        self.assertEqual(window.tree.topLevelItem(0).child(0).childCount(), 1)
        window.input.setPlainText("多行\n回答")
        window.new_chat()
        self.assertEqual(window.drafts[state["session_id"]], "多行\n回答")
        window.close()

    def test_pdf_drag_is_accepted_and_dispatched_to_import(self):
        window = Window(self.data)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(Path(self.tmp.name) / "paper.pdf"))])
        event = QDragEnterEvent(QPoint(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        window.dragEnterEvent(event)
        self.assertTrue(event.isAccepted())
        with patch.object(window, "launch") as launch:
            window.dropEvent(event)
            self.assertEqual(launch.call_args.args[0], "import")
            self.assertEqual(len(launch.call_args.args[1]), 1)
        window.close()


if __name__ == "__main__":
    unittest.main()
