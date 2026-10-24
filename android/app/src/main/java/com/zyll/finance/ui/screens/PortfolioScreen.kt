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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
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
import com.zyll.finance.core.Pnl
import com.zyll.finance.core.Quote
import com.zyll.finance.core.Rate
import com.zyll.finance.core.SymbolPosition
import com.zyll.finance.data.ApiException
import com.zyll.finance.data.PfHistory
import com.zyll.finance.data.Portfolio
import com.zyll.finance.data.Zyll
import com.zyll.finance.data.parseRates
import com.zyll.finance.ui.AppNav
import com.zyll.finance.ui.components.GlassCard
import com.zyll.finance.ui.components.LoadBox
import com.zyll.finance.ui.components.LoginRequired
import com.zyll.finance.ui.components.Muted
import com.zyll.finance.ui.components.ScreenHeader
import com.zyll.finance.ui.components.SectionTitle
import com.zyll.finance.ui.components.SymbolField
import com.zyll.finance.ui.components.Tag
import com.zyll.finance.ui.components.rememberLoader
import com.zyll.finance.ui.theme.LocalUpDown
import com.zyll.finance.ui.theme.Palette
import kotlinx.coroutines.launch
import org.json.JSONObject

/** 持仓分析页的弹窗状态 */
sealed class PfDialog {
    data class AddTrade(val symbol: String?, val tradeId: Long? = null) : PfDialog()
    data class Cash(val kind: String, val grp: String? = null) : PfDialog()
    data object CashRecords : PfDialog()
    data object Settings : PfDialog()
    data object Import : PfDialog()
    data object Batches : PfDialog()
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PortfolioScreen() {
    val token by Zyll.session.token.collectAsState()
    val config by Zyll.config.collectAsState()
    Column(Modifier.fillMaxSize()) {
        if (token == null) {
            ScreenHeader("持仓分析")
            LoginRequired("登录后可以记录美股持仓，按每笔交易的货币对计算含汇率的盈亏，并统计总资本。", Modifier.padding(16.dp))
            return@Column
        }
        if (config?.portfolioEnabled == false) {
            ScreenHeader("持仓分析")
            Muted("网站暂未开放持仓分析功能。", Modifier.padding(16.dp), 14)
            return@Column
        }
        PortfolioContent()
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PortfolioContent() {
    val lists by Zyll.listsVersion.collectAsState()
    val pf = rememberLoader(lists) { Portfolio.parse(Zyll.api.obj("/portfolio")) }
    val hist = rememberLoader(lists) { PfHistory.parse(Zyll.api.obj("/portfolio/history")) }
    val live = remember { mutableStateMapOf<String, Double>() }
    var fxLive by remember { mutableStateOf<Map<String, Rate>?>(null) }
    var dialog by remember { mutableStateOf<PfDialog?>(null) }
    var sheetSymbol by remember { mutableStateOf<String?>(null) }
    var analysis by remember { mutableStateOf<PfCard?>(null) }
    val scope = rememberCoroutineScope()
    val ctx = LocalContext.current
    // 本页修改后静默刷新（不闪加载圈，打开的弹窗保持不动）
    val changed: () -> Unit = { pf.reload(silent = true); hist.reload(silent = true) }

    LaunchedEffect(pf) {
        Zyll.live.events.collect { ev ->
            when (ev.topic) {
                "ticks" -> {
                    val o = ev.data as? JSONObject ?: return@collect
                    pf.data?.symbols?.forEach { s ->
                        val p = o.optJSONArray(s.symbol)?.optDouble(0)
                        if (p != null && !p.isNaN()) live[s.symbol] = p
                    }
                }
                "fx" -> parseRates((ev.data as? JSONObject)?.optJSONObject("rates"))?.let { fxLive = it }
            }
        }
    }

    val config by Zyll.config.collectAsState()
    ScreenHeader("持仓分析", pf.data?.let { "本币 ${Fmt.ccyLabel(it.base)} · 汇率 ${it.fxSource.ifBlank { "外汇交易中心" }} ${it.fxTime}" }, onRefresh = { live.clear(); pf.reload(); hist.reload() }) {
        IconButton(onClick = { dialog = PfDialog.Settings }) { Icon(Icons.Filled.Settings, "设置", tint = Palette.Muted) }
    }
    if (config?.aiImport?.enabled == true || pf.data?.trades?.any { it.batch.isNotBlank() } == true) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (config?.aiImport?.enabled == true) Button(onClick = { dialog = PfDialog.Import }, modifier = Modifier.weight(1f)) { Text("✨ AI 导入结单") }
            OutlinedButton(onClick = { dialog = PfDialog.Batches }) { Text("导入记录") }
        }
    }
    LoadBox(pf, Modifier.padding(16.dp)) { d ->
        val fxNow = fxLive ?: d.fxNow
        val positions: List<Pair<String, SymbolPosition>> = remember(d, fxNow, live.toMap()) {
            d.symbols.map { s ->
                val q = d.quotes[s.symbol]
                val quote = Quote(live[s.symbol] ?: q?.price, q?.prevClose)
                s.symbol to Pnl.computeSymbol(d.trades.filter { it.symbol == s.symbol }, quote, fxNow, d.fxPrev, d.fxMode, d.base, d.sessionDate, d.deflate())
            }
        }
        val totals = Pnl.totals(positions.map { it.second })
        val summary = PfSummary(d.base, d.sessionDate, totals, positions, hist.data, d.inflation, d.includeFx)
        val capital = Pnl.capital(d.trades, d.cash, fxNow, d.base, d.fxMode, totals.mvBase)

        LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(start = 12.dp, end = 12.dp, bottom = 24.dp)) {
            item {
                ViewSwitches(d) { patch ->
                    scope.launch {
                        try {
                            Zyll.api.put("/portfolio/settings", JSONObject().put("base_currency", d.base).put("fx_mode", d.fxMode)
                                .put("inflation", patch["inflation"] ?: d.inflation).put("include_fx", patch["include_fx"] ?: d.includeFx))
                            changed()
                        } catch (e: ApiException) { Toast.makeText(ctx, e.friendly, Toast.LENGTH_SHORT).show() }
                    }
                }
                SummaryTiles(summary) { analysis = it }
                if (d.prevApprox) Muted("昨日汇率缺失，今日汇率部分为近似值。", Modifier.padding(top = 4.dp))
                Spacer(Modifier.height(10.dp))
                CapitalCard(d, capital, onCash = { kind -> dialog = PfDialog.Cash(kind) }, onRecords = { dialog = PfDialog.CashRecords })
            }
            item {
                SectionTitle("持仓与关注") {
                    OutlinedButton(onClick = { dialog = PfDialog.AddTrade(null) }, enabled = d.symbols.isNotEmpty()) {
                        Icon(Icons.Filled.Add, null); Spacer(Modifier.width(4.dp)); Text("记一笔")
                    }
                }
                AddSymbolRow(d.symbols.size, d.maxSymbols) { sym ->
                    scope.launch {
                        try {
                            Zyll.api.post("/portfolio/symbols", JSONObject().put("symbol", sym))
                            Zyll.listsVersion.value++
                        } catch (e: ApiException) { Toast.makeText(ctx, e.friendly, Toast.LENGTH_SHORT).show() }
                    }
                }
            }
            if (d.symbols.isEmpty()) item { Muted("还没有股票。添加股票后点“记一笔”录入买卖记录。", Modifier.padding(8.dp)) }
            items(positions, key = { it.first }) { (sym, p) ->
                HoldingRow(sym, d.quotes[sym]?.name.orEmpty(), p, d.base, d.includeFx, d.inflation) { sheetSymbol = sym }
            }
            item {
                Spacer(Modifier.height(8.dp))
                Muted("盈亏按每笔交易自己的货币对计算：股价部分 = 股价涨跌 × 买入时汇率，汇率部分 = 市值 × 汇率变化。点股票代码可查看K线。")
            }
        }

        sheetSymbol?.let { sym ->
            ModalBottomSheet(onDismissRequest = { sheetSymbol = null }, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true), containerColor = Palette.Bg2) {
                SymbolSheet(d, sym, positions.firstOrNull { it.first == sym }?.second,
                    onTrade = { tid -> dialog = PfDialog.AddTrade(sym, tid) },
                    onChanged = changed, onRemoved = { sheetSymbol = null })
            }
        }
        analysis?.let { c ->
            ModalBottomSheet(onDismissRequest = { analysis = null }, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true), containerColor = Palette.Bg2) {
                AnalysisSheet(c, summary)
            }
        }
        when (val dl = dialog) {
            is PfDialog.AddTrade -> TradeDialog(d, fxNow, dl.symbol, d.trades.firstOrNull { it.id == dl.tradeId }, onDismiss = { dialog = null }) { dialog = null; changed() }
            is PfDialog.Cash -> CashDialog(d, fxNow, dl.kind, dl.grp, onDismiss = { dialog = null }) { dialog = null; changed() }
            PfDialog.CashRecords -> CashRecordsDialog(d, onDismiss = { dialog = null }, onEdit = { kind, grp -> dialog = PfDialog.Cash(kind, grp) }) { changed() }
            PfDialog.Settings -> SettingsDialog(d, onDismiss = { dialog = null }) { dialog = null; changed() }
            PfDialog.Import -> ImportDialog(onDismiss = { dialog = null }) { changed() }
            PfDialog.Batches -> ImportBatchesDialog(onDismiss = { dialog = null }) { Zyll.listsVersion.value++ }
            null -> {}
        }
    }
}

