package com.zyll.finance.ui

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.DialogProperties
import com.zyll.finance.BuildConfig
import com.zyll.finance.data.VersionInfo
import com.zyll.finance.data.Zyll
import com.zyll.finance.ui.components.ExternalLinkDialog
import com.zyll.finance.ui.components.ExternalTarget
import com.zyll.finance.ui.screens.AccountScreen
import com.zyll.finance.ui.screens.CalendarScreen
import com.zyll.finance.ui.screens.DarkpoolScreen
import com.zyll.finance.ui.screens.LoginDialog
import com.zyll.finance.ui.screens.MarketScreen
import com.zyll.finance.ui.screens.PortfolioScreen
import com.zyll.finance.ui.screens.RedeemDialog
import com.zyll.finance.ui.theme.Palette
import kotlinx.coroutines.flow.MutableStateFlow

/** 全局弹窗与导航 */
object AppNav {
    val tab = MutableStateFlow(Tab.CALENDAR)
    val showLogin = MutableStateFlow(false)
    val showRedeem = MutableStateFlow(false)
    val external = MutableStateFlow<ExternalTarget?>(null)

    fun openStock(symbol: String) { external.value = ExternalTarget(symbol, symbol) }
}

enum class Tab(val label: String, val icon: ImageVector) {
    CALENDAR("日历", Icons.Filled.DateRange),
    MARKET("行情", Icons.AutoMirrored.Filled.List),
    PORTFOLIO("持仓", Icons.Filled.Star),
    DARKPOOL("暗盘·美期", Icons.Filled.Info),
    ACCOUNT("我的", Icons.Filled.Person),
}

@Composable
fun AppRoot() {
    val tab by AppNav.tab.collectAsState()
    val showLogin by AppNav.showLogin.collectAsState()
    val showRedeem by AppNav.showRedeem.collectAsState()
    val external by AppNav.external.collectAsState()
    val version by Zyll.version.collectAsState()
    val updateNonce by Zyll.updatePrompt.collectAsState()
    val server by Zyll.session.serverUrl.collectAsState()

    LaunchedEffect(server) { Zyll.bootstrap() }
    val ctx = LocalContext.current
    val notice by Zyll.notice.collectAsState()
    LaunchedEffect(notice) {
        notice?.let { android.widget.Toast.makeText(ctx, it, android.widget.Toast.LENGTH_LONG).show(); Zyll.notice.value = null }
    }

    Scaffold(
        containerColor = Palette.Bg,
        bottomBar = {
            NavigationBar(containerColor = Palette.Bg2, tonalElevation = 0.dp) {
                Tab.entries.forEach { t ->
                    NavigationBarItem(
                        selected = t == tab,
                        onClick = { AppNav.tab.value = t },
                        icon = { Icon(t.icon, contentDescription = t.label) },
                        label = { Text(t.label, maxLines = 1) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = Palette.Accent, selectedTextColor = Palette.Accent,
                            indicatorColor = Palette.Accent.copy(alpha = 0.15f),
                            unselectedIconColor = Palette.Muted, unselectedTextColor = Palette.Muted,
                        ),
                    )
                }
            }
        },
    ) { pad ->
        Box(Modifier.fillMaxSize().padding(pad)) {
            when (tab) {
                Tab.CALENDAR -> CalendarScreen()
                Tab.MARKET -> MarketScreen()
                Tab.PORTFOLIO -> PortfolioScreen()
                Tab.DARKPOOL -> DarkpoolScreen()
                Tab.ACCOUNT -> AccountScreen()
            }
        }
    }

    if (showLogin) LoginDialog(onDismiss = { AppNav.showLogin.value = false })
    if (showRedeem) RedeemDialog(onDismiss = { AppNav.showRedeem.value = false })
    external?.let { ExternalLinkDialog(it) { AppNav.external.value = null } }
    version?.let { v -> UpdateDialog(v, updateNonce) }
}

/** 版本更新提示；force_update 时不能关闭 */
@Composable
fun UpdateDialog(v: VersionInfo, nonce: Int) {
    val ctx = LocalContext.current
    var dismissed by remember(v.latestCode, nonce) { mutableStateOf(nonce == 0 && !v.forceUpdate && v.latestCode <= Zyll.session.skippedVersion) }
    if (!v.hasUpdate && !v.forceUpdate || dismissed) return
    AlertDialog(
        onDismissRequest = { if (!v.forceUpdate) dismissed = true },
        properties = DialogProperties(dismissOnBackPress = !v.forceUpdate, dismissOnClickOutside = !v.forceUpdate),
        title = { Text(if (v.forceUpdate) "需要更新才能继续使用" else "发现新版本 ${v.latestName}") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                Text("当前版本 ${BuildConfig.VERSION_NAME}，最新版本 ${v.latestName.ifBlank { v.latestCode.toString() }}", style = MaterialTheme.typography.bodySmall, color = Palette.Muted)
                Spacer(Modifier.height(8.dp))
                Text(v.changelog.ifBlank { "修复问题，提升体验。" })
            }
        },
        confirmButton = {
            TextButton(enabled = v.apkUrl.isNotBlank(), onClick = {
                runCatching { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(v.apkUrl)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
            }) { Text("下载更新") }
        },
        dismissButton = {
            if (!v.forceUpdate) TextButton(onClick = { Zyll.session.skippedVersion = v.latestCode; dismissed = true }) { Text("以后再说") }
        },
    )
}
