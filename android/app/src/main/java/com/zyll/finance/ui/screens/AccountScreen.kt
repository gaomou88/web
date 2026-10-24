package com.zyll.finance.ui.screens

import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
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
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.zyll.finance.BuildConfig
import com.zyll.finance.core.Fmt
import com.zyll.finance.data.ApiException
import com.zyll.finance.data.Device
import com.zyll.finance.data.MemberInfo
import com.zyll.finance.data.Membership
import com.zyll.finance.data.Zyll
import com.zyll.finance.data.mapObj
import com.zyll.finance.ui.AppNav
import com.zyll.finance.ui.components.GlassCard
import com.zyll.finance.ui.components.KV
import com.zyll.finance.ui.components.LoadBox
import com.zyll.finance.ui.components.Muted
import com.zyll.finance.ui.components.ScreenHeader
import com.zyll.finance.ui.components.SectionTitle
import com.zyll.finance.ui.components.Segmented
import com.zyll.finance.ui.components.Tag
import com.zyll.finance.ui.components.rememberLoader
import com.zyll.finance.ui.theme.Palette
import kotlinx.coroutines.launch
import org.json.JSONObject

@Composable
fun AccountScreen() {
    val token by Zyll.session.token.collectAsState()
    val me by Zyll.me.collectAsState()
    val config by Zyll.config.collectAsState()
    val redUp by Zyll.session.redUp.collectAsState()
    val server by Zyll.session.serverUrl.collectAsState()
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var dlg by remember { mutableStateOf("") }   // password / server / delete / logout

    val exportLauncher = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            try {
                val data = Zyll.api.get("/me/export")
                val text = (data as? JSONObject)?.toString(2) ?: data.toString()
                ctx.contentResolver.openOutputStream(uri)?.use { it.write(text.toByteArray(Charsets.UTF_8)) }
                Toast.makeText(ctx, "已导出", Toast.LENGTH_SHORT).show()
            } catch (e: ApiException) {
                Toast.makeText(ctx, e.friendly, Toast.LENGTH_LONG).show()
            } catch (e: Exception) {
                Toast.makeText(ctx, "保存失败：${e.message}", Toast.LENGTH_LONG).show()
            }
        }
    }

    Column(Modifier.fillMaxSize()) {
        ScreenHeader("我的", config?.siteName)
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 12.dp).padding(bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if (token == null) {
                GlassCard(Modifier.fillMaxWidth()) {
                    Text("未登录", fontWeight = FontWeight.SemiBold, fontSize = 18.sp)
                    Muted("登录后可以同步持仓分析、关注的个股和指数设置，与网页版共用一个账号。")
                    Spacer(Modifier.height(10.dp))
                    Button(onClick = { AppNav.showLogin.value = true }) { Text(if (config?.registerEnabled != false) "登录 / 注册" else "登录") }
                }
            } else {
                GlassCard(Modifier.fillMaxWidth()) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(me?.email ?: Zyll.session.email ?: "已登录", fontWeight = FontWeight.SemiBold, fontSize = 17.sp, modifier = Modifier.weight(1f))
                        if (me?.emailVerified == true) Tag("已验证") else if (me != null) Tag("邮箱未验证", Palette.Warn)
                    }
                    // 会员模式关闭时完全不显示会员信息
                    if (config?.membershipEnabled == true) {
                        Spacer(Modifier.height(10.dp))
                        MemberBlock(me?.membership)
                    }
                }
                if (config?.membershipEnabled == true) MemberHistory()
                DevicesCard()
            }

            GlassCard(Modifier.fillMaxWidth()) {
                SectionTitle("设置")
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("涨跌配色")
                        Muted(if (redUp) "红涨绿跌" else "绿涨红跌")
                    }
                    Switch(checked = redUp, onCheckedChange = { Zyll.session.setRedUp(it) })
                }
                Divider()
                Item("服务器设置", server) { dlg = "server" }
                Divider()
                Item("检查更新", "当前版本 ${BuildConfig.VERSION_NAME}（${BuildConfig.VERSION_CODE}）") {
                    scope.launch {
                        val v = Zyll.checkVersion()
                        when {
                            v == null -> Toast.makeText(ctx, "检查失败，请稍后再试", Toast.LENGTH_SHORT).show()
                            v.hasUpdate || v.forceUpdate -> Zyll.updatePrompt.value++
                            else -> Toast.makeText(ctx, "已是最新版本", Toast.LENGTH_SHORT).show()
                        }
                    }
                }
                Divider()
                Item("隐私政策", "在浏览器中打开") {
                    runCatching { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("$server/#/privacy")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
                }
                if (token != null) {
                    Divider()
                    Item("修改密码", "修改后其他设备会被下线") { dlg = "password" }
                    Divider()
                    Item("导出我的数据", "下载服务器上与你有关的全部数据（JSON）") { exportLauncher.launch("zyll-my-data.json") }
                    Divider()
                    Item("删除账号", "永久删除账号与全部数据", Palette.Red) { dlg = "delete" }
                }
            }
            if (token != null) OutlinedButton(onClick = { dlg = "logout" }, modifier = Modifier.fillMaxWidth()) { Text("退出登录") }
            Muted("${config?.siteName ?: "Zyll财经"} · App ${BuildConfig.VERSION_NAME}", Modifier.fillMaxWidth().padding(top = 4.dp), 11)
        }
    }

    when (dlg) {
        "server" -> ServerDialog { dlg = "" }
        "password" -> PasswordDialog { dlg = "" }
        "delete" -> DeleteAccountDialog { dlg = "" }
        "logout" -> AlertDialog(
            onDismissRequest = { dlg = "" },
            title = { Text("退出登录？") },
            confirmButton = { TextButton(onClick = { dlg = ""; scope.launch { Zyll.logout() } }) { Text("退出") } },
            dismissButton = { TextButton(onClick = { dlg = "" }) { Text("取消") } },
        )
    }
}

