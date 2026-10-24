# Zyll财经 安卓 App 编译指导

这是 Zyll财经 的原生安卓 App 源码（Kotlin + Jetpack Compose），与网站共用账号和数据，通过网站的 App 接口（`/api/app/v1`，见 `docs/APP_API.md`）通信。

功能：

- **经济日历**：重要程度、货币筛选；节假日和休市提示；“下一个非常重要”倒计时（到点未公布时显示“等待数据”，不会跳来跳去）；点击事件查看中文解释，以及历史公布值和预测值的折线图。
- **行情**：
  - 自选指数，最多 5 个；
  - 我的个股，与持仓分析双向同步；
  - 成交最多榜，可按成交额或成交量切换；
  - 实时推送；
  - 点击代码时先选数据服务商，再提示风险，然后跳转。
- **持仓分析**（原“自选”，底部标签“持仓”）：
  - 含汇率的盈亏，算法与网站完全一致；
  - “扣除通胀”“计入汇率”两个开关（与网页同步），卡片、图表和每只股票一起切换；
  - 总市值、今日、持仓、总盈亏四张卡片，各带分析和折线图；
  - 总资本，可记录入金、出金、换汇；
  - 交易记录的增删改，可选“用之前换好的美元”；
  - AI 导入券商结单（PDF、Excel、CSV、截图，可一次选多个文件），已经记录过的交易自动跳过，核对后一键导入，可整批撤销。
- **暗盘 · 美期**：场外卖空、ATS 周报、个股暗池、股指期货、CFTC 持仓。
- **我的**：
  - 登录和注册（网站开启人机验证时自动改为网页登录）、忘记密码；
  - 卡密激活与续期（后台关闭会员模式时完全不显示）；
  - 设备管理、修改密码；
  - 服务器地址设置、涨跌配色；
  - 检查更新（支持强制更新）；
  - 导出数据、删除账号。

---

## 一、准备工作（只需做一次）

| 需要 | 说明 |
|---|---|
| 电脑 | Windows 10/11、macOS 或 Linux，内存建议 8GB 以上 |
| **Android Studio** | 2024.2（Ladybug）或更新版本：<https://developer.android.com/studio>（国内可用 <https://developer.android.google.cn/studio>） |
| JDK 17 | Android Studio 自带，不用另装 |
| Android SDK 35 | 第一次打开项目时 Android Studio 会提示安装，点同意即可 |
| 网络 | 第一次编译要下载约 1GB 的 Gradle 和依赖库。国内网络慢的话见下面“国内网络加速” |

## 二、打开项目

1. 把整个 `android` 文件夹复制到电脑上，**路径里最好不要有中文和空格**，例如 `D:\zyll\android`。
2. 打开 Android Studio，选 **Open**，选中 `android` 文件夹（里面有 `settings.gradle.kts` 的那一层），点 OK。
3. 右下角会开始 **Gradle Sync**，第一次可能要 5~20 分钟，等它跑完。
   - 提示安装 SDK 或 “Accept licenses” 时点同意。
   - 提示 “Trust project” 时选 Trust。

### 国内网络加速（下载卡住或报 `Could not resolve` 时）

1. 打开 `settings.gradle.kts`，把里面 `maven.aliyun.com` 那几行开头的 `//` 删掉（共 5 行），保存后点右上角的 🐘 **Sync Now**。
2. Gradle 本体下载慢时，打开 `gradle/wrapper/gradle-wrapper.properties`，把 `distributionUrl` 改成：
   ```
   distributionUrl=https\://mirrors.cloud.tencent.com/gradle/gradle-8.10.2-bin.zip
   ```

## 三、填写你的服务器地址

在 `android` 文件夹里，把 `local.properties.example` 复制一份改名为 `local.properties`。Android Studio 可能已经自动生成了这个文件，那就直接在里面追加。然后填写：

```properties
zyll.serverUrl=https://你的域名
zyll.appKey=
```

- `zyll.serverUrl`：你的网站地址，**必须是 https**。正式版不允许 http；调试版允许 http，方便连局域网测试服务器。
- `zyll.appKey`：后台 → **安卓 App** 页里开启了“要求 App Key”才需要填，内容和后台一致；没开启留空。
- 不填就用占位地址 `https://zyll.example.com`。App 里也可以在 **我的 → 服务器设置** 中随时修改，所以先不填也能编译。

同时确认后台 **安卓 App** 页的“开放 App 接口”是开启的（默认开启）。

## 四、在手机上调试运行

