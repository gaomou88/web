package com.zyll.finance.data

import com.zyll.finance.core.CashMove
import com.zyll.finance.core.Pnl
import com.zyll.finance.core.Quote
import com.zyll.finance.core.Rate
import com.zyll.finance.core.Trade
import org.json.JSONArray
import org.json.JSONObject

/* ======================= JSON 小工具 ======================= */

fun JSONObject.dbl(key: String): Double? {
    if (!has(key) || isNull(key)) return null
    val v = optDouble(key)
    return if (v.isNaN()) null else v
}

fun JSONObject.str(key: String): String? = if (!has(key) || isNull(key)) null else optString(key).takeIf { it.isNotEmpty() }

/** 注意：Android 的 optString 遇到 JSON null 会返回字符串 "null"，所以统一用这两个 */
fun JSONObject.s(key: String): String = str(key) ?: ""
fun JSONObject.sd(key: String, def: String): String = str(key) ?: def
fun JSONObject.lng(key: String): Long? = dbl(key)?.toLong()
fun JSONObject.bool(key: String): Boolean = optBoolean(key, false)

inline fun <T> JSONArray?.mapObj(f: (JSONObject) -> T): List<T> {
    if (this == null) return emptyList()
    val out = ArrayList<T>(length())
    for (i in 0 until length()) optJSONObject(i)?.let { out.add(f(it)) }
    return out
}

fun JSONArray?.strings(): List<String> {
    if (this == null) return emptyList()
    return (0 until length()).mapNotNull { if (isNull(it)) null else optString(it).takeIf { s -> s.isNotEmpty() } }
}

fun JSONArray?.doubles(): List<Double> {
    if (this == null) return emptyList()
    return (0 until length()).mapNotNull { i -> optDouble(i).takeIf { !it.isNaN() } }
}

inline fun <T> JSONObject?.mapValues(f: (String, JSONObject) -> T?): Map<String, T> {
    if (this == null) return emptyMap()
    val out = LinkedHashMap<String, T>()
    val it = keys()
    while (it.hasNext()) {
        val k = it.next()
        optJSONObject(k)?.let { o -> f(k, o)?.let { v -> out[k] = v } }
    }
    return out
}

fun parseRates(o: JSONObject?): Map<String, Rate>? {
    if (o == null) return null
    val m = o.mapValues { _, r -> val b = r.dbl("bid"); val a = r.dbl("ask"); if (b != null && a != null) Rate(b, a) else null }
    return m.ifEmpty { null }
}

/* ======================= 账号 / 会员 / 配置 ======================= */

data class Membership(val active: Boolean, val permanent: Boolean, val expires: Long?, val expired: Boolean) {
    companion object {
        fun parse(o: JSONObject?): Membership? = o?.let { Membership(it.bool("active"), it.bool("permanent"), it.lng("expires"), it.bool("expired")) }
    }
}

data class Me(val id: Long, val email: String, val emailVerified: Boolean, val membership: Membership?) {
    companion object {
        fun parse(o: JSONObject): Me {
            val u = o.optJSONObject("user") ?: JSONObject()
            return Me(u.optLong("id"), u.s("email"), u.bool("email_verified"), Membership.parse(o.optJSONObject("membership")))
        }
    }
}

data class AiImportConfig(val enabled: Boolean, val vision: Boolean, val membersOnly: Boolean)

data class SiteConfig(
    val siteName: String,
    val membershipEnabled: Boolean,
    val gatedSections: List<String>,
    val buyHint: String,
    val registerEnabled: Boolean,
    val portfolioEnabled: Boolean,
    val serverTime: Long,
    /** web = 登录要跳转网页（网站开启了人机验证）；native = App 内输入密码 */
    val loginMode: String = "native",
    val registerMode: String = "native",
    val passwordReset: Boolean = false,
    val webAuthPath: String = "/#/app-auth",
    val aiImport: AiImportConfig = AiImportConfig(false, false, false),
) {
    companion object {
        fun parse(o: JSONObject): SiteConfig {
            val ai = o.optJSONObject("ai_import")
            return SiteConfig(
                o.sd("site_name", "Zyll财经"), o.bool("membership_enabled"), o.optJSONArray("gated_sections").strings(),
                o.s("buy_hint"), o.optBoolean("register_enabled", true), o.optBoolean("portfolio_enabled", true), o.optLong("server_time"),
                o.sd("login_mode", "native"), o.sd("register_mode", "native"), o.bool("password_reset"), o.sd("web_auth_path", "/#/app-auth"),
                AiImportConfig(ai?.bool("enabled") == true, ai?.bool("vision") == true, ai?.bool("members_only") == true),
            )
        }
    }
}

