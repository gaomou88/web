package com.zyll.finance.ui.screens

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
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
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.zyll.finance.core.Fmt
import com.zyll.finance.data.ApiException
import com.zyll.finance.data.Zyll
import com.zyll.finance.data.dbl
import com.zyll.finance.data.mapObj
import com.zyll.finance.data.mapValues
import com.zyll.finance.data.s
import com.zyll.finance.data.str
import com.zyll.finance.data.strings
import com.zyll.finance.ui.AppNav
import com.zyll.finance.ui.components.GlassCard
import com.zyll.finance.ui.components.Muted
import com.zyll.finance.ui.components.SectionTitle
import com.zyll.finance.ui.components.Segmented
import com.zyll.finance.ui.components.SelectBox
import com.zyll.finance.ui.theme.LocalUpDown
import com.zyll.finance.ui.theme.Palette
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject

/* ======================= 数据 ======================= */

class Issue(val level: String, val code: String, val msg: String)

private fun issues(a: JSONArray?) = a.mapObj { Issue(it.s("level"), it.s("code"), it.s("msg")) }

/** 一行识别结果（成交 / 期初持仓），用户可以修改和勾选 */
data class ImpTrade(
    val key: String, val date: String, val symbol: String, val side: String, val shares: Double?, val price: Double?, val fee: Double,
    val raw: String, val issues: List<Issue>, val selected: Boolean, val opening: Boolean = false,
    /** 订单号（代号）、成交时间：用于去重 */
    val extId: String = "", val time: String = "",
    /** 预览判为重复 / 对不上：用户勾选就表示确认导入 */
    val dup: Boolean = false,
) {
    /** 已记录过、自动跳过的行（默认隐藏） */
    val skipped: Boolean get() = dup && issues.any { it.code == "duplicate" || it.code == "dup_file" }
}

data class ImpCash(
    val key: String, val date: String, val type: String, val currency: String, val amount: Double?, val fromCcy: String, val fromAmount: Double?,
    val toCcy: String, val toAmount: Double?, val raw: String, val issues: List<Issue>, val selected: Boolean, val dup: Boolean = false,
) {
    val skipped: Boolean get() = dup && issues.any { it.code == "duplicate" || it.code == "dup_file" }
}

class ImportConfig(
    val enabled: Boolean, val vision: Boolean, val allowed: Boolean, val maxMb: Int, val maxPages: Int, val dailyLimit: Int, val usedToday: Int,
    val base: String, val currencies: List<String>, val pools: Map<String, Pair<Int, Double>>,
) {
    companion object {
        fun parse(o: JSONObject) = ImportConfig(
            o.optBoolean("enabled"), o.optBoolean("vision"), o.optBoolean("allowed", true), o.optInt("max_mb", 10), o.optInt("max_pages", 30),
            o.optInt("daily_limit"), o.optInt("used_today"), o.s("base").ifBlank { "CNY" }, o.optJSONArray("currencies").strings(),
            o.optJSONObject("fx_pools").mapValues { _, p -> Pair(p.optInt("records"), p.optDouble("rate")) },
        )
    }
}

private val CASH_ZH = mapOf("deposit" to "入金", "withdrawal" to "出金", "dividend" to "股息", "interest" to "利息", "fee" to "费用", "tax" to "税费", "fx" to "换汇", "other" to "其他")

/** 一个正在识别的文件 */
private data class UpJob(val name: String, val job: String)

private sealed class Step {
    data object Upload : Step()
    data class Waiting(val jobs: List<UpJob>) : Step()
    data class Review(val result: JSONObject, val job: String) : Step()
    data class Failed(val msg: String) : Step()
}

/* ======================= 对话框 ======================= */

