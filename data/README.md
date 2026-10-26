# data 数据目录

这是直接归属 data 的唯一文件。正式内容以 results 为准，当前用 JSON/文本存储；旧数据库只作迁移备份。

桌面工作台新增 `runs/desktop/workspace.json`，保存聊天标题、文件夹归属和展示历史；该目录内的锁文件用于防止重复打开工作台。它们是界面运行数据，不属于十类正式结果。导入 PDF 仍统一复制到 `papers/`，新材料的 source 字段登记导入前路径。

## 材料与十类结果

| 目录 | 内容 |
|---|---|
| papers/ | 原始 PDF，导入时复制，登记以 pdf_path 引用；现有 pi0.pdf |
| results/1profile/ | current.json 当前画像，学习中只读 |
| results/2knowledgeframework/ | knowledge.txt 当前框架原文，尚未节点化，学习中只读 |
| results/3learningnotes/ | planning_编号.json 规划；PLAN_ID.VERIFICATION_RUN_ID.result.json 每轮结果 |
| results/4papers/ | 论文编号.json，登记、来源、哈希、解析状态和当前版本 |
| results/5papercontents/ | 论文编号/parse_编号.json，逐页正文、内容块、坐标和工具元信息 |
| results/6readingrecords/ | read_编号.json，阅读范围、重点、来源和实际交互 |
| results/7qarecords/ | qa_编号.json 普通问答、verify_编号.json 理解验证；旧 reading_会话目录仅历史留存 |
| results/8discussionrecords/ | discussion_编号.json，观点、分歧、阶段结论与真实交互 |
| results/9knowledgenotes/ | note_编号.json，知识内容、概念关联、来源与未验证状态 |
| results/10knowledgepoints/ | concept_编号.json，名称、别名、分类和关联；不表示用户已经掌握 |

行为记录关联 plan_id，学习内由统一入口自动传入。单独启动而未关联的记录不会被时间猜测混入结果。知识笔记以 concept_ids 关联知识点，已有概念可复用。

## 运行产物

| 目录 | 内容 |
|---|---|
| artifacts/docling/ | 论文/解析版本下的 docling.json 和 document.md，原始工具输出 |
| artifacts/exports/ | 可读 JSON/Markdown 导出副本；旧副本可能保留迁移前路径 |
| runs/chats/ | chat_编号/state.json，当前阶段、用户输入、子任务引用、调用计数和恢复点；selection-N.json 保存选择响应；.active.lock 为进程锁 |
| runs/planning/ | 每版规划的指令、上下文、工具历史与响应，含 study_id、revision、previous_plan_id |
| runs/behaviors/ | 真实交互、工具历史、候选和保存状态；候选不是正式知识 |
| runs/reviews/ | 根据验证生成 reason 的输入、模型响应、结果路径和下一版规划引用 |
| runs/learning/ | 按共同 study_id 保存整个学习当前状态及结束决定，不替代正式 result |
| runs/diagnostics/ | 旧摘要诊断输入与候选，仅留作历史 |
| runs/migration-backup/ | library.sqlite3 迁移前备份，当前程序不读写 |
| logs/model-usage.jsonl | 调用状态、token、耗时、错误，不包含密钥或完整提示词 |

快照和交互可能含个人材料，应作为私有数据；运行数据不提交版本管理。API 发送范围按当前任务选取，Python 环境、配置、密钥和缓存位于 data 外。

## 约定

正式 UUID 编号稳定；每版规划与每轮结果单独保存，不覆盖原目标。新规划未通过时可再迭代，但不自动代答或无限调用。

旧存储没有历史逐页文本的版本保留显式 pages_status 标记，不能伪造。旧输入快照保留原样，其中路径不是当前配置。工作区根部框架文件是历史来源，程序读取本目录副本。

默认单用户单进程写入，chat 入口有锁，但不要与单项命令并发操作。批量普通错误会回滚新文件，断电级事务尚未实现。缓存、导出与模型候选不能自动当作已验证知识。
