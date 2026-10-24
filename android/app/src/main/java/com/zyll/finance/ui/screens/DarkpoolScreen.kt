package com.zyll.finance.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.zyll.finance.core.Fmt
import com.zyll.finance.data.Ats
import com.zyll.finance.data.COT_GROUP_ZH
import com.zyll.finance.data.DpDaily
import com.zyll.finance.data.DpRow
import com.zyll.finance.data.DpSymbol
import com.zyll.finance.data.DpWatch
import com.zyll.finance.data.Futures
import com.zyll.finance.data.Zyll
import com.zyll.finance.ui.AppNav
import com.zyll.finance.ui.components.ChartSeries
import com.zyll.finance.ui.components.EmptyHint
import com.zyll.finance.ui.components.GlassCard
import com.zyll.finance.ui.components.InteractiveChart
import com.zyll.finance.ui.components.KV
import com.zyll.finance.ui.components.LoadBox
import com.zyll.finance.ui.components.Loader
import com.zyll.finance.ui.components.MembersOnlyBox
import com.zyll.finance.ui.components.Muted
import com.zyll.finance.ui.components.RatioBar
import com.zyll.finance.ui.components.ScreenHeader
import com.zyll.finance.ui.components.SectionTitle
import com.zyll.finance.ui.components.Segmented
import com.zyll.finance.ui.components.SelectBox
import com.zyll.finance.ui.components.SeriesType
import com.zyll.finance.ui.components.SymbolField
import com.zyll.finance.ui.components.rememberLoader
import com.zyll.finance.ui.theme.LocalUpDown
import com.zyll.finance.ui.theme.Palette

@Composable
fun DarkpoolScreen() {
    var tab by rememberSaveable { mutableStateOf(0) }
    val token by Zyll.session.token.collectAsState()
    val lists by Zyll.listsVersion.collectAsState()
    val daily = rememberLoader("daily") { DpDaily.parse(Zyll.api.obj("/darkpool/daily")) }
    val watch = rememberLoader(token, lists) { if (token == null) null else DpWatch.parse(Zyll.api.obj("/darkpool/watch")) }
    val ats = rememberLoader("ats") { Ats.parse(Zyll.api.obj("/darkpool/ats")) ?: Ats("", null, emptyList(), null) }
    val fut = rememberLoader("fut", token) { Futures.parse(Zyll.api.obj("/futures")) }

    LaunchedEffect(Unit) {
        Zyll.live.events.collect { ev ->
            when (ev.topic) {
                "finra_daily" -> { daily.reload(silent = true); watch.reload(silent = true) }
                "finra_ats" -> ats.reload(silent = true)
                "futures", "cftc" -> fut.reload(silent = true)
            }
        }
    }

    Column(Modifier.fillMaxSize()) {
        ScreenHeader("暗盘 · 美期", "数据来源 FINRA / CME / CFTC", onRefresh = {
            when (tab) { 0 -> { daily.reload(); watch.reload() }; 1 -> ats.reload(); 3 -> fut.reload(); else -> {} }
        })
        Segmented(listOf("场外卖空", "ATS 周报", "个股", "股指期货"), tab, Modifier.padding(horizontal = 12.dp)) { tab = it }
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 12.dp).padding(top = 8.dp, bottom = 24.dp)) {
            when (tab) {
                0 -> DailyTab(daily, watch, token != null)
                1 -> AtsTab(ats)
                2 -> SymbolTab()
                3 -> FuturesTab(fut)
            }
        }
    }
}

private fun stamp(fetched: Double?, date: String) = buildString {
    if (date.isNotBlank()) append("数据日期 $date")
    if (fetched != null) append(if (isEmpty()) "" else " · ").append("最后更新 ${Fmt.dateTime(fetched.toLong())}")
}

