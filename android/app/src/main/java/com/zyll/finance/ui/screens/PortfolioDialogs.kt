package com.zyll.finance.ui.screens

import android.widget.Toast
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.zyll.finance.core.Fmt
import com.zyll.finance.core.Pnl
import com.zyll.finance.core.Rate
import com.zyll.finance.core.SymbolPosition
import com.zyll.finance.core.Trade
import com.zyll.finance.data.ApiException
import com.zyll.finance.data.Portfolio
import com.zyll.finance.data.dbl
import com.zyll.finance.data.Zyll
import com.zyll.finance.data.cashKindZh
import com.zyll.finance.ui.AppNav
import com.zyll.finance.ui.components.KV
import com.zyll.finance.ui.components.Muted
import com.zyll.finance.ui.components.Segmented
import com.zyll.finance.ui.components.SelectBox
import com.zyll.finance.ui.components.Tag
import com.zyll.finance.ui.theme.LocalUpDown
import com.zyll.finance.ui.theme.Palette
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.util.Locale
import kotlin.math.abs

private val DATE_RE = Regex("""^\d{4}-\d{2}-\d{2}$""")

private fun String.num(): Double? = trim().replace(",", "").toDoubleOrNull()

private fun fmtInput(v: Double?, digits: Int = 4): String =
    v?.let { String.format(Locale.US, "%.${digits}f", it).trimEnd('0').trimEnd('.') } ?: ""

@Composable
private fun NumField(label: String, value: String, modifier: Modifier = Modifier, enabled: Boolean = true, supporting: String? = null, onChange: (String) -> Unit) {
    Column(modifier) {
        OutlinedTextField(
            value = value, onValueChange = { onChange(it.filter { c -> c.isDigit() || c == '.' }) }, label = { Text(label) }, singleLine = true, enabled = enabled,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), modifier = Modifier.fillMaxWidth(),
        )
        if (supporting != null) Text(supporting, fontSize = 11.sp, color = Palette.Muted, modifier = Modifier.padding(start = 4.dp, top = 2.dp))
    }
}

@Composable
private fun DateField(value: String, modifier: Modifier = Modifier, onChange: (String) -> Unit) {
    OutlinedTextField(
        value = value, onValueChange = { onChange(it.filter { c -> c.isDigit() || c == '-' }.take(10)) }, label = { Text("日期（年-月-日）") },
        singleLine = true, isError = !DATE_RE.matches(value), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), modifier = modifier,
    )
}

/* ======================= 交易记录 ======================= */

