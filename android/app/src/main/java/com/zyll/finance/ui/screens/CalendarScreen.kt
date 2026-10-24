package com.zyll.finance.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
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
import com.zyll.finance.data.CalDetail
import com.zyll.finance.data.CalEvent
import com.zyll.finance.data.Holidays
import com.zyll.finance.data.MarketToday
import com.zyll.finance.data.Zyll
import com.zyll.finance.ui.components.ChartSeries
import com.zyll.finance.ui.components.GlassCard
import com.zyll.finance.ui.components.InteractiveChart
import com.zyll.finance.ui.components.LoadBox
import com.zyll.finance.ui.components.Muted
import com.zyll.finance.ui.components.ScreenHeader
import com.zyll.finance.ui.components.Segmented
import com.zyll.finance.ui.components.Tag
import com.zyll.finance.ui.components.rememberLoader
import com.zyll.finance.ui.theme.LocalUpDown
import com.zyll.finance.ui.theme.Palette
import org.json.JSONArray

private val IMPACT_COLOR = mapOf(3 to Color(0xFFFF5D5D), 2 to Color(0xFFF5B971), 1 to Color(0xFFE8D36A), 0 to Color(0xFF8C9AB3))
private val IMPACT_ZH = mapOf(3 to "非常重要", 2 to "重要", 1 to "一般", 0 to "节假日")

private val REGION_FLAG = mapOf(
    "US" to "🇺🇸", "EU" to "🇪🇺", "CN" to "🇨🇳", "JP" to "🇯🇵", "GB" to "🇬🇧", "DE" to "🇩🇪", "FR" to "🇫🇷", "IT" to "🇮🇹",
    "CA" to "🇨🇦", "AU" to "🇦🇺", "NZ" to "🇳🇿", "CH" to "🇨🇭", "HK" to "🇭🇰", "SG" to "🇸🇬", "KR" to "🇰🇷", "IN" to "🇮🇳",
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CalendarScreen() {
    val events = rememberLoader("cal") { CalEvent.list(Zyll.api.get("/calendar") as? JSONArray) }
    val next = rememberLoader("next") { CalEvent.list(Zyll.api.get("/calendar/next") as? JSONArray) }
    val hol = rememberLoader("hol") { Holidays.parse(Zyll.api.obj("/holidays")) }
    var impactSel by remember { mutableStateOf(Zyll.session.getString("cal_impact", "0").toIntOrNull() ?: 0) }
    var ccy by remember { mutableStateOf(Zyll.session.getString("cal_ccy", "")) }
    var detail by remember { mutableStateOf<CalEvent?>(null) }
    // 每 15 秒刷新一次“下一个重要数据”的倒计时和状态
    var nowSec by remember { mutableStateOf(System.currentTimeMillis() / 1000) }
    LaunchedEffect(Unit) { while (true) { kotlinx.coroutines.delay(15_000); nowSec = System.currentTimeMillis() / 1000 } }

    // 实时：有新公布值时直接合并，空数组表示需要重新拉取
    LaunchedEffect(Unit) {
        Zyll.live.events.collect { ev ->
            when (ev.topic) {
                "calendar" -> {
                    val arr = ev.data as? JSONArray
                    val upd = CalEvent.list(arr)
                    val cur = events.data
                    if (upd.isEmpty() || cur == null) events.reload(silent = true)
                    else {
                        val m = upd.associateBy { it.id }
                        events.data = cur.map { m[it.id] ?: it } + upd.filter { u -> cur.none { it.id == u.id } }
                        next.reload(silent = true)
                    }
                }
                "holidays" -> hol.reload(silent = true)
            }
        }
    }

    Column(Modifier.fillMaxSize()) {
        ScreenHeader("经济日历", "时间为本机时区 · 点击事件查看详情", onRefresh = { events.reload(); next.reload(); hol.reload() })
        LoadBox(events, Modifier.padding(16.dp)) { list ->
            val minImpact = listOf(0, 2, 3)[impactSel]
            val currencies = remember(list) { list.map { it.currency }.filter { it.isNotBlank() }.distinct().sorted() }
            val filtered = list.filter { it.impact >= minImpact && (ccy.isEmpty() || it.currency == ccy) }.sortedBy { it.ts }
            val groups = filtered.groupBy { Fmt.dayKey(it.ts) }
            val today = Fmt.today()
            LazyColumn(Modifier.fillMaxSize(), contentPadding = androidx.compose.foundation.layout.PaddingValues(start = 12.dp, end = 12.dp, bottom = 24.dp)) {
                item {
                    hol.data?.let { MarketStrip(it.today) }
                    pickNext(next.data.orEmpty(), list, nowSec)?.let { NextCard(it, nowSec) { detail = it } }
                    Spacer(Modifier.height(8.dp))
                    Segmented(listOf("全部", "重要及以上", "非常重要"), impactSel) { impactSel = it; Zyll.session.putString("cal_impact", it.toString()) }
                    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(vertical = 6.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        (listOf("") + currencies).forEach { c ->
                            FilterChip(
                                selected = ccy == c, onClick = { ccy = c; Zyll.session.putString("cal_ccy", c) },
                                label = { Text(if (c.isEmpty()) "全部货币" else c) },
                                colors = FilterChipDefaults.filterChipColors(selectedContainerColor = Palette.Accent.copy(alpha = 0.2f), selectedLabelColor = Palette.Accent),
                            )
                        }
                    }
                }
                if (groups.isEmpty()) item { Muted("没有符合条件的事件", Modifier.padding(16.dp), 13) }
                groups.forEach { (day, evs) ->
                    item(key = "d_$day") {
                        val hs = hol.data?.items?.filter { it.date == day }.orEmpty()
                        Column(Modifier.padding(top = 14.dp, bottom = 6.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(Fmt.dayTitle(day), fontWeight = FontWeight.SemiBold, color = if (day == today) Palette.Accent else Palette.Text)
                                if (day == today) { Spacer(Modifier.width(6.dp)); Tag("今天") }
                            }
                            hs.forEach { h -> Muted("🏖 ${h.name}", size = 12) }
                        }
                    }
                    items(evs, key = { it.id }) { e -> EventRow(e) { detail = e } }
                }
            }
        }
    }

    detail?.let { e ->
        ModalBottomSheet(onDismissRequest = { detail = null }, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true), containerColor = Palette.Bg2) {
            EventDetail(e)
        }
    }
}