@Composable
private fun AddSymbolRow(count: Int, max: Int, onAdd: (String) -> Unit) {
    var sym by remember { mutableStateOf("") }
    Row(verticalAlignment = Alignment.Top, modifier = Modifier.padding(bottom = 6.dp)) {
        SymbolField(sym, { sym = it }, Modifier.weight(1f), label = "添加股票（$count/$max）", onPick = { sym = it.symbol },
            onDone = { if (sym.isNotBlank()) { onAdd(sym); sym = "" } })
        Spacer(Modifier.width(8.dp))
        Button(onClick = { if (sym.isNotBlank()) { onAdd(sym); sym = "" } }, modifier = Modifier.padding(top = 8.dp)) { Text("加入") }
    }
}

@Composable
private fun HoldingRow(sym: String, name: String, p: SymbolPosition, base: String, includeFx: Boolean, inflation: Boolean, onClick: () -> Unit) {
    val ud = LocalUpDown.current
    val held = (p.qty ?: 0.0) > 0
    val v = Pnl.view(p, includeFx)
    val cost = if (inflation) p.costReal else p.costBase
    val pct = if (cost != null && cost != 0.0) v.unreal?.let { it / cost * 100 } else null
    Column {
        Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).clickable(onClick = onClick).padding(vertical = 10.dp, horizontal = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1.1f)) {
                Text(sym, fontWeight = FontWeight.SemiBold, color = Palette.Accent, modifier = Modifier.clickable { AppNav.openStock(sym) })
                Text(if (held) "${Fmt.num(p.qty, if (p.qty!! % 1.0 == 0.0) 0 else 4)} 股 · 成本 ${Fmt.price(p.avgUsd)}" else name.ifBlank { "仅关注" },
                    fontSize = 11.sp, color = Palette.Muted, maxLines = 1, overflow = TextOverflow.Ellipsis)
                if (p.ccys.size > 1) Tag(p.ccys.joinToString("/"), Palette.Muted)
            }
            Column(Modifier.weight(0.9f), horizontalAlignment = Alignment.End) {
                Text(Fmt.price(p.price), color = ud.of(p.dayChangePct), fontWeight = FontWeight.SemiBold)
                Text(Fmt.pct(p.dayChangePct), color = ud.of(p.dayChangePct), fontSize = 12.sp)
            }
            Column(Modifier.weight(1.2f), horizontalAlignment = Alignment.End) {
                if (held) {
                    Text(Fmt.money(p.mvBase, base), fontSize = 13.sp)
                    Text("${Fmt.signedMoney(v.unreal, base)} ${Fmt.pct(pct, 1)}", color = ud.of(v.unreal), fontSize = 11.sp, maxLines = 1)
                    Text("今日 ${Fmt.signedMoney(v.today, base)}", color = ud.of(v.today), fontSize = 11.sp, maxLines = 1)
                } else if ((v.realized ?: 0.0) != 0.0) {
                    Muted("已清仓", size = 11)
                    Text("已实现 ${Fmt.signedMoney(v.realized, base)}", color = ud.of(v.realized), fontSize = 11.sp)
                }
            }
        }
        HorizontalDivider(color = Color(0x10FFFFFF))
    }
}

