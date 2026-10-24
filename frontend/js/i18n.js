const dict = {
  zh: {
    portfolio: "持仓分析", close: "关闭", pfLoginFirst: "登录后即可添加持仓，实时查看含汇率损益的盈亏，可选择扣除通胀。", pfBase: "汇总本币", pfFxMode: "汇率", pfMid: "中间价", pfBid: "卖出美元价", pfAddPh: "输入代码或公司名，如 AAPL", pfAdd: "加入持仓分析", pfLast: "最新价 USD", pfQty: "股数", pfAvg: "成本价 / 汇率", pfMv: "市值", pfToday: "今日盈亏", pfUnreal: "持仓盈亏", pfTargets: "目标 / 止损", pfRealtime: "实时", pfDelayed: "延迟 15 分钟", pfExport: "导出交易记录", pfEmpty: "还没有股票，在上方输入代码添加。", pfHelp: "每笔交易可选择自己的货币对（例如用港币账户买入选 USD/HKD），盈亏先按该货币计算，再按当前汇率折成本币汇总，并拆分为股价部分和汇率部分。汇率来自中国外汇交易中心银行间即期报价；“今日”以上一美股交易日收盘（美东 16:00）时的股价和汇率为基准，今天买入的部分以成交价和成交汇率为基准（所以按当前汇率录入的当日买入，今日汇率部分接近 0）。成本采用加权平均法。", pfPair: "货币对", pfMultiCcy: "多币种", pfFxBase: "今日汇率基准", pfFxBaseClose: "美东昨收 16:00", pfFxBaseApprox: "首次记录于 {t}，部署满一个交易日后改为美东昨收", pfTrades: "交易", pfEdit: "编辑", pfPricePart: "股价", pfFxPart: "汇率", pfRealized: "已实现盈亏", pfTarget: "目标", pfStop: "止损", pfTotalMv: "总市值", pfCost: "成本", pfNoFx: "汇率暂不可用，盈亏将在取得汇率后显示", pfVsPrev: "较昨收", pfNoPrevFx: "暂无昨日收盘汇率，今日汇率影响按 0 计", pfFxSrc: "中国外汇交易中心", pfConverted: "已按当前汇率把历史成交汇率换算到新本币，可在交易记录里逐笔修改", pfRemoveConfirm: "从持仓分析中移除 {s}？该股票的交易记录也会一并删除。", pfBuy: "买入", pfSell: "卖出", pfDate: "日期", pfSide: "方向", pfTradeFx: "成交汇率", pfFee: "手续费", pfNote: "备注", pfAddTrade: "添加记录", pfDelTrade: "删除这条交易记录？", pfNoTrades: "还没有交易记录", pfFxHint: "成交汇率默认填入当前汇率，请改成你实际换汇时的汇率，盈亏会更准确。", 
    netError: "网络连接失败，请稍后重试", turnstileFirst: "请先完成人机验证（勾选框出现绿色对勾后再提交）", membersOnly: "该内容仅对会员开放", becomeMember: "开通会员", rtUnavailable: "实时大单暂未开放", minNotional: "成交金额不低于", liveUnavailable: "盘前盘后实时价暂未开放，以下为延迟 15 分钟的常规时段价格。", email: "邮箱", register: "注册", noAccount: "没有账号？注册", haveAccount: "已有账号？登录", loggedIn: "已登录", verifyFirst: "请先到邮箱点击验证链接（已重新发送验证邮件）", registerVerifyDesc: "注册后我们会给你的邮箱发送验证链接，验证后即可登录。", checkInbox: "注册成功！请到邮箱点击验证链接后登录。", registered: "注册成功，已自动登录", cookieTitle: "Cookie 设置", cookieText: "我们使用必要 Cookie 保持登录状态；出于账号安全，登录和注册时会记录 IP 与设备信息。经你同意后，还会收集性能与诊断数据（加载耗时、错误、浏览器、设备与网络类型等，不关联账号，IP 截断后保存），用于修复故障和提速。你可随时在页脚“Cookie 设置”中更改。", cookieNecessary: "仅必要", cookieAll: "同意全部", cookieSettings: "Cookie 设置", allRights: "版权所有", disclaimer: "数据来自公开渠道，仅供参考，不构成投资建议。", verifiedOk: "邮箱验证成功，请登录", verifiedFail: "验证链接无效或已过期", 
    calendar: "经济日历", darkpool: "暗盘", futures: "美期", quotes: "行情", status: "数据源", admin: "用户管理",
    login: "登录", logout: "退出登录", username: "用户名", password: "密码", loginFailed: "用户名或密码错误", setupTitle: "设置管理员", setupDesc: "网站目前还没有管理员。设置后可以管理用户账号；不设置也不影响浏览数据。", setupBtn: "设置管理员", confirmPassword: "再次输入密码", mismatch: "两次输入的密码不一致", setupDone: "管理员已创建并登录", setupBanner: "首次使用：建议先设置管理员账号，避免被别人抢先设置。", later: "稍后", liveConn: "实时推送连接", timezone: "时区", account: "账户", backendDown: "后台服务未运行或正在启动，请稍后再试",
    changePassword: "修改密码", oldPassword: "原密码", newPassword: "新密码（至少 8 位）", save: "保存", cancel: "取消",
    yesterday: "昨天", today: "今天", tomorrow: "明天", thisWeek: "本周", nextWeek: "下周",
    imp3: "非常重要", imp2: "重要", imp1: "一般", imp0: "假日",
    time: "时间", region: "地区", event: "事件", actual: "公布值", forecast: "预测值", previous: "前值", importance: "重要性",
    org: "组织", nextKey: "下一个非常重要数据", released: "已公布", awaitingPrint: "已到公布时间，等待数据…", noEvents: "所选范围内没有事件，试着放宽筛选条件。",
    allDay: "全天", revised: "修正自",
    rtPrints: "实时大单", offExchange: "场外成交", atsFirms: "ATS 机构", stock: "个股",
    rtOff: "实时暗池逐笔数据只有付费源提供，目前未配置。在 .env 中设置 DARKPOOL_PROVIDER=polygon 和 POLYGON_API_KEY 后重启即可启用；免费的 FINRA 数据见其他标签。",
    waitingPrints: "已连接，等待满足阈值的大单…",
    symbol: "代码", price: "价格", size: "股数", notional: "金额", venue: "上报设施",
    offVol: "场外成交量", shortVol: "其中卖空", shortRatio: "卖空占比", markets: "上报设施",
    marketRatio: "全市场场外卖空占比", marketRatioSub: "FINRA 每日数据，覆盖所有非交易所撮合成交（暗池+券商内部化）",
    watchlist: "关注列表", topVolume: "场外成交量前列", topShort: "卖空占比最高（成交量 ≥ 200 万股）",
    dataDate: "数据日期", week: "周", firm: "机构（ATS）", shares: "成交股数", trades: "笔数", share: "份额", avgSize: "平均每笔",
    atsSub: "FINRA ATS 周报，一级股票约延迟 2 周发布",
    searchSymbol: "输入股票代码，如 NVDA", look: "查看", symHistory: "每日场外成交与卖空占比", symAts: "各暗池成交分布",
    noData: "暂无数据，采集器首次运行可能需要几分钟。",
    dataSource: "数据来源", activateMember: "激活会员", renewMember: "会员续期", memberUntil: "会员至 {d}（点击续期）", memberPermanent: "永久会员", memberExpired: "会员已过期（点击续期）", memberPermanentDesc: "你已经是永久会员，无需再激活。", memberRenewDesc: "当前会员到期日：{d}。输入卡密续期，时长从到期日往后累加。", memberExpiredDesc: "你的会员已于 {d} 到期，输入卡密重新激活。", memberActivateDesc: "输入卡密激活会员。", renewNow: "立即续期", activateNow: "立即激活", cardCode: "卡密", memberNowPermanent: "激活成功，你已是永久会员", memberNowUntil: "激活成功，会员有效期至 {d}", pfHoverHint: "悬停或点击查看分析", pfTotalPl: "总盈亏", pfVsYesterday: "较昨日", pfVsWeekAvg: "较近一周日均", pfHistLoading: "历史数据加载中…", pfHistShort: "历史数据还不够（系统会用历史收盘价回填近 3 个月，首次可能需要几分钟）。", pfHistApproxFx: "部分日期没有当日汇率，暂用当前汇率近似。", pfHistMissing: "以下股票暂缺历史收盘价，未计入历史市值", pfChg1d: "较上一交易日", pfChg1w: "近 1 周", pfChg1m: "近 1 个月", pfHighLow: "区间最高 / 最低", pfMaxDd: "最大盈亏回撤", pfConcentration: "第一大持仓", pfMvNote: "市值变化包含加仓和减仓；衡量投资表现请看“总盈亏”。", pfLive: "实时", pfWeights: "持仓权重", pfYesterday: "昨日盈亏", pfWeekAvg: "近一周日均", pfWinDays: "近 20 日盈利天数", pfDayPl: "每日盈亏", pfMovers: "今日贡献最大", pfFxShare: "汇率影响占比", pfWinners: "盈利持仓", pfContrib: "盈亏贡献（最多 / 最少）", pfTotalNote: "总盈亏 = 持仓盈亏 + 已实现盈亏（均按本币计、含汇率影响）。", pfRealizedBy: "已实现盈亏（按股票）", capTitle: "总资本", capIn: "（折合 {c}）", capDeposit: "入金", capWithdraw: "出金", capFx: "换汇", capRecords: "资金记录", capAlloc: "资产占比", capAsset: "资产", capAmount: "原币金额", capValue: "折合 {c}", capPct: "占比", capNoRate: "暂无汇率", capEmpty: "还没有资金记录。先“入金”记录你的本金，换汇后用“换汇”记录。", capNegative: "{c} 现金为负数：可能漏记了入金或换汇，请到“资金记录”补上。", capStocks: "美股持仓", capCash: "现金", capHelp: "现金余额 = 入金 − 出金 ± 换汇 − 买入（含手续费） + 卖出，按每笔交易所选货币对自动扣减或加回；全部按当前外汇交易中心汇率折合本币。占比按资产合计计算。", capMktRate: "当前中间价", capYourRate: "你的成交价", capVsMkt: "相比中间价", capFillMkt: "按中间价填写", capFromCcy: "换出货币", capFromAmt: "换出金额", capToCcy: "换入货币", capToAmt: "换入金额", capCcy: "货币", capAmountIn: "金额", capAdd: "添加", capFxHint: "按银行实际成交的金额填写，系统会算出你的换汇价并与当前中间价比较。", capType: "类型", capDetail: "内容", capDelConfirm: "删除这条资金记录？", capNoRecords: "暂无资金记录", capTradeEffect: "另外，买卖记录对现金的影响", keptInPf: "已从行情移除；该股票在“持仓分析”中有交易记录，已保留。", latestRatio: "最新卖空占比", ma20: "20 日均线", vsMa: "较均线", pctile90: "近 90 日分位", pctHigh: "处于高位", pctLow: "处于低位", pctMid: "处于中间", rangeHL: "区间最高 / 最低", tradingDays: "个交易日", offVolume: "场外成交量", vsAvg20: "较 20 日均量", histFilling: "历史数据回填中", histFillingLong: "历史数据正在回填（每 30 分钟补几天，约一天内补齐近 3 个月）。", range1m: "1 个月", range3m: "3 个月", rangeAll: "全部", watchSynced: "我的关注（已同步持仓分析）", watchSyncedSub: "与“持仓分析”和“行情 → 我的个股”同步。", watchDefaultSub: "登录后这里会显示你自己的股票。", noOffData: "最新一天没有场外成交数据", extTitle: "查看 {s} 的 K 线", extWarn: "你即将离开本站，前往第三方网站。第三方网站的内容、广告和服务与本站无关，本站不对其负责；请注意甄别风险、谨防诈骗，不要在第三方网站输入本站的账号密码。请选择网站：", extRemember: "记住我的选择（下次默认高亮）", loginToEdit: "登录后才能编辑", viewChart: "点击查看 K 线", maxIndices: "最多选择 {n} 个指数", editIndices: "编辑指数", editIndicesDesc: "最多选择 {n} 个，显示顺序与勾选顺序一致。", extHours: "盘前/盘后", openHL: "开/高/低", prevClose: "昨收", amount: "成交额", mktcap: "市值", mineLogin: "登录后可以添加自己关注的个股，实时查看行情。", mineEmpty: "还没有添加个股，在上方输入代码或公司名。", byAmount: "按成交额", byVolume: "按成交量", updatedAt: "更新于", myStocks: "我的个股", mostActive: "成交最多", clickForChart: "点击代码查看 K 线（跳转第三方网站）", quotesSrc: "实时数据：新浪 / 腾讯 / Yahoo", usClosed: "今日美股休市", usEarly: "今日美股 13:00（美东）提前收盘", cfetsClosed: "今日外汇交易中心休市", earlyClose: "提前收盘", closedTag: "休市", noNextKey: "暂无已公布日程的非常重要数据（下周日程通常周末前发布）", evDetail: "查看详情", effUp: "通常：实际值高于预期 → 利好该国货币；低于预期 → 利空。", effDown: "通常：实际值高于预期 → 利空该国货币；低于预期 → 利好（数值越低越好）。", effNone: "", evNoDesc: "暂无该指标的中文说明。", evNoHistory: "历史数据积累中（系统会自动回填近半年的数据）。", date: "日期", privacy: "隐私政策", exportMyData: "导出我的数据", deleteAccount: "删除账号", deleteAccountDesc: "将立即永久删除你的账号、持仓分析里的股票、交易记录和登录安全记录，无法恢复。请输入密码确认。", accountDeleted: "账号及相关数据已删除", futQuotes: "股指期货", frontMonth: "主力合约", volume: "成交量", priorSettle: "前结算", curve: "合约序列",
    cot: "CFTC 机构持仓", cotSub: "交易者持仓报告（金融期货），每周五发布，数据截至当周二",
    levMoney: "杠杆基金净持仓", assetMgr: "资管净持仓", dealer: "交易商净持仓", oi: "持仓量", change: "周变化", market: "合约",
    blocks: "CME 大宗交易", blocksOff: "CME 大宗交易数据接口尚未配置（CME_BLOCKS_URL），确认接口地址后填入即可启用。",
    delayed: "延迟", session: { pre: "盘前", regular: "盘中", post: "盘后", closed: "休市" },
    indexes: "指数", stocks: "个股", last: "最新", chg: "涨跌", chgPct: "涨跌幅", livePx: "实时/盘前盘后", liveTime: "成交时间",
    liveOff: "盘前盘后需要实时源。免费注册 Alpaca 后在 .env 填入 ALPACA_KEY_ID / ALPACA_SECRET_KEY 即可启用；下面是 Cboe 延迟 15 分钟的常规时段价格。",
    sourceStatus: "数据源状态", lastOk: "上次成功", never: "从未成功", disabled: "未启用",
    users: "用户", addUser: "添加用户", isAdmin: "管理员", active: "启用", created: "创建时间", actions: "操作",
    resetPw: "重置密码", makeAdmin: "设为管理员", removeAdmin: "取消管理员", statusSub: "所有抓取都会先检查目标网站的 robots.txt；未启用的项目需要在配置中填写 Key 或地址。", disable: "停用", enable: "启用", remove: "删除", confirmRemove: "确定删除该用户？",
    upDown: "涨跌配色", redUp: "红涨绿跌", greenUp: "绿涨红跌", saved: "已保存", srcNames: {
      calendar: "经济日历日程（Forex Factory JSON）", calendar_actuals: "公布值（Forex Factory 页面）",
      finra_daily: "FINRA 每日场外成交", finra_ats: "FINRA ATS 周报", cftc: "CFTC 持仓报告",
      market: "美股行情", cme_futures: "CME 期货报价", cme_blocks: "CME 大宗交易",
      alpaca: "Alpaca 实时（盘前盘后）", darkpool_rt: "实时暗池大单（付费）",
    },
  },
  en: {
    portfolio: "Portfolio", close: "Close", pfLoginFirst: "Sign in to add stocks and see live P&L including currency effects, optionally net of inflation.", pfBase: "Base currency", pfFxMode: "FX", pfMid: "Mid", pfBid: "Sell-USD rate", pfAddPh: "Ticker or company, e.g. AAPL", pfAdd: "Add", pfLast: "Last USD", pfQty: "Shares", pfAvg: "Avg cost / FX", pfMv: "Market value", pfToday: "Today P&L", pfUnreal: "Unrealized P&L", pfTargets: "Target / Stop", pfRealtime: "Real-time", pfDelayed: "Delayed 15 min", pfExport: "Export trades", pfEmpty: "No stocks yet. Add a ticker above.", pfHelp: "Each trade has its own currency pair (e.g. USD/HKD if you paid from an HKD account). P&L is computed in that currency, converted to your base currency at the current rate and split into price and FX effects. FX comes from CFETS interbank spot quotes. Today is measured from the previous US close (16:00 ET); shares bought today are measured from their trade price and FX, so a same-day buy at the current rate shows ~0 FX effect. Costs use weighted average.", pfPair: "Currency pair", pfMultiCcy: "Multi-ccy", pfFxBase: "Today FX base", pfFxBaseClose: "prev. US close 16:00 ET", pfFxBaseApprox: "first recorded {t}; switches to prev. US close after one trading day", pfTrades: "Trades", pfEdit: "Edit", pfPricePart: "Price", pfFxPart: "FX", pfRealized: "Realized P&L", pfTarget: "Target", pfStop: "Stop", pfTotalMv: "Total value", pfCost: "Cost", pfNoFx: "FX unavailable; P&L will appear once rates load", pfVsPrev: "vs prev close", pfNoPrevFx: "no prior-close FX yet; today's FX effect counted as 0", pfFxSrc: "CFETS", pfConverted: "Past trade FX rates were converted to the new base currency at today's rate. Edit them individually if needed.", pfRemoveConfirm: "Remove {s}? Its trades will be deleted too.", pfBuy: "Buy", pfSell: "Sell", pfDate: "Date", pfSide: "Side", pfTradeFx: "Trade FX", pfFee: "Fee", pfNote: "Note", pfAddTrade: "Add trade", pfDelTrade: "Delete this trade?", pfNoTrades: "No trades yet", pfFxHint: "Trade FX defaults to the current rate. Change it to the rate you actually converted at for accurate P&L.", 
    netError: "Network error. Try again shortly.", turnstileFirst: "Complete the human check first (wait for the green tick).", membersOnly: "This content is for members only", becomeMember: "Become a member", rtUnavailable: "Live prints aren't available yet", minNotional: "Notional at least", liveUnavailable: "Extended-hours prices aren't available yet. Below are regular-session prices delayed 15 minutes.", email: "Email", register: "Sign up", noAccount: "No account? Sign up", haveAccount: "Have an account? Sign in", loggedIn: "Signed in", verifyFirst: "Verify your email first. We've sent the link again.", registerVerifyDesc: "We'll email you a verification link. Sign in after verifying.", checkInbox: "Account created. Check your inbox for the verification link.", registered: "Account created and signed in", cookieTitle: "Cookie settings", cookieText: "We use necessary cookies to keep you signed in, and for account security we log IP and device details when you sign in or sign up. With your consent we also collect performance and diagnostics data (load times, errors, browser, device and network type; not linked to your account, IPs truncated) to fix faults and improve speed. You can change this any time via \"Cookie settings\" in the footer.", cookieNecessary: "Necessary only", cookieAll: "Accept all", cookieSettings: "Cookie settings", allRights: "All rights reserved", disclaimer: "Data comes from public sources for reference only and is not investment advice.", verifiedOk: "Email verified. Please sign in.", verifiedFail: "The link is invalid or expired", 
    calendar: "Calendar", darkpool: "Dark pools", futures: "Futures", quotes: "Markets", status: "Sources", admin: "Users",
    login: "Sign in", logout: "Sign out", username: "Username", password: "Password", loginFailed: "Wrong username or password", setupTitle: "Set up admin", setupDesc: "This site has no admin yet. The admin can manage user accounts. Browsing data works without one.", setupBtn: "Set up admin", confirmPassword: "Repeat password", mismatch: "The passwords don't match", setupDone: "Admin created and signed in", setupBanner: "First run: set up the admin account now so nobody else claims it first.", later: "Later", liveConn: "Live updates", timezone: "Time zone", account: "Account", backendDown: "The backend is not running or still starting. Try again shortly.",
    changePassword: "Change password", oldPassword: "Current password", newPassword: "New password (8+ chars)", save: "Save", cancel: "Cancel",
    yesterday: "Yesterday", today: "Today", tomorrow: "Tomorrow", thisWeek: "This week", nextWeek: "Next week",
    imp3: "High", imp2: "Medium", imp1: "Low", imp0: "Holiday",
    time: "Time", region: "Region", event: "Event", actual: "Actual", forecast: "Forecast", previous: "Previous", importance: "Impact",
    org: "Org", nextKey: "Next high-impact release", released: "Released", awaitingPrint: "Due now — waiting for the print…", noEvents: "No events in this range. Try widening the filters.",
    allDay: "All day", revised: "revised from",
    rtPrints: "Live prints", offExchange: "Off-exchange", atsFirms: "ATS venues", stock: "By ticker",
    rtOff: "Real-time dark pool prints only come from paid feeds and none is configured. Set DARKPOOL_PROVIDER=polygon and POLYGON_API_KEY in .env and restart. Free FINRA data is in the other tabs.",
    waitingPrints: "Connected. Waiting for prints above the threshold…",
    symbol: "Ticker", price: "Price", size: "Shares", notional: "Notional", venue: "Facility",
    offVol: "Off-exchange volume", shortVol: "Short volume", shortRatio: "Short %", markets: "Facilities",
    marketRatio: "Market-wide off-exchange short ratio", marketRatioSub: "FINRA daily data covering all non-exchange trades (dark pools + internalizers)",
    watchlist: "Watchlist", topVolume: "Largest off-exchange volume", topShort: "Highest short ratio (volume ≥ 2M)",
    dataDate: "Data date", week: "Week", firm: "Venue (ATS)", shares: "Shares", trades: "Trades", share: "Share", avgSize: "Avg size",
    atsSub: "FINRA weekly ATS report, Tier 1 published with about a 2-week lag",
    searchSymbol: "Enter a ticker, e.g. NVDA", look: "Look up", symHistory: "Daily off-exchange volume and short ratio", symAts: "Volume by dark pool",
    noData: "No data yet. The collectors may need a few minutes on first run.",
    dataSource: "Source", activateMember: "Activate membership", renewMember: "Renew membership", memberUntil: "Member until {d} (renew)", memberPermanent: "Lifetime member", memberExpired: "Membership expired (renew)", memberPermanentDesc: "You already have a lifetime membership.", memberRenewDesc: "Current expiry: {d}. Enter a card code to extend; time is added after the current expiry.", memberExpiredDesc: "Your membership expired on {d}. Enter a card code to reactivate.", memberActivateDesc: "Enter a card code to activate membership.", renewNow: "Renew", activateNow: "Activate", cardCode: "Card code", memberNowPermanent: "Done — you are now a lifetime member", memberNowUntil: "Done — membership valid until {d}", pfHoverHint: "hover or tap for analysis", pfTotalPl: "Total P&L", pfVsYesterday: "vs yesterday", pfVsWeekAvg: "vs 1-week avg", pfHistLoading: "Loading history…", pfHistShort: "Not enough history yet (about 3 months are backfilled from daily closes; the first run can take a few minutes).", pfHistApproxFx: "Some days have no FX close; the current rate is used as an approximation.", pfHistMissing: "No daily closes yet for", pfChg1d: "vs prev. session", pfChg1w: "1 week", pfChg1m: "1 month", pfHighLow: "High / low", pfMaxDd: "Max P&L drawdown", pfConcentration: "Largest holding", pfMvNote: "Market value includes buys and sells; use Total P&L to judge performance.", pfLive: "live", pfWeights: "Weights", pfYesterday: "Yesterday", pfWeekAvg: "1-week daily avg", pfWinDays: "Up days (20d)", pfDayPl: "Daily P&L", pfMovers: "Top movers today", pfFxShare: "FX share", pfWinners: "Winning positions", pfContrib: "Contribution (best / worst)", pfTotalNote: "Total P&L = unrealized + realized (in base currency, including FX).", pfRealizedBy: "Realized by stock", capTitle: "Total capital", capIn: "(in {c})", capDeposit: "Deposit", capWithdraw: "Withdraw", capFx: "Convert", capRecords: "Cash records", capAlloc: "Allocation", capAsset: "Asset", capAmount: "Amount", capValue: "In {c}", capPct: "Share", capNoRate: "no rate", capEmpty: "No cash records yet. Record a deposit, then use Convert after exchanging currency.", capNegative: "Negative {c} cash: a deposit or conversion may be missing.", capStocks: "US stocks", capCash: "Cash", capHelp: "Cash = deposits − withdrawals ± conversions − buys (incl. fees) + sells, using each trade's currency pair; converted to your base currency at current CFETS rates.", capMktRate: "Current mid", capYourRate: "Your rate", capVsMkt: "vs mid", capFillMkt: "Fill at mid", capFromCcy: "From", capFromAmt: "Amount out", capToCcy: "To", capToAmt: "Amount in", capCcy: "Currency", capAmountIn: "Amount", capAdd: "Add", capFxHint: "Enter the amounts your bank actually settled; your rate is compared with the current mid.", capType: "Type", capDetail: "Details", capDelConfirm: "Delete this record?", capNoRecords: "No records", capTradeEffect: "Cash impact from trades", keptInPf: "Removed from Markets; kept in Portfolio because it has trades.", latestRatio: "Latest short ratio", ma20: "20-day avg", vsMa: "vs avg", pctile90: "90-day percentile", pctHigh: "high", pctLow: "low", pctMid: "mid-range", rangeHL: "High / low", tradingDays: "trading days", offVolume: "Off-exchange volume", vsAvg20: "vs 20-day avg", histFilling: "backfilling history", histFillingLong: "History is being backfilled (a few days every 30 minutes; about 3 months within a day).", range1m: "1M", range3m: "3M", rangeAll: "All", watchSynced: "My watchlist (synced)", watchSyncedSub: "Synced with Portfolio and Markets → My stocks.", watchDefaultSub: "Sign in to see your own stocks here.", noOffData: "No off-exchange data on the latest day", extTitle: "View {s} chart", extWarn: "You are about to leave this site for a third-party website. Its content, ads and services are not ours and we are not responsible for them. Stay alert to scams and never enter your account password for this site there. Choose a site:", extRemember: "Remember my choice", loginToEdit: "Sign in to edit", viewChart: "Click to view chart", maxIndices: "Up to {n} indices", editIndices: "Edit indices", editIndicesDesc: "Pick up to {n}. They are shown in the order you tick them.", extHours: "Pre/After", openHL: "Open/High/Low", prevClose: "Prev close", amount: "Turnover", mktcap: "Mkt cap", mineLogin: "Sign in to add your own stocks and follow them live.", mineEmpty: "No stocks yet. Type a ticker or company name above.", byAmount: "By turnover", byVolume: "By volume", updatedAt: "Updated", myStocks: "My stocks", mostActive: "Most active", clickForChart: "Click a ticker to view its chart on a third-party site", quotesSrc: "Live data: Sina / Tencent / Yahoo", usClosed: "US stock market closed today", usEarly: "US stocks close early today at 13:00 ET", cfetsClosed: "CFETS (China FX) closed today", earlyClose: "Early close", closedTag: "Closed", noNextKey: "No scheduled high-impact release yet (next week's schedule is usually out before the weekend)", evDetail: "details", effUp: "Typically: actual above forecast is positive for the currency; below is negative.", effDown: "Typically: actual above forecast is negative for the currency (lower is better).", effNone: "", evNoDesc: "No description available.", evNoHistory: "History is being collected (about six months are backfilled automatically).", date: "Date", privacy: "Privacy", exportMyData: "Export my data", deleteAccount: "Delete account", deleteAccountDesc: "This permanently deletes your account, portfolio stocks, trades and sign-in security log. Enter your password to confirm.", accountDeleted: "Your account and data have been deleted", futQuotes: "Index futures", frontMonth: "Front month", volume: "Volume", priorSettle: "Prior settle", curve: "Contracts",
    cot: "CFTC positioning", cotSub: "Traders in Financial Futures, published Fridays with Tuesday data",
    levMoney: "Leveraged funds net", assetMgr: "Asset managers net", dealer: "Dealers net", oi: "Open interest", change: "Weekly chg", market: "Contract",
    blocks: "CME block trades", blocksOff: "The CME block trade endpoint isn't configured yet (CME_BLOCKS_URL).",
    delayed: "Delayed", session: { pre: "Pre-market", regular: "Regular", post: "After hours", closed: "Closed" },
    indexes: "Indexes", stocks: "Stocks", last: "Last", chg: "Change", chgPct: "Change %", livePx: "Live / extended", liveTime: "Trade time",
    liveOff: "Extended hours need a real-time feed. Add a free Alpaca key (ALPACA_KEY_ID / ALPACA_SECRET_KEY) to .env. Below are Cboe regular-session prices delayed 15 minutes.",
    sourceStatus: "Source status", lastOk: "Last success", never: "Never succeeded", disabled: "Off",
    users: "Users", addUser: "Add user", isAdmin: "Admin", active: "Active", created: "Created", actions: "Actions",
    resetPw: "Reset password", makeAdmin: "Make admin", removeAdmin: "Remove admin", statusSub: "Every fetch checks the site's robots.txt first. Items marked off need a key or URL in the config.", disable: "Disable", enable: "Enable", remove: "Delete", confirmRemove: "Delete this user?",
    upDown: "Up/down colors", redUp: "Red up", greenUp: "Green up", saved: "Saved", srcNames: {
      calendar: "Calendar schedule (Forex Factory JSON)", calendar_actuals: "Actuals (Forex Factory page)",
      finra_daily: "FINRA daily off-exchange", finra_ats: "FINRA weekly ATS", cftc: "CFTC positioning",
      market: "US market data", cme_futures: "CME futures quotes", cme_blocks: "CME block trades",
      alpaca: "Alpaca real-time (extended hours)", darkpool_rt: "Live dark pool prints (paid)",
    },
  },
};

