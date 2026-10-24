package com.zyll.finance.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.background
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.zyll.finance.ui.theme.Palette
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

enum class SeriesType { LINE, AREA, BAR }

/**
 * 图表的一条数据。values 与 labels 一一对应，null 表示该点没有数据。
 * barColor：柱状图按数值给颜色（例如正红负绿）。
 */
class ChartSeries(
    val name: String,
    val values: List<Double?>,
    val color: Color = Palette.Accent,
    val type: SeriesType = SeriesType.LINE,
    val dashed: Boolean = false,
    val width: Float = 2f,
    val barColor: ((Double) -> Color)? = null,
    /** 放到右侧坐标轴（双轴图，例如期货持仓与价格） */
    val rightAxis: Boolean = false,
)

/**
 * 可交互折线 / 柱状图：手指按住左右滑动显示十字线和数值（与网站悬停提示一致），点击也会选中最近的点。
 */
@Composable
fun InteractiveChart(
    labels: List<String>,
    series: List<ChartSeries>,
    modifier: Modifier = Modifier,
    height: Dp = 190.dp,
    zeroLine: Boolean = false,
    format: (Double) -> String = { com.zyll.finance.core.Fmt.num(it, 2) },
    formatRight: (Double) -> String = format,
    tipTitle: (Int) -> String = { labels.getOrElse(it) { "" } },
) {
    var sel by remember(labels.size, series.size) { mutableStateOf<Int?>(null) }
    val tm = rememberTextMeasurer()
    val n = labels.size
    val hasRightAxis = series.any { it.rightAxis }
    Column(modifier) {
        // 选中点的数值（代替浮动提示框，手机上不会被手指挡住）
        Row(Modifier.fillMaxWidth().height(20.dp), verticalAlignment = Alignment.CenterVertically) {
            val i = sel
            if (i != null && i in 0 until n) {
                Text(tipTitle(i), fontSize = 11.sp, color = Palette.Muted)
                Spacer(Modifier.width(8.dp))
                series.forEach { s ->
                    val v = s.values.getOrNull(i)
                    if (v != null) {
                        Box(Modifier.size(7.dp).background(s.barColor?.invoke(v) ?: s.color, CircleShape))
                        Spacer(Modifier.width(3.dp))
                        Text("${s.name} ${if (s.rightAxis) formatRight(v) else format(v)}", fontSize = 11.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
                        Spacer(Modifier.width(8.dp))
                    }
                }
            } else {
                // 图例
                series.forEach { s ->
                    Box(Modifier.size(7.dp).background(s.color, CircleShape))
                    Spacer(Modifier.width(3.dp))
                    Text(s.name, fontSize = 11.sp, color = Palette.Muted, maxLines = 1)
                    Spacer(Modifier.width(10.dp))
                }
            }
        }
        if (n == 0) {
            EmptyHint("暂无数据")
            return@Column
        }
        Canvas(
            Modifier
                .fillMaxWidth()
                .height(height)
                .pointerInput(n) {
                    detectTapGestures { p -> sel = indexAt(p.x, size.width.toFloat(), n, chartPads(density, hasRightAxis)) }
                }
                .pointerInput(n) {
                    detectHorizontalDragGestures(
                        onDragStart = { p -> sel = indexAt(p.x, size.width.toFloat(), n, chartPads(density, hasRightAxis)) },
                        onHorizontalDrag = { change, _ -> sel = indexAt(change.position.x, size.width.toFloat(), n, chartPads(density, hasRightAxis)) },
                    )
                },
        ) {
            val hasRight = series.any { it.rightAxis }
            val (leftPad, rightPad) = chartPads(density, hasRight)
            val topPad = 6f
            val bottomPad = 18f * density
            val w = size.width - leftPad - rightPad
            val h = size.height - topPad - bottomPad
            if (w <= 0 || h <= 0) return@Canvas

            fun range(list: List<ChartSeries>): Pair<Double, Double> {
                var lo = Double.POSITIVE_INFINITY; var hi = Double.NEGATIVE_INFINITY
                list.forEach { s -> s.values.forEach { v -> if (v != null) { lo = min(lo, v); hi = max(hi, v) } } }
                if (lo == Double.POSITIVE_INFINITY) return Pair(0.0, 1.0)
                val withZero = list.any { it.type == SeriesType.BAR } || zeroLine
                if (withZero) { lo = min(lo, 0.0); hi = max(hi, 0.0) }
                if (hi - lo < 1e-12) { val d = if (abs(hi) > 0) abs(hi) * 0.05 else 1.0; lo -= d; hi += d }
                val padv = (hi - lo) * 0.08
                return Pair(if (withZero && lo == 0.0) 0.0 else lo - padv, if (withZero && hi == 0.0) 0.0 else hi + padv)
            }
            val (lo, hi) = range(series.filter { !it.rightAxis })
            val (rlo, rhi) = if (hasRight) range(series.filter { it.rightAxis }) else Pair(0.0, 1.0)
            fun x(i: Int) = leftPad + if (n == 1) w / 2 else w * i / (n - 1).toFloat()
            fun y(v: Double, right: Boolean) = if (right) topPad + h * (1 - ((v - rlo) / (rhi - rlo))).toFloat() else topPad + h * (1 - ((v - lo) / (hi - lo))).toFloat()

            val grid = Color(0x1FFFFFFF)
            val label = TextStyle(color = Palette.Muted, fontSize = 10.sp)
            // 网格与左轴刻度
            for (k in 0..3) {
                val v = lo + (hi - lo) * k / 3
                val yy = y(v, false)
                drawLine(grid, Offset(leftPad, yy), Offset(leftPad + w, yy), 1f)
                val t = tm.measure(format(v), label)
                drawText(t, topLeft = Offset(max(0f, leftPad - t.size.width - 6f), yy - t.size.height / 2))
                if (hasRight) {
                    val rv = rlo + (rhi - rlo) * k / 3
                    val rt = tm.measure(formatRight(rv), label)
                    drawText(rt, topLeft = Offset(leftPad + w + 6f, yy - rt.size.height / 2))
                }
            }
            if (lo < 0 && hi > 0) drawLine(Color(0x55FFFFFF), Offset(leftPad, y(0.0, false)), Offset(leftPad + w, y(0.0, false)), 1.5f)
            // X 轴标签：首、中、尾
            val idx = listOf(0, n / 2, n - 1).distinct()
            idx.forEach { i ->
                val t = tm.measure(labels[i], label)
                val xx = (x(i) - t.size.width / 2).coerceIn(0f, size.width - t.size.width)
                drawText(t, topLeft = Offset(xx, topPad + h + 6f))
            }

            // 柱状
            val bars = series.filter { it.type == SeriesType.BAR }
            if (bars.isNotEmpty()) {
                val slot = if (n <= 1) w else w / (n - 1).toFloat()
                val bw = min(28f * density / 2.75f, slot * 0.7f / bars.size).coerceAtLeast(2f)
                bars.forEachIndexed { bi, s ->
                    s.values.forEachIndexed { i, v ->
                        if (v == null) return@forEachIndexed
                        val cx = x(i) + (bi - (bars.size - 1) / 2f) * bw
                        val y0 = y(0.0, s.rightAxis).coerceIn(topPad, topPad + h); val y1 = y(v, s.rightAxis)
                        drawRect(s.barColor?.invoke(v) ?: s.color, topLeft = Offset(cx - bw / 2, min(y0, y1)), size = Size(bw, max(1f, abs(y1 - y0))))
                    }
                }
            }
            // 折线 / 面积
            series.filter { it.type != SeriesType.BAR }.forEach { s ->
                val path = Path()
                var started = false
                var firstX = 0f; var lastX = 0f
                s.values.forEachIndexed { i, v ->
                    if (v == null) return@forEachIndexed
                    val px = x(i); val py = y(v, s.rightAxis)
                    if (!started) { path.moveTo(px, py); firstX = px; started = true } else path.lineTo(px, py)
                    lastX = px
                }
                if (!started) return@forEach
                if (s.type == SeriesType.AREA) {
                    val fill = Path().apply {
                        addPath(path)
                        lineTo(lastX, topPad + h); lineTo(firstX, topPad + h); close()
                    }
                    drawPath(fill, Brush.verticalGradient(listOf(s.color.copy(alpha = 0.35f), s.color.copy(alpha = 0.02f)), startY = topPad, endY = topPad + h))
                }
                drawPath(
                    path, s.color,
                    style = Stroke(width = s.width * density / 1.5f, cap = StrokeCap.Round,
                        pathEffect = if (s.dashed) PathEffect.dashPathEffect(floatArrayOf(14f, 10f)) else null),
                )
                if (s.values.count { it != null } == 1) {
                    val i = s.values.indexOfFirst { it != null }
                    drawCircle(s.color, 4f * density / 1.5f, Offset(x(i), y(s.values[i]!!, s.rightAxis)))
                }
            }
            // 十字线
            sel?.let { i ->
                if (i !in 0 until n) return@let
                val cx = x(i)
                drawLine(Color(0x88FFFFFF), Offset(cx, topPad), Offset(cx, topPad + h), 1.5f)
                series.filter { it.type != SeriesType.BAR }.forEach { s ->
                    s.values.getOrNull(i)?.let { v -> drawCircle(s.color, 5f * density / 1.5f, Offset(cx, y(v, s.rightAxis))) }
                }
            }
        }
    }
}

/** 图表左右留白（像素）：左侧放刻度文字，双轴图右侧也放 */
private fun chartPads(density: Float, hasRight: Boolean): Pair<Float, Float> {
    val left = 46f * density
    return Pair(left, if (hasRight) left else 4f * density)
}

private fun indexAt(px: Float, width: Float, n: Int, pads: Pair<Float, Float>): Int {
    if (n <= 1) return 0
    val w = (width - pads.first - pads.second).coerceAtLeast(1f)
    return ((px - pads.first) / w * (n - 1)).roundToInt().coerceIn(0, n - 1)
}

/** 迷你走势线（卡片右侧） */
@Composable
fun Sparkline(values: List<Double>, color: Color, modifier: Modifier = Modifier.size(width = 96.dp, height = 34.dp), baseline: Double? = null) {
    if (values.size < 2) {
        Spacer(modifier)
        return
    }
    Canvas(modifier) { drawSpark(values, color, baseline) }
}

private fun DrawScope.drawSpark(values: List<Double>, color: Color, baseline: Double?) {
    var lo = values.min(); var hi = values.max()
    if (baseline != null) { lo = min(lo, baseline); hi = max(hi, baseline) }
    if (hi - lo < 1e-12) { hi += 1; lo -= 1 }
    val w = size.width; val h = size.height
    fun x(i: Int) = w * i / (values.size - 1).toFloat()
    fun y(v: Double) = 2f + (h - 4f) * (1 - ((v - lo) / (hi - lo))).toFloat()
    val path = Path()
    values.forEachIndexed { i, v -> if (i == 0) path.moveTo(x(i), y(v)) else path.lineTo(x(i), y(v)) }
    val fill = Path().apply { addPath(path); lineTo(w, h); lineTo(0f, h); close() }
    drawPath(fill, Brush.verticalGradient(listOf(color.copy(alpha = 0.28f), Color.Transparent)))
    if (baseline != null) drawLine(Color(0x44FFFFFF), Offset(0f, y(baseline)), Offset(w, y(baseline)), 1f, pathEffect = PathEffect.dashPathEffect(floatArrayOf(6f, 6f)))
    drawPath(path, color, style = Stroke(width = 1.5f * density, cap = StrokeCap.Round))
}

/** 横向占比条 */
@Composable
fun RatioBar(fraction: Float, color: Color, modifier: Modifier = Modifier) {
    Canvas(modifier.height(8.dp)) {
        drawRoundRect(Color(0x1AFFFFFF), cornerRadius = androidx.compose.ui.geometry.CornerRadius(size.height / 2))
        drawRoundRect(color, size = Size(size.width * fraction.coerceIn(0f, 1f), size.height), cornerRadius = androidx.compose.ui.geometry.CornerRadius(size.height / 2))
    }
}

@Composable
fun Legend(items: List<Pair<String, Color>>) {
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
        items.forEach { (t, c) ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(8.dp).background(c, CircleShape))
                Spacer(Modifier.width(4.dp))
                Text(t, fontSize = 11.sp, color = Palette.Muted)
            }
        }
    }
}