@Composable
fun TradeDialog(d: Portfolio, fxNow: Map<String, Rate>?, fixedSymbol: String?, edit: Trade?, onDismiss: () -> Unit, onSaved: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var symbol by remember { mutableStateOf(edit?.symbol ?: fixedSymbol ?: d.symbols.firstOrNull()?.symbol.orEmpty()) }
    var side by remember { mutableStateOf(if (edit?.side == "sell") 1 else 0) }
    var date by remember { mutableStateOf(edit?.tradeDate ?: Fmt.todayNewYork()) }
    var shares by remember { mutableStateOf(fmtInput(edit?.shares)) }
    var price by remember { mutableStateOf(fmtInput(edit?.price) .ifEmpty { fmtInput(d.quotes[symbol]?.price, 2) }) }
    var ccy by remember { mutableStateOf(edit?.ccy ?: d.base) }
    var fx by remember { mutableStateOf(fmtInput(edit?.fx ?: Pnl.usdTo(fxNow, ccy, d.fxMode))) }
    var fee by remember { mutableStateOf(fmtInput(edit?.fee?.takeIf { it > 0 })) }
    var note by remember { mutableStateOf(edit?.note.orEmpty()) }
    var funding by remember { mutableStateOf(edit?.funding ?: "ccy") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var fxHint by remember { mutableStateOf<String?>(null) }
    var touched by remember { mutableStateOf(edit == null) }

    // “用之前换好的美元”：成交汇率默认填换汇记录的平均成本（截至交易日期）
    LaunchedEffect(funding, ccy, date) {
        if (!touched || funding != "usd" || ccy == "USD" || !DATE_RE.matches(date)) return@LaunchedEffect
        try {
            val r = Zyll.api.obj("/portfolio/fx-cost?ccy=$ccy&date=$date")
            val rate = r.dbl("rate")
            if (rate != null) { fx = fmtInput(rate); fxHint = "已按你 ${r.optInt("records")} 笔换汇的平均成本填写" + if (r.optBoolean("borrowed")) "（这笔早于第一笔换汇）" else "" }
            else fxHint = "还没有用 $ccy 换美元的记录，请先在“总资本 → 换汇”记录，或手动填写"
        } catch (_: ApiException) { }
    }

    val sh = shares.num(); val pr = price.num(); val f = if (ccy == "USD") 1.0 else fx.num(); val fe = fee.num() ?: 0.0
    val total = if (sh != null && pr != null && f != null) (sh * pr + if (side == 0) fe else -fe) * f else null

    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text(if (edit != null) "修改交易记录" else "记一笔交易") },
        text = {
            Column(Modifier.heightIn(max = 520.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                if (edit == null && fixedSymbol == null) {
                    SelectBox("股票", symbol, d.symbols.map { it.symbol }, { it }) { symbol = it; price = fmtInput(d.quotes[it]?.price, 2) }
                } else Text(symbol, fontWeight = FontWeight.SemiBold, fontSize = 18.sp)
                Segmented(listOf("买入", "卖出"), side) { side = it }
                DateField(date, Modifier.fillMaxWidth()) { date = it }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    NumField("股数", shares, Modifier.weight(1f)) { shares = it }
                    NumField("成交价（美元）", price, Modifier.weight(1f)) { price = it }
                }
                SelectBox("资金货币（这笔钱用什么货币换的美元）", ccy, d.currencies, { Fmt.ccyLabel(it) }) {
                    ccy = it; touched = true; fx = fmtInput(Pnl.usdTo(fxNow, it, d.fxMode))
                }
                if (ccy != "USD") {
                    Segmented(listOf("当场按成交汇率换汇", "用之前换好的美元"), if (funding == "usd") 1 else 0) {
                        touched = true
                        funding = if (it == 1) "usd" else "ccy"
                        if (funding == "ccy") { fx = fmtInput(Pnl.usdTo(fxNow, ccy, d.fxMode)); fxHint = null }
                    }
                    Muted(if (funding == "usd") "已用“换汇”记录过换美元的选这个：现金从美元里扣，汇率只用来算汇率盈亏，不会重复扣$ccy。"
                          else "这笔美元是当场用$ccy 换的：按成交汇率从$ccy 现金里扣。", size = 11)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    NumField(if (funding == "usd" && ccy != "USD") "美元成本汇率：1 美元 = ? $ccy" else "汇率：1 美元 = ? $ccy", if (ccy == "USD") "1" else fx,
                        Modifier.weight(1f), enabled = ccy != "USD",
                        supporting = if (ccy == "USD") null else fxHint ?: "默认填当前汇率，可改成实际换汇价") { fx = it }
                    NumField("手续费（美元）", fee, Modifier.weight(0.7f)) { fee = it }
                }
                OutlinedTextField(note, { note = it.take(200) }, label = { Text("备注（可不填）") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                if (total != null) Muted("${if (side == 0) "花费" else "收回"} ${Fmt.money(total, ccy)}${if (ccy != "USD") "（${Fmt.money(sh!! * pr!!, "USD")}）" else ""}")
                Muted("买入会自动从 ${if (funding == "usd" || ccy == "USD") "美元" else ccy} 现金中扣除，卖出自动加回。")
                error?.let { Text(it, color = Palette.Red, fontSize = 13.sp) }
            }
        },
        confirmButton = {
            TextButton(enabled = !busy, onClick = {
                error = when {
                    symbol.isBlank() -> "请先选择股票"
                    !DATE_RE.matches(date) -> "日期格式应为 2026-10-22"
                    sh == null || sh <= 0 -> "股数必须大于 0"
                    pr == null || pr <= 0 -> "价格必须大于 0"
                    f == null || f <= 0 -> "汇率必须大于 0"
                    else -> null
                }
                if (error != null) return@TextButton
                busy = true
                val body = JSONObject().put("symbol", symbol).put("side", if (side == 0) "buy" else "sell").put("trade_date", date)
                    .put("shares", sh!!).put("price", pr!!).put("ccy", ccy).put("fx", f!!).put("fee", fe).put("note", note)
                    .put("funding", if (ccy == "USD") "ccy" else funding)
                scope.launch {
                    try {
                        if (edit != null) Zyll.api.patch("/portfolio/trades/${edit.id}", body) else Zyll.api.post("/portfolio/trades", body)
                        Toast.makeText(ctx, "已保存", Toast.LENGTH_SHORT).show()
                        onSaved()
                    } catch (e: ApiException) {
                        error = e.friendly
                    } finally { busy = false }
                }
            }) { Text(if (busy) "保存中…" else "保存") }
        },
        dismissButton = { TextButton(onClick = onDismiss, enabled = !busy) { Text("取消") } },
    )
}

/* ======================= 资金：入金 / 出金 / 换汇 ======================= */

@Composable
fun CashDialog(d: Portfolio, fxNow: Map<String, Rate>?, kind0: String, grp: String?, onDismiss: () -> Unit, onSaved: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val rows = d.cash.filter { grp != null && it.grp == grp }
    val kinds = listOf("deposit", "withdraw", "fx")
    var kind by remember { mutableStateOf(rows.firstOrNull()?.kind ?: kind0) }
    var date by remember { mutableStateOf(rows.firstOrNull()?.tradeDate ?: Fmt.today()) }
    var ccy by remember { mutableStateOf(rows.firstOrNull()?.ccy ?: d.base) }
    var amount by remember { mutableStateOf(fmtInput(rows.firstOrNull()?.amount?.let { abs(it) }, 2)) }
    val fromRow = rows.firstOrNull { it.amount < 0 }; val toRow = rows.firstOrNull { it.amount > 0 }
    var fromCcy by remember { mutableStateOf(fromRow?.ccy ?: d.base) }
    var toCcy by remember { mutableStateOf(toRow?.ccy ?: (if (d.base == "USD") d.currencies.firstOrNull { it != "USD" } ?: "CNY" else "USD")) }
    var fromAmt by remember { mutableStateOf(fmtInput(fromRow?.amount?.let { abs(it) }, 2)) }
    var toAmt by remember { mutableStateOf(fmtInput(toRow?.amount, 2)) }
    var note by remember { mutableStateOf(rows.firstOrNull()?.note.orEmpty()) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    // 换汇：按当前汇率估算另一边金额（用户可以改成实际成交金额）
    fun estimate(a: Double?, from: String, to: String): Double? {
        val rf = Pnl.usdTo(fxNow, from, d.fxMode) ?: return null
        val rt = Pnl.usdTo(fxNow, to, d.fxMode) ?: return null
        return a?.let { it / rf * rt }
    }

    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text(if (grp != null) "修改资金记录" else "资金记录") },
        text = {
            Column(Modifier.heightIn(max = 520.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                if (grp == null) Segmented(listOf("入金", "出金", "换汇"), kinds.indexOf(kind).coerceAtLeast(0)) { kind = kinds[it] }
                DateField(date, Modifier.fillMaxWidth()) { date = it }
                if (kind == "fx") {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        SelectBox("换出货币", fromCcy, d.currencies, { it }, Modifier.weight(1f)) { fromCcy = it }
                        NumField("换出金额", fromAmt, Modifier.weight(1f)) {
                            fromAmt = it
                            estimate(it.num(), fromCcy, toCcy)?.let { e -> toAmt = fmtInput(e, 2) }
                        }
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        SelectBox("换入货币", toCcy, d.currencies, { it }, Modifier.weight(1f)) { toCcy = it }
                        NumField("换入金额", toAmt, Modifier.weight(1f)) { toAmt = it }
                    }
                    val fa = fromAmt.num(); val ta = toAmt.num()
                    if (fa != null && ta != null && fa > 0 && ta > 0) Muted("成交汇率：1 $fromCcy = ${Fmt.num(ta / fa, 4)} $toCcy")
                    Muted("换入金额已按当前汇率估算，请改成银行实际到账金额。")
                } else {
                    SelectBox("货币", ccy, d.currencies, { Fmt.ccyLabel(it) }) { ccy = it }
                    NumField("金额", amount, Modifier.fillMaxWidth()) { amount = it }
                }
                OutlinedTextField(note, { note = it.take(200) }, label = { Text("备注（可不填）") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                error?.let { Text(it, color = Palette.Red, fontSize = 13.sp) }
            }
        },
        confirmButton = {
            TextButton(enabled = !busy, onClick = {
                val body = JSONObject().put("kind", kind).put("trade_date", date).put("note", note)
                error = if (!DATE_RE.matches(date)) "日期格式应为 2026-10-22" else null
                if (kind == "fx") {
                    val fa = fromAmt.num(); val ta = toAmt.num()
                    if (fa == null || ta == null || fa <= 0 || ta <= 0) error = "换出和换入金额都必须大于 0"
                    if (fromCcy == toCcy) error = "换出和换入的货币不能相同"
                    body.put("from_ccy", fromCcy).put("to_ccy", toCcy).put("from_amount", fa ?: 0.0).put("to_amount", ta ?: 0.0)
                } else {
                    val a = amount.num()
                    if (a == null || a <= 0) error = "金额必须大于 0"
                    body.put("ccy", ccy).put("amount", a ?: 0.0)
                }
                if (error != null) return@TextButton
                busy = true
                scope.launch {
                    try {
                        if (grp != null) Zyll.api.put("/portfolio/cash/$grp", body) else Zyll.api.post("/portfolio/cash", body)
                        Toast.makeText(ctx, "已保存", Toast.LENGTH_SHORT).show()
                        onSaved()
                    } catch (e: ApiException) {
                        error = e.friendly
                    } finally { busy = false }
                }
            }) { Text(if (busy) "保存中…" else "保存") }
        },
        dismissButton = { TextButton(onClick = onDismiss, enabled = !busy) { Text("取消") } },
    )
}

@Composable
fun CashRecordsDialog(d: Portfolio, onDismiss: () -> Unit, onEdit: (String, String) -> Unit, onChanged: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var confirmDel by remember { mutableStateOf<String?>(null) }
    val groups = d.cash.groupBy { it.grp }.values.sortedByDescending { it.first().tradeDate }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("资金记录") },
        text = {
            Column(Modifier.heightIn(max = 480.dp).verticalScroll(rememberScrollState())) {
                if (groups.isEmpty()) Muted("还没有资金记录")
                groups.forEach { g ->
                    val first = g.first()
                    val desc = when (first.kind) {
                        "fx" -> {
                            val from = g.firstOrNull { it.amount < 0 }; val to = g.firstOrNull { it.amount > 0 }
                            "换汇  ${from?.let { Fmt.money(abs(it.amount), it.ccy) } ?: "?"} → ${to?.let { Fmt.money(it.amount, it.ccy) } ?: "?"}"
                        }
                        else -> "${cashKindZh(first.kind)}  ${Fmt.money(abs(first.amount), first.ccy)}"
                    }
                    Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(desc, fontSize = 14.sp)
                            Muted(first.tradeDate + (if (first.note.isNotBlank()) " · ${first.note}" else "") + (if (first.batch.isNotBlank()) " · 导入" else ""), size = 11)
                        }
                        IconButton(onClick = { onEdit(first.kind, first.grp) }) { Icon(Icons.Filled.Edit, "修改", tint = Palette.Muted, modifier = Modifier.size(18.dp)) }
                        IconButton(onClick = { confirmDel = first.grp }) { Icon(Icons.Filled.Delete, "删除", tint = Palette.Muted, modifier = Modifier.size(18.dp)) }
                    }
                    HorizontalDivider(color = Color(0x10FFFFFF))
                }
                Spacer(Modifier.height(6.dp))
                Muted("买卖股票引起的现金变化会自动计算，不在这里列出。")
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("关闭") } },
    )
    confirmDel?.let { g ->
        AlertDialog(
            onDismissRequest = { confirmDel = null },
            title = { Text("删除这条资金记录？") },
            confirmButton = {
                TextButton(onClick = {
                    confirmDel = null
                    scope.launch {
                        try { Zyll.api.delete("/portfolio/cash/$g"); onChanged() } catch (e: ApiException) { Toast.makeText(ctx, e.friendly, Toast.LENGTH_SHORT).show() }
                    }
                }) { Text("删除") }
            },
            dismissButton = { TextButton(onClick = { confirmDel = null }) { Text("取消") } },
        )
    }
}