Object.assign(dict.zh, {
  aiImport: "AI 导入结单", importHistory: "导入记录", imported: "导入",
  fundLabel: "这笔美元从哪来", fundCcy: "按成交汇率当场换汇（从该货币现金扣）", fundUsd: "用之前换好的美元（从美元现金扣）",
  fundHint: "如果你已经用“换汇”记录过换美元，选第二项：成交汇率默认填你换汇的平均成本，现金从美元里扣，不会重复扣人民币。",
  fundCostFx: "美元成本汇率", fundNoRecords: "还没有用 {c} 换美元的记录，请先在“总资本 → 换汇”里记录，或手动填写汇率",
  capDividend: "股息", capInterest: "利息", capFeeKind: "费用", capTax: "税费",
  forgotPassword: "忘记密码？", forgotTitle: "找回密码", forgotDesc: "输入注册邮箱，我们会发送一个重置密码的链接（30 分钟内有效）。", sendResetLink: "发送重置链接",
  resetSent: "如果该邮箱已注册，重置链接已发送，请查收邮件（也看看垃圾邮件箱）。", resetTitle: "设置新密码", resetDone: "密码已重置，所有设备都需要重新登录。",
  resetUnavailable: "网站暂未配置邮件服务，无法通过邮件找回密码，请联系管理员。",
  appAuthTitle: "登录 Zyll财经 App", appAuthDesc: "安卓 App 请求使用你的账号登录。确认是你本人在操作后点“授权登录”，然后会自动回到 App。",
  appAuthDevice: "设备", appAuthAccount: "账号", appAuthApprove: "授权登录", appAuthDeny: "取消", appAuthBack: "回到 App",
  appAuthLogin: "请先登录（或注册）网站账号，然后在这里授权 App。", appAuthBad: "授权参数不完整，请回到 App 重新点击“登录”。",
  appAuthDone: "已授权。如果没有自动回到 App，请点下面的按钮。", appAuthDenied: "已取消，可以关闭此页面。", appAuthWarn: "如果你没有在 App 里点登录，请不要授权，并关闭此页面。",
});
Object.assign(dict.zh, {
  pfInflation: "扣除通胀", pfInflationTip: "按付款货币所在地区的物价（CPI）把每笔成本和卖出所得折算成今天的购买力，看实际赚了多少",
  pfIncludeFx: "计入汇率", pfIncludeFxTip: "关闭后只看股价涨跌带来的盈亏（按买入时的平均成本汇率换算），不含汇率变化",
  pfInflNote: "已扣除通胀：", pfInflInfo: "{r}近 12 个月物价上涨 {p}（数据截至 {m}）", pfInflApprox: "，最近几个月按趋势推算",
  pfInflNone: "{c} 暂无物价数据，按不变计算", pfNoFxNote: "未计入汇率：盈亏只含股价部分，按买入时的平均成本汇率换算",
  pfRealCost: "成本（今天购买力）", pfExFx: "不含汇率影响", pfInflShort: "已扣除通胀", pfInflImpact: "通胀侵蚀",
  pfInflCardNote: "扣除通胀：每笔成本和卖出所得按付款货币所在地区的 CPI 折算到今天的购买力；今日盈亏不受影响。",
  pfTotalNoteView: "总盈亏 = 持仓盈亏 + 已实现盈亏（按上方开关：扣除通胀 / 不计汇率）。",
});
Object.assign(dict.en, {
  aiImport: "AI import", importHistory: "Import history", imported: "imported",
  fundLabel: "Where did these USD come from", fundCcy: "Converted at the trade rate (deducted from that currency)", fundUsd: "USD I converted earlier (deducted from USD cash)",
  fundHint: "If you already recorded the conversion under Capital → FX, choose the second option: the rate defaults to your average conversion cost and USD cash is used.",
  fundCostFx: "USD cost rate", fundNoRecords: "No {c}→USD conversion recorded yet. Record one under Capital → FX, or enter the rate manually",
  capDividend: "Dividend", capInterest: "Interest", capFeeKind: "Fee", capTax: "Tax",
  forgotPassword: "Forgot password?", forgotTitle: "Reset password", forgotDesc: "Enter your account email and we'll send a reset link (valid for 30 minutes).", sendResetLink: "Send link",
  resetSent: "If the email is registered, a reset link is on its way. Check your inbox (and spam).", resetTitle: "Set a new password", resetDone: "Password reset. All devices need to sign in again.",
  resetUnavailable: "Email is not configured on this site, so passwords can't be reset by email. Please contact the administrator.",
  appAuthTitle: "Sign in to the Zyll Finance app", appAuthDesc: "The Android app wants to sign in with your account. If this is you, tap Authorize and you'll return to the app.",
  appAuthDevice: "Device", appAuthAccount: "Account", appAuthApprove: "Authorize", appAuthDeny: "Cancel", appAuthBack: "Return to the app",
  appAuthLogin: "Sign in (or register) first, then authorize the app here.", appAuthBad: "Missing parameters. Go back to the app and tap Sign in again.",
  appAuthDone: "Authorized. If the app didn't open automatically, tap the button below.", appAuthDenied: "Cancelled. You can close this page.", appAuthWarn: "If you didn't just tap Sign in in the app, don't authorize — close this page.",
});
Object.assign(dict.en, {
  pfInflation: "Net of inflation", pfInflationTip: "Restate each cost and sale in today's money using CPI of the currency you paid with",
  pfIncludeFx: "Include FX", pfIncludeFxTip: "Turn off to see price-only P&L (converted at your average cost rate), excluding currency moves",
  pfInflNote: "Net of inflation: ", pfInflInfo: "{r} prices up {p} over 12 months (data to {m})", pfInflApprox: "; latest months estimated from trend",
  pfInflNone: "no price data for {c}; treated as flat", pfNoFxNote: "FX excluded: price-only P&L at your average cost rate",
  pfRealCost: "Cost (today's money)", pfExFx: "Excluding FX", pfInflShort: "net of inflation", pfInflImpact: "Inflation drag",
  pfInflCardNote: "Net of inflation: costs and sale proceeds are restated in today's money using CPI of the currency paid; today's P&L is unaffected.",
  pfTotalNoteView: "Total P&L = unrealized + realized (per the switches above: net of inflation / excluding FX).",
});