data class VersionInfo(
    val latestCode: Int, val latestName: String, val minCode: Int, val apkUrl: String, val changelog: String,
    val hasUpdate: Boolean, val forceUpdate: Boolean,
) {
    companion object {
        fun parse(o: JSONObject) = VersionInfo(
            o.optInt("latest_version_code"), o.s("latest_version_name"), o.optInt("min_version_code"), o.s("apk_url"),
            o.s("changelog"), o.bool("has_update"), o.bool("force_update"),
        )
    }
}

data class Device(val id: Long, val name: String, val platform: String, val appVersion: String, val lastUsedAt: Long?, val lastIp: String, val current: Boolean) {
    companion object {
        fun parse(o: JSONObject) = Device(
            o.optLong("id"), o.s("device_name").ifBlank { "未知设备" }, o.s("platform"), o.s("app_version"),
            o.lng("last_used_at"), o.s("last_ip"), o.bool("current"),
        )
    }
}

data class MemberLog(val ts: Long?, val source: String, val days: Int?, val newExpires: Long?)

data class MemberInfo(val status: Membership?, val history: List<MemberLog>, val buyHint: String) {
    companion object {
        fun parse(o: JSONObject) = MemberInfo(
            Membership.parse(o.optJSONObject("status")),
            o.optJSONArray("history").mapObj { MemberLog(it.lng("ts"), it.s("source"), it.dbl("days")?.toInt(), it.lng("new_expires")) },
            o.s("buy_hint"),
        )
    }
}

/* ======================= 日历 / 节假日 ======================= */

data class CalEvent(
    val id: String, val ts: Long, val currency: String, val region: String, val title: String, val impact: Int,
    val forecast: String, val previous: String, val actual: String, val revision: String, val surprise: Int,
) {
    companion object {
        fun parse(o: JSONObject) = CalEvent(
            o.s("id"), o.optLong("ts"), o.s("currency"), o.s("region"), o.s("title"), o.optInt("impact"),
            o.s("forecast"), o.s("previous"), o.s("actual"), o.s("revision"), o.optInt("surprise"),
        )

        fun list(a: JSONArray?) = a.mapObj { parse(it) }
    }
}

data class CalHist(val ts: Long, val actual: String, val forecast: String, val a: Double?, val f: Double?)

data class CalDetail(
    val event: CalEvent, val unit: String, val nameZh: String, val desc: String, val effect: String, val history: List<CalHist>,
) {
    companion object {
        fun parse(o: JSONObject) = CalDetail(
            CalEvent.parse(o.optJSONObject("event") ?: JSONObject()), o.s("unit"), o.s("name_zh"), o.s("desc"),
            o.s("effect"),
            o.optJSONArray("history").mapObj { CalHist(it.optLong("ts"), it.s("actual"), it.s("forecast"), it.dbl("a"), it.dbl("f")) },
        )
    }
}

data class MarketToday(
    val date: String, val usClosedZh: String?, val weekend: Boolean, val usEarly: String?, val cme: String?,
    val cfetsOpen: Boolean, val nextTradingDay: String,
) {
    companion object {
        fun parse(o: JSONObject?): MarketToday? = o?.let {
            MarketToday(
                it.s("date"), it.str("us_closed_zh") ?: it.str("us_closed"), it.bool("weekend"), it.opt("us_early")?.takeIf { v -> v != JSONObject.NULL }?.toString(),
                it.str("cme"), it.optBoolean("cfets_open", true), it.s("next_trading_day"),
            )
        }
    }
}