@Composable
private fun DailyTab(daily: Loader<DpDaily>, watch: Loader<DpWatch?>, loggedIn: Boolean) {
    LoadBox(daily) { d ->
        GlassCard(Modifier.fillMaxWidth()) {
            SectionTitle("全市场场外卖空占比")
            Muted(stamp(d.fetched, d.date))
            val m = d.market
            val last = m.lastOrNull()
            if (last != null) {
                Row(Modifier.padding(top = 6.dp), verticalAlignment = Alignment.Bottom) {
                    Text(Fmt.ratio(last.ratio), fontWeight = FontWeight.SemiBold, fontSize = 24.sp, color = Palette.Accent)
                    Spacer(Modifier.width(8.dp))
                    val prev = m.getOrNull(m.size - 2)
                    if (prev?.ratio != null && last.ratio != null) {
                        val diff = (last.ratio - prev.ratio) * 100
                        Muted("较前一日 ${Fmt.signed(diff, 1)} 个百分点", Modifier.padding(bottom = 4.dp))
                    }
                }
                val avg = m.mapNotNull { it.ratio }.let { if (it.isEmpty()) null else it.average() }
                if (avg != null && m.size > 1) Muted("近 ${m.size} 日均值 ${Fmt.ratio(avg)}，高于 50% 通常表示做市商卖空较多（不等于看空）")
                InteractiveChart(
                    labels = m.map { it.date.takeLast(5).replace("-", "/") },
                    series = listOf(
                        ChartSeries("卖空量", m.map { it.short }, Palette.Accent2.copy(alpha = 0.55f), SeriesType.BAR),
                        ChartSeries("卖空占比", m.map { it.ratio?.times(100) }, Palette.Gold, width = 2.2f, rightAxis = true),
                    ),
                    format = { Fmt.compact(it) }, formatRight = { Fmt.num(it, 1) + "%" },
                    tipTitle = { m[it].date }, modifier = Modifier.padding(top = 8.dp),
                )
            } else EmptyHint("暂无数据")
        }
        Spacer(Modifier.height(12.dp))
        SectionTitle("我的关注（与持仓分析同步）")
        if (!loggedIn) Muted("登录后，持仓分析里的股票会自动出现在这里。")
        else LoadBox(watch) { w ->
            if (w == null || w.rows.isEmpty()) Muted("持仓分析里还没有股票，或这些股票今天没有场外卖空数据。")
            else DpTable(w.rows, d.date)
            if (w != null && w.missing.isNotEmpty()) Muted("暂无数据：${w.missing.joinToString("、")}")
        }
        Spacer(Modifier.height(12.dp))
        SectionTitle("成交量最大")
        DpTable(d.topVolume, d.date)
        Spacer(Modifier.height(12.dp))
        SectionTitle("卖空占比最高")
        DpTable(d.topShortRatio, d.date)
        if (d.watchlist.isNotEmpty()) {
            Spacer(Modifier.height(12.dp))
            SectionTitle("常见 ETF 与大盘股")
            DpTable(d.watchlist, d.date)
        }
    }
}

