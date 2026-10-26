# 文件地图

当前自有文件用途如下；第三方依赖内部不逐一列出。日常入口见 [README](../README.md)。

## 资料与约定

| 路径 | 用途 |
|---|---|
| README.md | 日常启动和交互 |
| config/.env.local | 私密 API 密钥，不输出或提交 |
| config/.env.example | 空密钥模板 |
| config/model.toml | 连通测试模型参数 |
| config/planning.toml | 规划、行为、调度和复盘共用模型参数 |
| prompts/agent-policy.md | 总职责、只读边界、真实回答、验证与预算规则 |
| prompts/dispatch.md | 根据实际进展选择下一行为 |
| prompts/learning-review.md | 根据验证生成结果 reason |
| behaviors/ | 七行为和两项辅助说明，见 [行为目录](../behaviors/README.md) |
| schemas/ | 正式信息、候选及运行状态结构，见 [结构说明](../schemas/README.md) |
| data/ | 所有材料、正式结果和运行产物，仅由 [data/README.md](../data/README.md) 详述 |

## 源码

| 路径（src/paper_agent 下） | 用途 |
|---|---|
| __main__.py | python -m paper_agent 入口 |
| __init__.py、各包 __init__.py | 包标记和运行环境初始化 |
| runtime.py | D 盘缓存和临时路径配置 |
| app/cli.py | 命令参数及入口分派 |
| app/chat.py | 终端多行交互、选论文、恢复与进程锁 |
| agent/session.py | 持久会话、模型选行为、自动衔接、总调用预算 |
| agent/planning.py | 规划工具循环、澄清、模型工具校验与规划保存 |
| agent/behavior.py | 五种学习行为、真实交互、候选审阅、保存和结束决定 |
| agent/review.py | 结果汇总、reason、失败后下一版规划与版本关联 |
| ingestion/library.py | PDF 登记、去重、Schema 校验、解析版本和读取导出 |
| ingestion/docling_backend.py | Docling 原始输出与位置规范化 |
| memory/profile.py | 初始画像读取和字段校验，不修改画像 |
| models/client.py | 官方 API 请求、响应工具项、错误与用量日志 |
| storage/json_files.py | UTF-8 JSON 临时写入后原子替换 |
| storage/behavior_records.py | 五类行为产物及验证问答的编号、来源、校验与保存 |

## 测试与项目环境

| 路径 | 用途 |
|---|---|
| tests/test_library.py | 材料去重、解析、检查、持久化与错误 |
| tests/test_docling_normalization.py | 跨页和位置提取、公式缺失提示 |
| tests/test_profile.py | 画像读取与未知字段 |
| tests/test_models.py | 密钥处理、响应、工具续接与日志 |
| tests/test_planning.py | 规划、澄清恢复、编号和禁用行为 |
| tests/test_behaviors.py | 四行为记录、知识复用、来源和受限记录读取 |
| tests/test_verification.py | 真实问答、逐题判断与结束约束 |
| tests/test_learning_review.py | 结果、真实关联及失败后新版规划 |
| tests/test_session.py | 完整统一会话、恢复、覆盖选择、预算和进程锁 |
| scripts/env.ps1、run.ps1 | 设置本项目环境、转发启动参数 |
| pyproject.toml | 项目元信息与依赖 |
| requirements.txt | 当前 Windows 环境依赖版本清单 |
| uv.toml | 本地 uv 缓存设置 |
| .gitignore | 忽略密钥、运行数据与环境，只保留 data/README.md |
| .runtime/、.venv/ | Python 本体和第三方依赖 |
| .cache/、tmp/、__pycache__/ | 模型权重、缓存、临时文件和字节码；模型权重需保留 |

## 文档

workflow.md 说明实际完整流程，business-results.md 是业务约定，implementation-status.md 记录当前能力和验证，commands.md 是排查接口，review-report.md 是本轮检查报告，development-log.md 是按时间保留的历史。

工作区 tools/README.md 是总入口；knowledge.txt 与 paper-reading-profile.md 保留作历史来源，当前正式画像和框架副本在 data/results。
# 桌面界面补充（2026-10-27）

- `启动工作台.pyw`、`启动工作台.vbs`：无终端独立窗口启动入口，复用 D 盘虚拟环境。
- `src/paper_agent/app/desktop.py`：原生界面与后台任务，调用原有 LearningSession，不复制 Agent 逻辑。
- `src/paper_agent/app/desktop_store.py`：聊天标题、文件夹和展示历史的持久化。
- `data/runs/desktop/`：上述界面数据及工作台进程锁；不属于十类正式结果。
- `docs/desktop.md`：桌面使用、导入位置、运行限制说明。