/* ======================= 设置 ======================= */

@Composable
fun SettingsDialog(d: Portfolio, onDismiss: () -> Unit, onSaved: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var base by remember { mutableStateOf(d.base) }
    var mode by remember { mutableStateOf(if (d.fxMode == "bid") 1 else 0) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("股票设置") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                SelectBox("汇总本币（盈亏、总资本都折算成这种货币）", base, d.currencies, { Fmt.ccyLabel(it) }) { base = it }
                Muted("汇率口径")
                Segmented(listOf("中间价", "银行买入价（保守）"), mode) { mode = it }
                Muted("切换本币不会改动交易记录，每笔交易仍按自己的货币对计算。")
            }
        },
        confirmButton = {
            TextButton(onClick = {
                scope.launch {
                    try {
                        Zyll.api.put("/portfolio/settings", JSONObject().put("base_currency", base).put("fx_mode", if (mode == 1) "bid" else "mid"))
                        onSaved()
                    } catch (e: ApiException) { Toast.makeText(ctx, e.friendly, Toast.LENGTH_SHORT).show() }
                }
            }) { Text("保存") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("取消") } },
    )
}

/* ======================= 单只股票详情（底部弹窗） ======================= */

@Composable
fun SymbolSheet(d: Portfolio, sym: String, p: SymbolPosition?, onTrade: (Long?) -> Unit, onChanged: () -> Unit, onRemoved: () -> Unit) {
    val ud = LocalUpDown.current
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var confirmRemove by remember { mutableStateOf(false) }
    var confirmDel by remember { mutableStateOf<Trade?>(null) }
    val trades = d.trades.filter { it.symbol == sym }.sortedWith(compareByDescending<Trade> { it.tradeDate }.thenByDescending { it.id })
    Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 18.dp).padding(bottom = 24.dp).navigationBarsPadding()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(sym, fontWeight = FontWeight.SemiBold, fontSize = 20.sp)
            Spacer(Modifier.width(8.dp))
            Text(d.quotes[sym]?.name.orEmpty(), color = Palette.Muted, fontSize = 12.sp, modifier = Modifier.weight(1f))
            TextButton(onClick = { AppNav.openStock(sym) }) { Text("看K线") }
        }
        if (p != null) {
            KV("现价", "${Fmt.price(p.price)}  ${Fmt.pct(p.dayChangePct)}", ud.of(p.dayChangePct))
            if ((p.qty ?: 0.0) > 0) {
                KV("持股", Fmt.num(p.qty, 4).trimEnd('0').trimEnd('.'))
                KV("平均成本（美元）", Fmt.price(p.avgUsd))
                p.avgFx?.let { KV("平均成交汇率", Fmt.num(it, 4)) }
                KV("市值", Fmt.money(p.mvBase, d.base))
                val v = com.zyll.finance.core.Pnl.view(p, d.includeFx)
                val cost = if (d.inflation) p.costReal else p.costBase
                KV("持仓盈亏" + if (d.inflation) "（扣除通胀）" else "", "${Fmt.signedMoney(v.unreal, d.base)}  ${Fmt.pct(if (cost != null && cost != 0.0) v.unreal?.let { it / cost * 100 } else null)}", ud.of(v.unreal))
                if (d.includeFx) {
                    KV("　其中股价部分", Fmt.signedMoney(p.unrealPrice, d.base), ud.of(p.unrealPrice))
                    KV("　其中汇率部分", Fmt.signedMoney(p.unrealFx, d.base), ud.of(p.unrealFx))
                }
                KV("今日盈亏", Fmt.signedMoney(v.today, d.base), ud.of(v.today))
            }
            val rv = com.zyll.finance.core.Pnl.view(p, d.includeFx).realized
            if ((rv ?: 0.0) != 0.0) KV("已实现盈亏", Fmt.signedMoney(rv, d.base), ud.of(rv))
        }
        Spacer(Modifier.height(10.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { onTrade(null) }) { Text("记一笔") }
            OutlinedButton(onClick = { confirmRemove = true }) { Text("移出持仓分析") }
        }
        Spacer(Modifier.height(12.dp))
        Text("交易记录", fontWeight = FontWeight.SemiBold)
        if (trades.isEmpty()) Muted("暂无交易记录（仅关注）", Modifier.padding(vertical = 8.dp))
        trades.forEach { t ->
            Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                Tag(if (t.side == "buy") "买" else "卖", if (t.side == "buy") ud.up else ud.down)
                Spacer(Modifier.width(8.dp))
                Column(Modifier.weight(1f)) {
                    Text("${Fmt.num(t.shares, 4).trimEnd('0').trimEnd('.')} 股 × ${Fmt.price(t.price)}", fontSize = 14.sp)
                    Muted("${t.tradeDate} · ${t.ccy ?: d.base}" + (if (t.ccy != "USD") " @${Fmt.num(t.fx, 4)}" else "") +
                        (if (t.funding == "usd") " · 美元资金" else "") + (if (t.batch.isNotBlank()) " · 导入" else "") +
                        (if (t.fee > 0) " · 费 ${Fmt.num(t.fee)}" else "") + (if (t.note.isNotBlank()) " · ${t.note}" else ""), size = 11)
                }
                IconButton(onClick = { onTrade(t.id) }) { Icon(Icons.Filled.Edit, "修改", tint = Palette.Muted, modifier = Modifier.size(18.dp)) }
                IconButton(onClick = { confirmDel = t }) { Icon(Icons.Filled.Delete, "删除", tint = Palette.Muted, modifier = Modifier.size(18.dp)) }
            }
            HorizontalDivider(color = Color(0x10FFFFFF))
        }
    }
    if (confirmRemove) AlertDialog(
        onDismissRequest = { confirmRemove = false },
        title = { Text("把 $sym 移出持仓分析？") },
        text = { Text(if (trades.isNotEmpty()) "该股票的 ${trades.size} 条交易记录也会一并删除，且无法恢复。" else "也会从行情的“我的个股”中移除。") },
        confirmButton = {
            TextButton(onClick = {
                confirmRemove = false
                scope.launch {
                    try {
                        Zyll.api.delete("/portfolio/symbols/$sym")
                        onRemoved()
                        Zyll.listsVersion.value++
                    } catch (e: ApiException) { Toast.makeText(ctx, e.friendly, Toast.LENGTH_SHORT).show() }
                }
            }) { Text("移出", color = Palette.Red) }
        },
        dismissButton = { TextButton(onClick = { confirmRemove = false }) { Text("取消") } },
    )
    confirmDel?.let { t ->
        AlertDialog(
            onDismissRequest = { confirmDel = null },
            title = { Text("删除这条交易记录？") },
            text = { Text("${t.tradeDate} ${if (t.side == "buy") "买入" else "卖出"} ${Fmt.num(t.shares, 4).trimEnd('0').trimEnd('.')} 股") },
            confirmButton = {
                TextButton(onClick = {
                    confirmDel = null
                    scope.launch {
                        try { Zyll.api.delete("/portfolio/trades/${t.id}"); onChanged() } catch (e: ApiException) { Toast.makeText(ctx, e.friendly, Toast.LENGTH_SHORT).show() }
                    }
                }) { Text("删除", color = Palette.Red) }
            },
            dismissButton = { TextButton(onClick = { confirmDel = null }) { Text("取消") } },
        )
    }
}