data class Holiday(val date: String, val region: String, val name: String, val kind: String)

data class Holidays(val items: List<Holiday>, val today: MarketToday?) {
    companion object {
        fun parse(o: JSONObject) = Holidays(
            o.optJSONArray("items").mapObj { Holiday(it.s("date"), it.s("region"), it.str("name_zh") ?: it.s("name"), it.s("kind")) },
            MarketToday.parse(o.optJSONObject("today")),
        )
    }
}

/* ======================= 行情 ======================= */

data class IndexInfo(val code: String, val zh: String, val en: String, val yahoo: String, val tv: String)

data class IndexQuote(
    val code: String, val name: String, val price: Double?, val prevClose: Double?, val change: Double?, val changePct: Double?,
    val spark: List<Double>,
) {
    companion object {
        fun parse(code: String, o: JSONObject) = IndexQuote(
            code, o.sd("name", code), o.dbl("live") ?: o.dbl("price"), o.dbl("prev_close"), o.dbl("change"), o.dbl("change_pct"),
            o.optJSONArray("spark").doubles(),
        )
    }
}

data class StockSnap(
    val symbol: String, val name: String, val price: Double?, val prevClose: Double?, val change: Double?, val changePct: Double?,
    val open: Double?, val high: Double?, val low: Double?, val volume: Double?, val amount: Double?, val mktcap: Double?,
    val extPrice: Double?, val extPct: Double?, val src: String,
) {
    companion object {
        fun parse(o: JSONObject, sym: String? = null) = StockSnap(
            sym ?: o.s("symbol"), o.s("name").takeIf { it != "Name" }.orEmpty(), o.dbl("live") ?: o.dbl("price"), o.dbl("prev_close"),
            o.dbl("change"), o.dbl("change_pct"), o.dbl("open"), o.dbl("high"), o.dbl("low"), o.dbl("volume"), o.dbl("amount"),
            o.dbl("mktcap")?.takeIf { it > 0 }, o.dbl("ext_price")?.takeIf { it > 0 }, o.dbl("ext_pct"), o.s("src"),
        )
    }

    /** 收到逐笔价格（ticks）后更新 */
    fun withPrice(p: Double): StockSnap {
        val chg = prevClose?.let { p - it }
        val pct = prevClose?.takeIf { it != 0.0 }?.let { (p / it - 1) * 100 }
        return copy(price = p, change = chg ?: change, changePct = pct ?: changePct)
    }
}

data class MarketData(
    val session: String,
    val today: MarketToday?,
    val catalog: List<IndexInfo>,
    val maxIndices: Int,
    val maxStocks: Int,
    val loggedIn: Boolean,
    val indices: List<String>,
    val indexQuotes: Map<String, IndexQuote>,
    val stocks: List<String>,
    val snaps: Map<String, StockSnap>,
    val rankAmount: List<StockSnap>,
    val rankVolume: List<StockSnap>,
    val rankUpdated: Double?,
    val updated: Double?,
) {
    companion object {
        fun parse(o: JSONObject): MarketData {
            val rank = o.optJSONObject("rank")
            return MarketData(
                o.s("session"), MarketToday.parse(o.optJSONObject("market")),
                o.optJSONArray("catalog").mapObj { IndexInfo(it.s("code"), it.s("zh"), it.s("en"), it.s("yahoo"), it.s("tv")) },
                o.optInt("max_indices", 5), o.optInt("max_stocks", 30), o.bool("logged_in"),
                o.optJSONArray("indices").strings(), o.optJSONObject("index_quotes").mapValues { k, v -> IndexQuote.parse(k, v) },
                o.optJSONArray("stocks").strings(), o.optJSONObject("snaps").mapValues { k, v -> StockSnap.parse(v, k) },
                parseRank(rank, "amount"), parseRank(rank, "volume"), rank?.dbl("updated"), o.dbl("updated"),
            )
        }

        fun parseRank(rank: JSONObject?, key: String) = rank?.optJSONArray(key).mapObj { StockSnap.parse(it) }
    }
}

data class SymbolHit(val symbol: String, val name: String, val exchange: String, val etf: Boolean)

