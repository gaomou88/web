package com.zyll.finance.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.zyll.finance.core.Fmt
import com.zyll.finance.core.Pnl
import com.zyll.finance.core.PlView
import com.zyll.finance.core.SymbolPosition
import com.zyll.finance.core.Totals
import com.zyll.finance.data.HistPoint
import com.zyll.finance.data.PfHistory
import com.zyll.finance.ui.components.ChartSeries
import com.zyll.finance.ui.components.GlassCard
import com.zyll.finance.ui.components.InteractiveChart
import com.zyll.finance.ui.components.Muted
import com.zyll.finance.ui.components.RatioBar
import com.zyll.finance.ui.components.SeriesType
import com.zyll.finance.ui.components.Sparkline
import com.zyll.finance.ui.components.StatGrid
import com.zyll.finance.ui.theme.LocalUpDown
import com.zyll.finance.ui.theme.Palette
import com.zyll.finance.ui.theme.UpDown
import kotlin.math.abs
import kotlin.math.max

/** 汇总卡片的分析弹窗种类 */
enum class PfCard(val title: String) { MV("总市值"), TODAY("今日盈亏"), UNREAL("持仓盈亏"), TOTAL("总盈亏") }

/** 持仓分析汇总需要的数据（与网页 pf_analysis.js 相同的口径） */
class PfSummary(
    val base: String,
    val sessionDate: String,
    val totals: Totals,
    val positions: List<Pair<String, SymbolPosition>>,
    val hist: PfHistory?,
    /** 扣除通胀 / 计入汇率：所有盈亏数字和图表都按这两个开关取值 */
    val inflation: Boolean = false,
    val includeFx: Boolean = true,
) {
    fun money(v: Double?) = Fmt.money(v, base)
    fun signed(v: Double?) = Fmt.signedMoney(v, base)
    fun axis(v: Double) = Fmt.ccySymbol(base) + Fmt.compact(v)

    /** 当前视图下的合计 */
    val v: PlView get() = Pnl.view(totals, includeFx)
    fun pv(p: SymbolPosition): PlView = Pnl.view(p, includeFx)
    val cost: Double get() = if (inflation) totals.costReal else totals.costBase
    val costLabel: String get() = if (inflation) "成本（今天购买力）" else "成本"
    val pct: Double? get() = v.unreal?.let { u -> if (cost != 0.0) u / cost * 100 else null }
    fun ppct(p: SymbolPosition): Double? {
        val c = (if (inflation) p.costReal else p.costBase) ?: return null
        return pv(p).unreal?.let { if (c != 0.0) it / c * 100 else null }
    }

    /** 历史 + 今天（实时）合成的序列 */
    val series: List<HistPoint> by lazy {
        val pts = hist?.view(inflation, includeFx).orEmpty().toMutableList()
        val t = totals
        val live = HistPoint(sessionDate, t.mvBase, cost, v.unreal, v.realized, v.total, null, null, v.today, live = true)
        if (pts.isNotEmpty() && pts.last().date >= sessionDate) {
            val last = pts.last()
            pts[pts.size - 1] = live.copy(cash = last.cash, capital = last.capital)
        } else pts.add(live)
        pts
    }

    fun prevDays(n: Int): List<HistPoint> = series.filter { !it.live && it.date < sessionDate && it.dayPl != null }.takeLast(n)

    /** 视图说明（扣除通胀 / 不计汇率） */
    val viewNotes: List<String> get() = listOfNotNull(
        if (inflation) "已扣除通胀：每笔成本和卖出所得按付款货币所在地区的 CPI 折算到今天的购买力；今日盈亏不受影响。" else null,
        if (!includeFx) "未计入汇率：盈亏只含股价部分，按买入时的平均成本汇率换算。" else null,
    )

    /** 与 back 个交易日前相比的变化：(差额, 百分比) */
    fun change(key: (HistPoint) -> Double?, back: Int): Pair<Double?, Double?> {
        val pts = series
        if (pts.size < 2) return Pair(null, null)
        val now = key(pts.last()) ?: return Pair(null, null)
        val was = key(pts[max(0, pts.size - 1 - back)]) ?: return Pair(null, null)
        return Pair(now - was, if (was != 0.0) (now - was) / abs(was) * 100 else null)
    }
}

