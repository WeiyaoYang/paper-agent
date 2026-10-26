# 开发与排查命令

日常优先使用 README 的 chat。这里保留单项接口，便于开发、检查或处理现场。所有命令在 paper-agent 目录执行；可在子命令前用 --data 指定数据目录。

## 论文与资料（无 GPT 调用）

```powershell
.\scripts\run.ps1 list
.\scripts\run.ps1 import data/papers/pi0.pdf --title '论文标题' --source '来源链接'
.\scripts\run.ps1 show PAPER_ID
.\scripts\run.ps1 check PAPER_ID
.\scripts\run.ps1 parse PAPER_ID
.\scripts\run.ps1 parse PAPER_ID --backend pdfplumber
.\scripts\run.ps1 read PAPER_ID --start 2 --end 3
.\scripts\run.ps1 export PAPER_ID
.\scripts\run.ps1 profile
.\scripts\run.ps1 model-config
```

parse 默认 Docling；公式增强 --formula 需要额外模型，尚未真实验证。导入复制原文件并按哈希去重，输出 PDF 位于 data/papers。

## 模型规划（有费用）

```powershell
.\scripts\run.ps1 model-test
.\scripts\run.ps1 plan PAPER_ID --goal '希望理解的内容'
.\scripts\run.ps1 plan-resume PLANNING_ID --reply '澄清回答'
```

model-test 是短句连通测试；其他命令根据上下文可能多次调用。plan-resume 仅恢复 awaiting_user。

## 单行为

```powershell
.\scripts\run.ps1 behavior start reading PAPER_ID --plan-id PLANNING_ID --request '本次阅读要求'
.\scripts\run.ps1 behavior start verification PAPER_ID --plan-id PLANNING_ID --request '验证本轮目标'
.\scripts\run.ps1 behavior reply BEHAVIOR_ID --text '原始回答或补充要求'
.\scripts\run.ps1 behavior show BEHAVIOR_ID
.\scripts\run.ps1 behavior pause BEHAVIOR_ID
.\scripts\run.ps1 behavior finish BEHAVIOR_ID
.\scripts\run.ps1 learning-review BEHAVIOR_ID
.\scripts\run.ps1 behavior decide BEHAVIOR_ID --choice end
```

start/reply/learning-review 调用 API；show/pause/finish/decide 为本地操作。可用行为包括 reading、discussion、qa、knowledge-recording、verification。前四类 --plan-id 可选，学习中应填写以纳入结果；verification 必须填写。

awaiting_user 等回复；awaiting_finish 等审阅保存；验证保存后先 learning-review，再 decide end/continue。未通过的明确 end 为提前结束。普通行为 finish 不结束整个学习。

## 环境与测试

```powershell
. .\scripts\env.ps1
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

测试使用临时数据与模拟模型，不调用 API。重建环境时加载 env.ps1，再使用 D 盘的 uv 缓存和运行时：

```powershell
uv python install 3.13.5
uv venv .venv --python "$env:UV_PYTHON_INSTALL_DIR\cpython-3.13.5-windows-x86_64-none\python.exe"
uv pip install --python .venv/Scripts/python.exe -r requirements.txt
uv pip install --python .venv/Scripts/python.exe --no-deps --no-build-isolation -e .
```

requirements.txt 为当前 Windows 依赖清单，已去掉固定绝对路径的 editable 项目引用；项目单独 -e 安装。模型权重需要保留或另行准备。
