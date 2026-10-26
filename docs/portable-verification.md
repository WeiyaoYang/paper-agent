# Windows 便携构建验证（2026-10-27）

使用 PyInstaller 6.22.3、Python 3.13.5、PySide6 6.12.0 构建 Windows x64 onedir。应用资源和配置显式位于 EXE 旁，依赖位于 _internal。

## 证据

- 56 项源码离线测试通过。
- 生成的 AgentWorkbench.exe 在清空 PYTHONPATH、VIRTUAL_ENV，且 PATH 只保留 Windows 系统目录时完成离线自检。
- frozen=true；资源根目录正确定位到 EXE 所在目录。
- 启动页和聊天页真实渲染；配图和浅蓝主题保留。
- 真 PDF 导入、pdfplumber 解析成功。
- 使用模拟模型完成规划、阅读记录、真实提交模拟回答、理解验证、复盘结果保存、确认结束，并重新读取已完成会话。
- Docling 在复用本机解析模型缓存、HF_HUB_OFFLINE=1 的情况下完成实际 PDF 解析。缓存仅供本机检查，不进入 ZIP。
- 本轮没有真实 API 调用。尚未在另一台干净 Windows 机器或不同 Windows 版本上复测，也未验证首次联网下载模型。

## 修复的打包问题

1. 宿主开发环境 PATH 引入另一套工具的 ICU 等 DLL，导致 QtCore 的 DLL 加载失败。构建脚本限制 PATH，后处理排除来自项目、Python 运行时及 Windows 目录之外的 DLL。
2. latex2mathml 的符号表、docling_parse 的 PDF 资源未被默认 hook 收集；后处理显式补齐包数据。
3. 新 torchvision 使用 _C_stable/image_stable 扩展，默认 hook 仍按旧扩展名收集，导致 nms 算子缺失；后处理显式复制该包的 .pyd 和 .dll。

## 产物与边界

Personal ZIP 保留本机人物配图；Public ZIP 排除私人图片，显示通用默认图。两者都不含密钥、个人画像、论文、学习记录、日志或模型缓存。ZIP 必须完整解压，不能单独复制 EXE。未进行代码签名。

自检截图和报告位于本机便携目录 tmp 中，由白名单打包脚本排除。自检用临时数据自动清理，不写入作者现有学习数据。