/** 扣除通胀 / 计入汇率 两个开关（存服务器，与网页同步） */
@Composable
private fun ViewSwitches(d: Portfolio, onChange: (Map<String, Boolean>) -> Unit) {
    Column(Modifier.fillMaxWidth().padding(bottom = 8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("扣除通胀", fontSize = 13.sp)
            Switch(checked = d.inflation, onCheckedChange = { onChange(mapOf("inflation" to it)) })
            Spacer(Modifier.width(10.dp))
            Text("计入汇率", fontSize = 13.sp)
            Switch(checked = d.includeFx, onCheckedChange = { onChange(mapOf("include_fx" to it)) })
        }
        if (d.inflation) {
            val used = (listOf(d.base) + d.trades.mapNotNull { it.ccy }).distinct()
            Muted("已扣除通胀：" + used.joinToString("；") { c ->
                val x = d.cpi[c]
                if (x == null || x.noData) "$c 暂无物价数据，按不变计算"
                else "${x.region}近 12 个月物价上涨 ${x.yoy12m?.let { Fmt.num(it, 1) + "%" } ?: "—"}（数据截至 ${x.lastKnown ?: "—"}${if (x.approx) "，最近几个月按趋势推算" else ""}）"
            }, size = 11)
        }
        if (!d.includeFx) Muted("未计入汇率：盈亏只含股价部分，按买入时的平均成本汇率换算。", size = 11)
    }
}

