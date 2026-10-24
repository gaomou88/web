package com.zyll.finance.core

import java.time.LocalDate
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/**
 * 连汇盈亏计算，逐行移植自网站的 frontend/js/pnl.js（后端 backend/app/pnl.py 也是同一算法）。
 *
 * 约定：股价、手续费以美元计；fx 表示“1 美元 = 多少该笔交易的货币”。
 * 成本用加权平均法；持仓盈亏拆成“股价部分”和“汇率部分”；
 * 今日盈亏 = 现市值 + 今日卖出所得 − 今日买入花费 − 昨收市值。
 * 同一股票按交易货币分组各自计算，再按当前交叉汇率折算成用户的本币汇总。
 * 扣除通胀（可选）：每笔成本、卖出所得按付款货币所在地区的物价指数折算成今天的购买力（cpiFactor），今日盈亏不受影响。
 * 不计汇率（可选）：持仓盈亏取 unrealPrice，已实现取 realizedPrice（按平均成本汇率换算），今日取 todayPrice。
 *
 * 本文件不依赖 Android，可以直接在 JVM 上单元测试（app/src/test 里有与网站一致性的测试）。
 */

/** 外汇交易中心报价：1 单位该货币 = 多少人民币（bid/ask）。 */
data class Rate(val bid: Double, val ask: Double)

data class Trade(
    val id: Long,
    val symbol: String,
    val side: String,          // "buy" / "sell"
    val tradeDate: String,     // yyyy-MM-dd
    val shares: Double,
    val price: Double,
    val ccy: String?,
    val fx: Double,
    val fee: Double = 0.0,
    val note: String = "",
    /** ccy：按成交汇率当场换汇；usd：用之前换好的美元（汇率只作成本汇率） */
    val funding: String = "ccy",
    /** 导入批次（AI 导入的记录才有） */
    val batch: String = "",
)

data class CashMove(
    val id: Long,
    val grp: String,
    val kind: String,          // deposit / withdraw / fx
    val tradeDate: String,
    val ccy: String,
    val amount: Double,
    val note: String = "",
    val batch: String = "",
)

data class Quote(val price: Double?, val prevClose: Double?)

data class Position(
    val qty: Double,
    val costUsd: Double,
    val costBase: Double,
    val realized: Double,
    /** 按今天购买力计算的成本（不扣通胀时等于 costBase） */
    val costReal: Double = costBase,
    /** 已实现盈亏中的股价部分（按卖出时的平均成本汇率换算，不含汇率变化） */
    val realizedPrice: Double = 0.0,
    val avgUsd: Double?,
    val avgFx: Double?,
    val price: Double?,
    val prevClose: Double?,
    val mvUsd: Double? = null,
    val mvBase: Double? = null,
    val unreal: Double? = null,
    val unrealPct: Double? = null,
    val unrealPrice: Double? = null,
    val unrealFx: Double? = null,
    val today: Double? = null,
    val todayPrice: Double? = null,
    val todayFx: Double? = null,
) {
    val dayChangePct: Double?
        get() = if (price != null && prevClose != null && prevClose != 0.0) (price / prevClose - 1) * 100 else null
}

/** 一只股票（可能多种货币买入）折算到本币后的结果。 */
data class SymbolPosition(
    val ccys: List<String>,
    val qty: Double?,
    val costUsd: Double?,
    val costBase: Double?,
    val realized: Double?,
    val costReal: Double? = costBase,
    val realizedPrice: Double? = null,
    val mvUsd: Double?,
    val mvBase: Double?,
    val unreal: Double?,
    val unrealPrice: Double?,
    val unrealFx: Double?,
    val today: Double?,
    val todayPrice: Double?,
    val todayFx: Double?,
    val price: Double?,
    val prevClose: Double?,
    val avgUsd: Double?,
    val avgFx: Double?,
    val unrealPct: Double?,
    val fxPrevMissing: Boolean,
) {
    val dayChangePct: Double?
        get() = if (price != null && prevClose != null && prevClose != 0.0) (price / prevClose - 1) * 100 else null
}

data class Totals(
    val mvBase: Double,
    val costBase: Double,
    val unreal: Double,
    val unrealPct: Double?,
    val unrealPrice: Double,
    val unrealFx: Double,
    val today: Double,
    val todayPrice: Double,
    val todayFx: Double,
    val realized: Double,
    val costReal: Double = costBase,
    val realizedPrice: Double = 0.0,
) {
    val totalPl: Double get() = unreal + realized
}

/** 按“是否计入汇率”取要显示的盈亏 */
data class PlView(val unreal: Double?, val realized: Double?, val today: Double?) {
    val total: Double? get() = if (unreal == null && realized == null) null else (unreal ?: 0.0) + (realized ?: 0.0)
}

