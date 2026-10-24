package com.zyll.finance.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.zyll.finance.data.ApiException
import com.zyll.finance.data.Zyll
import com.zyll.finance.ui.AppNav
import com.zyll.finance.ui.theme.Palette
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

/* ======================= 加载状态 ======================= */

/**
 * 一个接口数据的加载状态。reload() 重新请求；silent = true 时不显示加载圈（实时刷新用）。
 */
@Stable
class Loader<T>(private val scope: CoroutineScope, private val fetch: suspend () -> T) {
    var data by mutableStateOf<T?>(null)
    var error by mutableStateOf<ApiException?>(null)
    var loading by mutableStateOf(false)
    private var job: Job? = null

    fun reload(silent: Boolean = false) {
        job?.cancel()
        if (!silent) loading = true
        job = scope.launch {
            try {
                data = fetch()
                error = null
            } catch (e: ApiException) {
                if (!silent || data == null) error = e
            } finally {
                loading = false
            }
        }
    }
}

/** 记住一个 Loader，key 变化时重新创建并加载 */
@Composable
fun <T> rememberLoader(vararg keys: Any?, fetch: suspend () -> T): Loader<T> {
    val scope = rememberCoroutineScope()
    val loader = remember(*keys) { Loader(scope, fetch) }
    LaunchedEffect(loader) { loader.reload() }
    return loader
}

/** 按加载状态显示：加载中 / 出错 / 仅会员 / 内容 */
@Composable
fun <T> LoadBox(loader: Loader<T>, modifier: Modifier = Modifier, content: @Composable (T) -> Unit) {
    val d = loader.data
    val e = loader.error
    when {
        d != null -> content(d)
        e != null && e.membersOnly -> MembersOnlyBox(e.friendly, modifier)
        e != null -> ErrorBox(e.friendly, modifier) { loader.reload() }
        else -> Box(modifier.fillMaxWidth().padding(40.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator(Modifier.size(32.dp)) }
    }
}

@Composable
fun ErrorBox(message: String, modifier: Modifier = Modifier, retry: (() -> Unit)? = null) {
    GlassCard(modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Filled.Warning, null, tint = Palette.Warn, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(8.dp))
            Text(message, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f))
        }
        if (retry != null) {
            Spacer(Modifier.height(10.dp))
            OutlinedButton(onClick = retry) { Text("重试") }
        }
    }
}

@Composable
fun MembersOnlyBox(notice: String, modifier: Modifier = Modifier) {
    GlassCard(modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Filled.Lock, null, tint = Palette.Gold, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(8.dp))
            Text(notice, modifier = Modifier.weight(1f))
        }
        Spacer(Modifier.height(10.dp))
        if (Zyll.session.isLoggedIn) {
            Button(onClick = { AppNav.showRedeem.value = true }) { Text("激活会员") }
        } else {
            Button(onClick = { AppNav.showLogin.value = true }) { Text("登录") }
        }
    }
}

@Composable
fun LoginRequired(text: String, modifier: Modifier = Modifier) {
    GlassCard(modifier.fillMaxWidth()) {
        Text(text, color = Palette.Muted)
        Spacer(Modifier.height(10.dp))
        Button(onClick = { AppNav.showLogin.value = true }) { Text("登录 / 注册") }
    }
}

/* ======================= 卡片与布局 ======================= */

val CardShape = RoundedCornerShape(16.dp)

@Composable
fun GlassCard(
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
    padding: PaddingValues = PaddingValues(14.dp),
    content: @Composable ColumnScope.() -> Unit,
) {
    Column(
        modifier
            .clip(CardShape)
            .background(Palette.Glass)
            .border(BorderStroke(1.dp, Palette.GlassBorder), CardShape)
            .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier)
            .padding(padding),
        content = content,
    )
}

