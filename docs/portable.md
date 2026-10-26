# Windows 便携版

解压完整文件夹到可写目录，双击 AgentWorkbench.exe。不要只复制 EXE；_internal、config、schemas、prompts、behaviors、templates、assets 必须随程序一起保留。

首次运行自动创建 data。个人画像和知识框架使用空白模板，需要填写自己的资料。导入 PDF 后输入学习要求，首次发送可填写自己的 OpenAI API Key，存放 config/.env.local。API 单独计费，需要网络；解析模型首次使用也可能下载。

本机数据在 EXE 旁的 data，模型缓存位于 .cache，临时文件位于 tmp。不写入安装目录之外的固定盘符路径。请不要解压到 Program Files 等只读位置。更新程序前先备份 data、config/.env.local 和 .cache；不要用空白数据覆盖自己的资料。

便携版不包含作者的 API Key、画像、论文或聊天。个人配图版外观与作者当前界面一致，公开版使用通用素材。首次启动、解析模型下载和大型依赖载入可能较慢。

未进行代码签名，Windows 可能提示未知发布者。仅从可信来源取得本程序。当前 Windows x64 构建，其他平台需要另外打包。

开发者从源码构建：安装源码版依赖以及 PyInstaller，然后执行 scripts/build-portable.ps1。默认公开素材，加 -Personal 使用本机私人配图（不应直接公开分发）。失败日志位于 build/portable；程序启动异常记录到 tmp/startup-error.log。

构建检查与已知边界见 docs/portable-verification.md。开发者可运行 AgentWorkbench.exe --portable-check（离线窗口、材料、模拟学习与恢复检查）；额外添加 --check-docling 会使用解析模型，首次缺缓存可能需要联网，不调用付费大模型。导出 ZIP 使用 scripts/archive-portable.py，只按白名单加入程序依赖和资源，不加入 data、.cache、tmp 或 .env.local。
