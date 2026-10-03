# CourseInbox · 课务收件箱

把学习通、课程群和教务通知，整理成**有原文依据、需要确认的学习任务**。
本地运行，数据保存在自己的电脑。基础版不需要平台密码或模型 API Key。

## 30 秒启动

项目目录：`D:\Doc\course-inbox`。

1. 双击 **start.cmd**，启动窗口保持打开，浏览器会打开 http://127.0.0.1:8765 。
2. 点击“加载示例数据”，体验 3 个任务、延期通知和缺少截止日期的通知。所有示例都标注为示例。
3. 点击“导入通知”，粘贴真实消息，填写来源和**消息发布时间**。也可选择截图，检查 OCR 识别文字后提取。
4. 在“消息收件箱”核对任务名称、课程、班级、截止和材料，再确认。
5. 在“待办任务”记录材料和任务状态；“截止日历”可导出 `.ics`。

首次启动为空库；示例只在点击加载后写入。重新启动会继续使用原来的 SQLite 数据。
停止服务：在启动窗口按 `Ctrl+C`。

如果浏览器没有自动打开，访问上面的本机地址。端口被占用时在 PowerShell 运行：

```powershell
cd D:\Doc\course-inbox
.\start.ps1 -Port 8877
```

需要 Python **3.10+**。本机启动器已验证使用现有 Python 3.12.14；它会查找 `CI_PYTHON`、项目虚拟环境、Codex 自带 Python 和系统 Python，不会自动安装软件。基础闭环只使用 Python 标准库。

## 已实现的基础功能

- 文本 / UTF-8 文件导入，Windows 本地中文截图 OCR；可选文本 PDF 提取。
- 提取课程、任务名称、截止日期、提交材料，保留完整通知和提取依据。
- 相对日期以消息时间为准；日期未写时刻则保留日期，不补 23:59；缺失或无效日期提示核对。
- 草稿可以编辑和忽略，确认后才写任务；延期、取消和材料变化都需要确认。
- 同课程、同班级、明确任务标识的消息可提出更新或关联来源。笼统名称和缺失课程不自动合并。
- 重复导入 / 手机重传幂等，确认幂等；版本冲突和较旧消息不能静默覆盖最新任务。
- 待开始、进行中、已做完、已提交、已取消；材料勾选；原文来源和变更历史。
- 按截止时间排列待办、课程与状态筛选、逾期 / 近期统计、网页截止提醒、月历和 `.ics` 导出。
- Android 通知接收接口和原生手机伴侣源码：应用白名单、配对令牌、手机本地排队。
- 可选大模型工具调用：查询任务、对照原文提出草稿、显示轨迹；最多8次调用，无直接任务写入工具。

规则提取适合结构较明确的作业、实验、考试通知。它不是通用自然语言理解系统，也不会登录学习通读取完整作业详情。
“已提交”由你手动确认，不代表原平台提交回执；电脑不会代交作业。

## 提醒和日期

网页打开时每15秒检查截止，浏览器通知需你主动授权。提醒阈值为24小时内、2小时内和逾期；相同任务、截止和阈值在当前浏览器只通知一次。页面关闭或电脑休眠时网页提醒不运行。

日历导出使用北京时间换算 UTC；只有日期的任务导出为全天事件，不生成具体时刻。精确时刻任务附提前2小时闹钟。是否响铃依赖导入的日历客户端；导出为快照，截止变更后需要再次导入。

未写年份暂按消息年份并提示核对；普通“周五”默认最近一个周五并提示，跨年、模糊表达仍需人工检查。不要把规则提取当成零遗漏保证。

## 截图和 PDF

截图识别使用 Windows 自带 `Windows.Media.Ocr`，上传只交给本机脚本处理，不发往第三方 OCR 服务。已在本机使用 `zh-Hans-CN` 实际识别 `samples/sample-notice.png`。系统需安装 OCR 语言，支持 PNG/JPG/BMP，最大8 MB，过大尺寸可能被系统拒绝。

识别后先检查文字，特别是人名、材料名称和日期。图片未识别成功时可直接复制文字。Linux / Docker 基础镜像不提供此 Windows OCR。

PDF 文本提取为可选功能：

```powershell
python -m pip install -r requirements-optional.txt
```

最多30页，不支持加密 PDF；扫描 PDF 请改用页面截图。Pillow 只用于生成验收图片，运行时截图 OCR 不依赖 Pillow。

## 接入 Android 手机

电脑默认只监听 `127.0.0.1`。需要手机接入时，先停止当前服务，再双击 **start-lan.cmd**，打开网页“手机连接”查看地址、令牌和白名单。