@Composable
private fun DpTable(rows: List<DpRow>, date: String) {
    GlassCard(Modifier.fillMaxWidth(), padding = PaddingValues(horizontal = 12.dp, vertical = 6.dp)) {
        Row(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
            Muted("代码", Modifier.weight(1f), 11); Muted("卖空 / 总量", Modifier.weight(1.4f), 11); Muted("占比", Modifier.weight(1.2f), 11)
        }
        rows.forEach { r ->
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).clickable { AppNav.openStock(r.symbol) }.padding(vertical = 6.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(r.symbol, fontWeight = FontWeight.SemiBold, fontSize = 13.sp, modifier = Modifier.weight(1f))
                Text("${Fmt.compact(r.short)} / ${Fmt.compact(r.total)}", fontSize = 12.sp, modifier = Modifier.weight(1.4f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                Column(Modifier.weight(1.2f)) {
                    Text(Fmt.ratio(r.ratio), fontSize = 12.sp, color = if ((r.ratio ?: 0.0) >= 0.5) Palette.Gold else Palette.Text)
                    RatioBar((r.ratio ?: 0.0).toFloat(), if ((r.ratio ?: 0.0) >= 0.5) Palette.Gold else Palette.Accent, Modifier.fillMaxWidth())
                }
            }
        }
        if (rows.isEmpty()) EmptyHint("暂无数据")
        if (date.isNotBlank()) Muted("FINRA 场外（非交易所）成交中的卖空量，$date", Modifier.padding(vertical = 4.dp), 10)
    }
}

@Composable
private fun AtsTab(ats: Loader<Ats>) {
    LoadBox(ats) { a ->
        GlassCard(Modifier.fillMaxWidth()) {
            SectionTitle("暗池（ATS）成交排行")
            Muted(stamp(a.fetched, if (a.week.isNotBlank()) "${a.week} 当周" else ""))
            if (a.totalShares != null) KV("全部 ATS 成交股数", Fmt.compact(a.totalShares) + "股")
            Muted("FINRA 按周公布，延迟约 2~4 周。", Modifier.padding(bottom = 6.dp), 11)
            AtsFirms(a)
        }
    }
}

@Composable
private fun AtsFirms(a: Ats) {
    if (a.firms.isEmpty()) { EmptyHint("暂无数据"); return }
    a.firms.forEachIndexed { i, f ->
        Column(Modifier.padding(vertical = 5.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(f.name.ifBlank { f.mpid }, fontSize = 13.sp, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(Fmt.ratio(f.sharePct), fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
            }
            RatioBar((f.sharePct ?: 0.0).toFloat(), Palette.Series[i % Palette.Series.size], Modifier.fillMaxWidth().padding(vertical = 2.dp))
            Muted("${f.mpid} · ${Fmt.compact(f.shares)}股 · ${Fmt.compact(f.trades)}笔 · 平均每笔 ${Fmt.num(f.avgSize, 0)} 股", size = 11)
        }
    }
}

@Composable
private fun SymbolTab() {
    var input by rememberSaveable { mutableStateOf("") }
    var query by rememberSaveable { mutableStateOf("") }
    Row(verticalAlignment = Alignment.Top) {
        SymbolField(input, { input = it }, Modifier.weight(1f), onPick = { input = it.symbol; query = it.symbol }, onDone = { query = input.trim() })
        Spacer(Modifier.width(8.dp))
        Button(onClick = { query = input.trim() }, modifier = Modifier.padding(top = 8.dp)) { Text("查询") }
    }
    Spacer(Modifier.height(10.dp))
    if (query.isBlank()) {
        Muted("输入美股代码，查看该股票每天的场外卖空占比和在各个暗池的成交分布。")
        return
    }
    val d = rememberLoader(query) { DpSymbol.parse(Zyll.api.obj("/darkpool/symbol/${query}")) }
    LoadBox(d) { s ->
        GlassCard(Modifier.fillMaxWidth()) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(s.symbol, fontWeight = FontWeight.SemiBold, fontSize = 18.sp, modifier = Modifier.weight(1f))
                Text("看K线", color = Palette.Accent, modifier = Modifier.clickable { AppNav.openStock(s.symbol) })
            }
            Muted(stamp(null, s.history.lastOrNull()?.date.orEmpty()))
            if (s.history.isEmpty()) EmptyHint("没有该股票的场外卖空数据")
            else InteractiveChart(
                labels = s.history.map { it.date.takeLast(5).replace("-", "/") },
                series = listOf(
                    ChartSeries("总量", s.history.map { it.total }, Palette.Accent2.copy(alpha = 0.45f), SeriesType.BAR),
                    ChartSeries("卖空占比", s.history.map { it.ratio?.times(100) }, Palette.Gold, width = 2.2f, rightAxis = true),
                ),
                format = { Fmt.compact(it) }, formatRight = { Fmt.num(it, 1) + "%" }, tipTitle = { s.history[it].date },
                modifier = Modifier.padding(top = 8.dp),
            )
        }
        Spacer(Modifier.height(12.dp))
        GlassCard(Modifier.fillMaxWidth()) {
            SectionTitle("暗池成交分布")
            val a = s.ats
            if (a == null) Muted("暂无该股票的 ATS 周报数据")
            else {
                Muted(stamp(a.fetched, if (a.week.isNotBlank()) "${a.week} 当周" else ""))
                if (a.totalShares != null) KV("ATS 合计", Fmt.compact(a.totalShares) + "股")
                AtsFirms(a)
            }
        }
    }
}

@Composable
private fun FuturesTab(fut: Loader<Futures>) {
    val ud = LocalUpDown.current
    LoadBox(fut) { f ->
        GlassCard(Modifier.fillMaxWidth()) {
            SectionTitle("股指期货") { if (f.delayed) Muted("延迟行情") }
            Muted(f.updated?.let { "最后更新 ${Fmt.dateTime(it.toLong())}" } ?: "")
            if (f.futures.isEmpty()) EmptyHint("暂无数据")
            f.futures.forEach { x ->
                val q = x.front
                Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(x.name.ifBlank { x.root }, fontSize = 14.sp)
                        Muted("${x.root} ${q?.month.orEmpty()} · ${x.source}", size = 11)
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text(Fmt.num(q?.last, 2), color = ud.of(q?.change), fontWeight = FontWeight.SemiBold)
                        Text("${Fmt.signed(q?.change)}  ${Fmt.pct(q?.changePct)}", color = ud.of(q?.change), fontSize = 12.sp)
                    }
                }
                if (q != null) Muted("昨结 ${Fmt.num(q.priorSettle)} · 开 ${Fmt.num(q.open)} · 高 ${Fmt.num(q.high)} · 低 ${Fmt.num(q.low)}" +
                    (q.volume?.let { " · 量 ${Fmt.compact(it)}" } ?: ""), size = 11)
                HorizontalDivider(color = Color(0x10FFFFFF), modifier = Modifier.padding(top = 6.dp))
            }
        }
        Spacer(Modifier.height(12.dp))
        when {
            f.cotLocked -> MembersOnlyBox("CFTC 持仓报告仅会员可见")
            f.cot.isEmpty() -> GlassCard(Modifier.fillMaxWidth()) { SectionTitle("CFTC 持仓（TFF）"); EmptyHint("暂无数据") }
            else -> CotCard(f)
        }
    }
}

