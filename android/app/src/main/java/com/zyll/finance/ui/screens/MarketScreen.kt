package com.zyll.finance.ui.screens

import android.widget.Toast
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.zyll.finance.core.Fmt
import com.zyll.finance.data.ApiException
import com.zyll.finance.data.IndexQuote
import com.zyll.finance.data.MarketData
import com.zyll.finance.data.StockSnap
import com.zyll.finance.data.Zyll
import com.zyll.finance.data.dbl
import com.zyll.finance.data.mapValues
import com.zyll.finance.data.sessionZh
import com.zyll.finance.ui.AppNav
import com.zyll.finance.ui.components.ExternalTarget
import com.zyll.finance.ui.components.GlassCard
import com.zyll.finance.ui.components.INDEX_SITES
import com.zyll.finance.ui.components.LoadBox
import com.zyll.finance.ui.components.LoginRequired
import com.zyll.finance.ui.components.Muted
import com.zyll.finance.ui.components.ScreenHeader
import com.zyll.finance.ui.components.SectionTitle
import com.zyll.finance.ui.components.Segmented
import com.zyll.finance.ui.components.Sparkline
import com.zyll.finance.ui.components.SymbolField
import com.zyll.finance.ui.components.Tag
import com.zyll.finance.ui.components.rememberLoader
import com.zyll.finance.ui.theme.LocalUpDown
import com.zyll.finance.ui.theme.Palette
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject

@Composable
fun MarketScreen() {
    val token by Zyll.session.token.collectAsState()
    val lists by Zyll.listsVersion.collectAsState()
    val market = rememberLoader(token, lists) { MarketData.parse(Zyll.api.obj("/market")) }
    var rankKind by remember { mutableStateOf(0) }
    var editIndices by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val ctx = LocalContext.current

    // 实时推送：逐笔价格、完整快照、指数、成交榜
    LaunchedEffect(market) {
        Zyll.live.events.collect { ev ->
            val cur = market.data ?: return@collect
            when (ev.topic) {
                "ticks" -> {
                    val o = ev.data as? JSONObject ?: return@collect
                    var changed = false
                    val snaps = cur.snaps.toMutableMap()
                    for (sym in cur.stocks) {
                        val arr = o.optJSONArray(sym) ?: continue
                        val p = arr.optDouble(0)
                        if (!p.isNaN()) { snaps[sym] = (snaps[sym] ?: continue).withPrice(p); changed = true }
                    }
                    if (changed) market.data = cur.copy(snaps = snaps)
                }
                "snap" -> {
                    val o = ev.data as? JSONObject ?: return@collect
                    val upd = o.mapValues { k, v -> if (k in cur.stocks) StockSnap.parse(v, k) else null }
                    if (upd.isNotEmpty()) market.data = cur.copy(snaps = cur.snaps + upd)
                }
                "indices" -> {
                    val o = ev.data as? JSONObject ?: return@collect
                    val upd = o.mapValues { k, v -> if (k in cur.indices) IndexQuote.parse(k, v).let { q -> if (q.spark.isEmpty()) q.copy(spark = cur.indexQuotes[k]?.spark.orEmpty()) else q } else null }
                    if (upd.isNotEmpty()) market.data = cur.copy(indexQuotes = cur.indexQuotes + upd)
                }
                "rank" -> {
                    val o = ev.data as? JSONObject ?: return@collect
                    market.data = cur.copy(rankAmount = MarketData.parseRank(o, "amount"), rankVolume = MarketData.parseRank(o, "volume"), rankUpdated = o.dbl("updated"))
                }
            }
        }
    }

    Column(Modifier.fillMaxSize()) {
        val d = market.data
        ScreenHeader(
            "行情",
            d?.let { "美股${sessionZh(it.session)}" + (it.today?.usClosedZh?.let { h -> " · 今日休市（$h）" } ?: "") + " · 实时数据来自新浪/腾讯/Yahoo" },
            onRefresh = { market.reload() },
        )
        LoadBox(market, Modifier.padding(16.dp)) { m ->
            LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(start = 12.dp, end = 12.dp, bottom = 24.dp)) {
                item {
                    SectionTitle("指数") {
                        IconButton(onClick = { if (Zyll.session.isLoggedIn) editIndices = true else AppNav.showLogin.value = true }) {
                            Icon(Icons.Filled.Edit, "编辑指数", tint = Palette.Muted)
                        }
                    }
                    m.indices.chunked(2).forEach { row ->
                        Row(Modifier.fillMaxWidth().padding(bottom = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            row.forEach { code ->
                                val q = m.indexQuotes[code]
                                val info = m.catalog.firstOrNull { it.code == code }
                                IndexCard(code, info?.zh ?: q?.name ?: code, q, Modifier.weight(1f)) {
                                    if (info != null) AppNav.external.value = ExternalTarget(info.zh, "${info.yahoo}|${info.tv}", INDEX_SITES)
                                }
                            }
                            if (row.size == 1) Spacer(Modifier.weight(1f))
                        }
                    }
                }
                item {
                    SectionTitle("我的个股") { Muted("与持仓分析同步 · ${m.stocks.size}/${m.maxStocks}") }
                    if (!m.loggedIn) LoginRequired("登录后可以添加关注的个股，并与“持仓分析”自动同步。")
                    else AddStockRow { sym ->
                        scope.launch {
                            try {
                                Zyll.api.post("/market/stocks", JSONObject().put("symbol", sym))
                                Zyll.listsVersion.value++
                            } catch (e: ApiException) { Toast.makeText(ctx, e.friendly, Toast.LENGTH_SHORT).show() }
                        }
                    }
                }
                if (m.loggedIn && m.stocks.isEmpty()) item { Muted("还没有添加个股", Modifier.padding(8.dp)) }
                items(m.stocks, key = { "s_$it" }) { sym ->
                    StockRow(m.snaps[sym] ?: StockSnap(sym, "", null, null, null, null, null, null, null, null, null, null, null, null, ""), showExt = m.session != "regular",
                        onDelete = {
                            scope.launch {
                                try {
                                    val r = Zyll.api.delete("/market/stocks/${sym}") as? JSONObject
                                    if (r?.optBoolean("kept_in_portfolio") == true) Toast.makeText(ctx, "$sym 有交易记录，已保留在持仓分析中", Toast.LENGTH_LONG).show()
                                    Zyll.listsVersion.value++
                                } catch (e: ApiException) { Toast.makeText(ctx, e.friendly, Toast.LENGTH_SHORT).show() }
                            }
                        })
                }
                item {
                    SectionTitle("成交最多") { Muted(m.rankUpdated?.let { "更新于 ${Fmt.ago(it)}" } ?: "") }
                    Segmented(listOf("按成交额", "按成交量"), rankKind) { rankKind = it }
                    Spacer(Modifier.height(6.dp))
                }
                val rank = if (rankKind == 0) m.rankAmount else m.rankVolume
                if (rank.isEmpty()) item { Muted("暂无数据", Modifier.padding(8.dp)) }
                items(rank.take(30), key = { "r_${rankKind}_${it.symbol}" }) { s -> RankRow(rank.indexOf(s) + 1, s, rankKind) }
            }
        }
    }

    if (editIndices) market.data?.let { m ->
        IndicesEditor(m, onDismiss = { editIndices = false }) { codes ->
            editIndices = false
            scope.launch {
                try {
                    Zyll.api.put("/market/indices", JSONObject().put("codes", JSONArray(codes)))
                    market.reload(silent = true)
                } catch (e: ApiException) { Toast.makeText(ctx, e.friendly, Toast.LENGTH_SHORT).show() }
            }
        }
    }
}

