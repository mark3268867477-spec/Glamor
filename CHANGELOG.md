# G'lamor 更新日志 (Changelog)

> 本文档记录 **G'lamor**（G'lam OS 官方零环境开发控制器 & PC 端协同中心）相对于上一版本（`f5a59f8` / `v1.0.0`）的核心更新内容。  
> 本次升级将 G'lamor 从纯粹的 `.gla` C/ELF 应用打包装机工具，正式扩展为 **小智 AI 的 Windows 桌面桥接、视觉 Computer Use、外部 MCP 网关与 SolidWorks 2025 3D CAD 自动化工作台**。

---

## v1.1.0（2026-11-25）— 小智 Windows PC 桥接、视觉 Computer Use、外部 MCP 挂载与 SolidWorks 2025 原生 COM 建模引擎

### 一、Tab 4 小智 PC 桥接工作台与 `glamctl pc-agent` 守护进程
- **双通道零配置桥接（`glam_studio.py`、`glamctl.py`、`pc_agent.py`）**：
  - 新增桌面工作台 Tab 4「小智 PC 桥接」与命令行无头模式 `glamctl pc-agent [--mode auto|serial|wifi] [--port COMx] [--wifi IP] [--mcp-config path.json]`。
  - 集成 `GlamorPcBridge`，支持通过 **USB 串口**（`115200` bps）或 **Wi-Fi HTTP**（`/api/pc_mcp/poll` & `/api/pc_mcp/reply`）自动探测并维持与 ESP32-S3 G'lam OS 的心跳连接。
- **Windows 本机快速执行器 `pc.control`（`PcToolExecutor`）**：
  - 覆盖系统状态查询、应用启停、窗口聚焦与枚举、浏览器 URL/搜索及标签页导航、组合热键/键入文本、鼠标点击与滚轮、系统音量与媒体控制、剪贴板读写、文件目录读写、Shell 执行，以及基于持久化 PowerShell UIA Worker（`_PersistentUiaWorker`）的控件树审查与精确点击。
  - 支持敏感操作安全确认门控与执行超时保护。

### 二、用户自配 API 的视觉 Computer Use 子代理（`pc.ai_agent`）
- **OpenAI / Anthropic 双协议桌面自定义配置（`vision_agent.py`）**：
  - 支持用户在 PC 端工作台自行填写 API Key、Base URL 与模型名称，同时兼容 **OpenAI 格式**（`build_openai_payload`，含图片视觉与推理回退处理）和 **Anthropic 格式**（`build_anthropic_payload`），并提供一键连通性自测（`test_ai_connection`）。
- **Set-of-Mark（SoM）视觉 + UIA 融合代理（`LocalComputerUseAgent`）**：
  - 结合 Win32 屏幕截图标注（`win32_capture_som_jpeg`）与实时 UIA 元素坐标索引（`win32_inspect_and_capture_som`），自动执行多轮屏幕观察与 GUI 操作，解决动态网页、B 站视频/链接点击及无标准控件桌面软件的交互难题。

### 三、外部 Stdio MCP 服务器动态挂载（`pc.ext_mcp`）
- **标准 `mcpServers` 协议网关（`ExternalMcpManager` / `_StdioMcpClient`）**：
  - 支持在工作台或配置文件中加载外部本地 Stdio MCP 服务器 JSON 配置（如文件系统、浏览器、专业工具 MCP 等），自动完成 `initialize` 握手与工具列表聚合，并通过 `pc.ext_mcp`（`action=list|call`）直接暴露给 ESP32 端小智调用。

### 四、SolidWorks 2025 原生 COM / VBScript 3D CAD 自动化引擎（`pc.solidworks`）
- **快捷参数化建模 + AI 自由建模（`sw_agent.py`）**：
  - 支持常规快捷动作：`get_status`、`new_part`、`create_box`、`create_cylinder`、`create_tube`（同时兼容 `inner_dia` 与旧版 `id` 参数）、`view`、`rebuild`、`save`、`export`（支持 `.SLDPRT` / `.STEP` / `.STL` / `.PNG` 等格式）；
  - 支持 **`ai_model` 自然语言自由建模**：由用户配置的 AI 模型生成 SolidWorks 2025 VBScript 并直接在活动零件中构建草图、拉伸与视图更新。
- **脚本引擎健壮性与超时治理**：
  - **自动拉起与实例保护**：执行建模指令检测到 SolidWorks 未运行时自动通过安装路径或快捷方式启动 GUI（`_launch_solidworks_app`），保持 `app.Visible = True` 与 `app.UserControl = True`；同时修复 `ConnectSolidWorks` 传参判断，避免查询状态时额外拉起隐藏重复 `SLDWORKS.exe` 进程。
  - **编码与语法自净化**：VBS 临时脚本统一改用 **UTF-16LE（带 BOM）** 写入并兼容多编码解码，消除中文路径/注释导致的 `cscript` `无效字符` 编译错误；新增 `_clean_args` 清洗部分模型输出的多余 `<arg_key>` / `<arg_value>` XML 标签；强化 `_extract_and_clean_vbs`（统一唯一清理入口，补全缺失前导连接代码、剥离 `Sub main()`/`Option Explicit`，并将类型声明清洗精确限定于已知 VBA / SolidWorks 类型以免误伤注释与文本）。
  - **语音链路超时对齐**：将 `pc.solidworks` 后台等待与脚本/API 超时对齐至 13s / 12s / 10s，配合固件侧 `14s` 等待上限与后台续跑提示，避免复杂 CAD 生成拖断小智语音长连接。

---

## v1.0.0（2026-11-19）— 初始发布
- 零环境 Windows x64 便携套件发布（内置精简 `xtensa-esp32s3-elf-gcc` 14.2.0 与 Python/Tk 运行时）。
- 支持多文件 `.c` 工程跨平台编译、17 符号内核 ABI 静态安全体检（`elf_check.py`）、`.gla` 打包、三通道热装机（Wi-Fi HTTP / USB 串口 / TF 卡直写）、远程应用卸载及 320×240 实时屏幕截图（`glam_studio.py`、`glamctl.py`）。