@Composable
fun ImportDialog(onDismiss: () -> Unit, onImported: () -> Unit) {
    val ctx = LocalContext.current
    var cfg by remember { mutableStateOf<ImportConfig?>(null) }
    var step by remember { mutableStateOf<Step>(Step.Upload) }
    var loadErr by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) {
        try {
            cfg = ImportConfig.parse(Zyll.api.obj("/portfolio/import/config"))
        } catch (e: ApiException) {
            loadErr = e.friendly
        }
    }
    Dialog(onDismissRequest = onDismiss, properties = DialogProperties(usePlatformDefaultWidth = false, dismissOnClickOutside = false)) {
        Column(Modifier.fillMaxSize().background(Palette.Bg).padding(top = 8.dp)) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("AI 导入券商结单", fontWeight = FontWeight.SemiBold, fontSize = 18.sp, modifier = Modifier.weight(1f))
                IconButton(onClick = onDismiss) { Icon(Icons.Filled.Close, "关闭") }
            }
            val c = cfg
            when {
                loadErr != null -> Muted(loadErr!!, Modifier.padding(16.dp), 14)
                c == null -> CircularProgressIndicator(Modifier.padding(32.dp).size(32.dp))
                !c.enabled -> Muted("网站暂未开启 AI 导入", Modifier.padding(16.dp), 14)
                !c.allowed -> Column(Modifier.padding(16.dp)) {
                    Text("AI 导入仅对会员开放")
                    Spacer(Modifier.height(10.dp))
                    Button(onClick = { onDismiss(); AppNav.showRedeem.value = true }) { Text("激活会员") }
                }
                else -> when (val s = step) {
                    Step.Upload -> UploadStep(c) { step = it }
                    is Step.Waiting -> WaitStep(s.jobs) { step = it }
                    is Step.Review -> ReviewStep(c, s.result, s.job, onDone = { onImported(); onDismiss() })
                    is Step.Failed -> Column(Modifier.padding(16.dp)) {
                        Text(s.msg, color = Palette.Red)
                        Spacer(Modifier.height(12.dp))
                        OutlinedButton(onClick = { step = Step.Upload }) { Text("重新上传") }
                    }
                }
            }
        }
    }
    LaunchedEffect(step) {
        if (step is Step.Failed) Toast.makeText(ctx, (step as Step.Failed).msg, Toast.LENGTH_SHORT).show()
    }
}

private fun displayName(ctx: Context, uri: Uri): String = try {
    ctx.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
        if (c.moveToFirst()) c.getString(0) ?: "" else ""
    } ?: ""
} catch (_: Exception) { "" }

/** 读取文件，超过上限返回 null */
private fun readLimited(ctx: Context, uri: Uri, max: Int): ByteArray? {
    ctx.contentResolver.openInputStream(uri)?.use { input ->
        val out = java.io.ByteArrayOutputStream()
        val buf = ByteArray(64 * 1024)
        while (true) {
            val n = input.read(buf)
            if (n < 0) break
            out.write(buf, 0, n)
            if (out.size() > max) return null
        }
        return out.toByteArray()
    }
    return ByteArray(0)
}