手机与电脑需在可互通网络。填电脑局域网 IP，不要填手机自己的 `127.0.0.1`。若系统防火墙拦截，请自行按需允许 Python 的专用网络访问；启动器不会自动修改防火墙。

手机工程见 [android/README.md](android/README.md)，需要 Android Studio、JDK17、SDK35、Gradle8.11.1。当前只交付源码，**本机没有 Android SDK，因此尚未构建 APK、安装或实机验证**。

授权通知访问后，手机只接收白名单应用已发布的系统通知，保留通知时间并尝试上传。电脑不可达时最多保存200条；客户端启动、监听连接、收到新通知或手动重试时补传。基础版未实现可靠周期后台重试。通知全文、附件、历史和系统隐藏内容可能无法取得，原平台详情需另行核对。

iPhone 使用截图或文本导入；此版本没有 iOS 跨应用通知监听。
令牌保存在 `data/access-token.txt`，仅分享给自己的设备。局域网 HTTP 适用于可信网络，远程使用 HTTPS。默认白名单只有 `com.chaoxing.mobile`，其他应用需在两端添加实际包名。

## 可选模型工具调用

未配置模型时界面明确显示“本地规则模式”。基础功能正常使用。

复制 `.env.example` 为 `.env`，配置支持工具调用的本地 Ollama 模型，再启动：

```dotenv
CI_MODEL_PROVIDER=ollama
CI_MODEL_BASE_URL=http://127.0.0.1:11434
CI_MODEL=你已安装且支持工具调用的模型名称
```

也支持 Chat Completions 兼容接口：`CI_MODEL_PROVIDER=openai`、`CI_MODEL_BASE_URL`、`CI_MODEL`、`CI_MODEL_API_KEY`。Base URL 按供应商要求包含 `/v1` 等路径，程序追加 `/chat/completions`。密钥仅在服务端读取，`.env` 不进入 Git；选择外部接口会把当前导入文字和范围内查询结果发送给该供应商。

模型先读任务，再调用 `propose_task` 生成草稿。服务器锁定课程/班级范围，校验原文和日期依据，最多8次工具调用；任务确认另走人工接口。自由问答只开放读取工具。

调用失败时会显示错误，你可以在导入面板显式改用规则模式。不会把规则结果伪装成模型结果。
本机没有可用模型服务：工具调用协议和边界已用受控模型响应测试，**尚未做真实大模型推理验收**。

## 测试和证据

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run-tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run-tests.ps1 -Browser
```

浏览器验收需要 Node.js、Playwright 和 Edge；当前电脑已具备，脚本会启动自己的临时数据库并清理。其他机器可先安装 `npm install --no-save playwright`。无需对正式数据运行验收。

截图 OCR 单独检查（需可选 Pillow）：`python -m scripts.verify-ocr`。
测试记录见 [docs/verification/acceptance.md](docs/verification/acceptance.md)，浏览器结果见 `docs/verification/browser-result.json`，截图在 `artifacts/`。

## 数据与备份

SQLite、访问令牌、白名单设置都放在 `data/`，目录被 Git 忽略。最可靠的恢复方式：先停止服务，再复制整个 `data/`；恢复时停止服务，把备份放回同一路径。

网页提供 JSON 导出用于查看和保存记录；当前没有 JSON 导入恢复界面。访问令牌不在 JSON 导出中。初版为单人本地工具，没有多人账号、权限角色或同步平台提交状态。

## Docker（提供配置，尚未在本机验证）

```bash
docker compose up --build -d
```

访问 http://127.0.0.1:8765 。容器中无法使用 Windows OCR，文字闭环仍可运行。命名卷保存 SQLite。
Docker 转发请求不属于服务端回环地址，因此需要手动输入令牌：在自己的终端运行 `docker compose exec courseinbox cat /app/data/access-token.txt`，填入浏览器连接页。不要把令牌写入公共日志或分享截图。
此配置默认只映射电脑回环端口。手机连接需自行改端口绑定，并配置可信网络 / HTTPS。

## 源码入口

- `server.py`：服务启动；`courseinbox/http.py`：API 和授权。
- `courseinbox/core.py`：日期、去重、任务确认、历史、统计和日历。
- `courseinbox/agent.py`：可选模型、受限工具循环。
- `courseinbox/files.py`、`scripts/windows-ocr.ps1`：文件提取。
- `web/`：中文页面；`android/`：手机通知伴侣。
- [docs/API.md](docs/API.md)：接口协议和手机事件示例。

官方实现参考：[Android 通知监听](https://developer.android.com/reference/android/service/notification/NotificationListenerService)、[Windows OCR](https://learn.microsoft.com/en-us/uwp/api/windows.media.ocr.ocrengine)、[Ollama 工具调用](https://docs.ollama.com/capabilities/tool-calling)。
