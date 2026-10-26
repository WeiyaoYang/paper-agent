"""Launch with the project's pythonw.exe; keep all project runtime data on D:."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
try:
    from paper_agent.app.desktop import main
    main()
except Exception:
    import ctypes
    ctypes.windll.user32.MessageBoxW(None, "工作台启动失败。请使用项目虚拟环境并安装 desktop 依赖。", "Agent 工作台", 16)
