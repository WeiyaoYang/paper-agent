# Paper Agent · 个人论文学习工作台

一个本地运行的论文学习 Agent，提供 Windows 桌面界面和终端入口。结合用户画像、知识框架及论文材料制定学习规划，自主选择阅读、问答、探讨或知识记录，通过真实回答验证理解，保存有来源的学习成果。

## 下载 Windows 便携版

[**下载 Windows x64 便携版 ZIP**](https://github.com/WeiyaoYang/paper-agent/releases/latest/download/AgentWorkbench-Windows-x64-Public.zip) · [全部发行版本](https://github.com/WeiyaoYang/paper-agent/releases)

1. 下载约 **413 MiB** 的 ZIP，完整解压到可写目录。
2. 双击 `AgentWorkbench.exe`，无需安装 Python 或 uv；不要只复制 EXE，旁边的 `_internal` 等目录也必须保留。
3. 按首次启动提示填写自己的画像和知识框架，导入本地 PDF，输入学习要求。
4. 首次发送时填写自己的 OpenAI API Key。API 单独计费；首次 PDF 解析可能需要下载模型。

便携版提供与源码版相同的启动页、淡蓝色聊天界面、文件夹管理和学习流程。公开包使用通用配图，不包含作者的密钥、画像、论文、聊天或解析模型缓存。用户数据在 EXE 旁的 `data/`，无需建立作者电脑上的目录。

当前构建面向 Windows x64，已在本机完成独立 EXE、PDF 解析及模拟学习保存恢复验证；尚未在其他电脑上复测，未进行代码签名。校验文件随 Release 提供。

## 从源码开始使用（Windows）

Windows 便携版的使用与构建见 [便携版说明](docs/portable.md)：完整解压后双击 `AgentWorkbench.exe`，保留当前桌面布局，不需另装 Python。首次解析模型下载及 API 调用仍需要网络。构建产物存放于 `dist/portable/`，不提交到 Git 源码仓库。

1. 安装 [uv](https://docs.astral.sh/uv/getting-started/installation/)，下载本项目到任意可写目录；无需使用作者的盘符或目录。
2. 在项目目录打开 PowerShell，运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

安装脚本在项目内创建 `.venv`，安装模型客户端、桌面界面及 Docling，并自动创建数据目录。首次安装需要网络和较充足磁盘空间，PDF 解析模型可能在首次使用时下载。虚拟环境不要从别人的电脑直接复制。

3. 双击项目中的 **启动工作台.vbs**。可选创建桌面快捷方式：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\create-shortcut.ps1
```

4. 根据首次启动提示编辑自己的资料：
   - `data/results/1profile/current.json`：个人背景、偏好，未知掌握状态保持未知。
   - `data/results/2knowledgeframework/knowledge.txt`：自己的知识分类。
5. 选择 Paper Agent，导入或拖入本地 PDF，输入本次学习要求。首次发送会提示填写自己的 OpenAI API Key，保存在被 Git 忽略的 `config/.env.local` 中。也可以提前从 `config/.env.example` 复制并填写；ChatGPT 订阅不等于 API 额度。

公开源码不附带作者画像、论文、聊天、密钥或私人配图。缺失的数据目录由程序初始化，已有数据不会被覆盖。默认使用通用书本图标；本机私人插画可保留，不进入发布包。

## 如何交互

左侧有新聊天、文件夹和最近会话；右键聊天可重命名或移动到文件夹。输入框 Enter 换行、Ctrl+Enter 发送。候选记录使用“确认保存”；验证通过后选择结束或继续。设置菜单可返回 Agent 选择页。运行任务时可查看其他聊天，同一时间只执行一个操作。

```text
指定论文与目标 → 准备材料 → 制定学习规划
                              ↓
                   自主选择行为 ↔ 交互与保存
                              ↓
                       提问并验证理解
                    ↙                  ↘
             有缺口：重新规划      通过：复盘、确认结束
```

个人画像和知识框架在学习过程中只读。模型负责判断与解释，代码负责状态、工具、结构及来源检查、调用预算和保存。

## 终端与开发

```powershell
.\scripts\run.ps1 init
.\scripts\run.ps1 chat
.\scripts\run.ps1 chat '论文完整路径.pdf' --goal '理解方法的输入输出和核心直觉'
.\scripts\run.ps1 chat --resume CHAT_ID
```

终端模式同样需要配置自己的密钥。仅使用终端可安装 `uv pip install --python .venv/Scripts/python.exe -e '.[models,docling]'`，无需桌面依赖。轻量 PDF 解析可使用终端的 `--backend pdfplumber`；桌面默认使用 Docling。

离线测试（包含桌面测试，需安装 desktop 依赖）：

```powershell
. .\scripts\env.ps1
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

测试使用合成材料和模拟模型，不需要作者数据、API Key，也不产生模型费用。

## 项目结构

| 目录 | 职责 |
|---|---|
| `src/paper_agent/agent/` | 规划、行为执行、复盘、会话协调 |
| `src/paper_agent/app/` | 桌面和终端入口 |
| `src/paper_agent/ingestion/` | 论文归档、解析、来源定位 |
| `prompts/`、`behaviors/` | 总指令、调度提示与可选行为说明 |
| `schemas/` | 结构化信息和运行状态约定 |
| `config/` | 模型参数和本机密钥（密钥不提交） |
| `templates/` | 可公开的空白画像和知识框架 |
| `data/` | 本机材料、十类结果、运行状态、日志（不提交） |
| `assets/` | 通用公开素材；个人插画本机保留 |
| `scripts/` | 安装、启动、快捷方式和源码导出 |

Agent 与前端放在同一个仓库，前端复用 LearningSession，不复制业务流程。

## 发布与数据边界

执行 `powershell -ExecutionPolicy Bypass -File .\scripts\release.ps1` 生成 `dist/paper-agent-source.zip` 和对应干净源码目录。脚本按白名单导出，不复制真实 data、密钥、缓存、虚拟环境、日志或私人插画。上传 GitHub 时应以该干净目录为仓库根目录，避免上传整个个人工作区。

项目提供源码安装和 Windows 便携版构建脚本。移动源码实例时需重建虚拟环境；便携版无需另装 Python，但必须保留完整文件夹。历史材料及记录可能包含绝对路径，已有学习数据跨目录迁移尚无自动修复工具；首次使用的干净实例不受影响。

## 配置、费用与限制

`config/model.toml` 用于连通测试，`config/planning.toml` 用于学习流程。选择自己的账号可访问的模型。API 请求发往 OpenAI 官方端点；发送本次所需材料、画像、框架并产生费用，失败不自动重试。默认每次学习最多 40 次模型尝试，次数预算不等于金额预算。

当前面向单用户、单篇论文的本地学习。尚无 RAG 向量库、画像自动更新、知识框架修改或跨机器数据迁移工具。解析及模型评分可能出错，引用核验不能证明讲解一定正确。

尚未选定开源许可证；发布前应由维护者明确授权条款。第三方依赖遵循各自许可证；个人配图未纳入公开包。

更多说明：[桌面工作台](docs/desktop.md)、[完整流程](docs/workflow.md)、[业务结果](docs/business-results.md)、[结构约定](schemas/README.md)、[数据目录](data/README.md)、[发布说明](docs/distribution.md)。