@Composable
private fun UploadStep(c: ImportConfig, go: (Step) -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var files by remember { mutableStateOf<List<Pair<Uri, String>>>(emptyList()) }
    var agree by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var err by remember { mutableStateOf<String?>(null) }
    // 可以一次选多个文件（例如几份日结单 + 月结单），服务器会互相去重
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        if (uris.isNotEmpty()) {
            files = uris.take(10).map { it to displayName(ctx, it).ifBlank { "文件" } }
            err = if (uris.size > 10) "一次最多 10 个文件，只保留前 10 个" else null
        }
    }
    val mimes = buildList {
        addAll(listOf("application/pdf", "text/csv", "text/comma-separated-values", "text/plain", "text/html",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/octet-stream"))
        if (c.vision) addAll(listOf("image/png", "image/jpeg", "image/webp"))
    }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Muted("上传券商的交易记录或月结单，AI 识别出成交、股息、换汇等明细，你核对后一键导入。只需记录一次换汇，导入的每笔交易都会按你的换汇成本计算汇率盈亏。", size = 13)
        Muted("不用担心重复：已经记录过的交易（包括手动录入的）会按“同一天 + 同一股票 + 同一方向”对账后自动跳过，多次上传或日结单、月结单混着传都只导入一次。", size = 12)
        Text("支持：文字版 PDF、Excel（.xlsx）、CSV" + (if (c.vision) "、截图 / 照片（PNG、JPG）" else "") + "。单个文件不超过 ${c.maxMb} MB，PDF 不超过 ${c.maxPages} 页。", fontSize = 13.sp)
        GlassCard(Modifier.fillMaxWidth(), onClick = { picker.launch(mimes.toTypedArray()) }) {
            Text(if (files.isEmpty()) "点这里选择文件（可多选）" else files.joinToString("、") { it.second }, fontWeight = FontWeight.SemiBold, color = Palette.Accent)
            Muted("可以从“文件”、网盘或券商 App 导出的位置选择", size = 11)
        }
        Row(verticalAlignment = Alignment.Top, modifier = Modifier.clickable { agree = !agree }) {
            Checkbox(checked = agree, onCheckedChange = { agree = it })
            Text("我同意把文件内容（已自动隐去姓名、地址、邮箱、手机号，账号和订单号换成代号）交给第三方 AI 服务（可能位于欧洲经济区以外）识别。文件不会保存，识别结果只用于本次导入。",
                fontSize = 13.sp, modifier = Modifier.padding(top = 12.dp))
        }
        if (c.dailyLimit > 0) Muted("今天已识别 ${c.usedToday} 次，每天最多 ${c.dailyLimit} 次")
        err?.let { Text(it, color = Palette.Red, fontSize = 13.sp) }
        Button(enabled = !busy, modifier = Modifier.fillMaxWidth(), onClick = {
            err = when {
                files.isEmpty() -> "请先选择文件"
                !agree -> "请先勾选同意"
                else -> null
            }
            if (err != null) return@Button
            busy = true
            scope.launch {
                val jobs = mutableListOf<UpJob>()
                try {
                    for ((f, name) in files) {
                        val bytes = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) { readLimited(ctx, f, c.maxMb * 1024 * 1024) }
                        if (bytes == null) { err = "$name 超过 ${c.maxMb} MB"; return@launch }
                        if (bytes.size < 20) { err = "$name 是空的"; return@launch }
                        val mime = ctx.contentResolver.getType(f) ?: "application/octet-stream"
                        // 服务器同时最多识别 3 个文件：满了就等一会儿再传
                        var r: JSONObject? = null
                        for (attempt in 0 until 40) {
                            try {
                                r = Zyll.api.upload("/portfolio/import/upload?consent=1&name=${com.zyll.finance.data.Api.enc(name.take(80))}", bytes, mime) as? JSONObject
                                break
                            } catch (e: ApiException) {
                                if (e.status == 429 && e.detail.contains("同时") && jobs.isNotEmpty()) delay(3000) else throw e
                            }
                        }
                        val job = r?.str("job") ?: throw ApiException(0, "服务器没有返回任务编号")
                        jobs.add(UpJob(name, job))
                    }
                    go(Step.Waiting(jobs))
                } catch (e: ApiException) {
                    if (e.membersOnly) { AppNav.showRedeem.value = true }
                    err = (if (jobs.isNotEmpty()) "第 ${jobs.size + 1} 个文件：" else "") + e.friendly
                } catch (e: Exception) {
                    err = "读取文件失败：${e.message}"
                } finally { busy = false }
            }
        }) { Text(if (busy) "上传中…" else "开始识别") }
    }
}

