# Android 通知伴侣

本机已于 2026-10-04 成功构建 0.2.0 [调试安装包](../artifacts/mobile/courseinbox-companion-0.2.0-debug.apk)，并通过 APK 签名检查。支持 Android 8.0（API 26）及以上，应用包名为 `cn.courseinbox.companion`。

APK 保存在本机 `artifacts/mobile/`，该目录不随 Git 提交。旧版通路已由用户确认发送成功；新版覆盖安装、自动发现及学习通真实通知仍需手机验收。[本次构建记录](../docs/verification/android-build.md)。

## 安装和学习通配对

1. 将 APK 通过 USB 或自己的文件传输方式复制到安卓手机，安装“CourseInbox 伴侣”。
2. 电脑需运行局域网模式 `start-lan.cmd`。首次从本机模式切换时先停止原服务，启动后保持窗口运行。
3. 手机和电脑连接可互通的网络。电脑网页“手机连接”显示手机应填写的服务地址；填写电脑的局域网 IPv4，不要填写手机自己的 `127.0.0.1`。
4. 在电脑网页点击“显示配对令牌”，将令牌填写到手机伴侣。填写班级/分组，并将应用白名单设为 `com.chaoxing.mobile`。电脑端也需允许同一包名，点击手机“保存配置”。
5. 点击手机“授权通知访问”，在系统设置中启用 CourseInbox。返回后检查是否显示“通知监听已连接”。
6. 可以先点击“发送示例通知事件”测试上传通路。示例标题和正文明确写有“示例”，这一步不算真实学习通通知或新版发现恢复验收。
7. 等待学习通在手机通知栏实际发出一条新通知。在电脑“消息收件箱 → 消息记录”核对来源 `Android · com.chaoxing.mobile`、消息原文和时间。有明确作业内容时，再核对任务草稿并确认。

连接排查先用手机浏览器打开服务地址后的 `/api/health`，应返回 `status: ok`。如果打不开，检查电脑服务、当前 IP、网络是否互通及防火墙；访客网络或校园网络可能隔离设备；本用户手机需继续用校园 Wi-Fi，应先核对当前电脑地址及受限防火墙规则，必要时联系网络管理员。手机上传失败时消息保留在队列，可点击“立即重试补传”。

## 接收范围和补传

使用 Android 官方 NotificationListenerService，接收用户授权后、白名单应用发布的新系统通知。通知可能只有摘要、被截断或隐藏；完整课程内容仍需在学习通核对。分组摘要会过滤，通知标题、正文和原通知发布时间上传到电脑。

离线队列保存在应用私有 SharedPreferences，系统备份关闭。只有明确收到 HTTP 200/201 才移除事件，最多保存 200 条；满队列会提示并记录未保存条数。当前补传由打开客户端、监听连接、新通知或手动重试触发，没有网络变化监听或可靠的周期后台重试。

HTTP 配对仅允许私有 IPv4/localhost，远程服务需配置 HTTPS。令牌只用于自己的设备；APK 不包含电脑访问令牌。保存手机配置不修改电脑防火墙或学习通账号。

## 从源码构建

需要 JDK 17、Android SDK 35 / Build Tools 35.0.0、Gradle 8.11.1。AGP 固定为 8.9.2，无第三方运行依赖。可用 Android Studio 打开本目录；源码没有附带 Gradle wrapper jar。

安装好环境后，在本目录运行 `gradle assembleDebug`。原始 APK 位于 `app/build/outputs/apk/debug/app-debug.apk`。

本次构建工具保存在 `../artifacts/android-build/`，路径记录在 `build-environment.json`。构建日志为 `assemble-debug.log`，签名日志为 `apk-signature.log`。这些本机构建文件不随 Git 提交。

官方参考：[NotificationListenerService](https://developer.android.com/reference/android/service/notification/NotificationListenerService)、[AGP 8.9 compatibility](https://developer.android.com/build/releases/agp-8-9-0-release-notes)。

## 0.2.0 自动配对与地址恢复

从电脑“手机连接”页下载安装包，或通过自己的 USB/文件传输方式复制。覆盖安装并保留原应用，不先卸载；版本号 2，保留包名和原调试签名。升级是否成功应以手机显示 0.2.0 为准。

1. 电脑安装发现组件并配置限定防火墙规则（见主 README），运行 `start-lan.cmd`。
2. 手机继续连接校园 Wi-Fi，填写电脑页面的固定配对名称和访问令牌。班级自由填写，例如“软件工程1班”，白名单仍为 `com.chaoxing.mobile`。
3. 点击“自动寻找并配对电脑”。正确的现有私有 IPv4 地址可加快配对；也可留空地址，只通过发现寻找。成功后应显示“已配对 CourseInbox-...”。
4. 点击“发送示例通知事件”，检查待传队列清零和电脑收件箱消息。
5. 以后电脑 IP 变化时，打开伴侣、收到新通知或点击“立即重试补传”会寻找同一台电脑；不保证系统休眠时定时寻找。

15 秒内无法找到或验证时保留消息。若校园网屏蔽发现，手动更新地址后重试；新地址也需通过原电脑身份验证。令牌变化需重新点击配对；换另一台电脑先点“重新配对另一台电脑”，该动作保留待传消息。

协议测试：用 JDK 17 编译 `PairingProof.java`、`ConnectionResolver.java` 与 `protocol-tests/` 内两个测试主类，再运行 `PairingProofTest`、`ConnectionResolverTest`。`PrivateAddressTest` 使用实际 Android 编译输出的 classes 检查 IPv4 过滤。这些 JVM 测试验证协议和恢复策略，不替代 Android 系统发现与安装验收。

本次升级的手机自动发现、覆盖安装配置保留及 IP 变化恢复仍需真机确认。[验收记录](../docs/verification/mobile-autodiscovery.md)。


独立检查修正：发现期间短时获取 Wi-Fi 多播锁并在所有退出路径释放（CHANGE_WIFI_MULTICAST_STATE 是正常权限）；单候选解析最多3秒，总发现预算15秒；手动地址的未保存编辑不会被后台刷新覆盖。Android 13 T Extensions 7 / Android 14+ 可取消解析；更旧系统没有公共取消接口，会忽略迟到结果并在系统忙时限时重试其他候选，具体系统行为仍需真机确认。