@Composable
private fun Divider() = HorizontalDivider(color = Color(0x12FFFFFF), modifier = Modifier.padding(vertical = 4.dp))

@Composable
private fun Item(title: String, sub: String, color: Color = Palette.Text, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().clickable(onClick = onClick).padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(title, color = color)
            Muted(sub)
        }
        Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, null, tint = Palette.Muted)
    }
}

@Composable
private fun MemberBlock(m: Membership?) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            when {
                m == null || (!m.active && !m.expired) -> { Text("普通用户"); Muted("激活会员可解锁仅会员可见的内容") }
                m.permanent -> { Text("永久会员", color = Palette.Gold, fontWeight = FontWeight.SemiBold) }
                m.active -> { Text("会员", color = Palette.Gold, fontWeight = FontWeight.SemiBold); Muted("到期：${Fmt.dateTime(m.expires)}") }
                else -> { Text("会员已过期", color = Palette.Warn); Muted("过期时间：${Fmt.dateTime(m.expires)}") }
            }
        }
        if (m?.permanent != true) {
            Button(onClick = { AppNav.showRedeem.value = true }) { Text(if (m?.active == true || m?.expired == true) "续期" else "激活会员") }
        }
    }
}

@Composable
private fun MemberHistory() {
    val me by Zyll.me.collectAsState()
    val info = rememberLoader(me?.membership) { MemberInfo.parse(Zyll.api.obj("/member")) }
    val d = info.data ?: return
    if (d.history.isEmpty()) return
    GlassCard(Modifier.fillMaxWidth()) {
        SectionTitle("开通记录")
        d.history.take(10).forEach { h ->
            KV(Fmt.dateTime(h.ts) + when (h.source) { "admin" -> " 后台开通"; "app" -> " App 激活"; else -> " 卡密激活" },
                when { h.days == 0 -> "永久"; h.days != null -> "+${h.days} 天"; else -> "" })
        }
    }
}