@Composable
private fun WaitStep(jobs: List<UpJob>, go: (Step) -> Unit) {
    val state = remember { mutableStateMapOf<String, String>() }   // 任务 → 当前步骤 / 结果
    var elapsed by remember { mutableStateOf(0) }
    LaunchedEffect(jobs) {
        val done = mutableMapOf<String, JSONObject>()
        val failed = mutableMapOf<String, String>()
        while (true) {
            for (j in jobs) {
                if (j.job in done || j.job in failed) continue
                try {
                    val r = Zyll.api.obj("/portfolio/import/job/${j.job}")
                    state[j.job] = r.s("step")
                    elapsed = maxOf(elapsed, r.optInt("elapsed"))
                    when (r.s("status")) {
                        "done" -> { done[j.job] = r.optJSONObject("result") ?: JSONObject(); state[j.job] = "✓" }
                        "failed" -> { failed[j.job] = r.s("error").ifBlank { "识别失败" }; state[j.job] = "失败：${failed[j.job]}" }
                    }
                } catch (e: ApiException) {
                    if (e.status != 0) { failed[j.job] = e.friendly; state[j.job] = "失败：${e.friendly}" }
                }
            }
            if (done.size + failed.size == jobs.size) break
            delay(1500)
        }
        val ok = jobs.filter { it.job in done }
        when {
            ok.isEmpty() -> go(Step.Failed(failed.values.first()))
            ok.size == 1 && failed.isEmpty() -> go(Step.Review(done[ok[0].job]!!, ok[0].job))
            ok.size == 1 -> go(Step.Review(done[ok[0].job]!!, ok[0].job))
            else -> try {
                // 多个文件：合并识别结果，文件之间互相去重
                val m = Zyll.api.post("/portfolio/import/merge", JSONObject().put("jobs", JSONArray(ok.map { it.job }))) as? JSONObject
                go(Step.Review(m?.optJSONObject("result") ?: JSONObject(), m?.str("job").orEmpty()))
            } catch (e: ApiException) { go(Step.Failed(e.friendly)) }
        }
    }
    Column(Modifier.padding(24.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            CircularProgressIndicator(Modifier.size(28.dp))
            Spacer(Modifier.width(16.dp))
            Column {
                Text("正在识别 ${jobs.size} 个文件")
                Muted("已用 $elapsed 秒，通常每个文件 10~60 秒")
            }
        }
        Spacer(Modifier.height(10.dp))
        jobs.forEach { Muted("${it.name} — ${state[it.job] ?: "排队中"}", size = 12) }
    }
}

/* ======================= 核对与导入 ======================= */

