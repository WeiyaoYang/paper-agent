# 数据结构约定

JSON Schema Draft 2020-12。正式记录在 data/results，模型指令在 prompts/behaviors，程序负责校验、编号和保存。十类信息不等于十个 Schema：同一类可有不同片段，候选和运行状态也有自己的结构。

## 文件与作用

| Schema 文件 | 用途及是否接入 |
|---|---|
| paper.schema.json | 论文登记，已接入写入校验 |
| paper-content.schema.json | 一个解析版本的正文和位置，已接入写入校验 |
| learning-note.schema.json | 学习笔记 planning 部分，已接入规划工具和保存 |
| learning-result.schema.json | 学习笔记 result 部分，已接入复盘保存 |
| reading-record.schema.json | 正式阅读记录 |
| qa-record.schema.json | 正式普通问答记录 |
| discussion-record.schema.json | 正式探讨记录 |
| knowledge-note.schema.json | 正式知识笔记 |
| knowledge-point.schema.json | 正式知识点 |
| verification-record.schema.json | 理解验证的专用问答记录，仍属第七类 |
| knowledge-recording.schema.json | 模型提交知识记录的候选包，不单独成为正式知识 |
| chat-state.schema.json | 统一会话运行状态，保存与恢复时校验，不是第十一类正式信息 |

个人画像仍由 profile.py 校验既有结构，知识框架目前是原始文本，尚未制定节点 Schema。

## 论文与内容

论文 id 稳定，sha256 去重，pdf_path 指向原文件；status、page_count、error、active_run_id 表示解析情况。程序维护时间与 revision，标题和来源需有依据。

内容 paper_id 关联论文，parse_run_id 标识版本，pages 保存逐页文本，blocks 保存文本和位置；坐标解释遵循 bbox.coord_origin，不假定都是左上角原点。parse 保存工具元信息，limitations 明确限制。

旧历史版本可能未保留逐页文本，pages_status 明确标记，不能把空 pages 当成论文没有正文。保留原始工具产物以追溯。

## 学习笔记两部分

planning：part=planning、goal、materials（成对的 paper_id/paper_content_id）、plan（behavior、description）。paper_content_id 使用实际 parse_run_id。七种行为中，理解验证必经，两个核心更改禁用；由程序在规划提交时检查。

result：part=result、plan_id、goal_achieved、reason、question_ids、verification_record_id、changes。是否达到目标取自已保存验证，模型只提炼 reason；题号须真实，未通过时覆盖已识别缺口。

changes 的每项为 object_type、object_id、action、description，程序收集已关联的真实产物。材料使用为 used，新记录为 created，复用旧知识点为 used；当前无记录修改功能，不编造 modified。

新规划与每轮结果分别保存，旧文件不覆盖。study_id、revision、previous_plan_id 和复盘反馈放运行状态，保留同一次学习的版本关联；下一版原目标保持不变。

## 行为记录与来源

正式行为记录都有 schema_version、id、run_id、paper_id、paper_content_id、created_at、content；关联学习时由程序加 plan_id。阅读/问答/探讨含真实 messages；模型候选不能填写虚构用户话语或分配编号。

sources 指向具体版本、页码、可选块和连续 quote，必须来自已提供或读取的页面。程序核对真实引文，不证明模型解释正确。知识笔记和新知识点保持 unverified；名称或唯一别名匹配时复用既有编号，不做语义去重。

## 理解验证

content 保存 plan_id、原 goal、逐题 assessment/reference_answer/feedback、总体判断、总结与来源。verification_questions 由程序保存实际题号、问题、目标和原始回复。

一次回复可回答整组，每题保留同次原始文本，不伪造拆分原话。没有实际提问回复、漏评或部分正确却总体 passed 会被拒绝；语义判断本身仍由模型负责。

正常结束必须有当前验证和对应 result，且原规划和材料仍匹配。passed + end 为 completed；明确提前退出为 ended_early；继续学习不算完成。

## 版本与限制

已存在的 UUID 及旧记录不强制迁移。论文和内容的 schema_version 可省略以兼容旧文件；新行为记录版本为 1；planning/result 用 part 区分。字段变更需要同步模型工具、程序与必要迁移。

唯一性、外键归属、引文、目标是否漂移、状态转换和预算需要程序检查，不能只靠 JSON Schema。format 日期检查由相关校验器启用；正式时间由程序生成。