fun parseSymbolHits(a: JSONArray?) = a.mapObj { SymbolHit(it.s("symbol"), it.s("name"), it.s("exchange"), it.bool("etf")) }

fun sessionZh(s: String) = when (s) {
    "pre" -> "盘前"
    "regular" -> "盘中"
    "post" -> "盘后"
    else -> "休市"
}

/* ======================= 持仓分析 ======================= */

/** 某货币所在地区的月度物价指数（扣除通胀用） */
data class CpiInfo(val table: List<Pair<String, Double>>, val yoy12m: Double?, val lastKnown: String?, val approx: Boolean, val region: String, val noData: Boolean)

data class PfSymbol(val symbol: String, val note: String)

data class PfQuote(val price: Double?, val prevClose: Double?, val name: String, val delayed: Boolean) {
    fun toQuote() = Quote(price, prevClose)
}

data class Portfolio(
    val base: String,
    val fxMode: String,
    val currencies: List<String>,
    val symbols: List<PfSymbol>,
    val trades: List<Trade>,
    val cash: List<CashMove>,
    val quotes: Map<String, PfQuote>,
    val fxNow: Map<String, Rate>?,
    val fxSource: String,
    val fxTime: String,
    val fxPrev: Map<String, Rate>?,
    val prevApprox: Boolean,
    val sessionDate: String,
    val realtime: Boolean,
    val maxSymbols: Int,
    /** 扣除通胀 / 计入汇率（存服务器，网页和 App 同步） */
    val inflation: Boolean = false,
    val includeFx: Boolean = true,
    val today: String = "",
    val cpi: Map<String, CpiInfo> = emptyMap(),
) {
    /** 扣除通胀时传给 Pnl.computeSymbol 的折算函数 */
    fun deflate(): ((String) -> ((String) -> Double)?)? =
        if (inflation && today.isNotEmpty()) Pnl.deflator(cpi.mapValues { it.value.table }, today) else null

    companion object {
        fun parse(o: JSONObject): Portfolio {
            val st = o.optJSONObject("settings") ?: JSONObject()
            val fx = o.optJSONObject("fx") ?: JSONObject()
            val now = fx.optJSONObject("now")
            val base = st.sd("base_currency", "CNY")
            return Portfolio(
                base = base, fxMode = st.sd("fx_mode", "mid"),
                currencies = o.optJSONArray("currencies").strings().ifEmpty { listOf("CNY", "USD", "HKD") },
                symbols = o.optJSONArray("symbols").mapObj { PfSymbol(it.s("symbol"), it.s("note")) },
                trades = o.optJSONArray("trades").mapObj {
                    Trade(
                        it.optLong("id"), it.s("symbol"), it.s("side"), it.s("trade_date"), it.optDouble("shares", 0.0),
                        it.optDouble("price", 0.0), it.str("ccy") ?: base, it.optDouble("fx", 1.0), it.dbl("fee") ?: 0.0, it.s("note"),
                        it.sd("funding", "ccy"), it.s("batch"),
                    )
                },
                cash = o.optJSONArray("cash").mapObj {
                    CashMove(it.optLong("id"), it.s("grp"), it.s("kind"), it.s("trade_date"), it.s("ccy"), it.optDouble("amount", 0.0), it.s("note"), it.s("batch"))
                },
                quotes = o.optJSONObject("quotes").mapValues { _, q -> PfQuote(q.dbl("price"), q.dbl("prev_close"), q.s("name").takeIf { it != "Name" }.orEmpty(), q.bool("delayed")) },
                fxNow = parseRates(now?.optJSONObject("rates")), fxSource = now?.s("source").orEmpty(), fxTime = now?.s("time").orEmpty(),
                fxPrev = parseRates(fx.optJSONObject("prev")), prevApprox = fx.bool("prev_approx"),
                sessionDate = (o.optJSONObject("session") ?: JSONObject()).s("session_date"),
                realtime = o.bool("realtime"),
                maxSymbols = (o.optJSONObject("limits") ?: JSONObject()).optInt("symbols", 50),
                inflation = st.bool("inflation"), includeFx = if (st.has("include_fx")) st.bool("include_fx") else true,
                today = o.s("today"),
                cpi = o.optJSONObject("inflation").mapValues { _, c ->
                    val arr = c.optJSONArray("table")
                    val table = (0 until (arr?.length() ?: 0)).mapNotNull { i ->
                        arr!!.optJSONArray(i)?.let { r -> r.optString(0) to r.optDouble(1) }
                    }
                    CpiInfo(table, c.dbl("yoy_12m"), c.str("last_known"), c.bool("approx"), c.s("region"), c.bool("no_data"))
                },
            )
        }
    }
}

