# 新版界面融合说明

本目录是 `D:\Doc\CampusInbox-ui-integration`。原项目 `D:\Doc\CampusInbox` 保留，不参与融合修改。

## 启动

双击根目录 **启动融合版.cmd**（或 start.cmd），浏览器打开 http://127.0.0.1:8877 。如浏览器未自动打开，手动访问该地址。Ctrl+C 停止网页服务。

副本默认主服务 8877、手机提醒 8878、QQ 8879，与原项目的 8765/8766/8767 分开。手机、浏览器组件或 QQ 重新连接副本时，需要使用副本页面显示的端口与配对信息。副本的桌面程序也使用独立端口和单实例名称；其托盘与后台功能保留，点击消息/任务入口会打开新版网页。

日常启动只需已有 Python 环境，不需要安装 Node；构建产物已放入 `web/ui`。

已同步 2026-11-01 的统一新建任务更新：从「我的任务 → 新建任务」使用文本、图片、文件和手动填写。MinerU 配置、附件恢复及备份要求见 [新建任务与附件解析](task-import.md)。更新后需重启 Python 服务。

## 界面与功能对应

- 首页、任务列表、周/月日历、站内提醒、设置：Vue 3 组件，直接使用原项目受鉴权 API。
- 收件箱审核、完整任务详情、学习通与 QQ 同步、手机连接、识别评测：复用现有完整业务工作区，以同源内嵌方式整合并采用统一配色。不是将这些业务逻辑重新实现一遍。
- 导入、OCR、材料进度、消息来源、补充要求、更新/取消/合并/冲突、平台状态核对继续走原服务。
- 保留“已做完”与“已提交”的区别；仅日期截止不补造具体时刻。只有确认提交后才移出未提交列表。
- 网页提醒的已读/稍后/提前窗口保存在当前浏览器；后台、手机与微信推送仍由原服务管理。页面关闭后不承诺浏览器通知。
- 日历 `.ics` 导出仍导出原服务的全部日历，按钮已明确标注范围。
- `/legacy.html` 是独立完整工作区，可作为回退入口；数据库无结构迁移。
- Android 原生 UI 保留，本次未改写 Android App，也未重新验证真实账号和真机权限。

## 统一页面风格

网页风格以小组仓库 `frontend/src/styles/campus.css` 为准：暖白背景 `#faf9f5`、紫色主色 `#7045e8`、浅紫选中态、白色圆角卡片、统一字体及中性灰紫边框。黄色提示与粉红错误色保留各自含义。

原业务工作区使用 `ci-workspace` 主题，统一规则集中在 `web/integration.css`，覆盖收件箱、任务和消息详情、同步、手机连接、评测及完整工作区入口。内嵌布局、弹窗关闭和业务流程保持原有行为；修改这些样式后浏览器刷新即可加载。

## 前端维护

前端源码位于 `frontend`。修改后运行：

```powershell
cd D:\Doc\CampusInbox-ui-integration\frontend
npm ci
npm run lint:check
npm run format:check
npm test
npm run build
```

需要 Node.js 24。生产文件构建到 `web/ui`，由 Python 服务提供。前端开发服务器仅用于本地开发；常规验收应使用构建后的 Python 同源入口。

完整回归入口：`powershell -ExecutionPolicy Bypass -File scripts/check-integrated.ps1 -Browser`。浏览器测试使用独立临时数据库与合成通知，不启动正式账号同步。

## 来源

新版视觉样式及前端工程配置参考小组成员仓库 [Elias-2z/CampusInbox](https://github.com/Elias-2z/CampusInbox)，基于提交 `6307102e6b6f895127584c7ae6e09b39b9fa0674`。原样式保存在 `frontend/src/styles/upstream.css`；业务与数据规则继续使用本项目。该来源记录不代表对上游许可证作出变更。

统一新建界面与 MinerU 托管解析协议适配自更新提交 `1d02252df342fe4c837b386e16c4b83a5d0cd3f4`；保留原 Python 运行环境，没有切换到上游 FastAPI / SQLModel 后端。