@Composable
private fun IndexCard(code: String, name: String, q: IndexQuote?, modifier: Modifier, onClick: () -> Unit) {
    val c = LocalUpDown.current.of(q?.change)
    GlassCard(modifier, onClick = onClick, padding = PaddingValues(12.dp)) {
        Text(name, fontSize = 12.sp, color = Palette.Muted, maxLines = 1, overflow = TextOverflow.Ellipsis)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(Fmt.num(q?.price, 2), fontWeight = FontWeight.SemiBold, fontSize = 16.sp, color = c, maxLines = 1)
                Text("${Fmt.signed(q?.change)}  ${Fmt.pct(q?.changePct)}", fontSize = 11.sp, color = c, maxLines = 1)
            }
            Sparkline(q?.spark.orEmpty(), c, Modifier.size(width = 56.dp, height = 30.dp), baseline = q?.prevClose)
        }
        if (q == null) Muted("$code 暂无数据", size = 11)
    }
}

@Composable
private fun AddStockRow(onAdd: (String) -> Unit) {
    var sym by remember { mutableStateOf("") }
    Row(verticalAlignment = Alignment.Top, modifier = Modifier.padding(bottom = 6.dp)) {
        SymbolField(sym, { sym = it }, Modifier.weight(1f), label = "添加个股（如 AAPL）", onPick = { sym = it.symbol }, onDone = {
            if (sym.isNotBlank()) { onAdd(sym); sym = "" }
        })
        Spacer(Modifier.width(8.dp))
        Button(onClick = { if (sym.isNotBlank()) { onAdd(sym); sym = "" } }, modifier = Modifier.padding(top = 8.dp)) { Text("添加") }
    }
}

