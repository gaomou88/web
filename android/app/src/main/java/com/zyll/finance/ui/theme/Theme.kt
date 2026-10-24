package com.zyll.finance.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import com.zyll.finance.data.Zyll

/** 与网站一致的深色玻璃风配色 */
object Palette {
    val Bg = Color(0xFF0B1222)
    val Bg2 = Color(0xFF101A2E)
    val Glass = Color(0x1AFFFFFF)       // 卡片底色（白色 10%）
    val GlassBorder = Color(0x26FFFFFF)
    val Accent = Color(0xFF47C6C0)
    val Accent2 = Color(0xFF7FD8FF)
    val Gold = Color(0xFFF5B971)
    val Text = Color(0xFFE6EDF7)
    val Muted = Color(0xFF8C9AB3)
    val Red = Color(0xFFFF5D5D)
    val Green = Color(0xFF2FCF87)
    val Warn = Color(0xFFF5B971)
    val Series = listOf(Accent, Accent2, Gold, Color(0xFFC084FC), Color(0xFFF472B6), Color(0xFFA3E635), Color(0xFFFB923C), Color(0xFF60A5FA))
}

/** 涨跌配色（默认红涨绿跌，可在“我的”里切换） */
data class UpDown(val up: Color, val down: Color) {
    fun of(v: Double?): Color = when {
        v == null || v == 0.0 || v.isNaN() -> Palette.Text
        v > 0 -> up
        else -> down
    }
}

val LocalUpDown = staticCompositionLocalOf { UpDown(Palette.Red, Palette.Green) }

private val Scheme = darkColorScheme(
    primary = Palette.Accent,
    onPrimary = Color(0xFF04211F),
    secondary = Palette.Accent2,
    tertiary = Palette.Gold,
    background = Palette.Bg,
    onBackground = Palette.Text,
    surface = Palette.Bg2,
    onSurface = Palette.Text,
    surfaceVariant = Color(0xFF1A2640),
    onSurfaceVariant = Palette.Muted,
    surfaceContainer = Color(0xFF131E33),
    surfaceContainerHigh = Color(0xFF18243B),
    surfaceContainerHighest = Color(0xFF1E2B45),
    outline = Color(0xFF34435F),
    outlineVariant = Color(0xFF26324A),
    error = Palette.Red,
)

private val Type = Typography(
    titleLarge = TextStyle(fontSize = 20.sp, fontWeight = FontWeight.SemiBold),
    titleMedium = TextStyle(fontSize = 16.sp, fontWeight = FontWeight.SemiBold),
    titleSmall = TextStyle(fontSize = 14.sp, fontWeight = FontWeight.SemiBold),
    bodyLarge = TextStyle(fontSize = 15.sp),
    bodyMedium = TextStyle(fontSize = 14.sp),
    bodySmall = TextStyle(fontSize = 12.sp),
    labelSmall = TextStyle(fontSize = 11.sp),
)

@Composable
fun ZyllTheme(content: @Composable () -> Unit) {
    val redUp by Zyll.session.redUp.collectAsState()
    val ud = if (redUp) UpDown(Palette.Red, Palette.Green) else UpDown(Palette.Green, Palette.Red)
    MaterialTheme(colorScheme = Scheme, typography = Type) {
        CompositionLocalProvider(LocalUpDown provides ud, content = content)
    }
}