@Composable
private fun DevicesCard() {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val devices = rememberLoader("devices") { Zyll.api.obj("/auth/devices").optJSONArray("devices").mapObj { Device.parse(it) } }
    GlassCard(Modifier.fillMaxWidth()) {
        SectionTitle("已登录的 App 设备")
        LoadBox(devices) { list ->
            list.forEach { dv ->
                Row(Modifier.fillMaxWidth().padding(vertical = 5.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(dv.name, fontSize = 14.sp)
                            if (dv.current) { Spacer(Modifier.width(6.dp)); Tag("本机") }
                        }
                        Muted("${dv.platform} · App ${dv.appVersion} · ${Fmt.dateTime(dv.lastUsedAt)} · ${dv.lastIp}", size = 11)
                    }
                    if (!dv.current) TextButton(onClick = {
                        scope.launch {
                            try { Zyll.api.delete("/auth/devices/${dv.id}"); devices.reload(silent = true) } catch (e: ApiException) { Toast.makeText(ctx, e.friendly, Toast.LENGTH_SHORT).show() }
                        }
                    }) { Text("下线") }
                }
            }
            if (list.isEmpty()) Muted("暂无")
        }
    }
}

/* ======================= 登录 / 注册 ======================= */

@Composable
fun LoginDialog(onDismiss: () -> Unit) {
    val config by Zyll.config.collectAsState()
    val token by Zyll.session.token.collectAsState()
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var mode by remember { mutableStateOf(0) }
    var email by remember { mutableStateOf(Zyll.session.email.orEmpty()) }
    var pw by remember { mutableStateOf("") }
    var pw2 by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var msg by remember { mutableStateOf<String?>(null) }
    var forceWeb by remember { mutableStateOf(false) }
    val canRegister = config?.registerEnabled != false
    // 网页登录完成、跳回 App 后令牌就有了：自动关闭登录框
    LaunchedEffect(token) { if (token != null) onDismiss() }
    val web = forceWeb || if (mode == 0) Zyll.webLoginRequired else Zyll.webRegisterRequired
    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text(if (mode == 0) "登录" else "注册") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (canRegister) Segmented(listOf("登录", "注册"), mode) { mode = it; msg = null }
                if (web) {
                    Text("为了防止恶意注册和撞库，网站开启了人机验证。请在打开的网页中" + (if (mode == 0) "登录" else "注册") +
                        "，完成后点“授权登录”，会自动回到 App。")
                    Muted("App 不会接触到你的密码。注册需要验证邮箱时，请先验证再回来登录。")
                } else {
                    OutlinedTextField(email, { email = it.trim() }, label = { Text("邮箱") }, singleLine = true, modifier = Modifier.fillMaxWidth(),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email))
                    OutlinedTextField(pw, { pw = it }, label = { Text("密码") }, singleLine = true, modifier = Modifier.fillMaxWidth(),
                        visualTransformation = PasswordVisualTransformation(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password))
                    if (mode == 1) {
                        OutlinedTextField(pw2, { pw2 = it }, label = { Text("确认密码") }, singleLine = true, modifier = Modifier.fillMaxWidth(),
                            visualTransformation = PasswordVisualTransformation(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password))
                        Muted("密码至少 8 位。注册即表示同意本站隐私政策。")
                    }
                }
                Row {
                    if (mode == 0) TextButton(onClick = {
                        if (config?.passwordReset == false) msg = "网站暂未配置邮件服务，无法找回密码，请联系管理员"
                        else Zyll.openWeb(ctx, "/#/forgot")
                    }) { Text("忘记密码？") }
                    Spacer(Modifier.weight(1f))
                    if (!web) TextButton(onClick = { forceWeb = true; msg = null }) { Text("用网页登录") }
                }
                msg?.let { Text(it, color = if (it.startsWith("注册成功")) Palette.Accent else Palette.Red, fontSize = 13.sp) }
            }
        },
        confirmButton = {
            if (web) {
                TextButton(onClick = { if (Zyll.startWebLogin(ctx)) msg = "已在浏览器中打开，完成后会自动回到 App" }) {
                    Text(if (mode == 0) "打开网页登录" else "打开网页注册")
                }
            } else TextButton(enabled = !busy, onClick = {
                msg = when {
                    !email.contains("@") -> "请输入正确的邮箱"
                    pw.length < 8 -> "密码至少 8 位"
                    mode == 1 && pw != pw2 -> "两次输入的密码不一致"
                    else -> null
                }
                if (msg != null) return@TextButton
                busy = true
                scope.launch {
                    try {
                        val r = if (mode == 0) Zyll.login(email, pw) else Zyll.register(email, pw)
                        if (r == null) onDismiss() else { msg = r; if (mode == 1) mode = 0 }
                    } catch (e: ApiException) {
                        if (e.body?.optBoolean("web_login") == true) {
                            forceWeb = true  // 服务器要求网页登录（刚开启了人机验证）
                            msg = null
                        } else {
                            msg = if (e.body?.optBoolean("unverified") == true) "邮箱还没有验证，请先打开验证邮件中的链接" else e.friendly
                        }
                    } finally { busy = false }
                }
            }) { Text(if (busy) "请稍候…" else if (mode == 0) "登录" else "注册") }
        },
        dismissButton = { TextButton(onClick = onDismiss, enabled = !busy) { Text("取消") } },
    )
}