@Composable
private fun CapitalCard(d: Portfolio, cap: com.zyll.finance.core.Capital, onCash: (String) -> Unit, onRecords: () -> Unit) {
    val ud = LocalUpDown.current
    GlassCard(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Muted("总资本（现金 + 美股，折合${Fmt.ccyLabel(d.base)}）")
                Text(Fmt.money(cap.net, d.base), fontWeight = FontWeight.SemiBold, fontSize = 20.sp)
            }
        }
        Spacer(Modifier.height(8.dp))
        cap.items.forEachIndexed { i, it ->
            val name = if (it.kind == "stocks") "美股持仓" else "现金 ${Fmt.ccyLabel(it.ccy)}"
            Row(Modifier.fillMaxWidth().padding(vertical = 3.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(name, fontSize = 13.sp)
                    if (it.kind == "cash" && it.ccy != d.base) Muted("${Fmt.ccySymbol(it.ccy)}${Fmt.num(it.amount)}", size = 11)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(it.value?.let { v -> Fmt.money(v, d.base) } ?: "缺少汇率", fontSize = 13.sp, color = if ((it.value ?: 0.0) < 0) ud.down else Palette.Text)
                    Muted(it.pct?.let { p -> Fmt.num(p, 1) + "%" } ?: "—", size = 11)
                }
            }
            if (it.pct != null) com.zyll.finance.ui.components.RatioBar((it.pct / 100).toFloat(), Palette.Series[i % Palette.Series.size], Modifier.fillMaxWidth())
        }
        if (cap.items.isEmpty()) Muted("还没有资金记录。入金后买入股票会自动扣减对应货币的现金，卖出自动加回。")
        if (cap.negative.isNotEmpty()) Muted("⚠ ${cap.negative.joinToString("、") { Fmt.ccyLabel(it.ccy) }} 现金为负，可能漏记了入金或换汇。", Modifier.padding(top = 4.dp))
        if (cap.missingRate.isNotEmpty()) Muted("缺少 ${cap.missingRate.joinToString("、")} 的汇率，未计入合计。")
        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            OutlinedButton(onClick = { onCash("deposit") }, contentPadding = PaddingValues(horizontal = 10.dp)) { Text("入金", fontSize = 13.sp) }
            OutlinedButton(onClick = { onCash("withdraw") }, contentPadding = PaddingValues(horizontal = 10.dp)) { Text("出金", fontSize = 13.sp) }
            OutlinedButton(onClick = { onCash("fx") }, contentPadding = PaddingValues(horizontal = 10.dp)) { Text("换汇", fontSize = 13.sp) }
            OutlinedButton(onClick = onRecords, contentPadding = PaddingValues(horizontal = 10.dp)) { Text("记录", fontSize = 13.sp) }
        }
    }
}
