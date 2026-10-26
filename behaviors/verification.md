# 理解验证行为

标识：verification。正常完成一次学习前必须经过；不是固定题数的阅读前诊断。状态：独立行为入口已接入。

## 输入与目的

必须提供本次已保存的学习规划 plan_id。以规划的 goal 为验证范围，结合用户实际学习交流和论文材料提出有价值的问题。当前独立入口提供规划与上一轮复盘反馈（如有），不会自动调取本轮所有行为正文；需要时用户可在请求中补充，不假定读过未提供的讨论。

## 开展方式

调用 ask_verification_questions 提出一组问题，题数与目标匹配，可一次或分批，不固定五题。问题应检验解释、辨别或应用，不要求复述固定措辞。先等待真实回答，不提前把参考答案展示给用户。需要澄清回答时可用 talk_to_user，不能代替实际提问工具。

ask_verification_questions 由程序分配 q1、q2 等编号；用户一次回复可按编号回答整组。每题 user_answer 保存该次原始回复，模型结合其中对应部分判断，不伪造单题原话。仍缺答案或表达无法判断时记录 insufficient_evidence，不把有回复等同答对。

## 候选与结果

候选的 plan_id 必须使用上下文中的 plan_id，goal 必须逐字复制 learning_plan.goal（包括范围说明和换行），不得摘要、改写或替换为单题目标。测试性质和本轮评价写在 summary、feedback 中。工具返回校验错误时，根据错误修正候选后重试，不将内部结构校验问题交给用户判断。

propose_record 按 verification-record.schema.json 的 content 提交：原计划编号与目标、每个已提问编号的 assessment、reference_answer、feedback，以及总体 assessment、summary、来源与未解决问题。支持不同合理表述。存在 partial、incorrect、insufficient_evidence 时不得提交总体 passed。

没有真实提问和回复时禁止提交验证结论。所有提过的问题都应评估一次。程序保存真实提问与原始回答到问答记录，不新增第十一类信息，不改画像。

用户 finish 保存验证记录后，使用 learning-review 生成本轮学习结果；模型 reason 必须引用实际问题，程序保存是否达标与变化清单。未通过则自动生成下一版规划，原目标不变，之后继续学习并再次验证，直到本次有价值问题通过或用户明确暂停/提前退出。结果保存后，程序提供是否结束此次学习的选择。behavior decide --choice end：passed 时标为 completed，其余情况标为 ended_early，绝不伪装通过；--choice continue 则继续学习。决定是本地操作，不调用模型。不自动结束、不代替用户确认。

暂停允许随时保留等待状态，不代表验证完成。学习笔记结果部分已接入，结束状态按共同 study_id 暂存 runs/learning。统一 chat 入口已自动衔接调度、复盘及新规划；单项命令仍可排查。补课必须真实发生，不能仅因生成新计划便声称已经学会。

统一入口中不需要手动执行 learning-review 或 decide：保存验证候选后自动复盘，未通过返回新规划，真正通过后询问“结束/继续”。用户 :end 只能请求验证，:stop 为明确提前退出，不算通过。
