# Zyll财经 安卓 App 接口文档（v1）

所有 App 接口都在 `https://你的域名/api/app/v1/` 下，请求和返回都是 JSON（UTF-8）。

## 1. 通用约定

| 项目 | 说明 |
|---|---|
| 认证 | 登录后拿到 `token`，之后每个请求带请求头 `Authorization: Bearer <token>` |
| App Key | 后台开启“要求 App Key”时，每个请求还要带 `X-App-Key: <后台设置的值>`（WebSocket 可用 `?app_key=`） |
| Cookie | App 前缀下服务器会忽略 Cookie，只认 Bearer Token |
| 时间 | 所有时间戳都是 Unix 秒（UTC）；`*_ms` 结尾的是毫秒 |
| 金额 | 美股价格单位是美元；自选盈亏的本币由用户设置决定 |
| 错误 | HTTP 状态码 ≥ 400，返回 `{"detail": "中文错误说明", ...}` |

常见错误：

| 状态码 | detail | 含义 / App 处理 |
|---|---|---|
| 401 | `token_invalid` | 令牌失效（过期、被撤销、改了密码），跳转登录页 |
| 401 | `app_key_invalid` | App Key 不对 |
| 403 | `members_only` | 该内容仅会员可见，返回里有 `notice` 提示语，引导激活会员 |
| 404 | `App 接口未开启` | 后台关闭了 App 接口 |
| 429 | 尝试次数过多 | 稍后再试 |

令牌有效期默认 90 天，**每次使用自动续期**；同一设备（`device.id` 相同）重新登录会作废旧令牌。

## 2. 账号

### 注册 `POST /auth/register`
```json
{"email": "a@b.com", "password": "至少8位", "device": {"id": "设备唯一ID", "name": "Xiaomi 14", "os": "Android 15", "app_version": "1.0.0"}}
```
返回（若后台要求验证邮箱，则只返回 `{"verify_required": true}`，用户点邮件链接后再登录）：
```json
{"token": "zyt_xxx", "token_type": "Bearer", "expires_at": 1800000000,
 "user": {"id": 1, "email": "a@b.com", "email_verified": false, "membership": {...}},
 "membership": {"active": true, "permanent": false, "expires": 1800000000, "expired": false}}
```
> `membership` 在后台关闭会员模式时为 `null`，且 `user` 里不含会员字段——此时 App 不应显示任何会员相关界面。

### 登录 `POST /auth/login`
参数同注册（`email`、`password`、`device`），返回同上。邮箱未验证时 403，返回里 `unverified: true`。

### 当前用户 `GET /auth/me` → `{"user": {...}, "membership": {...}|null}`
### 退出 `POST /auth/logout`（作废当前令牌）
### 已登录设备 `GET /auth/devices` → `{"devices": [{"id", "device_name", "platform", "app_version", "last_used_at", "last_ip", "current"}]}`
### 下线某设备 `DELETE /auth/devices/{id}`
### 修改密码 `POST /auth/password`
`{"old_password": "...", "new_password": "至少8位"}` → 返回新的 `{"token", "expires_at"}`。所有其他设备会被下线，当前设备请换用新令牌。

### 网页登录（网站开启人机验证时必须使用）
`GET /meta/config` 返回 `login_mode` / `register_mode`：`native` 表示可以用上面的接口在 App 内登录 / 注册；`web` 表示必须跳转网页（此时 `/auth/login`、`/auth/register` 返回 403 `{"detail": "web_login_required", "web_login": true}`）。后台“安卓 App → App 登录与注册方式”可设为自动（开启了登录人机验证就走网页）/ 始终网页 / 始终 App 内。

流程（PKCE S256，App 永远拿不到密码，授权码被截获也无法使用）：
1. App 生成随机 `verifier`（43~128 位 base64url），`challenge = base64url(SHA256(verifier))`，再生成随机 `state`，自己保存；
2. 用浏览器打开 `https://你的域名/#/app-auth?challenge=…&state=…&device=设备名`；
3. 用户在网页登录或注册（有人机验证、找回密码），点“授权登录”；网页跳转 `zyllfinance://auth?code=…&state=…`（取消时为 `?error=denied&state=…`）；
4. App 检查 `state` 一致后调用 `POST /auth/exchange` `{"code": "…", "verifier": "…", "device": {…}}`，返回与登录相同的令牌。授权码 5 分钟有效、只能用一次。

### 找回密码
在浏览器打开 `https://你的域名/#/forgot`（网站需配置 SMTP，`/meta/config` 的 `password_reset` 为 true）。重置后该账号所有网页会话和 App 令牌立即失效。

## 3. 会员（卡密）

- 状态：`GET /member` → `{"status": {"active", "permanent", "expires", "expired"}, "history": [...], "buy_hint": "获取卡密说明"}`（会员模式关闭时 404）
- 激活 / 续期：`POST /member/redeem`，`{"code": "ZYLL-ABCD-EFGH-JKMN"}`（大小写、空格、横线都可以）
  返回 `{"days": 30, "expires": 1800000000, "permanent": false, "renewed": true, "user": {...}}`
  续期从当前到期日往后加；永久卡会变为永久会员。每个账号 10 分钟内最多尝试 8 次。