data class CapitalItem(val kind: String, val ccy: String, val amount: Double?, val value: Double?, val pct: Double?)

data class Capital(
    val items: List<CapitalItem>,
    val gross: Double,
    val net: Double,
    val negative: List<CapitalItem>,
    val missingRate: List<String>,
)

object Pnl {

    /** 1 美元 = 多少 ccy。mode: "mid" 中间价，"bid" 卖出美元可得价（更保守）。 */
    fun usdTo(rates: Map<String, Rate>?, ccy: String, mode: String = "mid"): Double? {
        if (rates == null) return null
        if (ccy == "USD") return 1.0
        val usd = rates["USD"] ?: return null
        val base = rates[ccy] ?: return null
        if (mode == "bid") return usd.bid / base.ask
        return ((usd.bid + usd.ask) / 2) / ((base.bid + base.ask) / 2)
    }

    /* ---------- 通胀：月度物价指数表 [(YYYY-MM, 指数)]，每月 15 日为该月的值，按天线性插值 ---------- */
    private fun dayNum(d: String): Long = LocalDate.of(d.substring(0, 4).toInt(), d.substring(5, 7).toInt(), d.substring(8, 10).toInt()).toEpochDay()

    fun cpiIndexAt(table: List<Pair<String, Double>>?, day: String): Double? {
        if (table.isNullOrEmpty()) return null
        val x = dayNum(day)
        val pts = table.map { dayNum("${it.first}-15") to it.second }
        if (x <= pts.first().first) return pts.first().second
        if (x >= pts.last().first) return pts.last().second
        var lo = 0; var hi = pts.size - 1
        while (hi - lo > 1) { val mid = (lo + hi) / 2; if (pts[mid].first <= x) lo = mid else hi = mid }
        val (x0, y0) = pts[lo]; val (x1, y1) = pts[hi]
        return y0 + (y1 - y0) * (x - x0).toDouble() / (x1 - x0).toDouble()
    }

    /** day 那天的 1 元相当于 nowDay 的多少元（物价上涨 → 大于 1）。没有数据时为 1。 */
    fun cpiFactor(table: List<Pair<String, Double>>?, day: String, nowDay: String): Double {
        val a = cpiIndexAt(table, day); val b = cpiIndexAt(table, nowDay)
        return if (a != null && b != null && a != 0.0) b / a else 1.0
    }

    /** 按货币返回折算函数：deflator(表, 今天)(货币)(日期)。 */
    fun deflator(tables: Map<String, List<Pair<String, Double>>>?, nowDay: String): (String) -> ((String) -> Double)? = { ccy ->
        val t = tables?.get(ccy)
        if (t.isNullOrEmpty()) null else { day: String -> cpiFactor(t, day, nowDay) }
    }

    fun pick(unreal: Double?, unrealPrice: Double?, realized: Double?, realizedPrice: Double?, today: Double?, todayPrice: Double?, includeFx: Boolean) =
        if (includeFx) PlView(unreal, realized, today) else PlView(unrealPrice, realizedPrice, todayPrice)

    fun view(p: SymbolPosition, includeFx: Boolean) = pick(p.unreal, p.unrealPrice, p.realized, p.realizedPrice, p.today, p.todayPrice, includeFx)
    fun view(t: Totals, includeFx: Boolean) = pick(t.unreal, t.unrealPrice, t.realized, t.realizedPrice, t.today, t.todayPrice, includeFx)

