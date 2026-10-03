# Android 通知伴侣（源码，尚未在本机构建 APK）

需要 Android Studio、JDK 17、Android SDK 35 / Build Tools 35.0.0、Gradle 8.11.1。AGP 固定为 8.9.2，无第三方运行依赖。

1. Android Studio 打开本目录。安装上述 SDK，Gradle 设置使用 8.11.1（此源码包没有附带 Gradle wrapper jar）。
2. 或在安装好 Gradle 8.11.1 后运行 `gradle assembleDebug`。APK 路径 `app/build/outputs/apk/debug/app-debug.apk`。
3. 电脑运行 `start-lan.cmd`。在手机填写电脑局域网地址和访问令牌，保存配置。
4. 两端设置应用包名白名单，手机点击“授权通知访问”。
5. 先发送明确标注为示例的事件，再用目标应用实际发布的一条通知验证授权和正文可见范围。

监听基于 Android 官方 NotificationListenerService，只能收到系统已发布的通知；通知可能被截断或隐藏。跳过通知分组摘要，避免重复提取。

队列保存在应用私有 SharedPreferences，系统备份关闭。每条事件保留通知发布时间；服务器确认 HTTP 200/201 后才移除。最大200条，超限显示未保存计数。网络失败或 HTTP 拒绝均保留事件。打开客户端、监听连上、收到新通知及手动重试时补传；基础版没有可靠的周期后台重试。

HTTP 配对仅允许私有 IPv4/localhost，可信局域网可用；远程应配置 HTTPS。不要把令牌公开。保存配置不会修改电脑防火墙或平台账号。

这台电脑没有 Android SDK/Gradle，因此没有宣称 APK 编译、安装、监听和实体手机端到端验收成功。电脑接口已用相同 JSON 协议验证，下一步需完成实机联调。

官方参考：
- [NotificationListenerService](https://developer.android.com/reference/android/service/notification/NotificationListenerService)
- [AGP 8.9 compatibility](https://developer.android.com/build/releases/agp-8-9-0-release-notes)