@Composable
private fun CotCard(f: Futures) {
    val ud = LocalUpDown.current
    var idx by remember(f.cot.size) { mutableStateOf(0) }
    val m = f.cot[idx.coerceIn(0, f.cot.size - 1)]
    GlassCard(Modifier.fillMaxWidth()) {
        SectionTitle("CFTC 持仓（TFF）")
        Muted("报告日期 ${f.cotDate} · 每周五公布周二数据")
        if (f.cot.size > 1) SelectBox("合约", m, f.cot, { it.market }, Modifier.fillMaxWidth().padding(vertical = 6.dp)) { idx = f.cot.indexOf(it) }
        else Muted(m.market, Modifier.padding(vertical = 4.dp), 12)
        val h = m.history
        if (h.size >= 2) InteractiveChart(
            labels = h.map { it.date.takeLast(5).replace("-", "/") },
            series = listOf(
                ChartSeries("杠杆基金净持仓", h.map { it.groups["lev_money"]?.net }, Palette.Gold, width = 2f),
                ChartSeries("资产管理净持仓", h.map { it.groups["asset_mgr"]?.net }, Palette.Accent, width = 2f),
                ChartSeries("交易商净持仓", h.map { it.groups["dealer"]?.net }, Palette.Accent2, width = 1.4f, dashed = true),
            ),
            zeroLine = true, format = { Fmt.compact(it) }, tipTitle = { h[it].date }, modifier = Modifier.padding(top = 6.dp),
        )
        m.latest?.let { r ->
            Spacer(Modifier.height(8.dp))
            r.openInterest?.let { KV("未平仓合约", "${Fmt.compact(it)}（${Fmt.signed(r.oiChange, 0)}）") }
            COT_GROUP_ZH.forEach { (k, zh) ->
                val g = r.groups[k] ?: return@forEach
                if (g.long == 0.0 && g.short == 0.0) return@forEach
                Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(zh, fontSize = 13.sp)
                        Muted("多 ${Fmt.compact(g.long)} · 空 ${Fmt.compact(g.short)}", size = 11)
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text("净 ${Fmt.compact(g.net)}", fontSize = 13.sp, color = ud.of(g.net), fontWeight = FontWeight.SemiBold)
                        Text("周变化 ${Fmt.signed(g.netChange, 0)}", fontSize = 11.sp, color = ud.of(g.netChange))
                    }
                }
            }
        }
    }
}
