# 学习规划准备

标识：learning-planning。状态：已接入 plan / plan-resume 入口、模型工具调用及规划保存；学习行为尚未执行。此为上层规划辅助说明，不是七种行为之一。

## 触发与输入

用户明确指定论文并表达目标后，先遵循 material-preparation.md 确认论文与内容版本可用。读取本次用户表达、材料准备结果，以及实际提供的个人画像、知识框架和必要论文材料；有关键歧义时向用户澄清，不要求用户先理解术语。

## 输出

按 schemas/learning-note.schema.json 组织学习笔记的规划部分：

- part：planning。
- goal：用户目标，保持原意；澄清结果和未确认假设在文字中分清。
- materials：每项成对填写实际 paper_id、paper_content_id；后者取材料准备返回的 parse_run_id，不编造新编号。
- plan：Agent 按目标编写候选步骤，每项给出 behavior 和 description。可以重复某行为，也可以不用某行为，路径可随反馈调整。

行为标识为 reading（阅读）、discussion（探讨）、qa（问答）、knowledge-recording（知识记录）、verification（理解验证）、framework-change（知识框架更改）、profile-change（个人画像更改）。当前后两项禁用，不安排进学习执行计划；阅读、探讨、问答、知识记录与 verification 已能独立运行，但提交规划不代表已执行。每个新规划必须包含 verification，作为正常完成前的必经环节，其余步骤由 Agent 自主规划。

本行为只形成规划内容，不替代 learning-review 生成结果，不伪造已经调用工具、学习完成或保存成功。程序通过 submit_plan 核对材料编号、结构与可选行为并保存；失败结果会返回模型或停止运行。如果提供上一版结果和真实问答，保留原 goal，优先处理识别出的理解缺口，不覆盖上一版。规划可以按需要在步骤描述中写明理解检查方向，暂不增加固定题数或额外必填字段。

统一 chat 入口自动衔接本说明对应的规划运行。需要用户澄清时在原终端暂停，规划成功后由调度模型选择下一行为。