private fun label(d: String) = if (d.length >= 10) d.substring(5).replace("-", "/") else d

@Composable
fun SummaryTiles(s: PfSummary, onOpen: (PfCard) -> Unit) {
    val ud = LocalUpDown.current
    val t = s.totals
    val v = s.v
    val today = v.today ?: 0.0
    val y = s.prevDays(1).firstOrNull()
    val wk = s.prevDays(5)
    val avg = if (wk.isNotEmpty()) wk.sumOf { it.dayPl ?: 0.0 } / wk.size else null
    val pts = s.series
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Tile(PfCard.MV.title, s.money(t.mvBase), Palette.Text, "${s.costLabel} ${s.money(s.cost)}", null,
                pts.mapNotNull { it.mv }, Palette.Accent, Modifier.weight(1f)) { onOpen(PfCard.MV) }
            Tile(PfCard.TODAY.title, s.signed(v.today), ud.of(v.today),
                if (s.includeFx) "股价 ${s.signed(t.todayPrice)} · 汇率 ${s.signed(t.todayFx)}" else "不含汇率影响",
                buildString {
                    if (y?.dayPl != null) append("较昨日 ${s.signed(today - y.dayPl)}")
                    if (avg != null) append(if (isEmpty()) "" else "\n").append("较近一周均值 ${s.signed(today - avg)}")
                }.ifBlank { null },
                pts.takeLast(20).mapNotNull { it.dayPl }, ud.of(v.today), Modifier.weight(1f)) { onOpen(PfCard.TODAY) }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Tile(PfCard.UNREAL.title, s.signed(v.unreal) + "  " + Fmt.pct(s.pct), ud.of(v.unreal),
                (if (s.includeFx) "股价 ${s.signed(t.unrealPrice)} · 汇率 ${s.signed(t.unrealFx)}" else "不含汇率影响") + (if (s.inflation) " · 已扣除通胀" else ""), null,
                pts.mapNotNull { it.unreal }, ud.of(v.unreal), Modifier.weight(1f)) { onOpen(PfCard.UNREAL) }
            Tile(PfCard.TOTAL.title, s.signed(v.total), ud.of(v.total),
                "已实现 ${s.signed(v.realized)}", null,
                pts.mapNotNull { it.totalPl }, ud.of(v.total), Modifier.weight(1f)) { onOpen(PfCard.TOTAL) }
        }
    }
}

@Composable
private fun Tile(title: String, main: String, color: Color, sub: String, extra: String?, spark: List<Double>, sparkColor: Color, modifier: Modifier, onClick: () -> Unit) {
    GlassCard(modifier, onClick = onClick, padding = PaddingValues(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(title, fontSize = 12.sp, color = Palette.Muted, modifier = Modifier.weight(1f))
            Text("ⓘ", fontSize = 11.sp, color = Palette.Muted)
        }
        Text(main, fontWeight = FontWeight.SemiBold, fontSize = 16.sp, color = color, maxLines = 1, overflow = TextOverflow.Ellipsis)
        Text(sub, fontSize = 10.sp, color = Palette.Muted, maxLines = 2)
        if (extra != null) Text(extra, fontSize = 10.sp, color = Palette.Muted, maxLines = 2)
        Spacer(Modifier.height(4.dp))
        Sparkline(spark, sparkColor, Modifier.fillMaxWidth().height(28.dp))
    }
}

