# 行为说明库

行为类似本项目自己的轻量 Skill：Markdown 描述用途、输入、工具和产物，src 负责真实执行与保存。文件不自动生效，也不是平台安装的 Skill 包。

| 文件 | 当前用途与边界 |
|---|---|
| reading.md | 可选：读取解释指定材料，保存阅读记录 |
| discussion.md | 可选：讨论观点、依据和限制，保存探讨记录 |
| qa.md | 可选：灵活解释/问答，保存真实对话及反馈 |
| knowledge-recording.md | 可选：提炼相互关联的知识点、知识笔记，保持未验证 |
| verification.md | 必经：依据规划提问、真实回答和逐题判断，保存验证问答 |
| framework-change.md | 禁用，未来独立沟通与确认流程 |
| profile-change.md | 禁用，未来独立沟通与确认流程 |
| material-preparation.md | 辅助：确认论文和内容可用，已有版本复用 |
| learning-planning.md | 辅助：形成/修订规划，不作为第八种可选行为 |

统一 chat 入口把当前目录简介提供给调度模型，选定后加载对应完整说明。行为可共享代码，不要求一个 .py 对应一个行为。可按需读取同一次学习允许的实际记录，不能随意访问本地文件。

候选先展示，输入“保存”提交，之后自动接回调度。验证后自动复盘，失败形成新规划，通过询问结束。结果复盘不是新增行为，仍服务于同一学习循环。

单项行为命令保留供开发排查，见 [命令说明](../docs/commands.md)。总规则见 [agent-policy](../prompts/agent-policy.md)，正式结构见 [schemas](../schemas/README.md)。
