"""Native desktop shell for the existing persistent learning coordinator."""
import json
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QTimer, QByteArray, QSize
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtGui import (QDesktopServices, QFont, QFontDatabase, QIcon, QPixmap,
    QPainter, QPainterPath, QLinearGradient, QColor, QPen, QTransform)
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QStackedWidget, QTreeWidget, QTreeWidgetItem, QTextBrowser,
    QPlainTextEdit, QComboBox, QFileDialog, QInputDialog, QMenu, QMessageBox, QSplitter, QLineEdit)

from paper_agent.agent.planning import ROOT
from paper_agent.agent.session import LearningSession
from paper_agent.app.chat import chat_lock
from paper_agent.app.desktop_store import DesktopStore
from paper_agent.ingestion.library import Library
from paper_agent.bootstrap import initialize_data

STATUS = {"active": "准备继续", "waiting_plan": "等待目标澄清", "waiting_answer": "等待回答",
          "waiting_save": "等待确认保存", "waiting_end": "等待结束决定", "paused": "已暂停",
          "completed": "已完成", "ended_early": "提前结束", "blocked": "运行已停止"}


def ui_icon(name):
    """Consistent monochrome SVG icons, crisp at Windows display scales."""
    paths = {
        "new": '<path d="M13 5H5v14h14v-8M10 14l1-4 7-7 3 3-7 7-4 1z"/>',
        "folder": '<path d="M3 7V5h6l2 2h10v13H3z"/>',
        "folder-plus": '<path d="M3 7V5h6l2 2h10v13H3zM12 11v6m-3-3h6"/>',
        "chat": '<path d="M4 4h16v12H9l-5 4zM8 8h8M8 12h5"/>',
        "clock": '<circle cx="12" cy="12" r="8"/><path d="M12 7v5l3 2"/>',
        "settings": '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="3"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3M5 5l2 2m10 10 2 2M5 19l2-2M17 7l2-2"/>',
        "import": '<path d="M12 3v12m-4-4 4 4 4-4M4 15v6h16v-6"/>',
        "document": '<path d="M5 3h9l5 5v13H5zM14 3v6h5M8 13h8M8 17h6"/>',
        "send": '<path d="M12 20V4m-6 6 6-6 6 6"/>',
    }
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">'
           '<g fill="none" stroke="#5276a1" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
           + paths[name] + '</g></svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


class Job(QThread):
    progress = Signal(str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, data, action, payload):
        super().__init__()
        self.data, self.action, self.payload = data, action, payload

    def run(self):
        try:
            with chat_lock(self.data):
                library = Library(self.data)
                if self.action == "import":
                    papers = []
                    for path in self.payload:
                        self.progress.emit("正在导入 " + Path(path).name)
                        papers.append(library.import_pdf(path, source=str(Path(path).resolve()))["paper"])
                    self.done.emit({"papers": papers})
                    return
                session = LearningSession(self.data, notify=self.progress.emit)
                if self.action == "create":
                    paper_id, goal = self.payload
                    check = library.check(paper_id)
                    if not check["ready"]:
                        if any(i != "content_not_ready" for i in check["issues"]):
                            raise ValueError("论文材料需要修复：" + ", ".join(check["issues"]))
                        self.progress.emit("正在解析 PDF，首次导入可能需要较长时间……")
                        library.parse(paper_id, backend="docling")
                    session.create(paper_id, goal)
                else:
                    session_id, text = self.payload
                    state = json.loads(session.path(session_id).read_text(encoding="utf-8"))
                    # Opening may advance paused work. Never append a reply against a stale prompt.
                    if state["status"] in ("paused", "active") or state.get("in_flight") or state.get("reply_pending") or state.get("selection_pending"):
                        session.open(session_id)
                    else:
                        session.validator.validate(state)
                        session.state = state
                        session.reply(text)
                self.done.emit({"state": session.state})
        except Exception as exc:
            # Never surface raw SDK errors or credential-bearing environment values.
            code = getattr(exc, "code", None)
            self.failed.emit("操作未完成（" + str(code or type(exc).__name__) + "）。已保存的进度保留，请查看当前状态。模型请求不会自动重试。")