/** 点卡片后的底部弹窗：分析 + 交互折线图 */
@Composable
fun AnalysisSheet(card: PfCard, s: PfSummary) {
    val ud = LocalUpDown.current
    Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 18.dp).padding(bottom = 24.dp).navigationBarsPadding()) {
        when (card) {
            PfCard.MV -> MvAnalysis(s, ud)
            PfCard.TODAY -> TodayAnalysis(s, ud)
            PfCard.UNREAL -> UnrealAnalysis(s, ud)
            PfCard.TOTAL -> TotalAnalysis(s, ud)
        }
        Spacer(Modifier.height(10.dp))
        val h = s.hist
        when {
            h == null -> Muted("历史数据加载中…")
            h.points.size < 2 -> Muted("历史数据还不够多：添加交易记录后，本站会用历史收盘价回算每天的市值。")
        }
        if (h?.approxFx == true) Muted("部分日期缺少历史汇率，已用当前汇率近似。")
        s.viewNotes.forEach { Muted(it, Modifier.padding(top = 4.dp)) }
        if (!h?.missing.isNullOrEmpty()) Muted("缺少收盘价：${h!!.missing.joinToString("、")}")
    }
}

@Composable
private fun Head(title: String, value: String, color: Color = Palette.Text) {
    Row(Modifier.fillMaxWidth().padding(bottom = 10.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(title, fontWeight = FontWeight.SemiBold, fontSize = 18.sp, modifier = Modifier.weight(1f))
        Text(value, fontWeight = FontWeight.SemiBold, fontSize = 18.sp, color = color)
    }
}

private fun pctTxt(v: Double?, d: Int = 2) = Fmt.pct(v, d)

@Composable
private fun MvAnalysis(s: PfSummary, ud: UpDown) {
    val t = s.totals
    val pts = s.series
    val (d1, p1) = s.change({ it.mv }, 1)
    val (d5, p5) = s.change({ it.mv }, 5)
    val (d21, p21) = s.change({ it.mv }, 21)
    val mvs = pts.mapNotNull { it.mv }
    // 盈亏回撤：总盈亏从高点回落的最大幅度（不受资金进出影响）
    var peak = Double.NEGATIVE_INFINITY; var dd = 0.0
    pts.forEach { p -> p.totalPl?.let { peak = max(peak, it); dd = max(dd, peak - it) } }
    val pos = s.positions.filter { (it.second.mvBase ?: 0.0) > 0 }.sortedByDescending { it.second.mvBase }
    Head("总市值", s.money(t.mvBase))
    StatGrid(listOf(
        Triple("较上一交易日", "${s.signed(d1)} (${pctTxt(p1)})", ud.of(d1)),
        Triple("近一周", "${s.signed(d5)} (${pctTxt(p5)})", ud.of(d5)),
        Triple("近一月", "${s.signed(d21)} (${pctTxt(p21)})", ud.of(d21)),
        Triple("区间最高 / 最低", if (mvs.isNotEmpty()) "${s.money(mvs.max())} / ${s.money(mvs.min())}" else "—", null),
        Triple("最大盈亏回撤", if (dd > 0) s.money(-dd) else "—", if (dd > 0) ud.down else null),
        Triple("第一大持仓", if (pos.isNotEmpty() && t.mvBase != 0.0) "${pos[0].first} ${Fmt.num(pos[0].second.mvBase!! / t.mvBase * 100, 1)}%" else "—", null),
    ))
    Muted("市值变化包含买入卖出带来的资金进出；看投资表现请参考“总盈亏”。", Modifier.padding(top = 6.dp))
    if (pts.size >= 2) InteractiveChart(
        labels = pts.map { label(it.date) },
        series = listOf(
            ChartSeries("市值", pts.map { it.mv }, Palette.Accent, SeriesType.AREA),
            ChartSeries("成本", pts.map { if (it.live) t.costBase else it.cost }, Palette.Gold, dashed = true, width = 1.5f),
        ),
        format = s::axis, tipTitle = { pts[it].date + if (pts[it].live) "（实时）" else "" }, modifier = Modifier.padding(top = 10.dp),
    )
    if (pos.isNotEmpty()) {
        Spacer(Modifier.height(10.dp))
        Muted("持仓占比")
        pos.take(6).forEachIndexed { i, (sym, p) ->
            val w = (p.mvBase ?: 0.0) / t.mvBase
            Row(Modifier.fillMaxWidth().padding(vertical = 3.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(sym, fontSize = 13.sp, modifier = Modifier.width(64.dp))
                RatioBar(w.toFloat(), Palette.Series[i % Palette.Series.size], Modifier.weight(1f))
                Text("${Fmt.num(w * 100, 1)}%", fontSize = 12.sp, modifier = Modifier.width(56.dp).padding(start = 6.dp))
            }
        }
    }
}

@Composable
private fun TodayAnalysis(s: PfSummary, ud: UpDown) {
    val t = s.totals
    val today = s.v.today ?: 0.0
    val days = s.prevDays(20)
    val y = days.lastOrNull()
    val wk = days.takeLast(5)
    val avg = if (wk.isNotEmpty()) wk.sumOf { it.dayPl ?: 0.0 } / wk.size else null
    val wins = days.count { (it.dayPl ?: 0.0) > 0 }
    val movers = s.positions.filter { (s.pv(it.second).today ?: 0.0) != 0.0 }.sortedByDescending { abs(s.pv(it.second).today ?: 0.0) }.take(5)
    Head("今日盈亏", s.signed(today), ud.of(today))
    StatGrid(listOfNotNull(
        Triple("昨日盈亏", y?.dayPl?.let { s.signed(it) } ?: "—", ud.of(y?.dayPl)),
        Triple("较昨日", y?.dayPl?.let { s.signed(today - it) } ?: "—", y?.dayPl?.let { ud.of(today - it) }),
        Triple("近一周日均", avg?.let { s.signed(it) } ?: "—", ud.of(avg)),
        Triple("较近一周均值", avg?.let { s.signed(today - it) } ?: "—", avg?.let { ud.of(today - it) }),
        if (s.includeFx) Triple("股价部分", s.signed(t.todayPrice), ud.of(t.todayPrice)) else null,
        if (s.includeFx) Triple("汇率部分", s.signed(t.todayFx), ud.of(t.todayFx)) else null,
        if (days.isNotEmpty()) Triple("近 ${days.size} 日盈利天数", "$wins / ${days.size}", null) else null,
    ))
    val pts = days + HistPoint(s.sessionDate, null, null, null, null, null, null, null, today, live = true)
    if (pts.size >= 2) InteractiveChart(
        labels = pts.map { label(it.date) },
        series = listOfNotNull(
            ChartSeries("当日盈亏", pts.map { it.dayPl }, type = SeriesType.BAR, barColor = { v -> if (v >= 0) ud.up else ud.down }),
            avg?.let { a -> ChartSeries("近一周均值", pts.map { a }, Palette.Gold, dashed = true, width = 1.2f) },
        ),
        zeroLine = true, format = s::axis, tipTitle = { pts[it].date + if (pts[it].live) "（实时）" else "" }, modifier = Modifier.padding(top = 10.dp),
    )
    if (movers.isNotEmpty()) {
        Spacer(Modifier.height(10.dp))
        Muted("今日影响最大")
        movers.forEach { (sym, p) ->
            Row(Modifier.fillMaxWidth().padding(vertical = 3.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(sym, fontSize = 13.sp, modifier = Modifier.width(64.dp))
                Muted(if (s.includeFx) "股价 ${s.signed(p.todayPrice)} · 汇率 ${s.signed(p.todayFx)}" else "", Modifier.weight(1f), 11)
                Text(s.signed(s.pv(p).today), color = ud.of(s.pv(p).today), fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

@Composable
private fun UnrealAnalysis(s: PfSummary, ud: UpDown) {
    val t = s.totals
    val v = s.v
    val pts = s.series
    val pos = s.positions.filter { (it.second.qty ?: 0.0) != 0.0 }.sortedByDescending { s.pv(it.second).unreal ?: 0.0 }
    val fxShare = if (s.includeFx && (v.unreal ?: 0.0) != 0.0) t.unrealFx / abs(v.unreal!!) * 100 else null
    Head("持仓盈亏", "${s.signed(v.unreal)} (${pctTxt(s.pct)})", ud.of(v.unreal))
    StatGrid(listOfNotNull(
        if (s.includeFx) Triple("股价部分", s.signed(t.unrealPrice), ud.of(t.unrealPrice)) else null,
        if (s.includeFx) Triple("汇率部分", s.signed(t.unrealFx), ud.of(t.unrealFx)) else null,
        if (s.includeFx) Triple("汇率贡献占比", fxShare?.let { pctTxt(it, 1) } ?: "—", ud.of(t.unrealFx)) else null,
        Triple(if (s.inflation) "持仓成本（今天购买力）" else "持仓成本", s.money(s.cost), null),
        if (s.inflation) Triple("通胀侵蚀", s.signed(t.costBase - t.costReal), ud.of(t.costBase - t.costReal)) else null,
        Triple("盈利只数", "${pos.count { (s.pv(it.second).unreal ?: 0.0) > 0 }} / ${pos.size}", null),
    ))
    if (pts.size >= 2) InteractiveChart(
        labels = pts.map { label(it.date) },
        series = listOf(ChartSeries("持仓盈亏", pts.map { it.unreal }, Palette.Accent, SeriesType.AREA)),
        zeroLine = true, format = s::axis, tipTitle = { pts[it].date }, modifier = Modifier.padding(top = 10.dp),
    )
    if (pos.isNotEmpty()) {
        Spacer(Modifier.height(10.dp))
        Muted("贡献最大 / 最小")
        val top = pos.take(3)
        (top + pos.takeLast(3).filter { it !in top }).forEach { (sym, p) ->
            Row(Modifier.fillMaxWidth().padding(vertical = 3.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(sym, fontSize = 13.sp, modifier = Modifier.width(64.dp))
                Muted(if (s.includeFx) "股价 ${s.signed(p.unrealPrice)} · 汇率 ${s.signed(p.unrealFx)}" else "", Modifier.weight(1f), 11)
                Text("${s.signed(s.pv(p).unreal)} (${pctTxt(s.ppct(p), 1)})", color = ud.of(s.pv(p).unreal), fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

@Composable
private fun TotalAnalysis(s: PfSummary, ud: UpDown) {
    val v = s.v
    val pts = s.series
    val (d5, _) = s.change({ it.totalPl }, 5)
    val (d21, _) = s.change({ it.totalPl }, 21)
    val realizedBy = s.positions.filter { (s.pv(it.second).realized ?: 0.0) != 0.0 }.sortedByDescending { s.pv(it.second).realized }
    Head("总盈亏", s.signed(v.total), ud.of(v.total))
    StatGrid(listOf(
        Triple("已实现", s.signed(v.realized), ud.of(v.realized)),
        Triple("持仓盈亏", s.signed(v.unreal), ud.of(v.unreal)),
        Triple("近一周变化", s.signed(d5), ud.of(d5)),
        Triple("近一月变化", s.signed(d21), ud.of(d21)),
    ))
    Muted(if (s.includeFx && !s.inflation) "总盈亏 = 已实现盈亏（卖出结转）+ 持仓盈亏，均含汇率影响，不受资金进出影响。"
        else "总盈亏 = 已实现盈亏 + 持仓盈亏（按开关：${listOfNotNull(if (s.inflation) "扣除通胀" else null, if (!s.includeFx) "不计汇率" else null).joinToString("、")}）。",
        Modifier.padding(top = 6.dp))
    if (pts.size >= 2) InteractiveChart(
        labels = pts.map { label(it.date) },
        series = listOf(
            ChartSeries("总盈亏", pts.map { it.totalPl }, Palette.Accent, SeriesType.AREA),
            ChartSeries("已实现", pts.map { it.realized }, Palette.Gold, dashed = true, width = 1.5f),
        ),
        zeroLine = true, format = s::axis, tipTitle = { pts[it].date }, modifier = Modifier.padding(top = 10.dp),
    )
    if (realizedBy.isNotEmpty()) {
        Spacer(Modifier.height(10.dp))
        Muted("已实现盈亏来源")
        realizedBy.take(6).forEach { (sym, p) ->
            Row(Modifier.fillMaxWidth().padding(vertical = 3.dp)) {
                Text(sym, fontSize = 13.sp, modifier = Modifier.weight(1f))
                Text(s.signed(s.pv(p).realized), color = ud.of(s.pv(p).realized), fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}