export const REGIONS = {
  US: { zh: "美国", en: "US", flag: "🇺🇸" }, EU: { zh: "欧元区", en: "Euro area", flag: "🇪🇺" },
  DE: { zh: "德国", en: "Germany", flag: "🇩🇪" }, FR: { zh: "法国", en: "France", flag: "🇫🇷" },
  IT: { zh: "意大利", en: "Italy", flag: "🇮🇹" }, ES: { zh: "西班牙", en: "Spain", flag: "🇪🇸" },
  CN: { zh: "中国", en: "China", flag: "🇨🇳" }, JP: { zh: "日本", en: "Japan", flag: "🇯🇵" },
  GB: { zh: "英国", en: "UK", flag: "🇬🇧" }, CA: { zh: "加拿大", en: "Canada", flag: "🇨🇦" },
  GL: { zh: "国际组织", en: "Global orgs", flag: "🌐" },
  AU: { zh: "澳大利亚", en: "Australia", flag: "🇦🇺" }, NZ: { zh: "新西兰", en: "New Zealand", flag: "🇳🇿" },
  CH: { zh: "瑞士", en: "Switzerland", flag: "🇨🇭" },
};
// 默认显示：前十大经济体中有数据的 + 国际组织
export const DEFAULT_REGIONS = ["US", "EU", "DE", "FR", "IT", "ES", "CN", "JP", "GB", "CA", "GL"];

