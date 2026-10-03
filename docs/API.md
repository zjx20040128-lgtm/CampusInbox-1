# CourseInbox API v0.1

默认服务 `http://127.0.0.1:8765`。除 health、静态页面和回环 bootstrap 外，所有接口都需要 `Authorization: Bearer <data/access-token.txt>`。JSON POST/PATCH 使用 `Content-Type: application/json`。

浏览器 Origin 必须为当前服务同源；Host 必须为本机地址和服务端口。普通远程浏览器无法调用 bootstrap 取令牌，需手动输入已有令牌。服务默认仅回环监听，局域网显式启动。

## 读取

- `GET /api/health`：健康状态。
- `GET /api/bootstrap`：只向本机回环、合法 Host 的请求提供访问令牌，禁止缓存。
- `GET /api/state`：任务、待确认草稿、消息记录、摘要和实际运行模式。
- `GET /api/tasks`，`GET /api/tasks/{id}`：列表与详情（来源 / 变更历史）。
- `GET /api/messages`：最近500条消息。
- `GET /api/proposals`：待确认草稿。
- `GET /api/dashboard`：尚未提交、已提交、7天截止、逾期及提醒。
- `GET /api/settings`：应用白名单、运行模式、监听地址，不包含模型密钥。
- `GET /api/calendar.ics`：日历文件，不含取消任务。
- `GET /api/export.json`：记录导出，不含访问令牌；没有导入恢复 API。

## 导入与确认

`POST /api/messages`：

```json
{
  "text":"《软件工程》 第三次作业：请提交实验报告、源代码。截止：10月12日 23:59。",
  "source":"学习通",
  "captured_at":"2026-10-03T16:00:00+08:00",
  "course":"",
  "scope":"计科1班",
  "mode":"rules"
}
```

mode 为 rules / agent / default。默认按服务端配置。明确 agent 但未配置模型返回400，模型失败返回502。文本最多30000字。201为新增，200 + duplicate=true为重放。返回 message、proposals、mode、trace；这一步不创建任务。

草稿包含 candidate（title/course/scope/deadline/kind/requirements/operation/evidence/warnings）、action（create/update/link/cancel）、target_id、expected_version、before。

`POST /api/proposals/{id}/confirm`，JSON对象为可选编辑字段：title、course、scope、deadline、kind、requirements。空对象按草稿确认。已有目标的名称、课程、班级不可改，需重新导入重新匹配。与已有任务链接/更新时，空截止和空材料保留已有值。确认时根据编辑后内容重算有效动作；纯link只关联来源，发生修改则按update执行时间和版本保护，并以实际动作写历史。

截止为 `YYYY-MM-DD` 或带时区 ISO 时间；缺失用 null。requirements 为字符串列表。确认幂等，过期版本和较旧消息覆盖返回409，任务不变。

`POST /api/messages/{id}/reanalyze`：空对象或 `{ "mode":"rules" }`，按原文及原发布时间重新规则提取；保留消息ID，旧待确认草稿变为已忽略，生成使用当前任务版本的新草稿。已确认任务不改变，已确认草稿和历史仍保留。可用来恢复状态更新后的过期草稿，不必伪造原文或时间。
`POST /api/proposals/{id}/dismiss` 忽略草稿，原消息保留。

`PATCH /api/tasks/{id}`：

```json
{"status":"done","checklist":[true,false],"expected_version":1}
```

字段都可选。checklist为与当前材料数等长的布尔数组。状态：pending/in_progress/done/submitted/cancelled。建议带expected_version避免并发覆盖。done仍提示提交；submitted为手动确认。

## 文件与助手

`POST /api/files/extract`：`{"filename":"notice.png","content_base64":"..."}`。文件最大8 MB，请求最大12 MB。返回text、engine、needs_review，不直接导入任务。PNG/JPG/BMP使用Windows OCR；TXT/MD需UTF-8；PDF需可选pypdf，最多30页。

`POST /api/assistant`：`{"question":"我有哪些待提交任务？","course":"软件工程","scope":"计科1班"}`。scope为null时查询全部班级。仅有读取工具，不直接写任务。返回answer、mode、trace、limited。

`POST /api/settings`：`{"allowed_packages":["com.chaoxing.mobile"]}`，最多30个包名。电脑接收和手机采集两端都要设置。
`POST /api/demo` 加载明确标注的合成示例；不会向学习平台取数据。

## Android 通知事件

`POST /api/mobile/notifications`：

```json
{
  "package_name":"com.chaoxing.mobile",
  "notification_key":"0|com.chaoxing.mobile|123|tag|10001",
  "title":"《软件工程》 第三次作业",
  "text":"请明天18:00前提交实验报告。",
  "captured_at":"2026-10-03T08:00:00Z",
  "scope":"计科1班",
  "course":""
}
```

captured_at 必填，使用通知的postTime，不用上传时间替代。package必须在白名单。只持久化和生成规则草稿，不自动确认，也不把后台通知发送至外部模型。

手机遇到200/201才移除本地事件；401/403或网络失败留在队列。重复事件返回200、duplicate=true，内容改变生成新的消息。来源为 `Android · 包名`。

## 错误

返回 `{"error":"可读说明"}`。400输入无效、401缺令牌、403来源/Host/应用未授权、404不存在、409版本冲突、502模型问题、500内部异常。令牌不出现在URL、工具结果或消息日志。