    fun computePosition(
        trades: List<Trade>, quote: Quote?, fxNow: Double?, fxPrev: Double?, sessionDate: String,
        deflate: ((String) -> Double)? = null,
    ): Position {
        val list = trades.sortedWith(compareBy<Trade>({ it.tradeDate }, { it.id }))
        var qty = 0.0; var costUsd = 0.0; var costBase = 0.0; var realized = 0.0
        var costUsdR = 0.0; var costBaseR = 0.0; var realizedPrice = 0.0
        var todayBuyQty = 0.0; var todayBuyFxQty = 0.0; var todayBuyCost = 0.0; var todaySell = 0.0
        var qtyPrev = 0.0
        for (t in list) {
            val today = t.tradeDate >= sessionDate
            if (!today) qtyPrev = qty
            val d = deflate?.invoke(t.tradeDate) ?: 1.0
            if (t.side == "buy") {
                val usd = t.shares * t.price + t.fee
                qty += t.shares; costUsd += usd; costBase += usd * t.fx
                costUsdR += usd * d; costBaseR += usd * t.fx * d
                if (today) { todayBuyQty += t.shares; todayBuyFxQty += t.shares * t.fx; todayBuyCost += usd * t.fx }
            } else {
                if (qty <= 0) continue
                val q = min(t.shares, qty)
                val avgUsd = costUsd / qty; val avgBase = costBase / qty
                val avgUsdR = costUsdR / qty; val avgBaseR = costBaseR / qty
                val avgFxNow = if (costUsd != 0.0) costBase / costUsd else t.fx
                val proceedsUsd = q * t.price - t.fee
                val proceeds = proceedsUsd * t.fx
                realized += proceeds * d - q * avgBaseR
                realizedPrice += (proceedsUsd * d - q * avgUsdR) * avgFxNow
                costUsd -= q * avgUsd; costBase -= q * avgBase; qty -= q
                costUsdR -= q * avgUsdR; costBaseR -= q * avgBaseR
                if (today) todaySell += proceeds
            }
            if (!today) qtyPrev = qty
        }
        if (qty < 1e-9) { qty = 0.0; costUsd = 0.0; costBase = 0.0; costUsdR = 0.0; costBaseR = 0.0 }

        val price = quote?.price
        val prevClose = quote?.prevClose ?: price
        val fxP = fxPrev ?: fxNow
        val avgFx = if (costUsd != 0.0) costBase / costUsd else null
        val baseOut = Position(
            qty = qty, costUsd = costUsd, costBase = costBase, realized = realized, costReal = costBaseR, realizedPrice = realizedPrice,
            avgUsd = if (qty != 0.0) costUsd / qty else null, avgFx = avgFx, price = price, prevClose = prevClose,
        )
        if (price == null || fxNow == null) return baseOut

        val mvUsd = qty * price
        val mvBase = mvUsd * fxNow
        val unreal: Double; val unrealPct: Double?; val unrealPrice: Double; val unrealFx: Double
        if (qty != 0.0) {
            unreal = mvBase - costBaseR
            unrealPct = if (costBaseR != 0.0) unreal / costBaseR * 100 else null
            // JS 里 avgFx 不会为 null（qty>0 时 costUsd>0）；保险起见按 0 处理
            unrealPrice = (mvUsd - costUsdR) * (avgFx ?: 0.0)
            unrealFx = unreal - unrealPrice
        } else {
            unreal = 0.0; unrealPct = null; unrealPrice = 0.0; unrealFx = 0.0
        }
        val prevValue = qtyPrev * (prevClose ?: price) * (fxP ?: fxNow)
        val today = mvBase + todaySell - todayBuyCost - prevValue
        val kept = max(0.0, qty - todayBuyQty)
        val fp = fxP ?: fxNow
        val refFx = if (qty != 0.0) {
            (kept * fp + min(todayBuyQty, qty) * (if (todayBuyQty != 0.0) todayBuyFxQty / todayBuyQty else fp)) / qty
        } else fp
        val todayFx = mvUsd * (fxNow - refFx)
        return baseOut.copy(
            mvUsd = mvUsd, mvBase = mvBase, unreal = unreal, unrealPct = unrealPct, unrealPrice = unrealPrice, unrealFx = unrealFx,
            today = today, todayFx = todayFx, todayPrice = today - todayFx,
        )
    }

    /**
     * 一只股票的持仓。now / prev 为外汇交易中心报价表（prev 为昨收时的汇率，可为空）。
     */
    fun computeSymbol(
        trades: List<Trade>, quote: Quote?, now: Map<String, Rate>?, prev: Map<String, Rate>?,
        mode: String, base: String, sessionDate: String,
        deflate: ((String) -> ((String) -> Double)?)? = null,
    ): SymbolPosition {
        val groups = LinkedHashMap<String, MutableList<Trade>>()
        for (t in trades) groups.getOrPut(t.ccy?.takeIf { it.isNotEmpty() } ?: base) { mutableListOf() }.add(t)
        val toBaseNow = usdTo(now, base, mode)
        data class Part(val ccy: String, val p: Position, val k: Double?)
        val parts = groups.map { (c, list) ->
            val fn = usdTo(now, c, mode)
            val fp = usdTo(prev, c, mode)
            val p = computePosition(list, quote, fn, fp, sessionDate, deflate?.invoke(c))
            val k = if (fn != null && fn != 0.0 && toBaseNow != null && toBaseNow != 0.0) toBaseNow / fn else if (c == base) 1.0 else null
            Part(c, p, k)
        }
        fun sum(scale: Boolean, get: (Position) -> Double?): Double? {
            var total = 0.0; var any = false
            for (part in parts) {
                val v = get(part.p) ?: continue
                if (scale) { val k = part.k ?: continue; total += v * k } else total += v
                any = true
            }
            return if (any) total else if (parts.isNotEmpty()) null else 0.0
        }
        val price = quote?.price
        val prevClose = quote?.prevClose ?: price
        var qty = sum(false) { it.qty }
        var costUsd = sum(false) { it.costUsd }
        var costBase = sum(true) { it.costBase }
        var realized = sum(true) { it.realized }
        var costReal = sum(true) { it.costReal }
        var realizedPrice = sum(true) { it.realizedPrice }
        var mvUsd = sum(false) { it.mvUsd }
        var mvBase = sum(true) { it.mvBase }
        if (parts.isEmpty()) {
            qty = 0.0; costUsd = 0.0; costBase = 0.0; realized = 0.0; costReal = 0.0; realizedPrice = 0.0
            mvUsd = if (price != null) 0.0 else null; mvBase = mvUsd
        }
        val unreal = sum(true) { it.unreal }
        return SymbolPosition(
            ccys = parts.map { it.ccy },
            qty = qty, costUsd = costUsd, costBase = costBase, realized = realized, costReal = costReal, realizedPrice = realizedPrice,
            mvUsd = mvUsd, mvBase = mvBase,
            unreal = unreal, unrealPrice = sum(true) { it.unrealPrice }, unrealFx = sum(true) { it.unrealFx },
            today = sum(true) { it.today }, todayPrice = sum(true) { it.todayPrice }, todayFx = sum(true) { it.todayFx },
            price = price, prevClose = prevClose,
            avgUsd = if (qty != null && qty != 0.0 && costUsd != null) costUsd / qty else null,
            avgFx = if (parts.size == 1) parts[0].p.avgFx else null,
            unrealPct = if (qty != null && qty != 0.0 && costReal != null && costReal != 0.0 && unreal != null) unreal / costReal * 100 else null,
            fxPrevMissing = prev == null,
        )
    }