@Composable
fun StockRow(s: StockSnap, showExt: Boolean, onDelete: (() -> Unit)? = null) {
    val ud = LocalUpDown.current
    val c = ud.of(s.change ?: s.changePct)
    var confirm by remember { mutableStateOf(false) }
    Column {
        Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).clickable { AppNav.openStock(s.symbol) }.padding(vertical = 10.dp, horizontal = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                Text(s.symbol, fontWeight = FontWeight.SemiBold)
                Text(s.name.ifBlank { "成交额 ${Fmt.compact(s.amount)}" }, fontSize = 11.sp, color = Palette.Muted, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(Fmt.price(s.price), color = c, fontWeight = FontWeight.SemiBold)
                Text(Fmt.pct(s.changePct), color = c, fontSize = 12.sp)
                if (showExt && s.extPrice != null) Text("盘外 ${Fmt.price(s.extPrice)} ${Fmt.pct(s.extPct)}", fontSize = 10.sp, color = ud.of(s.extPct))
            }
            if (onDelete != null) IconButton(onClick = { confirm = true }) { Icon(Icons.Filled.Close, "删除", tint = Palette.Muted, modifier = Modifier.size(18.dp)) }
        }
        HorizontalDivider(color = Color(0x10FFFFFF))
    }
    if (confirm && onDelete != null) {
        AlertDialog(
            onDismissRequest = { confirm = false },
            title = { Text("移除 ${s.symbol}？") },
            text = { Text("会同时从持仓分析中移除（有交易记录的股票会保留）。") },
            confirmButton = { TextButton(onClick = { confirm = false; onDelete() }) { Text("移除") } },
            dismissButton = { TextButton(onClick = { confirm = false }) { Text("取消") } },
        )
    }
}

@Composable
private fun RankRow(no: Int, s: StockSnap, kind: Int) {
    val c = LocalUpDown.current.of(s.changePct)
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).clickable { AppNav.openStock(s.symbol) }.padding(vertical = 8.dp, horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text("$no", color = if (no <= 3) Palette.Gold else Palette.Muted, fontSize = 12.sp, modifier = Modifier.width(26.dp))
        Column(Modifier.weight(1f)) {
            Text(s.symbol, fontWeight = FontWeight.SemiBold)
            if (s.name.isNotBlank()) Text(s.name, fontSize = 11.sp, color = Palette.Muted, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        Column(horizontalAlignment = Alignment.End, modifier = Modifier.width(96.dp)) {
            Text(if (kind == 0) "$" + Fmt.compact(s.amount) else Fmt.compact(s.volume) + "股", fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
            Text(if (kind == 0) Fmt.compact(s.volume) + "股" else "$" + Fmt.compact(s.amount), fontSize = 11.sp, color = Palette.Muted)
        }
        Column(horizontalAlignment = Alignment.End, modifier = Modifier.width(80.dp)) {
            Text(Fmt.price(s.price), color = c, fontSize = 13.sp)
            Text(Fmt.pct(s.changePct), color = c, fontSize = 12.sp)
        }
    }
}

@Composable
private fun IndicesEditor(m: MarketData, onDismiss: () -> Unit, onSave: (List<String>) -> Unit) {
    val sel = remember { mutableStateListOf<String>().apply { addAll(m.indices) } }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("选择指数（最多 ${m.maxIndices} 个）") },
        text = {
            Column(Modifier.heightIn(max = 420.dp).verticalScroll(rememberScrollState())) {
                m.catalog.forEach { c ->
                    val on = c.code in sel
                    Row(
                        Modifier.fillMaxWidth().clickable {
                            if (on) sel.remove(c.code) else if (sel.size < m.maxIndices) sel.add(c.code)
                        },
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Checkbox(checked = on, enabled = on || sel.size < m.maxIndices, onCheckedChange = {
                            if (on) sel.remove(c.code) else if (sel.size < m.maxIndices) sel.add(c.code)
                        })
                        Column {
                            Text(c.zh)
                            Muted(c.en, size = 11)
                        }
                        if (on) { Spacer(Modifier.weight(1f)); Tag("#${sel.indexOf(c.code) + 1}") }
                    }
                }
            }
        },
        confirmButton = { TextButton(enabled = sel.isNotEmpty(), onClick = { onSave(sel.toList()) }) { Text("保存") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("取消") } },
    )
}