class Composer(QPlainTextEdit):
    send = Signal()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and event.modifiers() & Qt.ControlModifier:
            self.send.emit()
        else:
            super().keyPressEvent(event)


class WelcomeHeadline(QWidget):
    """Resolution-independent outlined lettering for the welcome screen."""
    def __init__(self, text="我要吃白饭！"):
        super().__init__()
        self.text = text
        self.setFixedHeight(116)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        font = QFont("Microsoft YaHei")
        size = min(70, max(36, self.width() // 12))
        font.setPixelSize(size)
        font.setBold(True)
        path = QPainterPath()
        for index, letter in enumerate(self.text):
            glyph = QPainterPath()
            glyph.addText(-size / 2, 0, font, letter)
            transform = QTransform()
            transform.translate(index * size * 1.08, [2, -3, 3, -2, 1, -5][index])
            transform.rotate([-9, 6, -6, 7, -5, 12][index])
            transform.scale(1.04, [1.02, 1.09, 1.0, 1.08, 1.03, 1.13][index])
            path.addPath(transform.map(glyph))
        bounds = path.boundingRect()
        painter.translate((self.width() - bounds.width()) / 2 - bounds.left(),
                          (self.height() - bounds.height()) / 2 - bounds.top())
        painter.translate(3, 6)
        painter.strokePath(path, QPen(QColor("#9eafe1"), 14, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.fillPath(path, QColor("#9eafe1"))
        painter.translate(-3, -6)
        painter.strokePath(path, QPen(QColor("#ffffff"), 17, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.strokePath(path, QPen(QColor("#243b78"), 10, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        gradient = QLinearGradient(0, bounds.top(), 0, bounds.bottom())
        gradient.setColorAt(0, QColor("#ffffff"))
        gradient.setColorAt(0.5, QColor("#f2f7ff"))
        gradient.setColorAt(1, QColor("#bad5ff"))
        painter.fillPath(path, gradient)
        painter.setPen(QPen(QColor("#516db2"), 3, Qt.SolidLine, Qt.RoundCap))
        for x, y, direction in [(bounds.left() - 22, -size * .5, -1), (bounds.right() + 24, -size * .45, 1)]:
            painter.drawLine(round(x), round(y), round(x + direction * 11), round(y - 8))
            painter.drawLine(round(x + direction * 2), round(y + 12), round(x + direction * 16), round(y + 10))


class Window(QMainWindow):
    def __init__(self, data=None):
        super().__init__()
        self.data = Path(data) if data else ROOT / "data"
        self.first_setup = not (self.data / "results/1profile/current.json").exists()
        initialize_data(self.data)
        self.store = DesktopStore(self.data)
        self.selected = None
        self.worker = None
        self.drafts = {}
        self.setWindowTitle("Agent 工作台")
        self.setWindowIcon(QIcon(str(ROOT / "assets/app-icon-cutout.ico" if (ROOT / "assets/app-icon-cutout.ico").exists() else ROOT / "assets/default-agent.svg")))
        self.resize(1180, 820)
        self.setMinimumSize(860, 600)
        self.setAcceptDrops(True)
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.home = QWidget()
        welcome_layout = QVBoxLayout(self.home)
        welcome_layout.setContentsMargins(52, 20, 40, 35)
        welcome_layout.setSpacing(0)
        personal_art = (ROOT / "assets/welcome-character-hd.png").exists()
        welcome_layout.addWidget(WelcomeHeadline("我要吃白饭！" if personal_art else "从好奇开始！"))
        home = QHBoxLayout()
        welcome_layout.addLayout(home, 1)
        home.setSpacing(24)
        choices = QWidget()
        choices.setMaximumWidth(430)
        intro = QVBoxLayout(choices)
        intro.setContentsMargins(0, 0, 0, 0)
        intro.setSpacing(16)
        intro.addStretch()
        title = QLabel("你的 Agent 工作台")
        title.setObjectName("hero")
        intro.addWidget(title)
        intro.addWidget(QLabel("选择一个 Agent，继续你的项目与学习。"))
        card = QPushButton("Paper Agent  →\n论文阅读 · 自主规划 · 理解验证")
        card.setObjectName("agentCard")
        card.setFixedHeight(92)
        card.setMaximumWidth(390)
        card.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        intro.addSpacing(10)
        intro.addWidget(card)
        intro.addWidget(QLabel("更多 Agent 将在这里加入。"))
        intro.addStretch()
        home.addWidget(choices, 1)
        self.welcome_art = QLabel()
        self.welcome_art.setMinimumSize(0, 0)
        self.welcome_art.setAlignment(Qt.AlignCenter)
        self.welcome_art.setStyleSheet("background:transparent;")
        if personal_art:
            self.welcome_pixmap = QPixmap(str(ROOT / "assets/welcome-character-hd.png"))
        else:
            self.welcome_pixmap = QIcon(str(ROOT / "assets/default-agent.svg")).pixmap(1024, 1024)
        home.addWidget(self.welcome_art, 1)
        self.stack.addWidget(self.home)
        work = QWidget()
        layout = QHBoxLayout(work)
        layout.setContentsMargins(0, 0, 0, 0)
        split = QSplitter()
        layout.addWidget(split)
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 20, 14, 14)
        side.setSpacing(8)
        brand = QLabel("Paper Agent")
        brand.setObjectName("sidebarBrand")
        side.addWidget(brand)
        new_button = self.button(side, "新聊天", self.new_chat)
        new_button.setObjectName("navigation")
        new_button.setIcon(ui_icon("new"))
        folder_button = self.button(side, "新建文件夹", self.add_folder)
        folder_button.setObjectName("navigation")
        folder_button.setIcon(ui_icon("folder-plus"))
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIconSize(QSize(18, 18))
        self.tree.setIndentation(15)
        self.tree.setAnimated(True)
        self.tree.itemClicked.connect(self.pick)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.context_menu)
        side.addWidget(self.tree)
        settings_button = self.button(side, "设置", self.settings)
        settings_button.setObjectName("navigation")
        settings_button.setIcon(ui_icon("settings"))
        split.addWidget(sidebar)
        main = QWidget()
        col = QVBoxLayout(main)
        col.setContentsMargins(24, 20, 24, 18)
        self.heading = QLabel("新聊天")
        self.heading.setObjectName("heading")
        col.addWidget(self.heading)
        self.status = QLabel("选择论文，输入本次学习要求。")
        self.status.setWordWrap(True)
        col.addWidget(self.status)
        paperrow = QHBoxLayout()
        self.papers = QComboBox()
        self.papers.setMinimumWidth(260)
        paperrow.addWidget(self.papers, 1)
        self.import_button = QPushButton("导入 PDF")
        self.import_button.setIcon(ui_icon("import"))
        self.import_button.clicked.connect(self.choose_pdf)
        paperrow.addWidget(self.import_button)
        self.pdf_button = QPushButton("打开原文")
        self.pdf_button.setIcon(ui_icon("document"))
        self.pdf_button.clicked.connect(self.open_pdf)
        paperrow.addWidget(self.pdf_button)
        col.addLayout(paperrow)
        self.transcript = QTextBrowser()
        self.transcript.setOpenExternalLinks(True)
        col.addWidget(self.transcript, 1)
        self.actions = QHBoxLayout()
        col.addLayout(self.actions)
        self.save_button = self.button(self.actions, "确认保存", lambda: self.submit("保存"))
        self.end_button = self.button(self.actions, "结束学习", lambda: self.submit("结束"))
        self.continue_button = self.button(self.actions, "继续学习", lambda: self.submit("继续"))
        self.verify_button = self.button(self.actions, "验证并准备结束", lambda: self.submit(":end"))
        self.resume_button = self.button(self.actions, "恢复学习", lambda: self.submit(":status"))
        self.input = Composer()
        self.input.setPlaceholderText("输入学习要求或回答问题……\nEnter 换行，Ctrl+Enter 发送。也可拖入 PDF。")
        self.input.setMaximumHeight(150)
        self.input.setMinimumHeight(100)
        self.input.send.connect(lambda: self.submit())
        for widget in (self.tree, self.transcript, self.input):
            widget.setAcceptDrops(False)
            widget.viewport().setAcceptDrops(False)
        col.addWidget(self.input)
        bottom = QHBoxLayout()
        hint = QLabel("自动保存进度 · 模型调用使用 OpenAI API 并计费")
        hint.setWordWrap(True)
        bottom.addWidget(hint, 1)
        self.send_button = self.button(bottom, "发送", lambda: self.submit())
        self.send_button.setIcon(ui_icon("send"))
        self.send_button.setObjectName("primary")
        col.addLayout(bottom)
        split.addWidget(main)
        split.setSizes([265, 915])
        self.stack.addWidget(work)
        self.statusBar().showMessage("就绪 · 本地工作台")
        self.load_papers()
        self.refresh_tree()
        self.render()
        QTimer.singleShot(0, self.update_welcome_art)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "welcome_art"):
            self.update_welcome_art()

    def update_welcome_art(self):
        if not self.welcome_pixmap.isNull():
            available = self.welcome_art.size()
            ratio = self.welcome_art.devicePixelRatioF()
            pixmap = self.welcome_pixmap.scaled(
                max(1, round(available.width() * ratio)), max(1, round(min(540, available.height()) * ratio)),
                Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pixmap.setDevicePixelRatio(ratio)
            self.welcome_art.setPixmap(pixmap)

    @staticmethod
    def button(layout, label, callback):
        button = QPushButton(label)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def load_papers(self, selected=None):
        self.papers.clear()
        for paper in Library(self.data).list_papers():
            self.papers.addItem(paper["title"], paper["id"])
        if selected:
            self.papers.setCurrentIndex(self.papers.findData(selected))

    def refresh_tree(self):
        collapsed = set()
        def remember(node):
            if not node.isExpanded():
                collapsed.add(node.data(0, Qt.UserRole))
            for index in range(node.childCount()):
                remember(node.child(index))
        for index in range(self.tree.topLevelItemCount()):
            remember(self.tree.topLevelItem(index))
        self.tree.clear()
        def section(title, name, icon):
            node = QTreeWidgetItem([title])
            node.setData(0, Qt.UserRole, ("section", name))
            node.setIcon(0, ui_icon(icon))
            node.setFlags(Qt.ItemIsEnabled)
            font = node.font(0)
            font.setBold(True)
            node.setFont(0, font)
            node.setForeground(0, QColor("#6583a3"))
            self.tree.addTopLevelItem(node)
            return node
        folder_section = section("文件夹", "folders", "folder")
        recent_section = section("最近", "recent", "clock")
        folders = {}
        for item in self.store.value["folders"]:
            node = QTreeWidgetItem([item["title"]])
            node.setIcon(0, ui_icon("folder"))
            node.setData(0, Qt.UserRole, ("folder", item["id"]))
            folder_section.addChild(node)
            folders[item["id"]] = node
        for state in self.store.chats():
            meta = self.store.meta(state)
            node = QTreeWidgetItem([meta["title"] + "\n" + STATUS.get(state["status"], state["status"])])
            node.setData(0, Qt.UserRole, ("chat", state["session_id"]))
            node.setIcon(0, ui_icon("chat"))
            node.setToolTip(0, meta["title"] + "\n" + STATUS.get(state["status"], state["status"]))
            parent = folders.get(meta.get("folder"))
            if parent is not None:
                parent.addChild(node)
            else:
                recent_section.addChild(node)
            if state["session_id"] == self.selected:
                self.tree.setCurrentItem(node)
        self.tree.expandAll()
        def restore(node):
            if node.data(0, Qt.UserRole) in collapsed:
                node.setExpanded(False)
            for index in range(node.childCount()):
                restore(node.child(index))
        for index in range(self.tree.topLevelItemCount()):
            restore(self.tree.topLevelItem(index))

    def state(self):
        if not self.selected:
            return None
        return json.loads((self.data / "runs/chats" / self.selected / "state.json").read_text(encoding="utf-8"))

    def pick(self, item, column=0):
        kind, ident = item.data(0, Qt.UserRole)
        if kind == "chat":
            self.drafts[self.selected] = self.input.toPlainText()
            self.selected = ident
            self.input.setPlainText(self.drafts.get(ident, ""))
            self.render()

    def new_chat(self):
        self.drafts[self.selected] = self.input.toPlainText()
        self.selected = None
        self.input.setPlainText(self.drafts.get(None, ""))
        self.tree.clearSelection()
        self.render()

    def render(self):
        import html
        state = self.state()
        busy = self.worker is not None
        self.heading.setText(self.store.meta(state)["title"] if state else "新聊天")
        self.papers.setEnabled(not state and not busy)
        if state:
            self.papers.setCurrentIndex(self.papers.findData(state["paper_id"]))
        messages = self.store.history(state) if state else []
        self.transcript.clear()
        for message in messages:
            name = "你" if message["role"] == "user" else "Paper Agent"
            body = html.escape(message["text"]).replace("\n", "<br>")
            self.transcript.append(f'<p style="color:#727980;font-size:12px">{name}</p><p style="line-height:150%">{body}</p><br>')
        if not messages:
            self.transcript.setHtml("<h2>从一个想弄懂的问题开始</h2><p>选择已有论文，或拖入一份 PDF。描述你的目标，Agent 会与你一起制定学习规划。</p>")
        status = state["status"] if state else "new"
        self.status.setText((STATUS.get(status, "选择论文，输入学习要求。") + (f' · 模型调用 {state["model_calls"]}/{state["max_calls"]}' if state else "")) if not busy else "任务正在后台运行，可切换查看其他聊天。")
        if status == "blocked":
            self.status.setText("运行已停止：" + str(state.get("error", "未知错误")) + "。进度已保留，不会自动重放模型请求。")
        self.save_button.setVisible(status == "waiting_save")
        self.end_button.setVisible(status == "waiting_end")
        self.continue_button.setVisible(status == "waiting_end")
        self.verify_button.setVisible(status in ("waiting_answer", "waiting_save"))
        self.resume_button.setVisible(status in ("paused", "active"))
        terminal = status in ("blocked", "completed", "ended_early", "paused", "active")
        self.input.setEnabled(not busy and not terminal)
        self.send_button.setEnabled(not busy and not terminal)
        self.import_button.setEnabled(not busy)
        for i in range(self.actions.count()):
            self.actions.itemAt(i).widget().setEnabled(not busy)

    def launch(self, action, payload):
        if self.worker:
            return
        self.worker = Job(self.data, action, payload)
        self.worker.progress.connect(self.show_progress)
        self.worker.done.connect(self.finished)
        self.worker.failed.connect(self.failed)
        self.worker.finished.connect(self.released)
        self.worker.start()
        self.render()

    def show_progress(self, message):
        self.status.setText(message)
        self.statusBar().showMessage(message)

    def submit(self, text=None):
        text = text if text is not None else self.input.toPlainText().strip()
        if not text or self.worker:
            return
        state = self.state()
        if not state:
            if not self.papers.currentData():
                QMessageBox.information(self, "先导入论文", "请选择或拖入 PDF。")
                return
            from paper_agent.models.client import load_api_key, ModelError
            try:
                load_api_key()
            except ModelError:
                key, ok = QInputDialog.getText(self, "配置 OpenAI API Key", "仅保存在本机 config/.env.local，不会上传 GitHub。\n使用 OpenAI API 单独计费。请输入密钥：", QLineEdit.Password)
                if not ok or not key.strip():
                    return
                key = key.strip()
                if any(c.isspace() for c in key):
                    QMessageBox.warning(self, "格式有误", "密钥不能包含空白或换行。")
                    return
                env_path = ROOT / "config/.env.local"
                with env_path.open("a", encoding="utf-8") as stream:
                    stream.write("\nOPENAI_API_KEY=" + key + "\n")
            self.launch("create", (self.papers.currentData(), text))
        else:
            self.store.history(state).append({"role": "user", "text": {":end": "请求验证并准备结束", ":status": "恢复学习"}.get(text, text)})
            self.store.save()
            self.launch("reply", (self.selected, text))
        self.input.clear()
        self.drafts[self.selected] = ""

    def finished(self, result):
        if "papers" in result:
            self.stack.setCurrentIndex(1)
            # Keep the current conversation's paper fixed; imported PDFs are available for new chats.
            self.load_papers(result["papers"][-1]["id"] if result["papers"] else None)
            self.status.setText("PDF 已复制到论文库，可新建聊天使用。")
        else:
            self.store.collect(result["state"])
            if not self.selected:
                self.selected = result["state"]["session_id"]
        self.refresh_tree()

    def failed(self, message):
        self.refresh_tree()
        QMessageBox.warning(self, "操作未完成", message)

    def released(self):
        worker = self.worker
        self.worker = None
        worker.deleteLater()
        self.statusBar().showMessage("操作完成 · 进度已保留")
        self.render()

    def choose_pdf(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择论文", "", "PDF 文件 (*.pdf)")
        if paths:
            self.launch("import", paths)

    def dragEnterEvent(self, event):
        if not self.worker and event.mimeData().hasUrls() and all(u.isLocalFile() and Path(u.toLocalFile()).suffix.lower() == ".pdf" for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not self.worker:
            self.launch("import", [u.toLocalFile() for u in event.mimeData().urls()])
            event.acceptProposedAction()

    def open_pdf(self):
        ident = self.papers.currentData()
        if ident:
            QDesktopServices.openUrl(QUrl.fromLocalFile(Library(self.data).get(ident)["pdf_path"]))

    def add_folder(self):
        title, ok = QInputDialog.getText(self, "新建文件夹", "文件夹名称")
        if ok and title.strip():
            self.store.folder(title.strip())
            self.refresh_tree()

    def context_menu(self, point):
        item = self.tree.itemAt(point)
        if not item:
            return
        kind, ident = item.data(0, Qt.UserRole)
        if kind == "section":
            return
        target = self.store.value["chats"][ident] if kind == "chat" else next(f for f in self.store.value["folders"] if f["id"] == ident)
        menu = QMenu(self)
        rename = menu.addAction("重命名")
        moves = {}
        if kind == "chat":
            submenu = menu.addMenu("移动到文件夹")
            moves[submenu.addAction("未分类")] = None
            for folder in self.store.value["folders"]:
                moves[submenu.addAction(folder["title"])] = folder["id"]
        chosen = menu.exec(self.tree.viewport().mapToGlobal(point))
        if chosen == rename:
            title, ok = QInputDialog.getText(self, "重命名", "名称", text=target["title"])
            if ok and title.strip():
                target["title"] = title.strip()
        elif chosen in moves:
            target["folder"] = moves[chosen]
        self.store.save()
        self.refresh_tree()
        self.render()

    def settings(self):
        menu = QMenu(self)
        action = menu.addAction("返回 Agent 选择页")
        if menu.exec(self.cursor().pos()) == action:
            self.stack.setCurrentIndex(0)

    def closeEvent(self, event):
        if self.worker:
            QMessageBox.information(self, "任务仍在运行", "请等待当前操作完成再关闭窗口。你可以返回启动页或查看其他聊天。")
            event.ignore()
            return
        self.store.save()
        event.accept()


def configure_appearance(app):
    app.setStyle("Fusion")
    font = Path("C:/Windows/Fonts/msyh.ttc")
    if font.exists():
        QFontDatabase.addApplicationFont(str(font))
    app.setFont(QFont("Microsoft YaHei", 10))
    app.setStyleSheet("""
        QWidget { background:#f3f8ff; color:#253c57; }
        QWidget#sidebar, QTreeWidget { background:#e7f0fc; border:0; }
        QLabel#sidebarBrand { font-size:17px; font-weight:600; padding:0 10px 15px; color:#315b88; }
        QPushButton { background:#ffffff; border:1px solid #cfdef1; border-radius:10px; padding:10px 14px; text-align:left; }
        QPushButton:hover { background:#e1edff; border-color:#a9c7ec; }
        QPushButton:pressed { background:#cedff8; }
        QPushButton:disabled { color:#97abc2; border-color:#e0e9f5; }
        QPushButton#navigation { background:transparent; border:0; padding:11px 12px; }
        QPushButton#navigation:hover { background:#d5e5fa; }
        QPushButton#primary { background:#d9e9ff; border-color:#aecdf3; color:#214f89; }
        QTextBrowser { background:#f3f8ff; border:0; padding:16px; font-size:14px; }
        QPlainTextEdit { background:#ffffff; border:1px solid #c4d8f1; border-radius:14px; padding:12px; selection-background-color:#cce0ff; }
        QPlainTextEdit:focus { border:1px solid #7ca9df; }
        QComboBox { background:white; padding:8px; border:1px solid #cfdef1; border-radius:8px; }
        QTreeWidget::item { padding:9px 4px; border-radius:7px; }
        QTreeWidget::item:hover { background:#dce9fa; }
        QTreeWidget::item:selected { background:#ccdef7; color:#244c7d; }
        QMenu { background:#f8fbff; border:1px solid #cfdef1; padding:5px; }
        QMenu::item { padding:7px 22px; } QMenu::item:selected { background:#dceaff; }
        QStatusBar { background:#eaf2fe; color:#6583a3; }
        QSplitter::handle { background:#dce8f7; width:1px; }
        QScrollBar:vertical { background:transparent; width:8px; }
        QScrollBar::handle:vertical { background:#c0d3ed; border-radius:4px; min-height:25px; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
        QLabel#hero { font-size:32px; font-weight:600; } QLabel#heading { font-size:21px; font-weight:600; }
    """)


def main():
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PersonalAgents.Workbench")
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(ROOT / "assets/app-icon-cutout.ico" if (ROOT / "assets/app-icon-cutout.ico").exists() else ROOT / "assets/default-agent.svg")))
    configure_appearance(app)
    window = Window()
    window.show()
    if window.first_setup:
        QTimer.singleShot(0, lambda: QMessageBox.information(window, "首次使用", "已自动创建数据目录和空白画像、知识框架。\n请先编辑 data/results/1profile/current.json 和 data/results/2knowledgeframework/knowledge.txt，填写自己的情况。未知掌握程度不会被推断为已掌握。\n随后导入 PDF 并输入学习要求。首次发送时可配置自己的 OpenAI API Key。"))
    try:
        with chat_lock(ROOT / "data/runs/desktop"):
            result = app.exec()
    except Exception:
        QMessageBox.information(window, "工作台已打开", "另一个工作台窗口正在运行，请使用已有窗口。")
        result = 1
    sys.exit(result)


if __name__ == "__main__":
    main()

