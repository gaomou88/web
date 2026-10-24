"""设置中心：网站的所有可调参数都在这里定义，后台按此自动生成编辑表单。

值保存在数据库 settings 表里，改动立即生效（采集器会按需自动重启）。
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

from . import store

SECTIONS = [
    ("darkpool_ats", "暗盘：ATS 机构排行"),
    ("darkpool_stock", "暗盘：个股详情"),
    ("darkpool_prints", "暗盘：实时大单"),
    ("quotes_live", "行情页（指数、个股、成交最多）"),
    ("futures_cot", "美期：CFTC 机构持仓"),
]
AD_PROVIDERS = [("none", "不投放"), ("google", "Google AdSense"), ("adsterra", "Adsterra"),
                ("propeller", "PropellerAds"), ("medianet", "Media.net"), ("custom", "自定义代码")]


AI_PROVIDERS = [["deepseek", "DeepSeek（深度求索）"], ["qwen", "通义千问（阿里云百炼·北京）"], ["qwen_intl", "通义千问（阿里云百炼·国际站）"],
                ["zhipu", "智谱 GLM"], ["doubao", "豆包（火山方舟）"], ["kimi", "Kimi（月之暗面）"], ["custom", "其他（兼容 OpenAI 接口）"]]


def guess_provider(base: str) -> str:
    b = (base or "").lower()
    for host, prov in (("deepseek.com", "deepseek"), ("dashscope-intl", "qwen_intl"), ("dashscope", "qwen"), ("maas.aliyuncs", "qwen"),
                       ("bigmodel.cn", "zhipu"), ("volces.com", "doubao"), ("moonshot", "kimi")):
        if host in b:
            return prov
    return "custom"


def F(key: str, label: str, type_: str, default: Any, help_: str = "", options: list | None = None) -> dict[str, Any]:
    return {"key": key, "label": label, "type": type_, "default": default, "help": help_, "options": options}


def source_group(name: str, title: str, desc: str, enabled: bool, interval: int | None, *extra: dict[str, Any]) -> dict[str, Any]:
    fields = [F(f"sources.{name}.enabled", "启用", "bool", enabled)]
    if interval is not None:  # 实时流没有刷新间隔
        fields.append(F(f"sources.{name}.interval", "刷新间隔（秒）", "int", interval))
    return {"id": f"src_{name}", "page": "sources", "title": title, "desc": desc, "source": name, "fields": fields + list(extra)}


GROUPS: list[dict[str, Any]] = [
    {"id": "site", "page": "site", "title": "站点信息", "desc": "名称、版权、备案号和公告。", "fields": [
        F("site.name", "网站名称（中文）", "str", "Zyll财经"),
        F("site.name_en", "网站名称（英文）", "str", "Zyll Finance"),
        F("site.copyright", "版权所有方", "str", "Zyll团队", "页脚显示为：© 年份 版权所有方 版权所有"),
        F("site.icp", "备案号", "str", "", "填写后显示在页脚，留空不显示"),
        F("site.announcement", "前台公告", "text", "", "显示在页面顶部，留空不显示"),
    ]},
    {"id": "crawler", "page": "sources", "title": "采集通用设置", "desc": "对所有数据源生效。", "fields": [
        F("crawler.respect_robots", "遵守 robots.txt", "bool", False, "关闭后不再检查目标网站的 robots.txt；请求限速保持不变"),
        F("crawler.bot_token", "爬虫名称", "str", "ZyllBot", "出现在请求的 User-Agent 里"),
        F("crawler.bot_contact", "联系地址", "str", "", "出现在 User-Agent 里，便于对方网站联系你；可填网址或邮箱"),
    ]},
    source_group("calendar", "经济日历：日程", "Forex Factory 官方 JSON：日程、预测值、前值、重要性。对方限流较严（短时间多次请求会返回 429），最短 15 分钟请求一次；公布值由下一项单独抓取，不受影响。", True, 3600),
    source_group("calendar_actuals", "经济日历：公布值", "Forex Factory 日历页。数据公布前 1 分钟到公布后 3 分钟按“公布时刻间隔”高频检查；其余时间按“刷新间隔”补齐，另外每 30 分钟完整同步一次。", True, 30,
                 F("sources.calendar_actuals.fast_interval", "公布时刻检查间隔（秒）", "int", 5, "数据公布前后高频检查的间隔，最小 3 秒")),
    source_group("finra_daily", "FINRA 每日场外成交", "每只股票每日的场外（暗池+内部化）成交量与卖空量。", True, 1800),
    source_group("finra_ats", "FINRA ATS 周报", "各暗池（ATS）在每只股票上的成交量，约延迟 2 周。", True, 21600),
    source_group("cftc", "CFTC 机构持仓", "交易者持仓报告（金融期货），每周五发布。", True, 21600,
                 F("sources.cftc.codes", "合约代码", "str", "13874A,209742,124603,239742,1170E1,043602",
                   "依次为标普500迷你、纳指迷你、道指迷你、罗素迷你、VIX、10年美债")),
    source_group("market", "美股行情（新浪 / 腾讯 / Yahoo）", "全站个股、指数和“成交最多”的实时数据来源（已弃用 Cboe）。按“来源顺序”依次尝试，某个来源失败后 2 分钟内自动改用下一个。美股休市时自动降为 30 秒一次，无人访问时再放慢。", True, 3,
                 F("sources.market.order", "来源顺序", "str", "sina,tencent,yahoo", "逗号分隔，可选 sina、tencent、yahoo"),
                 F("sources.market.watchlist", "关注股票", "str", "SPY,QQQ,DIA,IWM,AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA,AMD",
                   "用于暗盘关注列表和 ATS 个股预取，也会一直保持实时报价"),
                 F("sources.market.default_indices", "默认指数", "str", "DJI,NDX,SPX,RUT,VIX",
                   "未登录用户看到的指数（最多 5 个）。可选：" + "、".join(["DJI 道琼斯", "NDX 纳斯达克100", "SPX 标普500", "RUT 罗素2000", "VIX 恐慌指数", "IXIC 纳斯达克综合", "SOX 费城半导体", "NYA 纽交所综合", "DXY 美元指数", "TNX 10年美债收益率", "HSI 恒生", "SSEC 上证", "N225 日经225", "FTSE 富时100", "DAX", "STOXX50 欧洲斯托克50"])),
                 F("sources.market.max_stocks", "每人最多添加个股", "int", 30),
                 F("sources.market.rank_enabled", "显示“成交最多”", "bool", True),
                 F("sources.market.rank_interval", "“成交最多”刷新间隔（秒）", "int", 30)),
    source_group("cme_futures", "股指期货报价", "按“来源顺序”依次尝试：新浪财经（接近实时）、Yahoo（接近实时）、CME 官网（延迟约 10 分钟，常拦截服务器 IP）。某个来源失败后 10 分钟内自动跳过。", True, 15,
                 F("sources.cme_futures.products", "品种", "str", "ES:133,NQ:146,YM:318,RTY:8314", "格式：代码:CME产品编号（编号只在使用 CME 来源时需要）"),
                 F("sources.cme_futures.order", "来源顺序", "str", "sina,yahoo,cme", "逗号分隔，可选 sina、yahoo、cme；删掉某项即停用该来源")),
    source_group("cme_blocks", "CME 大宗交易", "需要填写 CME 大宗交易页面的数据接口地址。", False, 120,
                 F("sources.cme_blocks.url", "接口地址", "str", "")),
    source_group("realtime", "美股实时行情", "可选的逐笔推送（WebSocket），多家同时使用以凑出更多免费额度：股票按“来源顺序”依次分给已连接的供应商（各家按自己的额度）；没分到的、以及某家断线期间它负责的股票，由上面的“美股行情”每几秒轮询，不需要 Key 也有实时价。优先订阅会员持仓分析里的股票，其次行情页个股和关注股票。无人访问超过 5 分钟自动断开。", True, None,
                 F("sources.realtime.providers", "来源顺序", "str", "finnhub,alpaca,polygon",
                   "逗号分隔，可选 finnhub、alpaca、polygon；没填 Key 的自动跳过"),
                 F("sources.realtime.finnhub_key", "Finnhub API Key", "secret", "", "finnhub.io 免费注册"),
                 F("sources.realtime.finnhub_limit", "Finnhub 订阅上限", "int", 50, "免费版约 50 只"),
                 F("sources.realtime.alpaca_key_id", "Alpaca API Key ID", "str", "", "alpaca.markets 免费注册"),
                 F("sources.realtime.alpaca_secret", "Alpaca API Secret", "secret", ""),
                 F("sources.realtime.alpaca_feed", "Alpaca 数据源", "select", "iex", options=[["iex", "IEX（免费）"], ["sip", "SIP（付费，全市场）"]]),
                 F("sources.realtime.alpaca_limit", "Alpaca 订阅上限", "int", 30, "免费版约 30 只"),
                 F("sources.realtime.polygon_key", "Polygon API Key", "secret", "", "留空则使用“实时暗池大单”里的 Polygon Key；实时数据需付费套餐"),
                 F("sources.realtime.polygon_ws", "Polygon WebSocket 地址", "str", "wss://socket.polygon.io/stocks", "延迟套餐用 wss://delayed.polygon.io/stocks"),
                 F("sources.realtime.polygon_limit", "Polygon 订阅上限", "int", 1000)),
    source_group("fx_cfets", "汇率：中国外汇交易中心", "银行间外汇市场人民币即期报价（买价/卖价），用于持仓分析的连汇盈亏。交易时间为北京时间 9:30 至次日 3:00，其余时间沿用最后报价。", True, 10),
    source_group("holidays", "节假日与休市日", "美股休市和 13:00 提前收盘按纽交所规则计算（无需联网，始终可用）；CME 股指期货假日安排据此推算；欧元区按 TARGET2 规则计算。各国公众假日从 Nager.Date 下载，中国法定假日和调休（外汇交易中心休市）从 holiday-cn 下载。每周更新一次。", True, 86400,
                 F("sources.holidays.extra_us_closed", "美股临时休市日", "text", "", "规则无法预知的临时休市（如国丧日），每行一个，格式：2027-01-09:国丧日")),
    source_group("pf_history", "持仓分析历史（日线与汇率）", "从 Yahoo 获取持仓分析里股票近 6 个月的日收盘价和各货币的日汇率，用于总市值折线图和盈亏分析；之后每个交易日收盘后自动补充。Yahoo 不可用时，用本站每天记录的收盘价逐日积累。", True, 3600),
    source_group("inflation", "通胀数据（物价指数）", "用于持仓分析里“扣除通胀”的实际盈亏。美国 CPI 指数来自 FRED（圣路易斯联储），各地区年度通胀率来自世界银行；中国、欧元区、英国等的月度数据直接取经济日历里抓到的 CPI 公布值。每天更新一次。后台“通胀数据”页可以查看覆盖情况、手动补录。", True, 86400),
    source_group("us_symbols", "美股代码表", "用于输入股票代码时的联想提示。来自 Nasdaq Trader 公开代码目录（含 NYSE、ETF），失败时改用 SEC 公司代码表；每天更新一次。", True, 21600),
    source_group("darkpool_rt", "实时暗池大单（付费）", "目前支持 Polygon（现名 Massive）实时逐笔成交套餐。", False, None,
                 F("sources.darkpool_rt.provider", "供应商", "select", "polygon", options=[["polygon", "Polygon / Massive"]]),
                 F("sources.darkpool_rt.api_key", "API Key", "secret", ""),
                 F("sources.darkpool_rt.ws_url", "WebSocket 地址", "str", "wss://socket.polygon.io/stocks"),
                 F("sources.darkpool_rt.min_notional", "最小金额（美元）", "float", 1_000_000.0),
                 F("sources.darkpool_rt.symbols", "订阅股票", "str", "", "留空则使用关注股票")),

    {"id": "register", "page": "users", "title": "注册与登录", "desc": "前台用户使用邮箱和密码注册。", "fields": [
        F("register.enabled", "开放注册", "bool", True),
        F("register.email_verify", "注册需验证邮箱", "bool", False, "开启后，用户点击邮件里的链接完成验证才能登录。需要先配置下方邮件服务"),
    ]},
    {"id": "smtp", "page": "mail", "title": "邮件服务（SMTP）", "desc": "用于发送验证、欢迎、登录提醒等邮件。", "fields": [
        F("smtp.host", "SMTP 服务器", "str", "", "例如 smtp.qq.com、smtp.gmail.com"),
        F("smtp.port", "端口", "int", 465),
        F("smtp.security", "加密方式", "select", "ssl", options=[["ssl", "SSL（通常 465）"], ["starttls", "STARTTLS（通常 587）"], ["none", "不加密"]]),
        F("smtp.username", "用户名", "str", ""),
        F("smtp.password", "密码 / 授权码", "secret", ""),
        F("smtp.from_addr", "发件人地址", "str", ""),
        F("smtp.site_url", "网站地址", "str", "", "邮件里验证链接的前缀，例如 https://zyll.example.com；留空则用访问时的地址"),
    ]},
    {"id": "privacy", "page": "privacy", "title": "隐私政策（GDPR）",
     "desc": "这些信息显示在前台“隐私政策”页面。按欧盟《通用数据保护条例》（GDPR），必须写明数据控制者和联系方式。",
     "fields": [
        F("privacy.controller", "数据控制者（公司或个人名称）", "str", "Zyll团队"),
        F("privacy.address", "联系地址", "str", ""),
        F("privacy.contact_email", "隐私联系邮箱", "str", "", "用户行使查阅、更正、删除等权利时联系的邮箱"),
        F("privacy.dpo", "数据保护官（DPO，可选）", "str", ""),
        F("privacy.eu_rep", "欧盟代表（非欧盟机构适用，可选）", "str", ""),
        F("privacy.updated", "政策更新日期", "str", "2026-10-22"),
        F("privacy.extra", "补充条款", "text", "", "追加到隐私政策末尾"),
    ]},
    {"id": "security_log", "page": "privacy", "title": "登录安全记录（防欺诈）",
     "desc": "每次注册、登录（成功和失败）、退出、改密码都会记录 IP、国家/地区、浏览器、设备特征和风险标记，用于识别盗号和欺诈。法律依据为 GDPR 第 6(1)(f) 条正当利益，已在隐私政策中说明。",
     "fields": [
        F("privacy.login_log", "记录登录安全信息", "bool", True),
        F("privacy.login_log_days", "保留天数", "int", 180, "到期自动删除。GDPR 要求不超过实现目的所需的时间，一般 3–12 个月"),
    ]},
    {"id": "turnstile", "page": "security", "title": "Cloudflare 人机验证（Turnstile）",
     "desc": "到 Cloudflare 控制台的 Turnstile 页面创建站点获取 Key。三个开关默认关闭；只有填好 Key 且打开开关才生效，不会把你锁在后台外面。",
     "fields": [
        F("turnstile.site_key", "Site Key", "str", ""),
        F("turnstile.secret_key", "Secret Key", "secret", ""),
        F("turnstile.on_register", "前台注册时验证", "bool", False),
        F("turnstile.on_login", "前台登录时验证", "bool", False, "开启后安卓 App 也改为跳转网页登录（App 里无法显示人机验证）"),
        F("turnstile.on_forgot", "找回密码时验证", "bool", True, "防止被人用“忘记密码”批量给用户发邮件"),
        F("turnstile.on_admin_login", "后台登录时验证", "bool", False, "若因此无法登录，可在服务器运行应急命令关闭（见 README）"),
    ]},
    {"id": "ads", "page": "ads", "title": "广告", "desc": "广告位只出现在页面底部、侧栏（宽屏）和板块之间，不遮挡内容。", "fields": [
        F("ads.enabled", "启用广告", "bool", False),
        F("ads.google_client", "Google AdSense 发布商 ID", "str", "", "形如 ca-pub-1234567890123456"),
        F("ads.footer_provider", "页面底部：广告商", "select", "none", options=[list(x) for x in AD_PROVIDERS]),
        F("ads.footer_slot", "页面底部：Google 广告单元 ID", "str", ""),
        F("ads.footer_code", "页面底部：广告代码", "text", "", "非 Google 广告商时，粘贴其提供的完整广告代码"),
        F("ads.inline_provider", "板块之间：广告商", "select", "none", options=[list(x) for x in AD_PROVIDERS]),
        F("ads.inline_slot", "板块之间：Google 广告单元 ID", "str", ""),
        F("ads.inline_code", "板块之间：广告代码", "text", ""),
        F("ads.side_provider", "宽屏侧栏：广告商", "select", "none", options=[list(x) for x in AD_PROVIDERS]),
        F("ads.side_slot", "宽屏侧栏：Google 广告单元 ID", "str", ""),
        F("ads.side_code", "宽屏侧栏：广告代码", "text", ""),
        F("ads.ads_txt", "ads.txt 内容", "text", "", "广告商要求的 ads.txt，保存后可通过 /ads.txt 访问"),
    ]},
    {"id": "membership", "page": "membership", "title": "会员", "desc": "会员可解锁指定板块并免广告，用户在前台用卡密激活或续期。默认关闭；关闭时前台不显示任何会员信息，所有板块（包括自选）对登录用户开放。", "fields": [
        F("membership.enabled", "启用会员模式", "bool", False),
        F("membership.no_ads", "会员免广告", "bool", True),
        F("membership.gated", "仅会员可见的板块", "multi", ["darkpool_stock", "darkpool_prints"], options=[list(x) for x in SECTIONS]),
        F("membership.notice", "非会员提示语", "str", "该内容仅对会员开放"),
        F("membership.buy_hint", "获取卡密说明", "text", "", "显示在前台“激活会员”窗口里，例如购买卡密的渠道、客服联系方式；留空不显示"),
    ]},
    {"id": "portfolio", "page": "portfolio", "title": "持仓分析与连汇盈亏", "desc": "用户在“持仓分析”添加美股并录入买卖记录，系统用实时股价和外汇交易中心汇率，计算含汇率损益的盈亏。", "fields": [
        F("portfolio.enabled", "开放此功能", "bool", True),
        F("portfolio.access", "谁可以使用", "select", "members", "选“仅会员”只在会员模式开启时生效；会员模式关闭时对所有登录用户开放",
          options=[["members", "仅会员"], ["users", "所有注册用户"]]),
        F("portfolio.max_symbols", "每人最多股票数量（持仓分析）", "int", 50),
        F("portfolio.max_trades", "每人最多交易记录", "int", 2000),
        F("portfolio.default_currency", "默认本币", "select", "CNY", options=[
            ["CNY", "人民币 CNY"], ["HKD", "港币 HKD"], ["SGD", "新加坡元 SGD"], ["EUR", "欧元 EUR"], ["GBP", "英镑 GBP"],
            ["JPY", "日元 JPY"], ["AUD", "澳元 AUD"], ["CAD", "加元 CAD"], ["CHF", "瑞士法郎 CHF"], ["USD", "美元 USD"]]),
    ]},
    {"id": "ai", "page": "ai", "title": "AI 导入券商结单",
     "desc": "用户上传券商的交易记录 / 月结单（PDF、Excel、CSV、截图），由 AI 识别成交易和资金记录，用户逐条核对后一键导入持仓分析。文件只在内存中处理，识别完即丢弃，不保存。",
     "fields": [
        F("ai.enabled", "开启 AI 导入", "bool", False),
        F("ai.members_only", "仅会员可用", "bool", True, "只在会员模式开启时生效；会员模式关闭时所有登录用户可用"),
        F("ai.daily_limit", "每人每天可识别次数", "int", 10),
        F("ai.global_daily_limit", "全站每天最多识别次数", "int", 500, "防止费用失控，0 表示不限"),
        F("ai.max_file_mb", "单个文件大小上限（MB）", "int", 10),
        F("ai.max_pages", "PDF 最多页数", "int", 30),
        F("ai.redact", "发送前隐去敏感信息", "bool", True, "把姓名、地址、邮箱、手机号替换成 [已隐去]，账号/证件号/订单号这类长编号替换成无法还原的代号（同一个号码代号相同，用于识别重复导入），再交给 AI。金额、日期和股票代码不受影响"),
    ]},
    {"id": "ai_mode", "page": "ai", "title": "使用哪些模型",
     "desc": "文字版 PDF、Excel、CSV 由“文字模型”提取交易；截图、照片、扫描版 PDF 需要能看图片的模型。新一代千问（qwen3.7-plus、qwen3.8-max）、Kimi k2.6、豆包 Seed 2.1 一个模型就能同时处理文字和图片。",
     "fields": [
        F("ai.mode", "模型组合", "select", "split", options=[
            ["split", "文字模型 + 图片模型（分别设置，例如 DeepSeek + 千问）"],
            ["single", "一个多模态模型同时处理文字和图片（只设置下面的文字模型）"],
            ["text", "只用文字模型（不接受截图和扫描版 PDF）"]]),
    ]},
    {"id": "ai_text", "page": "ai", "title": "文字模型",
     "desc": "从对账单文字里提取交易。选好服务商后接口地址可以留空（自动使用官方地址），模型可以从列表里选，也可以手动填写服务商支持的任何模型名。",
     "fields": [
        F("ai.text_provider", "服务商", "select", "deepseek", options=AI_PROVIDERS),
        F("ai.text_base_url", "接口地址", "str", "", "留空 = 使用该服务商的官方地址；不要带 /chat/completions"),
        F("ai.text_api_key", "API Key", "secret", ""),
        F("ai.text_model", "模型", "str", "deepseek-flash"),
    ]},
    {"id": "ai_vision", "page": "ai", "title": "图片模型",
     "desc": "只在“文字模型 + 图片模型”组合下使用：先把截图、扫描页逐字转写成文字，再交给文字模型提取交易。不填则只接受文字版文件。",
     "fields": [
        F("ai.vision_provider", "服务商", "select", "qwen", options=AI_PROVIDERS),
        F("ai.vision_base_url", "接口地址", "str", "", "留空 = 使用该服务商的官方地址"),
        F("ai.vision_api_key", "API Key", "secret", ""),
        F("ai.vision_model", "模型", "str", "qwen3.7-plus"),
    ]},
    {"id": "app", "page": "app", "title": "安卓 App 接口", "desc": "App 通过 /api/app/v1 访问，使用 Bearer Token 登录（每台设备一个令牌，可随时撤销）。接口文档见下方链接或项目里的 docs/APP_API.md。", "fields": [
        F("app.enabled", "开放 App 接口", "bool", True),
        F("app.require_key", "要求 App Key", "bool", False, "开启后，App 的每个请求都要带请求头 X-App-Key（WebSocket 可用 ?app_key=）。可防止别人随意调用接口；Key 会打包进 APK，不能当作真正的密钥"),
        F("app.api_key", "App Key", "secret", "", "点击下方“生成 App Key”可随机生成"),
        F("app.token_days", "登录有效天数", "int", 90, "App 持续使用会自动续期；超过这么多天没打开需要重新登录"),
        F("app.login_mode", "App 登录与注册方式", "select", "auto",
          "网页登录：App 打开浏览器进入本站登录页（带人机验证、找回密码），授权后自动回到 App，App 拿不到密码。",
          options=[["auto", "自动：开启了人机验证就走网页（推荐）"], ["web", "始终网页登录"], ["native", "始终在 App 内输入密码（无法人机验证）"]]),
    ]},
    {"id": "app_release", "page": "app", "title": "版本发布", "desc": "App 启动时调用 /api/app/v1/meta/version?version_code=当前版本号 检查更新。", "fields": [
        F("app.latest_version_code", "最新版本号（versionCode）", "int", 0),
        F("app.latest_version_name", "最新版本名（versionName）", "str", ""),
        F("app.min_version_code", "最低可用版本号", "int", 0, "低于这个版本号的 App 会被要求强制更新"),
        F("app.apk_url", "APK 下载地址", "str", ""),
        F("app.changelog", "更新说明", "text", ""),
    ]},
    {"id": "telemetry", "page": "diagnostics", "title": "性能与诊断数据",
     "desc": "访客同意“性能 Cookie”后才会上报（GDPR 与 ePrivacy 指令要求事先同意）。内容包括：页面加载各阶段耗时、核心网页指标（LCP、FCP、CLS、INP）、接口耗时与失败、实时连接状态、脚本错误（含堆栈）、长任务、内存占用、网络类型、屏幕与窗口尺寸、语言、时区、浏览器与系统。不与账号关联，IP 截断后保存（IPv4 去掉最后一段）。",
     "fields": [
        F("telemetry.enabled", "收集诊断数据", "bool", True),
        F("telemetry.retention_days", "保留天数", "int", 30),
        F("telemetry.sample_api", "接口耗时采样比例（%）", "int", 20, "每次接口请求按此概率记录耗时，100 为全部记录"),
    ]},
]

def _attach_mail_fields() -> None:
    from . import mailtpl
    i = next(i for i, g in enumerate(GROUPS) if g["id"] == "smtp")
    GROUPS[i + 1:i + 1] = mailtpl.groups()


_attach_mail_fields()
FIELDS: dict[str, dict[str, Any]] = {f["key"]: f for g in GROUPS for f in g["fields"]}
_values: dict[str, Any] = {}
_listeners: list[Callable[[set[str]], None]] = []


RENAMED = {"sources.cboe_quotes.watchlist": "sources.market.watchlist"}


async def load() -> None:
    rows = await store.query("SELECT key, value FROM settings")
    _values.clear()
    for r in rows:
        try:
            _values[r["key"]] = json.loads(r["value"])
        except ValueError:
            pass
    for old, new in RENAMED.items():  # 旧版设置项改名后保留原值
        if old in _values and new not in _values:
            _values[new] = _values[old]
            await store.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (new, json.dumps(_values[new], ensure_ascii=False)))
    fixes: dict[str, Any] = {}
    for kind in ("text", "vision"):  # 旧版没有“服务商”：按已填的接口地址推断
        base = _values.get(f"ai.{kind}_base_url")
        if f"ai.{kind}_provider" not in _values and base:
            fixes[f"ai.{kind}_provider"] = guess_provider(base)
    if _values.get("ai.text_model") in ("deepseek-chat", "deepseek-reasoner"):  # DeepSeek 2026-07-24 停用了这两个模型名
        fixes["ai.text_model"] = "deepseek-flash"
    if _values.get("ai.vision_model") in ("deepseek-chat", "deepseek-reasoner"):
        fixes["ai.vision_model"] = "deepseek-flash"
    for k, v in fixes.items():
        _values[k] = v
        await store.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, json.dumps(v, ensure_ascii=False)))


def get(key: str) -> Any:
    if key in _values:
        return _values[key]
    return FIELDS[key]["default"]


def get_list(key: str) -> list[str]:
    return [s.strip().upper() for s in str(get(key) or "").split(",") if s.strip()]


def on_change(fn: Callable[[set[str]], None]) -> None:
    _listeners.append(fn)


_INVISIBLE = re.compile(r"[\s\u200b-\u200f\u2028-\u202f\u2060\ufeff]+")


def coerce(field: dict[str, Any], value: Any) -> Any:
    t = field["type"]
    if t == "secret" or field["key"] == "turnstile.site_key":
        return _INVISIBLE.sub("", str(value or ""))  # Key 里不会有空白，去掉复制时混入的空格和隐藏字符
    if t == "bool":
        return bool(value) if not isinstance(value, str) else value.lower() in ("1", "true", "on", "yes")
    if t == "int":
        return int(float(value))
    if t == "float":
        return float(value)
    if t == "multi":
        allowed = {o[0] for o in field["options"]}
        return [v for v in (value or []) if v in allowed]
    if t == "select":
        allowed = {o[0] for o in field["options"]}
        if value not in allowed:
            raise ValueError(f"{field['label']}：无效选项")
        return value
    return str(value or "").strip() if t != "text" else str(value or "")


async def update(changes: dict[str, Any]) -> set[str]:
    clean: dict[str, Any] = {}
    for key, value in changes.items():
        field = FIELDS.get(key)
        if not field:
            continue
        if field["type"] == "secret" and value in (None, ""):
            continue  # 密钥留空表示不修改
        try:
            clean[key] = coerce(field, value)
        except (TypeError, ValueError) as e:
            raise ValueError(f"{field['label']}：格式不正确") from e
        low = 2 if key == "sources.market.interval" else 5  # 行情是批量轮询，允许更快
        if field["type"] == "int" and key.endswith(".interval") and clean[key] and clean[key] < low:
            raise ValueError(f"{field['label']}：不能小于 {low} 秒")
    _check_turnstile_keys(clean)
    await store.executemany(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        [(k, json.dumps(v, ensure_ascii=False)) for k, v in clean.items()],
    )
    _values.update(clean)
    changed = set(clean)
    for fn in _listeners:
        fn(changed)
    return changed


def _check_turnstile_keys(clean: dict[str, Any]) -> None:
    site = clean.get("turnstile.site_key", get("turnstile.site_key")) or ""
    secret = clean.get("turnstile.secret_key", get("turnstile.secret_key")) or ""
    if "turnstile.secret_key" in clean or "turnstile.site_key" in clean:
        if site and secret and site == secret:
            raise ValueError("Secret Key 和 Site Key 完全相同。请到 Cloudflare 的 Turnstile 设置里复制下方那个更长的 Secret Key")
        if "turnstile.secret_key" in clean and secret and len(secret) < 30:
            raise ValueError(f"Secret Key 只有 {len(secret)} 位，看起来像 Site Key（约 24 位）。Secret Key 通常约 35 位，请重新复制")
        if "turnstile.site_key" in clean and site and len(site) > 30:
            raise ValueError(f"Site Key 有 {len(site)} 位，看起来像 Secret Key。Site Key 通常约 24 位，请检查是否填反了")


def secret_hint(value: str) -> str:
    """显示前 6 位、后 4 位和长度，便于和 Cloudflare 等服务的后台对照，不暴露完整密钥。"""
    if not value:
        return ""
    if len(value) <= 12:
        return f"{value[:2]}…（{len(value)} 位）"
    return f"{value[:6]}…{value[-4:]}（{len(value)} 位）"


async def clear_secret(key: str) -> None:
    if FIELDS.get(key, {}).get("type") == "secret":
        await store.execute("DELETE FROM settings WHERE key = ?", (key,))
        _values.pop(key, None)
        for fn in _listeners:
            fn({key})


def export_for_admin() -> dict[str, Any]:
    values = {}
    for key, f in FIELDS.items():
        if f["type"] == "secret":
            values[key] = {"set": bool(get(key)), "hint": secret_hint(get(key))}
        else:
            values[key] = get(key)
    return {"groups": GROUPS, "values": values}