/* ======================= 会员卡密 ======================= */

@Composable
fun RedeemDialog(onDismiss: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val config by Zyll.config.collectAsState()
    val me by Zyll.me.collectAsState()
    var code by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var msg by remember { mutableStateOf<String?>(null) }
    if (config?.membershipEnabled != true || !Zyll.session.isLoggedIn) {
        LaunchedEffect(Unit) {
            onDismiss()
            if (config?.membershipEnabled == true) AppNav.showLogin.value = true
        }
        return
    }
    val m = me?.membership
    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text(if (m?.active == true) "会员续期" else "激活会员") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (m?.active == true && !m.permanent) Muted("当前到期：${Fmt.dateTime(m.expires)}，续期从到期日往后累加。")
                OutlinedTextField(code, { code = it.uppercase().take(40) }, label = { Text("卡密") }, placeholder = { Text("ZYLL-XXXX-XXXX-XXXX") },
                    singleLine = true, modifier = Modifier.fillMaxWidth())
                config?.buyHint?.takeIf { it.isNotBlank() }?.let { Muted(it, size = 13) }
                msg?.let { Text(it, color = Palette.Red, fontSize = 13.sp) }
            }
        },
        confirmButton = {
            TextButton(enabled = !busy && code.isNotBlank(), onClick = {
                busy = true
                scope.launch {
                    try {
                        val r = Zyll.redeem(code)
                        val txt = if (r.optBoolean("permanent")) "已成为永久会员" else "激活成功，到期时间 ${Fmt.dateTime(r.optLong("expires"))}"
                        Toast.makeText(ctx, txt, Toast.LENGTH_LONG).show()
                        Zyll.listsVersion.value++
                        onDismiss()
                    } catch (e: ApiException) {
                        msg = e.friendly
                    } finally { busy = false }
                }
            }) { Text(if (busy) "请稍候…" else "激活") }
        },
        dismissButton = { TextButton(onClick = onDismiss, enabled = !busy) { Text("取消") } },
    )
}

/* ======================= 服务器 / 密码 / 删除账号 ======================= */