    fun totals(positions: Collection<SymbolPosition>): Totals {
        fun s(get: (SymbolPosition) -> Double?) = positions.sumOf { get(it) ?: 0.0 }
        val cost = s { it.costBase }
        val costReal = s { it.costReal }
        val unreal = s { it.unreal }
        return Totals(
            mvBase = s { it.mvBase }, costBase = cost, unreal = unreal, unrealPct = if (costReal != 0.0) unreal / costReal * 100 else null,
            unrealPrice = s { it.unrealPrice }, unrealFx = s { it.unrealFx },
            today = s { it.today }, todayPrice = s { it.todayPrice }, todayFx = s { it.todayFx }, realized = s { it.realized },
            costReal = costReal, realizedPrice = s { it.realizedPrice },
        )
    }

    /** 各币种现金：资金记录 + 买卖自动联动（买入从该笔货币扣除，卖出加回）。 */
    fun cashBalances(trades: List<Trade>, moves: List<CashMove>, base: String, until: String? = null): Map<String, Double> {
        val bal = LinkedHashMap<String, Double>()
        for (m in moves) {
            if (until != null && m.tradeDate > until) continue
            bal[m.ccy] = (bal[m.ccy] ?: 0.0) + m.amount
        }
        for (t in trades) {
            if (until != null && t.tradeDate > until) continue
            val usd = if (t.side == "buy") t.shares * t.price + t.fee else -(t.shares * t.price - t.fee)
            // funding = "usd"：用之前换好的美元，从美元现金扣（汇率只用于成本）；否则按成交汇率从该笔货币扣
            val c = if (t.funding == "usd") "USD" else t.ccy?.takeIf { it.isNotEmpty() } ?: base
            val amt = if (t.funding == "usd") usd else usd * t.fx
            bal[c] = (bal[c] ?: 0.0) - amt
        }
        return bal.filterValues { abs(it) >= 1e-9 }
    }

    /**
     * 总资本：各币种现金（按当前汇率折合本币）+ 美股持仓市值。
     * 占比按“正值资产合计”计算；现金为负（可能漏记入金）时单独列出。
     */
    fun capital(trades: List<Trade>, moves: List<CashMove>, rates: Map<String, Rate>?, base: String, mode: String, stockValueBase: Double?): Capital {
        val cash = cashBalances(trades, moves, base)
        val toBase = usdTo(rates, base, mode)
        val raw = mutableListOf<CapitalItem>()
        for ((ccy, amount) in cash) {
            val r = usdTo(rates, ccy, mode)
            val value = if (r != null && r != 0.0 && toBase != null && toBase != 0.0) amount * toBase / r else null
            raw.add(CapitalItem("cash", ccy, amount, value, null))
        }
        if (stockValueBase != null && stockValueBase != 0.0) raw.add(CapitalItem("stocks", "USD", null, stockValueBase, null))
        val gross = raw.sumOf { if ((it.value ?: 0.0) > 0) it.value!! else 0.0 }
        val net = raw.sumOf { it.value ?: 0.0 }
        val items = raw.map { it.copy(pct = if (gross > 0 && (it.value ?: 0.0) > 0) it.value!! / gross * 100 else null) }
            .sortedByDescending { it.value ?: Double.NEGATIVE_INFINITY }
        return Capital(items, gross, net, items.filter { it.value != null && it.value < 0 }, items.filter { it.value == null }.map { it.ccy })
    }
}