@Composable
private fun ReviewStep(c: ImportConfig, r: JSONObject, job: String, onDone: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val ud = LocalUpDown.current
    val broker = r.s("broker")
    val periodStart = r.str("period_start")
    val trades = remember {
        mutableStateListOf<ImpTrade>().apply {
            addAll(r.optJSONArray("trades").mapObj {
                ImpTrade(it.s("key"), it.s("date"), it.s("symbol"), it.s("side"), it.dbl("shares"), it.dbl("price"), it.dbl("fee") ?: 0.0,
                    it.s("raw"), issues(it.optJSONArray("issues")), it.optBoolean("selected"),
                    extId = it.s("ext_id"), time = it.s("time"), dup = it.optBoolean("dup"))
            })
            addAll(r.optJSONArray("positions").mapObj {
                ImpTrade(it.s("key"), it.str("as_of") ?: dayBefore(periodStart), it.s("symbol"), "buy", it.dbl("shares"), it.dbl("price"), 0.0,
                    "期初持仓", issues(it.optJSONArray("issues")), false, opening = true)
            })
        }
    }
    val cash = remember {
        mutableStateListOf<ImpCash>().apply {
            addAll(r.optJSONArray("cash").mapObj {
                ImpCash(it.s("key"), it.s("date"), it.s("type"), it.s("currency"), it.dbl("amount"), it.s("from_currency"), it.dbl("from_amount"),
                    it.s("to_currency"), it.dbl("to_amount"), it.s("raw"), issues(it.optJSONArray("issues")), it.optBoolean("selected"), dup = it.optBoolean("dup"))
            })
        }
    }
    val notes = r.optJSONArray("notes").strings()
    // —— 美元来源 ——
    val stmtFx = cash.filter { it.type == "fx" && it.toCcy == "USD" && it.selected }.map { it.fromCcy }.distinct()
    val poolCcys = (c.pools.keys + stmtFx).distinct()
    var mode by remember { mutableStateOf(if (c.base == "USD") "usd" else if (poolCcys.isNotEmpty()) "records" else "new") }
    var fund by remember { mutableStateOf(if (c.base in poolCcys) c.base else poolCcys.firstOrNull() ?: if (c.base != "USD") c.base else "CNY") }
    var newDate by remember { mutableStateOf(trades.map { it.date }.filter { it.length == 10 }.minOrNull() ?: Fmt.today()) }
    var newFrom by remember { mutableStateOf("") }
    var newTo by remember { mutableStateOf("") }
    var plan by remember { mutableStateOf<JSONObject?>(null) }
    var planErr by remember { mutableStateOf<String?>(null) }
    var rowErr by remember { mutableStateOf<Map<String, String>>(emptyMap()) }
    var editing by remember { mutableStateOf<Int?>(null) }
    var busy by remember { mutableStateOf(false) }
    var showSkipped by remember { mutableStateOf(false) }
    val nSkipped = trades.count { it.skipped } + cash.count { it.skipped }
    val files = r.optJSONArray("files").mapObj { it }

    fun payload(): JSONObject {
        val tr = JSONArray()
        trades.filter { it.selected }.forEach {
            tr.put(JSONObject().put("key", it.key).put("date", it.date).put("symbol", it.symbol).put("side", it.side)
                .put("shares", it.shares ?: 0.0).put("price", it.price ?: 0.0).put("fee", it.fee).put("note", if (it.opening) "期初持仓" else "")
                .put("ext_id", it.extId).put("time", it.time).put("confirm_dup", it.dup))
        }
        val cs = JSONArray()
        cash.filter { it.selected }.forEach {
            cs.put(JSONObject().put("key", it.key).put("date", it.date).put("type", it.type).put("currency", it.currency).put("amount", it.amount ?: 0.0)
                .put("from_currency", it.fromCcy).put("from_amount", it.fromAmount ?: 0.0).put("to_currency", it.toCcy).put("to_amount", it.toAmount ?: 0.0)
                .put("note", (CASH_ZH[it.type] ?: "") + if (broker.isNotBlank()) "（$broker）" else "").put("confirm_dup", it.dup))
        }
        val fx = JSONObject().put("mode", mode).put("ccy", fund)
            .put("new", JSONObject().put("date", newDate).put("from_amount", newFrom.toDoubleOrNull() ?: 0.0).put("to_amount", newTo.toDoubleOrNull() ?: 0.0))
        return JSONObject().put("source", broker).put("trades", tr).put("cash", cs).put("fx", fx).put("job", job)
    }

    // 任何改动后 0.5 秒重新试算（服务器权威校验）
    val planKey = listOf(trades.toList(), cash.toList(), mode, fund, newDate, newFrom, newTo)
    LaunchedEffect(planKey) {
        delay(500)
        plan = null
        try {
            val p = Zyll.api.post("/portfolio/import/plan", payload()) as? JSONObject
            plan = p
            planErr = null
            rowErr = p?.optJSONObject("errors").let { e -> e?.keys()?.asSequence()?.associateWith { k -> e.optString(k) } ?: emptyMap() }
        } catch (e: ApiException) {
            planErr = e.friendly
            rowErr = e.body?.optJSONObject("errors").let { o -> o?.keys()?.asSequence()?.associateWith { k -> o.optString(k) } ?: emptyMap() }
        }
    }
    val rates = plan?.optJSONArray("trades").mapObj { it.s("key") to it }.toMap()

    Column(Modifier.fillMaxSize()) {
        LazyColumn(Modifier.weight(1f), contentPadding = PaddingValues(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            item {
                val st = r.optJSONObject("stats")
                Muted(listOfNotNull(broker.ifBlank { null }?.let { "券商：$it" }, periodStart?.let { "期间：$it ~ ${r.str("period_end") ?: "?"}" },
                    st?.let { "${it.optInt("pages", 1)} 页 · ${if (it.s("mode").contains("vision")) "图片识别" else "文字识别"}" }).joinToString("　"))
                if (files.size > 1) Muted("文件：" + files.mapIndexed { i, f -> "${i + 1}. ${f.s("name").ifBlank { "?" }}" }.joinToString("　"), size = 11)
                if (nSkipped > 0) Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.clickable { showSkipped = !showSkipped }) {
                    Checkbox(checked = showSkipped, onCheckedChange = { showSkipped = it })
                    Text("已自动跳过 $nSkipped 笔已经记录过的记录（勾选显示）", fontSize = 13.sp, color = Palette.Accent)
                }
            }
            item {
                GlassCard(Modifier.fillMaxWidth()) {
                    Text("这些美元是怎么来的？", fontWeight = FontWeight.SemiBold)
                    val pool = c.pools[fund]
                    FxOption(mode == "records", "用我记录过的换汇", if (pool != null) "${pool.first} 笔，平均 1 美元 = ${Fmt.num(pool.second, 4)} $fund" +
                        (if (stmtFx.isNotEmpty()) "；对账单里的换汇也会计入" else "") else if (stmtFx.isNotEmpty()) "使用对账单里的换汇" else "还没有记录过换汇") { mode = "records" }
                    FxOption(mode == "new", "现在补记一笔换汇", "填一次即可，之后的交易都按它计算") { mode = "new" }
                    if (mode != "usd") SelectBox("换汇前的货币", fund, c.currencies.filter { it != "USD" }, { Fmt.ccyLabel(it) }, Modifier.fillMaxWidth().padding(vertical = 4.dp)) { fund = it }
                    if (mode == "new") {
                        OutlinedTextField(newDate, { newDate = it.filter { ch -> ch.isDigit() || ch == '-' }.take(10) }, label = { Text("换汇日期") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedTextField(newFrom, { newFrom = it.filter { ch -> ch.isDigit() || ch == '.' } }, label = { Text("换出 $fund") }, singleLine = true,
                                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), modifier = Modifier.weight(1f))
                            OutlinedTextField(newTo, { newTo = it.filter { ch -> ch.isDigit() || ch == '.' } }, label = { Text("得到美元") }, singleLine = true,
                                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), modifier = Modifier.weight(1f))
                        }
                        val a = newFrom.toDoubleOrNull(); val b = newTo.toDoubleOrNull()
                        if (a != null && b != null && a > 0 && b > 0) Muted("1 美元 = ${Fmt.num(a / b, 4)} $fund")
                    }
                    FxOption(mode == "usd", "不计算汇率盈亏", "直接按美元记账") { mode = "usd" }
                }
            }
            if (trades.isNotEmpty()) item { SectionTitle("成交与期初持仓（${trades.size}）") }
            trades.forEachIndexed { i, t ->
                if (t.skipped && !showSkipped) return@forEachIndexed
                item(key = "t_${t.key}") {
                    val err = rowErr[t.key]
                    val rate = rates[t.key]
                    GlassCard(Modifier.fillMaxWidth(), padding = PaddingValues(10.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(checked = t.selected, onCheckedChange = { v -> trades[i] = t.copy(selected = v) })
                            Column(Modifier.weight(1f)) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Text(t.symbol.ifBlank { "?" }, fontWeight = FontWeight.SemiBold)
                                    Spacer(Modifier.width(6.dp))
                                    Text(if (t.opening) "期初持仓" else if (t.side == "buy") "买入" else "卖出", fontSize = 12.sp,
                                        color = if (t.side == "buy") ud.up else ud.down)
                                    Spacer(Modifier.weight(1f))
                                    Muted(t.date)
                                }
                                Text("${Fmt.num(t.shares, 4).trimEnd('0').trimEnd('.')} 股 × \$${Fmt.price(t.price)}" + if (t.fee > 0) "  费用 \$${Fmt.num(t.fee)}" else "", fontSize = 13.sp)
                                if (rate != null && rate.s("ccy") != "USD") Muted("成本汇率 ${Fmt.num(rate.dbl("fx"), 4)}" + (rate.str("rate_note")?.let { "（$it）" } ?: ""), size = 11)
                            }
                            IconButton(onClick = { editing = i }) { Icon(Icons.Filled.Edit, "修改", tint = Palette.Muted, modifier = Modifier.size(18.dp)) }
                        }
                        IssueLines(t.issues, err)
                        if (t.raw.isNotBlank() && !t.opening) Muted("原文：${t.raw}", size = 10)
                    }
                }
            }
            if (cash.isNotEmpty()) item { SectionTitle("资金流水（${cash.size}）") }
            cash.forEachIndexed { i, cRow ->
                if (cRow.skipped && !showSkipped) return@forEachIndexed
                item(key = "c_${cRow.key}") {
                    GlassCard(Modifier.fillMaxWidth(), padding = PaddingValues(10.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(checked = cRow.selected, onCheckedChange = { v -> cash[i] = cRow.copy(selected = v) })
                            Column(Modifier.weight(1f)) {
                                Text(CASH_ZH[cRow.type] ?: cRow.type, fontWeight = FontWeight.SemiBold)
                                Text(if (cRow.type == "fx") "${Fmt.num(cRow.fromAmount)} ${cRow.fromCcy} → ${Fmt.num(cRow.toAmount)} ${cRow.toCcy}" else "${Fmt.num(cRow.amount)} ${cRow.currency}", fontSize = 13.sp)
                            }
                            Muted(cRow.date)
                        }
                        IssueLines(cRow.issues, rowErr[cRow.key])
                    }
                }
            }
            if (notes.isNotEmpty()) item {
                GlassCard(Modifier.fillMaxWidth()) {
                    Text("AI 的备注", fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                    notes.forEach { Muted("· $it") }
                }
            }
        }
        // —— 底部：试算结果与确认 ——
        Column(Modifier.fillMaxWidth().background(Palette.Bg2).padding(12.dp)) {
            val p = plan
            when {
                planErr != null -> Text(planErr!!, color = Palette.Red, fontSize = 13.sp)
                p == null -> Muted("试算中…")
                else -> {
                    val sm = p.optJSONObject("summary") ?: JSONObject()
                    val newSyms = p.optJSONArray("new_symbols").strings()
                    Text("将导入 ${sm.optInt("trades")} 笔交易（买 ${sm.optInt("buys")} / 卖 ${sm.optInt("sells")}）、${sm.optInt("cash")} 笔资金记录" +
                        if (newSyms.isNotEmpty()) "，新增股票 ${newSyms.joinToString("、")}" else "", fontSize = 13.sp)
                    if (!p.optBoolean("ok")) Text("请修改或取消勾选标红的记录", color = Palette.Red, fontSize = 12.sp)
                    p.optJSONArray("notes").strings().forEach { Muted("⚠ $it", size = 11) }
                }
            }
            Spacer(Modifier.height(8.dp))
            val n = (p?.optJSONObject("summary")?.let { it.optInt("trades") + it.optInt("cash") }) ?: 0
            Button(enabled = !busy && p?.optBoolean("ok") == true && n > 0, modifier = Modifier.fillMaxWidth(), onClick = {
                busy = true
                scope.launch {
                    try {
                        val res = Zyll.api.post("/portfolio/import/commit", payload()) as? JSONObject
                        val sm = res?.optJSONObject("summary")
                        Toast.makeText(ctx, "已导入 ${sm?.optInt("trades")} 笔交易、${sm?.optInt("cash")} 笔资金记录，可在“导入记录”里撤销", Toast.LENGTH_LONG).show()
                        Zyll.listsVersion.value++
                        onDone()
                    } catch (e: ApiException) {
                        planErr = e.friendly
                        rowErr = e.body?.optJSONObject("errors").let { o -> o?.keys()?.asSequence()?.associateWith { k -> o.optString(k) } ?: emptyMap() }
                    } finally { busy = false }
                }
            }) { Text(if (busy) "导入中…" else "确认导入（$n）") }
        }
    }

    val ei = editing
    val et = ei?.let { trades.getOrNull(it) }
    if (ei != null && et != null) EditRowDialog(et, onDismiss = { editing = null }) { trades[ei] = it; editing = null }
}