## 4. 版本更新与配置

- `GET /meta/version?version_code=12` →
  `{"latest_version_code": 13, "latest_version_name": "1.2.0", "min_version_code": 10, "apk_url": "https://...", "changelog": "...", "has_update": true, "force_update": false}`
  `force_update` 为 true 时 App 应阻止继续使用并引导下载。此接口不需要 App Key 和登录。
- `GET /meta/config` → 站点名称、会员是否开启、仅会员可见的板块、是否开放注册、推送主题列表、服务器时间等。

## 5. 数据接口（与网页版共用）

`/api/app/v1/<路径>` 等同于网页的 `/api/<路径>`（带 Bearer Token 即视为已登录）：

| App 路径 | 说明 |
|---|---|
| `GET /site` | 站点配置 |
| `GET /calendar`、`GET /calendar?start=&end=` | 经济日历（默认前 8 天到后 15 天） |
| `GET /calendar/next` | 接下来的“非常重要”事件（含到点不足 30 分钟、还没公布值的事件，客户端显示“等待公布”） |
| `GET /calendar/event/{id}` | 事件详情：中文解释、历史公布值与预测值 |
| `GET /holidays` | 节假日、今日美股/期货/外汇休市情况 |
| `GET /market` | 行情：指数（用户自选）、我的个股、成交最多 |
| `PUT /market/indices` `{"codes": ["DJI", ...]}` | 设置指数（最多 5 个） |
| `POST /market/stocks` `{"symbol"}`、`DELETE /market/stocks/{symbol}` | 我的个股（与持仓分析同步） |
| `GET /symbols/search?q=` | 股票代码联想 |
| `GET /darkpool/daily`、`/darkpool/ats`、`/darkpool/watch`、`/darkpool/symbol/{sym}`、`/darkpool/prints` | 暗盘 |
| `GET /futures` | 股指期货、CFTC 持仓 |
| `GET /portfolio` | 持仓分析：股票、交易、资金记录、报价、汇率；`settings.inflation` / `settings.include_fx` 两个开关；`inflation: {货币: {table: [[YYYY-MM, 指数]], yoy_12m, last_known, approx, region, no_data}}` 月度物价指数表；`today` 计算通胀折算用的日期 |
| `GET /portfolio/history` | 历史每日市值与盈亏；每点另有 `pl_p / pl_r / pl_rp`（只含股价 / 扣除通胀 / 两者）总盈亏和 `u_p / u_r / u_rp` 持仓盈亏 |
| `POST /portfolio/symbols`、`PATCH/DELETE /portfolio/symbols/{symbol}` | 持仓分析里的股票 |
| `POST /portfolio/trades`、`PATCH/DELETE /portfolio/trades/{id}` | 交易记录（`side, trade_date, shares, price, ccy, fx, fee, note, funding`）。`funding`：`ccy`（默认）= 按成交汇率当场换汇、从该货币现金扣；`usd` = 用之前换好的美元、从美元现金扣，`fx` 只作成本汇率 |
| `POST /portfolio/cash`、`PUT/DELETE /portfolio/cash/{grp}` | 资金记录：入金/出金 `{"kind":"deposit","trade_date","ccy","amount"}`；换汇 `{"kind":"fx","from_ccy","from_amount","to_ccy","to_amount"}` |
| `PUT /portfolio/settings` `{"base_currency","fx_mode","inflation","include_fx"}` | 汇总本币、汇率口径、扣除通胀、计入汇率（只传要改的字段即可） |
| `GET /portfolio/fx-cost?ccy=CNY&date=` | 用该货币换到的美元的加权平均成本（`funding=usd` 的交易默认用它作成交汇率） |
| `GET /me/export`、`POST /me/delete` `{"password"}` | 导出 / 删除个人数据 |
| `GET /privacy` | 隐私政策内容 |

持仓盈亏的计算方法与网页一致，可参考项目 `frontend/js/pnl.js`（App 端 `core/Pnl.kt` 已移植，含 `cpiFactor` / `deflator` 通胀折算和 `realizedPrice`）。扣除通胀：每笔成本和卖出所得乘以 `I(today) / I(交易日)`（物价指数每月 15 日为该月值，按天线性插值）。

## 6. AI 导入券商结单

后台“AI 导入”开启后可用（`/meta/config` 的 `ai_import.enabled`；`members_only` 为 true 时非会员会收到 403 `members_only`）。

1. `GET /portfolio/import/config` → `{enabled, vision, allowed, max_mb, max_pages, daily_limit, used_today, base, currencies, fx_pools: {"CNY": {records, rate, first, last}}}`
2. `POST /portfolio/import/upload?consent=1&name=文件名`：请求体直接是文件内容（不是表单），`Content-Type` 写文件类型。支持文字版 PDF、.xlsx、CSV、TXT、HTML；配置了视觉模型时还支持 PNG / JPG / WEBP 和扫描版 PDF。返回 `{"job": "…"}`。同一用户最多同时识别 3 个文件（超过返回 429）。
3. `GET /portfolio/import/job/{job}` 每 1~2 秒轮询 → `{status: running|done|failed, step, error, elapsed, result}`。
   `result`：`broker, period_start, period_end, trades[], cash[], positions[], notes[], stats`；
   每行有 `key`、`issues: [{level: error|warn|info, code, msg}]`、建议的 `selected` 和 `dup`（判为重复 / 对不上）；成交另有 `time`、`ext_id`（订单号代号）、`file`。
   `skipped` 是自动跳过的条数；`code` 为 `duplicate`（与已有记录重复）、`dup_file`（与本次另一个文件重复）、`partial`（当天合计对不上，需要确认）。
