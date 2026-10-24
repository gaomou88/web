package com.zyll.finance.ui.components

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.zyll.finance.data.Api
import com.zyll.finance.data.ApiException
import com.zyll.finance.data.SymbolHit
import com.zyll.finance.data.Zyll
import com.zyll.finance.data.parseSymbolHits
import com.zyll.finance.ui.theme.Palette
import kotlinx.coroutines.delay
import org.json.JSONArray

/* ======================= 外部网站跳转（与网站相同的服务商与风险提示） ======================= */

class Site(val name: String, val url: (String) -> String)

val STOCK_SITES = listOf(
    Site("新浪财经") { "https://stock.finance.sina.com.cn/usstock/quotes/${it.replace(".", "")}.html" },
    Site("雪球") { "https://xueqiu.com/S/${it.replace(".", "-")}" },
    Site("富途牛牛") { "https://www.futunn.com/stock/${it.replace(".", "-")}-US" },
    Site("Yahoo Finance") { "https://finance.yahoo.com/quote/${it.replace(".", "-")}/chart" },
    Site("TradingView") { "https://www.tradingview.com/chart/?symbol=${Api.enc(it)}" },
)

/** 指数：code 为 "yahoo代码|tv代码" */
val INDEX_SITES = listOf(
    Site("Yahoo Finance") { "https://finance.yahoo.com/quote/${Api.enc(it.substringBefore("|"))}/chart" },
    Site("TradingView") { "https://www.tradingview.com/chart/?symbol=${Api.enc(it.substringAfter("|"))}" },
)

/** 要跳转的目标：title 显示用，key 传给 Site.url */
data class ExternalTarget(val title: String, val key: String, val sites: List<Site> = STOCK_SITES)

/**
 * 先选择数据服务商，再提示“即将离开本站”的风险，确认后用浏览器打开。
 */
@Composable
fun ExternalLinkDialog(target: ExternalTarget, onDismiss: () -> Unit) {
    val ctx = LocalContext.current
    var chosen by remember(target) { mutableStateOf<Site?>(null) }
    val c = chosen
    if (c == null) {
        AlertDialog(
            onDismissRequest = onDismiss,
            title = { Text("查看 ${target.title} 的K线") },
            text = {
                Column {
                    Muted("选择数据服务商：", size = 13)
                    Spacer(Modifier.height(6.dp))
                    target.sites.forEach { s ->
                        Text(
                            s.name, fontSize = 15.sp,
                            modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).clickable { chosen = s }.padding(vertical = 12.dp, horizontal = 6.dp),
                        )
                        HorizontalDivider(color = Color(0x14FFFFFF))
                    }
                }
            },
            confirmButton = {},
            dismissButton = { TextButton(onClick = onDismiss) { Text("取消") } },
        )
    } else {
        val url = c.url(target.key)
        AlertDialog(
            onDismissRequest = onDismiss,
            icon = { Icon(Icons.Filled.Warning, null, tint = Palette.Warn) },
            title = { Text("即将离开 Zyll财经") },
            text = {
                Column {
                    Text("你将前往第三方网站「${c.name}」。该网站不属于本站，其内容、广告、数据准确性和隐私做法由对方负责，请注意甄别，谨防诈骗，不要在不信任的网站输入账号密码。")
                    Spacer(Modifier.height(8.dp))
                    Muted(url, size = 11)
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    onDismiss()
                    try {
                        ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                    } catch (_: ActivityNotFoundException) {
                        Toast.makeText(ctx, "没有可以打开网页的应用", Toast.LENGTH_SHORT).show()
                    }
                }) { Text("继续前往") }
            },
            dismissButton = { TextButton(onClick = { chosen = null }) { Text("返回") } },
        )
    }
}

/* ======================= 股票代码输入（联想） ======================= */

/**
 * 带联想的代码输入框。联想结果直接显示在输入框下方（不用弹出层，避免遮挡和“穿模”）。
 */
@Composable
fun SymbolField(
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    label: String = "股票代码",
    onPick: (SymbolHit) -> Unit = { onValueChange(it.symbol) },
    onDone: (() -> Unit)? = null,
) {
    var hits by remember { mutableStateOf<List<SymbolHit>>(emptyList()) }
    var picked by remember { mutableStateOf("") }
    LaunchedEffect(value) {
        val q = value.trim()
        if (q.isEmpty() || q.equals(picked, ignoreCase = true)) { hits = emptyList(); return@LaunchedEffect }
        delay(250)
        hits = try {
            parseSymbolHits(Zyll.api.get("/symbols/search?q=${Api.enc(q)}") as? JSONArray).take(8)
        } catch (_: ApiException) { emptyList() }
    }
    Column(modifier) {
        OutlinedTextField(
            value = value,
            onValueChange = { onValueChange(it.uppercase().filter { ch -> ch.isLetterOrDigit() || ch == '.' || ch == '-' }.take(12)) },
            label = { Text(label) },
            singleLine = true,
            keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Characters, imeAction = ImeAction.Done),
            keyboardActions = KeyboardActions(onDone = { hits = emptyList(); onDone?.invoke() }),
            modifier = Modifier.fillMaxWidth(),
        )
        if (hits.isNotEmpty()) {
            Column(
                Modifier.fillMaxWidth().heightIn(max = 260.dp).padding(top = 4.dp).clip(RoundedCornerShape(10.dp))
                    .background(Color(0xFF1A2640)).verticalScroll(rememberScrollState()),
            ) {
                hits.forEach { h ->
                    Row(
                        Modifier.fillMaxWidth().clickable { picked = h.symbol; hits = emptyList(); onPick(h) }.padding(horizontal = 12.dp, vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(h.symbol, fontWeight = FontWeight.SemiBold, modifier = Modifier.width(70.dp))
                        Text(h.name, fontSize = 12.sp, color = Palette.Muted, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                        if (h.exchange.isNotBlank()) Tag(if (h.etf) "ETF" else h.exchange, Palette.Muted)
                    }
                }
            }
        }
    }
}