@Composable
private fun MarketStrip(t: MarketToday?) {
    if (t == null) return
    val items = buildList {
        add((if (t.usClosedZh != null) "🔴 美股休市：${t.usClosedZh}" else if (t.weekend) "⚪ 周末休市" else "🟢 美股今日开市") to (t.usClosedZh != null))
        t.usEarly?.let { add("⏰ 提前收盘：$it" to true) }
        t.cme?.let { add("📈 期货：$it" to true) }
        if (!t.cfetsOpen) add("💱 外汇交易中心休市" to true)
        if (t.usClosedZh != null || t.weekend) add("下一个交易日 ${t.nextTradingDay}" to false)
    }
    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(vertical = 4.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        items.forEach { (txt, warn) -> Tag(txt, if (warn) Palette.Warn else Palette.Accent) }
    }
}

/**
 * 下一个非常重要的数据（与网页相同的规则）：到点后还没公布值的继续显示“等待公布”（最多 30 分钟），
 * 公布后再显示 2 分钟，不会先跳到下一个再跳回来。日历列表里有实时推送的最新数据，优先用它。
 */
private fun pickNext(next: List<CalEvent>, window: List<CalEvent>, now: Long): CalEvent? {
    val byId = window.associateBy { it.id }
    val seen = HashSet<String>()
    return (window + next).map { byId[it.id] ?: it }
        .filter { it.impact == 3 && seen.add(it.id) }
        .filter { it.ts > now || (it.actual.isBlank() && now - it.ts < 1800) || (it.actual.isNotBlank() && now - it.ts < 120) }
        .minByOrNull { it.ts }
}

@Composable
private fun NextCard(e: CalEvent, now: Long, onClick: () -> Unit) {
    val ud = LocalUpDown.current
    val mins = (e.ts - now) / 60
    val due = e.ts <= now
    GlassCard(Modifier.fillMaxWidth().padding(top = 6.dp), onClick = onClick) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Tag("下一个非常重要", IMPACT_COLOR[3]!!)
            Spacer(Modifier.weight(1f))
            when {
                due && e.actual.isBlank() -> Text("已到公布时间，等待数据…", fontSize = 12.sp, color = Palette.Warn)
                due -> Text("已公布", fontSize = 12.sp, color = Palette.Accent)
                else -> Muted(if (mins in 0..1440) (if (mins < 60) "${maxOf(mins, 1)} 分钟后" else "${mins / 60} 小时 ${mins % 60} 分后") else Fmt.dateTime(e.ts))
            }
        }
        Spacer(Modifier.height(6.dp))
        Text("${REGION_FLAG[e.region] ?: ""} ${e.currency} ${e.title}", fontWeight = FontWeight.SemiBold)
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            if (e.actual.isNotBlank()) Text("公布 ${e.actual}", fontSize = 12.sp, fontWeight = FontWeight.SemiBold,
                color = when (e.surprise) { 1 -> ud.up; -1 -> ud.down; else -> Palette.Text })
            Muted("${Fmt.dateTime(e.ts)}   预测 ${e.forecast.ifBlank { "—" }}   前值 ${e.previous.ifBlank { "—" }}")
        }
    }
}