@Composable
private fun ServerDialog(onDismiss: () -> Unit) {
    val scope = rememberCoroutineScope()
    val ctx = LocalContext.current
    var url by remember { mutableStateOf(Zyll.session.serverUrl.value) }
    var key by remember { mutableStateOf(Zyll.session.appKey) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("服务器设置") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(url, { url = it.trim() }, label = { Text("网站地址") }, placeholder = { Text("https://example.com") }, singleLine = true,
                    modifier = Modifier.fillMaxWidth(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri))
                OutlinedTextField(key, { key = it.trim() }, label = { Text("App Key（后台未开启可留空）") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Muted("默认地址：${BuildConfig.SERVER_URL}。修改地址后需要重新登录。")
                TextButton(onClick = { Zyll.session.resetServerUrl(); onDismiss() }) { Text("恢复默认") }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                if (!url.startsWith("http://") && !url.startsWith("https://")) {
                    Toast.makeText(ctx, "地址要以 https:// 开头", Toast.LENGTH_SHORT).show(); return@TextButton
                }
                scope.launch { Zyll.switchServer(url, key) }
                onDismiss()
            }) { Text("保存") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("取消") } },
    )
}

@Composable
private fun PasswordDialog(onDismiss: () -> Unit) {
    val scope = rememberCoroutineScope()
    val ctx = LocalContext.current
    var old by remember { mutableStateOf("") }
    var new by remember { mutableStateOf("") }
    var new2 by remember { mutableStateOf("") }
    var msg by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text("修改密码") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(Triple("当前密码", old) { v: String -> old = v }, Triple("新密码（至少 8 位）", new) { v: String -> new = v }, Triple("确认新密码", new2) { v: String -> new2 = v })
                    .forEach { (label, value, set) ->
                        OutlinedTextField(value, set, label = { Text(label) }, singleLine = true, modifier = Modifier.fillMaxWidth(),
                            visualTransformation = PasswordVisualTransformation(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password))
                    }
                msg?.let { Text(it, color = Palette.Red, fontSize = 13.sp) }
            }
        },
        confirmButton = {
            TextButton(enabled = !busy, onClick = {
                msg = when { new.length < 8 -> "新密码至少 8 位"; new != new2 -> "两次输入的新密码不一致"; else -> null }
                if (msg != null) return@TextButton
                busy = true
                scope.launch {
                    try {
                        Zyll.changePassword(old, new)
                        Toast.makeText(ctx, "密码已修改，其他设备已下线", Toast.LENGTH_LONG).show()
                        onDismiss()
                    } catch (e: ApiException) { msg = e.friendly } finally { busy = false }
                }
            }) { Text("确定") }
        },
        dismissButton = { TextButton(onClick = onDismiss, enabled = !busy) { Text("取消") } },
    )
}

@Composable
private fun DeleteAccountDialog(onDismiss: () -> Unit) {
    val scope = rememberCoroutineScope()
    val ctx = LocalContext.current
    var pw by remember { mutableStateOf("") }
    var msg by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text("删除账号") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("将永久删除你的账号、持仓分析、交易记录、资金记录和所有个人数据，无法恢复。建议先导出数据。")
                OutlinedTextField(pw, { pw = it }, label = { Text("输入密码确认") }, singleLine = true, modifier = Modifier.fillMaxWidth(),
                    visualTransformation = PasswordVisualTransformation())
                msg?.let { Text(it, color = Palette.Red, fontSize = 13.sp) }
            }
        },
        confirmButton = {
            TextButton(enabled = !busy && pw.isNotBlank(), onClick = {
                busy = true
                scope.launch {
                    try {
                        Zyll.api.post("/me/delete", JSONObject().put("password", pw))
                        Zyll.logoutLocal()
                        Toast.makeText(ctx, "账号已删除", Toast.LENGTH_LONG).show()
                        onDismiss()
                    } catch (e: ApiException) { msg = e.friendly } finally { busy = false }
                }
            }) { Text("永久删除", color = Palette.Red) }
        },
        dismissButton = { TextButton(onClick = onDismiss, enabled = !busy) { Text("取消") } },
    )
}