/** 页面顶部标题栏：标题 + 副标题 + 右侧操作 */
@Composable
fun ScreenHeader(title: String, subtitle: String? = null, onRefresh: (() -> Unit)? = null, actions: @Composable RowScope.() -> Unit = {}) {
    Row(Modifier.fillMaxWidth().padding(start = 16.dp, end = 6.dp, top = 10.dp, bottom = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.titleLarge)
            if (subtitle != null) Text(subtitle, style = MaterialTheme.typography.bodySmall, color = Palette.Muted, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        actions()
        if (onRefresh != null) IconButton(onClick = onRefresh) { Icon(Icons.Filled.Refresh, "刷新") }
    }
}

@Composable
fun SectionTitle(text: String, modifier: Modifier = Modifier, trailing: @Composable RowScope.() -> Unit = {}) {
    Row(modifier.fillMaxWidth().padding(top = 6.dp, bottom = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(text, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
        trailing()
    }
}

/** 分段选择（不依赖实验性 API） */
@Composable
fun Segmented(options: List<String>, selected: Int, modifier: Modifier = Modifier, onSelect: (Int) -> Unit) {
    Row(
        modifier
            .clip(RoundedCornerShape(12.dp))
            .background(Color(0x14FFFFFF))
            .padding(3.dp),
        horizontalArrangement = Arrangement.spacedBy(3.dp),
    ) {
        options.forEachIndexed { i, label ->
            val sel = i == selected
            Box(
                Modifier
                    .weight(1f)
                    .clip(RoundedCornerShape(10.dp))
                    .background(if (sel) Palette.Accent.copy(alpha = 0.22f) else Color.Transparent)
                    .clickable { onSelect(i) }
                    .padding(vertical = 8.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text(label, color = if (sel) Palette.Accent else Palette.Muted, fontWeight = if (sel) FontWeight.SemiBold else FontWeight.Normal,
                    fontSize = 13.sp, maxLines = 1, textAlign = TextAlign.Center)
            }
        }
    }
}

/** 小标签 */
@Composable
fun Tag(text: String, color: Color = Palette.Accent, modifier: Modifier = Modifier) {
    Text(
        text, color = color, fontSize = 11.sp, maxLines = 1,
        modifier = modifier.clip(RoundedCornerShape(6.dp)).background(color.copy(alpha = 0.15f)).padding(horizontal = 6.dp, vertical = 2.dp),
    )
}

/** 统计格：每行两项 */
@Composable
fun StatGrid(items: List<Triple<String, String, Color?>>, modifier: Modifier = Modifier) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        items.chunked(2).forEach { row ->
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                row.forEach { (k, v, c) ->
                    Column(
                        Modifier.weight(1f).clip(RoundedCornerShape(10.dp)).background(Color(0x0FFFFFFF)).padding(horizontal = 10.dp, vertical = 8.dp),
                    ) {
                        Text(k, fontSize = 11.sp, color = Palette.Muted, maxLines = 1)
                        Text(v, fontWeight = FontWeight.SemiBold, fontSize = 14.sp, color = c ?: Palette.Text, maxLines = 2)
                    }
                }
                if (row.size == 1) Spacer(Modifier.weight(1f))
            }
        }
    }
}

/** 键值行 */
@Composable
fun KV(k: String, v: String, color: Color? = null) {
    Row(Modifier.fillMaxWidth().padding(vertical = 3.dp)) {
        Text(k, color = Palette.Muted, fontSize = 13.sp, modifier = Modifier.weight(1f))
        Text(v, fontSize = 13.sp, color = color ?: Palette.Text, fontWeight = FontWeight.Medium)
    }
}

/** 下拉选择（用稳定的 DropdownMenu 实现） */
@Composable
fun <T> SelectBox(label: String, value: T, options: List<T>, text: (T) -> String, modifier: Modifier = Modifier, onSelect: (T) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Box(modifier) {
        OutlinedButton(onClick = { open = true }, modifier = Modifier.fillMaxWidth(), contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp)) {
            Column(Modifier.weight(1f)) {
                Text(label, fontSize = 11.sp, color = Palette.Muted)
                Text(text(value), color = Palette.Text, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            Icon(Icons.Filled.ArrowDropDown, null)
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            options.forEach { o ->
                DropdownMenuItem(text = { Text(text(o)) }, onClick = { open = false; onSelect(o) })
            }
        }
    }
}

@Composable
fun EmptyHint(text: String, modifier: Modifier = Modifier) {
    Text(text, color = Palette.Muted, fontSize = 13.sp, modifier = modifier.fillMaxWidth().padding(vertical = 16.dp), textAlign = TextAlign.Center)
}

@Composable
fun Muted(text: String, modifier: Modifier = Modifier, size: Int = 12) {
    Text(text, color = Palette.Muted, fontSize = size.sp, modifier = modifier)
}