1. 手机打开 **开发者选项**（设置 → 关于手机 → 连点“版本号”7 次），再打开 **USB 调试**。
2. 用数据线连电脑，手机上点“允许 USB 调试”。
3. Android Studio 顶部设备栏选中你的手机，点绿色 ▶ **Run**。

没有手机也可以用模拟器：Device Manager → Create Virtual Device，选一个机型和 Android 14/15 系统镜像。

调试版的包名是 `com.zyll.finance.debug`，可以和正式版同时装在一台手机上。

## 五、打包正式版 APK

### 1. 生成签名文件（只做一次，千万保存好）

Android Studio 菜单 **Build → Generate Signed App Bundle / APK → APK → Next → Create new...**，填写路径（例如 `android/zyll-release.jks`）、密码、别名 `zyll`，点 OK。

也可以用命令行：

```bash
keytool -genkeypair -v -keystore zyll-release.jks -alias zyll -keyalg RSA -keysize 2048 -validity 36500
```

> ⚠️ 签名文件和密码丢了，以后发布的新版本就**无法覆盖安装**，用户只能卸载重装。请把 `.jks` 文件和密码备份到安全的地方，并且不要上传到网上或 Git。

### 2. 配置签名

把 `keystore.properties.example` 复制为 `keystore.properties`，填上刚才的文件名、密码和别名。

### 3. 打包

- **Android Studio**：右侧 Gradle 面板 → `app` → `Tasks` → `build` → 双击 **assembleRelease**；
- **或命令行**：在 `android` 目录执行
  ```bash
  ./gradlew assembleRelease        # Windows 用 gradlew.bat assembleRelease
  ```

生成的文件在 `app/build/outputs/apk/release/app-release.apk`，可以直接发给用户安装，或者上传到你的网站。

## 六、发布新版本与强制更新

1. 修改 `local.properties`：`zyll.versionCode` **加 1**（必须是整数，每次都要比上次大），`zyll.versionName` 改成例如 `1.1.0`。
2. 按第五步重新打包，把 APK 上传到能直接下载的地址，例如你网站的静态目录或对象存储。
3. 打开网站后台 → **安卓 App**，填写：
   - **最新版本号（versionCode）**：例如 `2`；
   - **最新版本名**：`1.1.0`；
   - **APK 下载地址**：上一步的链接；
   - **更新说明**：会显示在 App 的更新弹窗里；
   - **最低可用版本号**：低于这个版本号的 App 会被**强制更新**，不更新就不能继续使用。平时保持 0 或旧值即可。
4. 用户打开 App 时会自动检查。点“以后再说”后，同一个版本不再提示；在 **我的 → 检查更新** 里可以手动检查。

## 七、不装 Android Studio，用命令行编译（可选）

1. 安装 JDK 17。
2. 下载 Android 命令行工具（Command line tools only），解压到例如 `~/android-sdk/cmdline-tools/latest/`。
3. 安装 SDK：
   ```bash
   export ANDROID_HOME=~/android-sdk
   $ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager "platforms;android-35" "build-tools;35.0.0" "platform-tools"
   yes | $ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager --licenses
   ```
4. 在 `local.properties` 里写 `sdk.dir=/你的路径/android-sdk`。
5. 在 `android` 目录执行 `./gradlew assembleDebug`（调试版）或 `./gradlew assembleRelease`（正式版）。

## 八、运行单元测试

```bash
./gradlew test
```

`app/src/test` 里的 `PnlParityTest` 用 300 组随机用例（一半扣除通胀）核对 App 的盈亏算法和服务器 `pnl.py` 的结果，另有物价指数插值用例（`cpi_cases.json`）；网页的 `pnl.js` 也用这组用例测过，三端必须一致。修改 `core/Pnl.kt` 后请务必运行这个测试。

## 九、网页登录与 AI 导入

- 网站开启登录人机验证后，App 点“登录”会打开浏览器，在网页登录并点“授权登录”后自动回到 App。回跳地址是 `zyllfinance://auth`，在 `AndroidManifest.xml` 里声明。
- 如果手机上同时装了调试版和正式版，回跳时系统可能会问用哪个 App 打开，选你正在登录的那个即可。
- AI 导入在“持仓分析”页顶部，入口只在后台开启该功能后出现。文件通过系统文件选择器选取，不需要存储权限。

## 十、常见问题