@Composable
private fun FxOption(selected: Boolean, title: String, sub: String, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).clickable(onClick = onClick), verticalAlignment = Alignment.CenterVertically) {
        RadioButton(selected = selected, onClick = onClick)
        Column {
            Text(title, fontSize = 14.sp)
            Muted(sub, size = 11)
        }
    }
}

@Composable
private fun IssueLines(list: List<Issue>, serverErr: String?) {
    list.forEach {
        Text(it.msg, fontSize = 12.sp, color = when (it.level) { "error" -> Palette.Red; "warn" -> Palette.Warn; else -> Palette.Muted })
    }
    serverErr?.let { Text(it, fontSize = 12.sp, color = Palette.Red) }
}

@Composable
private fun EditRowDialog(t: ImpTrade, onDismiss: () -> Unit, onSave: (ImpTrade) -> Unit) {
    var date by remember { mutableStateOf(t.date) }
    var sym by remember { mutableStateOf(t.symbol) }
    var side by remember { mutableStateOf(if (t.side == "sell") 1 else 0) }
    var shares by remember { mutableStateOf(t.shares?.let { Fmt.num(it, 6).replace(",", "").trimEnd('0').trimEnd('.') } ?: "") }
    var price by remember { mutableStateOf(t.price?.let { Fmt.num(it, 6).replace(",", "").trimEnd('0').trimEnd('.') } ?: "") }
    var fee by remember { mutableStateOf(Fmt.num(t.fee, 4).replace(",", "").trimEnd('0').trimEnd('.')) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("修改这一行") },
        text = {
            Column(Modifier.heightIn(max = 460.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                if (t.raw.isNotBlank()) Muted("原文：${t.raw}", size = 11)
                OutlinedTextField(date, { date = it.filter { c -> c.isDigit() || c == '-' }.take(10) }, label = { Text("日期（年-月-日）") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(sym, { sym = it.uppercase().filter { c -> c.isLetterOrDigit() || c == '.' }.take(10) }, label = { Text("代码") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                if (!t.opening) Segmented(listOf("买入", "卖出"), side) { side = it }
                listOf(Triple("数量", shares) { v: String -> shares = v }, Triple("价格（美元）", price) { v: String -> price = v }, Triple("费用（美元）", fee) { v: String -> fee = v })
                    .forEach { (label, value, set) ->
                        OutlinedTextField(value, { set(it.filter { c -> c.isDigit() || c == '.' }) }, label = { Text(label) }, singleLine = true,
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), modifier = Modifier.fillMaxWidth())
                    }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                onSave(t.copy(date = date, symbol = sym, side = if (t.opening) "buy" else if (side == 1) "sell" else "buy",
                    shares = shares.toDoubleOrNull(), price = price.toDoubleOrNull(), fee = fee.toDoubleOrNull() ?: 0.0, selected = true))
            }) { Text("确定") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("取消") } },
    )
}

private fun dayBefore(d: String?): String {
    if (d == null || d.length != 10) return ""
    return try {
        val f = java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.US).apply { timeZone = java.util.TimeZone.getTimeZone("UTC") }
        f.format(java.util.Date(f.parse(d)!!.time - 86_400_000L))
    } catch (_: Exception) { "" }
}

/* ======================= 导入记录（撤销） ======================= */

@Composable
fun ImportBatchesDialog(onDismiss: () -> Unit, onChanged: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var rows by remember { mutableStateOf<List<JSONObject>?>(null) }
    var reload by remember { mutableStateOf(0) }
    var confirm by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(reload) {
        rows = try { Zyll.api.obj("/portfolio/import/batches").optJSONArray("batches").mapObj { it } } catch (e: ApiException) { emptyList() }
    }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("导入记录") },
        text = {
            Column(Modifier.heightIn(max = 460.dp).verticalScroll(rememberScrollState())) {
                val list = rows
                when {
                    list == null -> CircularProgressIndicator(Modifier.size(24.dp))
                    list.isEmpty() -> Muted("还没有导入过")
                    else -> list.forEach { b ->
                        Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(b.s("source").ifBlank { "AI 导入" }, fontSize = 14.sp)
                                Muted("${Fmt.dateTime(b.optLong("created_at"))} · ${b.optInt("trades")} 笔交易 / ${b.optInt("cash")} 笔资金" +
                                    (if (b.optInt("skipped") > 0) " · 跳过重复 ${b.optInt("skipped")}" else ""), size = 11)
                                if (b.s("period_start").isNotBlank()) Muted("期间 ${b.s("period_start")} ~ ${b.s("period_end")}", size = 11)
                            }
                            if (b.optInt("undone") == 1) Muted("已撤销")
                            else TextButton(onClick = { confirm = b.s("id") }) { Text("撤销", color = Palette.Red) }
                        }
                        HorizontalDivider(color = Color(0x10FFFFFF))
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("关闭") } },
    )
    confirm?.let { id ->
        AlertDialog(
            onDismissRequest = { confirm = null },
            title = { Text("撤销这次导入？") },
            text = { Text("这批导入的交易和资金记录会全部删除。") },
            confirmButton = {
                TextButton(onClick = {
                    confirm = null
                    scope.launch {
                        try {
                            Zyll.api.delete("/portfolio/import/batches/$id")
                            Toast.makeText(ctx, "已撤销", Toast.LENGTH_SHORT).show()
                            reload++
                            onChanged()
                        } catch (e: ApiException) { Toast.makeText(ctx, e.friendly, Toast.LENGTH_LONG).show() }
                    }
                }) { Text("撤销", color = Palette.Red) }
            },
            dismissButton = { TextButton(onClick = { confirm = null }) { Text("取消") } },
        )
    }
}