data class HistPoint(
    val date: String, val mv: Double?, val cost: Double?, val unreal: Double?, val realized: Double?, val totalPl: Double?,
    val cash: Double?, val capital: Double?, val dayPl: Double?, val live: Boolean = false,
    /** 只含股价 / 扣除通胀 / 扣除通胀且只含股价 的总盈亏和持仓盈亏 */
    val plP: Double? = null, val plR: Double? = null, val plRp: Double? = null,
    val uP: Double? = null, val uR: Double? = null, val uRp: Double? = null,
)

data class PfHistory(val points: List<HistPoint>, val missing: List<String>, val approxFx: Boolean) {
    /** 按两个开关取值后的序列（与网页 pf_analysis.js 的 series() 相同） */
    fun view(inflation: Boolean, includeFx: Boolean): List<HistPoint> {
        var prevP: Double? = null
        return points.map { p ->
            val total = (if (inflation) (if (includeFx) p.plR else p.plRp) else (if (includeFx) p.totalPl else p.plP)) ?: p.totalPl
            val unreal = (if (inflation) (if (includeFx) p.uR else p.uRp) else (if (includeFx) p.unreal else p.uP)) ?: p.unreal
            val day = if (includeFx) p.dayPl else prevP?.let { pp -> p.plP?.let { it - pp } }
            prevP = p.plP
            p.copy(totalPl = total, unreal = unreal, realized = if (total != null && unreal != null) total - unreal else p.realized, dayPl = day)
        }
    }

    companion object {
        fun parse(o: JSONObject) = PfHistory(
            o.optJSONArray("points").mapObj {
                HistPoint(it.s("date"), it.dbl("mv"), it.dbl("cost"), it.dbl("unreal"), it.dbl("realized"), it.dbl("total_pl"), it.dbl("cash"), it.dbl("capital"), it.dbl("day_pl"),
                    plP = it.dbl("pl_p"), plR = it.dbl("pl_r"), plRp = it.dbl("pl_rp"), uP = it.dbl("u_p"), uR = it.dbl("u_r"), uRp = it.dbl("u_rp"))
            },
            o.optJSONArray("missing").strings(), o.bool("approx_fx"),
        )
    }
}

/* ======================= 暗盘 / 期货 ======================= */

data class DpRow(val symbol: String, val short: Double?, val total: Double?, val ratio: Double?, val date: String = "")

private fun dpRows(a: JSONArray?) = a.mapObj { DpRow(it.s("symbol"), it.dbl("short"), it.dbl("total"), it.dbl("ratio"), it.s("date")) }

data class DpDaily(val date: String, val fetched: Double?, val topVolume: List<DpRow>, val topShortRatio: List<DpRow>, val watchlist: List<DpRow>, val market: List<DpRow>) {
    companion object {
        fun parse(o: JSONObject) = DpDaily(
            o.s("date"), o.dbl("fetched"), dpRows(o.optJSONArray("top_volume")), dpRows(o.optJSONArray("top_short_ratio")),
            dpRows(o.optJSONArray("watchlist")), dpRows(o.optJSONArray("market")).sortedBy { it.date },
        )
    }
}

data class AtsFirm(val mpid: String, val name: String, val shares: Double?, val trades: Double?, val sharePct: Double?, val avgSize: Double?)