| 现象 | 解决办法 |
|---|---|
| `SDK location not found` | 在 `local.properties` 里加 `sdk.dir=...`；用 Android Studio 打开一次也会自动生成 |
| `Could not resolve com.android.tools.build:gradle` / 一直下载 | 网络问题，按第二步的“国内网络加速”处理 |
| `Unsupported class file major version` / `requires Java 17` | Settings → Build Tools → Gradle → Gradle JDK 选 **17**（或 Android Studio 自带的 jbr-17） |
| 安装时提示“签名不一致” | 手机上已经装了用别的签名打包的版本，先卸载再装 |
| App 里提示“服务器未开启 App 接口” | 后台 → 安卓 App → 打开“开放 App 接口” |
| 提示“App Key 不正确” | `zyll.appKey` 和后台不一致，或者在 App 的 我的 → 服务器设置 里改 |
| 提示“服务器返回的数据无法解析” | 服务器地址填错了，例如多了路径，或者填成了后台地址。只填域名，例如 `https://zyll.example.com` |
| 正式版连不上 http 地址 | 正式版只允许 https，请给网站配置证书；调试版允许 http |
| 实时行情不动 | 确认反向代理放行了 WebSocket：Nginx 要给 `/api/app/v1/ws` 加 `proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade";` |
| 编译报某个 Compose 函数参数不对 | 见下面“关于首次编译”，把完整报错发给我 |

## 十一、修改名称、包名、图标

- **应用名称**：在 `local.properties` 里写 `zyll.appName=你的名字`。
- **包名**：写 `zyll.applicationId=com.你的.包名`。只改安装包的 ID，代码目录不用动。改了包名就是一个新 App，不能覆盖旧版本。
- **图标**：`app/src/main/res/drawable/ic_launcher_foreground.xml`（前景）和 `res/values/colors.xml` 里的 `icon_bg`（背景色）。也可以用 Android Studio 的 **File → New → Image Asset** 从图片生成。
- **配色**：`app/src/main/java/com/zyll/finance/ui/theme/Theme.kt`。

## 十二、代码结构

```
android/
├─ settings.gradle.kts / build.gradle.kts / gradle.properties   Gradle 配置
├─ gradlew, gradle/wrapper/                                    Gradle 8.10.2
└─ app/
   ├─ build.gradle.kts            依赖版本、服务器地址（BuildConfig）、签名
   └─ src/
      ├─ main/java/com/zyll/finance/
      │  ├─ MainActivity.kt        入口；前台时连接实时推送，后台断开
      │  ├─ core/Pnl.kt            连汇盈亏算法（移植自网站 pnl.js）
      │  ├─ core/Format.kt         金额、万/亿、日期格式化
      │  ├─ core/Pkce.kt           网页登录用的 PKCE（S256）
      │  ├─ data/Api.kt            OkHttp 调用 /api/app/v1，统一错误处理
      │  ├─ data/Session.kt        令牌（加密存储）、服务器地址、设备 ID
      │  ├─ data/Live.kt           WebSocket 实时推送，自动重连
      │  ├─ data/Models.kt         接口数据模型
      │  ├─ data/Zyll.kt           全局状态：登录、配置、版本检查
      │  └─ ui/                    界面（Compose）
      │     ├─ AppRoot.kt          底部导航、全局弹窗、版本更新
      │     ├─ components/         卡片、图表、外部跳转、代码联想
      │     └─ screens/            日历 / 行情 / 持仓分析（含 AI 导入）/ 暗盘·美期 / 我的
      └─ test/                     盈亏算法一致性测试
```

主要依赖：

- Android Gradle Plugin 8.7.2、Kotlin 2.0.21、Compose BOM 2024.10.01（Material 3）；
- OkHttp 4.12、kotlinx-coroutines 1.8.1、androidx.security-crypto 1.0.0；
- minSdk 24（Android 7.0），targetSdk 35。

## 关于首次编译（请务必阅读）

源码写好时，编写环境里没有 Android SDK，也连不上 Google 的 Maven 仓库，所以没能在那边完整编译出 APK。

已经做过的验证：

- **核心算法**（`core/`）用真实的 Kotlin 2.0.21 编译器编译，并运行了单元测试：300 组用例与服务器结果完全一致，网页登录用的 PKCE 也对照 RFC 7636 的示例测试过。
- **数据层**（`data/`）对照 OkHttp、org.json 和 Android 接口的签名做了完整的类型检查。
- **界面**（`ui/`）对照 Compose 和 Material 3 的接口签名做了完整的类型检查。
- 用脚本按 App 的请求方式（路径、方法、请求体与代码一致）把 44 个接口调用在测试服务器上全部跑通。

即便如此，第一次用 Android Studio 编译时，仍可能遇到个别库版本差异导致的小报错，例如某个参数名或弃用警告。遇到时，把 **Build** 窗口里第一条红色 `e:` 开头的报错完整复制给我，我来修正。