3b. 多个文件：分别上传、识别完成后 `POST /portfolio/import/merge {"jobs": ["…","…"]}` → `{job, result}`（文件之间互相去重，`result.files` 列出各文件和期间）。
4. `POST /portfolio/import/plan`（试算，不写入）与 `POST /portfolio/import/commit`（写入）请求体相同：
```json
{"source": "券商名", "job": "识别任务（或合并任务）编号",
 "trades": [{"key": "t0", "date": "2026-09-03", "symbol": "AAPL", "side": "buy", "shares": 10, "price": 220.5, "fee": 1, "note": "",
             "ext_id": "#1a2b3c4d", "time": "09:31:05", "confirm_dup": false}],
 "cash": [{"key": "c0", "date": "2026-09-02", "type": "fx", "from_currency": "CNY", "from_amount": 71000, "to_currency": "USD", "to_amount": 10000}],
 "fx": {"mode": "records|new|usd", "ccy": "CNY", "new": {"date": "2026-09-01", "from_amount": 71000, "to_amount": 10000}}}
```
   `mode`：`records` 用已记录（及本次导入）的换汇加权平均成本；`new` 同时补记一笔换汇；`usd` 不计汇率。
   返回 `{ok, errors: {key: 原因}, trades: [{key, ccy, fx, funding, rate_note}], new_symbols, notes, summary}`；commit 成功还返回 `batch`。
   服务器会重新校验每一行（日期、代码、数量、价格、卖出不超过持有等），有错误时一条都不写入。
   预览里 `dup` 为 true 的行必须带 `confirm_dup: true`（用户勾选即表示确认）才能导入；同一个 `job` 只能导入一次（撤销后可再导入）。
5. `GET /portfolio/import/batches` 导入记录（含 `period_start / period_end / broker / skipped`）；`DELETE /portfolio/import/batches/{batch}` 整批撤销。

## 7. 实时推送

推荐 WebSocket：`wss://你的域名/api/app/v1/ws`（开启 App Key 时加 `?app_key=`）。

- 连接后先收到 `{"topic": "_hello", "data": {...}}`；
- 发送 `{"op": "subscribe", "topics": ["ticks", "calendar"]}` 只接收这些主题（不发送则接收全部）；
- 服务器每 25 秒发 `{"topic": "_ping"}`，App 也可发送 `{"op": "ping"}`；
- 消息格式：`{"topic": "主题", "data": ...}`。

| 主题 | data |
|---|---|
| `ticks` | `{"AAPL": [价格, 毫秒时间戳], ...}`，只含有变化的股票，约 0.5 秒一批 |
| `snap` | `{"AAPL": {完整快照}, ...}` |
| `indices` | `{"DJI": {...}, ...}` |
| `rank` | 成交最多榜 |
| `calendar` | 有新公布值的事件数组（为空时请重新拉取 `/calendar`） |
| `fx` | 外汇交易中心最新汇率 |
| `holidays` | 节假日变化 |
| 其他 | `futures`、`finra_daily`、`finra_ats`、`cftc`、`dark_print` |

也可以用 SSE：`GET /api/app/v1/stream`（`text/event-stream`，每行 `data: {...}`）。

## 8. Kotlin 示例（OkHttp）

```kotlin
val client = OkHttpClient()
val json = "application/json".toMediaType()

fun api(path: String, token: String?, body: String? = null, method: String = if (body == null) "GET" else "POST"): Request =
    Request.Builder().url("https://example.com/api/app/v1$path")
        .apply { token?.let { header("Authorization", "Bearer $it") } }
        .header("X-App-Key", BuildConfig.ZYLL_APP_KEY)          // 后台开启时需要
        .method(method, body?.toRequestBody(json))
        .build()

// 登录
val login = client.newCall(api("/auth/login", null,
    """{"email":"a@b.com","password":"xxxxxxxx","device":{"id":"$androidId","name":"${Build.MODEL}","os":"Android ${Build.VERSION.RELEASE}","app_version":"${BuildConfig.VERSION_NAME}"}}""")).execute()

// 实时推送
client.newWebSocket(Request.Builder().url("wss://example.com/api/app/v1/ws").build(), object : WebSocketListener() {
    override fun onOpen(ws: WebSocket, r: Response) { ws.send("""{"op":"subscribe","topics":["ticks","calendar"]}""") }
    override fun onMessage(ws: WebSocket, text: String) { /* 解析 {"topic","data"} */ }
})
```

令牌请保存在 `EncryptedSharedPreferences`；收到 401 `token_invalid` 时清除令牌并回到登录页。