export const TIMEZONES = [
  { id: "Asia/Shanghai", zh: "北京", en: "Beijing" },
  { id: "America/New_York", zh: "纽约", en: "New York" },
  { id: "Europe/London", zh: "伦敦", en: "London" },
  { id: "Asia/Tokyo", zh: "东京", en: "Tokyo" },
];

export const prefs = {
  get lang() { return localStorage.getItem("mg.lang") || (navigator.language.startsWith("zh") ? "zh" : "en"); },
  set lang(v) { localStorage.setItem("mg.lang", v); },
  get tz() { return localStorage.getItem("mg.tz") || "Asia/Shanghai"; },
  set tz(v) { localStorage.setItem("mg.tz", v); },
  get updown() { return localStorage.getItem("mg.updown") || (this.lang === "zh" ? "red" : "green"); },
  set updown(v) { localStorage.setItem("mg.updown", v); },
  getJSON(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
  setJSON(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* 隐私模式 */ } },
};

export function t(key) {
  const d = dict[prefs.lang] || dict.zh;
  return key.split(".").reduce((o, k) => (o ? o[k] : undefined), d) ?? key;
}

export function regionName(code) {
  const r = REGIONS[code];
  return r ? `${r.flag} ${r[prefs.lang]}` : code;
}

/* 经济数据名称中文化：按短语替换（长短语优先），未收录的保留英文原名。悬停可看原文。 */
const EVENT_ZH = [
  ["Non-Farm Employment Change", "非农就业人数变化"], ["ADP Non-Farm Employment Change", "ADP 就业人数变化"],
  ["ADP Weekly Employment Change", "ADP 周度就业人数变化"], ["Unemployment Claims", "初请失业金人数"],
  ["Unemployment Rate", "失业率"], ["Average Hourly Earnings", "平均时薪"], ["Average Earnings Index 3m/y", "三个月平均薪资年率"],
  ["Claimant Count Change", "申请失业救济人数变化"], ["Employment Change", "就业人数变化"], ["JOLTS Job Openings", "JOLTS 职位空缺"],
  ["Core PCE Price Index", "核心 PCE 物价指数"], ["PCE Price Index", "PCE 物价指数"], ["Core CPI", "核心 CPI"],
  ["National Core CPI", "全国核心 CPI"], ["Tokyo Core CPI", "东京核心 CPI"], ["Median CPI", "CPI 中位数"],
  ["Trimmed CPI", "截尾均值 CPI"], ["Common CPI", "共同 CPI"], ["Flash CPI", "CPI 初值"], ["Prelim CPI", "CPI 初值"],
  ["Core PPI", "核心 PPI"], ["PPI Input", "PPI 投入"], ["PPI Output", "PPI 产出"], ["RPI", "零售物价指数"],
  ["Advance GDP", "GDP 初值"], ["Prelim GDP", "GDP 修正值"], ["Final GDP", "GDP 终值"],
  ["Flash Manufacturing PMI", "制造业 PMI 初值"], ["Flash Services PMI", "服务业 PMI 初值"],
  ["Manufacturing PMI", "制造业 PMI"], ["Services PMI", "服务业 PMI"], ["Non-Manufacturing PMI", "非制造业 PMI"],
  ["ISM Manufacturing PMI", "ISM 制造业 PMI"], ["ISM Services PMI", "ISM 服务业 PMI"], ["Caixin", "财新"],
  ["Core Retail Sales", "核心零售销售"], ["Retail Sales", "零售销售"], ["Industrial Production", "工业产出"],
  ["Fixed Asset Investment", "固定资产投资"], ["New Home Prices", "新房价格"], ["Trade Balance", "贸易差额"],
  ["Current Account", "经常账户"], ["Building Permits", "营建许可"], ["Housing Starts", "新屋开工"],
  ["Existing Home Sales", "成屋销售"], ["New Home Sales", "新屋销售"], ["Pending Home Sales", "成屋签约销售"],
  ["Durable Goods Orders", "耐用品订单"], ["Core Durable Goods Orders", "核心耐用品订单"], ["Factory Orders", "工厂订单"],
  ["Crude Oil Inventories", "EIA 原油库存"], ["Natural Gas Storage", "天然气库存"], ["Consumer Confidence", "消费者信心"],
  ["CB Consumer Confidence", "谘商会消费者信心"], ["UoM Consumer Sentiment", "密歇根消费者信心"],
  ["UoM Inflation Expectations", "密歇根通胀预期"], ["Economic Sentiment", "经济景气指数"], ["Business Climate", "商业景气"],
  ["Ifo Business Climate", "Ifo 商业景气"], ["CB Leading Index", "谘商会领先指标"], ["Loan Prime Rate", "贷款市场报价利率 (LPR)"],
  ["Federal Funds Rate", "联邦基金利率"], ["FOMC Statement", "FOMC 声明"], ["FOMC Meeting Minutes", "FOMC 会议纪要"],
  ["FOMC Press Conference", "FOMC 新闻发布会"], ["Main Refinancing Rate", "主要再融资利率"], ["Monetary Policy Statement", "货币政策声明"],
  ["Official Bank Rate", "官方银行利率"], ["BOJ Policy Rate", "日本央行政策利率"], ["Overnight Rate", "隔夜利率"],
  ["Rate Statement", "利率声明"], ["Press Conference", "新闻发布会"], ["Treasury Currency Report", "美财政部汇率报告"],
  ["Bond Auction", "国债拍卖"], ["Speaks", "讲话"], ["Meetings", "会议"], ["Daylight Saving Time Shift", "夏令时切换"],
  ["Bank Holiday", "银行假日"], ["German", "德国"], ["French", "法国"], ["Italian", "意大利"], ["Spanish", "西班牙"],
  ["Revised", "修正"], ["Final", "终值"], ["Flash", "初值"], ["Prelim", "初值"], ["Core", "核心"],
  [" m/m", " 月率"], [" q/q", " 季率"], [" q/y", " 年率"], ["10-y", "10年期"], ["30-y", "30年期"], ["5-y", "5年期"], ["1-y", "1年期"], [" y/y", " 年率"], ["ytd/y", "年初至今年率"], ["3m/3m", "三个月环比"],
];
const EVENT_ZH_SORTED = EVENT_ZH.sort((a, b) => b[0].length - a[0].length);

export function eventTitle(title) {
  if (prefs.lang !== "zh") return title;
  let out = title;
  for (const [en, zh] of EVENT_ZH_SORTED) if (out.includes(en)) out = out.split(en).join(zh);
  return out;
}