@Composable
private fun EventRow(e: CalEvent, onClick: () -> Unit) {
    val ud = LocalUpDown.current
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).clickable(onClick = onClick).padding(vertical = 8.dp, horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.width(48.dp)) {
            Text(Fmt.time(e.ts), fontSize = 13.sp, fontWeight = FontWeight.Medium)
            Text(e.currency, fontSize = 11.sp, color = Palette.Muted)
        }
        Box(Modifier.size(8.dp).background(IMPACT_COLOR[e.impact] ?: Palette.Muted, CircleShape))
        Spacer(Modifier.width(8.dp))
        Column(Modifier.weight(1f)) {
            Text("${REGION_FLAG[e.region] ?: ""} ${e.title}", fontSize = 14.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                val ac = when (e.surprise) { 1 -> ud.up; -1 -> ud.down; else -> Palette.Text }
                Text("公布 ${e.actual.ifBlank { "—" }}", fontSize = 12.sp, color = if (e.actual.isBlank()) Palette.Muted else ac, fontWeight = FontWeight.SemiBold)
                Text("预测 ${e.forecast.ifBlank { "—" }}", fontSize = 12.sp, color = Palette.Muted)
                Text("前值 ${e.previous.ifBlank { "—" }}", fontSize = 12.sp, color = Palette.Muted)
            }
        }
    }
}

@Composable
private fun EventDetail(e: CalEvent) {
    val d = rememberLoader(e.id) { CalDetail.parse(Zyll.api.obj("/calendar/event/${e.id}")) }
    Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 18.dp).padding(bottom = 24.dp).navigationBarsPadding()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Tag(IMPACT_ZH[e.impact] ?: "", IMPACT_COLOR[e.impact] ?: Palette.Muted)
            Spacer(Modifier.width(6.dp))
            Tag("${REGION_FLAG[e.region] ?: ""} ${e.currency}", Palette.Accent2)
            Spacer(Modifier.weight(1f))
            Muted(Fmt.dateTime(e.ts))
        }
        Spacer(Modifier.height(8.dp))
        LoadBox(d) { det ->
            Text(det.nameZh.ifBlank { e.title }, fontWeight = FontWeight.SemiBold, fontSize = 18.sp)
            if (det.nameZh.isNotBlank()) Muted(e.title)
            Spacer(Modifier.height(10.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("公布值" to e.actual, "预测值" to e.forecast, "前值" to e.previous).forEach { (k, v) ->
                    Column(Modifier.weight(1f).clip(RoundedCornerShape(10.dp)).background(Color(0x0FFFFFFF)).padding(10.dp)) {
                        Muted(k, size = 11)
                        Text(v.ifBlank { "—" }, fontWeight = FontWeight.SemiBold)
                    }
                }
            }
            if (e.revision.isNotBlank()) Muted("前值修正为 ${e.revision}", Modifier.padding(top = 4.dp))
            Spacer(Modifier.height(12.dp))
            if (det.desc.isNotBlank()) {
                Text("这是什么", fontWeight = FontWeight.SemiBold)
                Text(det.desc, fontSize = 13.sp, color = Palette.Text.copy(alpha = 0.85f))
                Spacer(Modifier.height(8.dp))
            }
            val effect = when (det.effect) {
                "up" -> "通常公布值高于预测 → 利好 ${e.currency}"
                "down" -> "通常公布值低于预测 → 利好 ${e.currency}（数值越低越好）"
                else -> ""
            }
            if (effect.isNotBlank()) Muted(effect, size = 12)
            Spacer(Modifier.height(12.dp))
            val hist = det.history.sortedBy { it.ts }
            if (hist.size >= 1 && hist.any { it.a != null || it.f != null }) {
                Text("历史公布值与预测值", fontWeight = FontWeight.SemiBold)
                InteractiveChart(
                    labels = hist.map { Fmt.date(it.ts).let { s -> if (s.length > 2) s.substring(2) else s } },
                    series = listOf(
                        ChartSeries("公布值", hist.map { it.a }, Palette.Accent, width = 2.2f),
                        ChartSeries("预测值", hist.map { it.f }, Palette.Gold, dashed = true, width = 1.6f),
                    ),
                    format = { Fmt.num(it, 2) + det.unit },
                    tipTitle = { Fmt.date(hist[it].ts) },
                    modifier = Modifier.padding(top = 6.dp),
                )
            } else Muted("暂无历史数据（本站会随着每次公布逐步积累）")
        }
    }
}