data class Ats(val week: String, val totalShares: Double?, val firms: List<AtsFirm>, val fetched: Double?) {
    companion object {
        fun parse(o: JSONObject?): Ats? = o?.takeIf { it.has("firms") }?.let {
            Ats(
                it.s("week"), it.dbl("total_shares"),
                it.optJSONArray("firms").mapObj { f -> AtsFirm(f.s("mpid"), f.s("name"), f.dbl("shares"), f.dbl("trades"), f.dbl("share_pct"), f.dbl("avg_size")) },
                it.dbl("fetched"),
            )
        }
    }
}

data class DpSymbol(val symbol: String, val history: List<DpRow>, val ats: Ats?) {
    companion object {
        fun parse(o: JSONObject) = DpSymbol(o.s("symbol"), dpRows(o.optJSONArray("history")).sortedBy { it.date }, Ats.parse(o.optJSONObject("ats")))
    }
}

data class DpWatch(val date: String, val rows: List<DpRow>, val missing: List<String>) {
    companion object {
        fun parse(o: JSONObject) = DpWatch(o.s("date"), dpRows(o.optJSONArray("rows")), o.optJSONArray("missing").strings())
    }
}

data class FutQuote(
    val contract: String, val month: String, val last: Double?, val change: Double?, val changePct: Double?, val priorSettle: Double?,
    val open: Double?, val high: Double?, val low: Double?, val volume: Double?, val updated: String,
) {
    companion object {
        fun parse(o: JSONObject) = FutQuote(
            o.s("contract"), o.s("month"), o.dbl("last"), o.dbl("change"), o.dbl("change_pct"), o.dbl("prior_settle"),
            o.dbl("open"), o.dbl("high"), o.dbl("low"), o.dbl("volume"), o.s("updated"),
        )
    }
}

data class Future(val root: String, val name: String, val front: FutQuote?, val curve: List<FutQuote>, val source: String)

data class CotGroup(val long: Double, val short: Double, val net: Double, val netChange: Double)

data class CotRow(val date: String, val openInterest: Double?, val oiChange: Double?, val groups: Map<String, CotGroup>) {
    companion object {
        fun parse(o: JSONObject) = CotRow(
            o.s("date"), o.dbl("open_interest"), o.dbl("oi_change"),
            o.optJSONObject("groups").mapValues { _, g -> CotGroup(g.optDouble("long", 0.0), g.optDouble("short", 0.0), g.optDouble("net", 0.0), g.optDouble("net_change", 0.0)) },
        )
    }
}

data class CotMarket(val code: String, val market: String, val latest: CotRow?, val history: List<CotRow>)

data class Futures(val futures: List<Future>, val updated: Double?, val delayed: Boolean, val cotDate: String, val cot: List<CotMarket>, val cotLocked: Boolean) {
    companion object {
        fun parse(o: JSONObject): Futures {
            val cme = o.optJSONObject("cme") ?: JSONObject()
            val cot = o.optJSONObject("cot") ?: JSONObject()
            return Futures(
                cme.optJSONObject("futures").mapValues { _, f ->
                    Future(f.s("root"), f.s("name"), f.optJSONObject("front")?.let { FutQuote.parse(it) },
                        f.optJSONArray("curve").mapObj { FutQuote.parse(it) }, f.s("source"))
                }.values.toList(),
                cme.dbl("updated"), cme.bool("delayed"), cot.s("date"),
                cot.optJSONArray("markets").mapObj {
                    CotMarket(it.s("code"), it.s("market"), it.optJSONObject("latest")?.let { r -> CotRow.parse(r) },
                        it.optJSONArray("history").mapObj { r -> CotRow.parse(r) }.sortedBy { r -> r.date })
                },
                o.opt("cot") == "locked",
            )
        }
    }
}

val COT_GROUP_ZH = linkedMapOf(
    "lev_money" to "杠杆基金", "asset_mgr" to "资产管理", "dealer" to "交易商", "other" to "其他可报告", "nonrept" to "非报告",
)

/** 资金记录类型的中文名 */
fun cashKindZh(kind: String) = when (kind) {
    "deposit" -> "入金"; "withdraw" -> "出金"; "fx" -> "换汇"; "dividend" -> "股息"; "interest" -> "利息"; "fee" -> "费用"; "tax" -> "税费"
    else -> kind
}
