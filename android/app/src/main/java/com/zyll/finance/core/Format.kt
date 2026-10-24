package com.zyll.finance.core

import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import kotlin.math.abs
import kotlin.math.roundToLong

/** 数字、金额、日期格式化（不依赖 Android，可单元测试）。 */
object Fmt {
    private val CCY_SYMBOL = mapOf(
        "CNY" to "¥", "USD" to "$", "HKD" to "HK$", "EUR" to "€", "GBP" to "£", "JPY" to "JP¥",
        "SGD" to "S$", "AUD" to "A$", "CAD" to "C$", "CHF" to "CHF ", "MYR" to "RM",
    )
    private val CCY_ZH = mapOf(
        "CNY" to "人民币", "USD" to "美元", "HKD" to "港币", "EUR" to "欧元", "GBP" to "英镑", "JPY" to "日元",
        "SGD" to "新加坡元", "AUD" to "澳元", "CAD" to "加元", "CHF" to "瑞士法郎", "MYR" to "马来西亚林吉特",
        "NZD" to "新西兰元", "KRW" to "韩元", "THB" to "泰铢", "RUB" to "卢布",
    )

    fun ccySymbol(c: String) = CCY_SYMBOL[c] ?: "$c "
    fun ccyLabel(c: String) = CCY_ZH[c]?.let { "$it $c" } ?: c

    /** 千分位 + 固定小数位；null / NaN 显示 “—”。 */
    fun num(v: Double?, digits: Int = 2): String {
        if (v == null || v.isNaN() || v.isInfinite()) return "—"
        return String.format(Locale.US, "%,.${digits}f", v)
    }

    fun signed(v: Double?, digits: Int = 2, suffix: String = ""): String {
        if (v == null || v.isNaN() || v.isInfinite()) return "—"
        val s = num(abs(v), digits)
        return (if (v > 0) "+" else if (v < 0) "−" else "") + s + suffix
    }

    fun pct(v: Double?, digits: Int = 2) = signed(v, digits, "%")

    /** 比例 0.53 → “53.0%” */
    fun ratio(v: Double?, digits: Int = 1) = if (v == null) "—" else num(v * 100, digits) + "%"

    fun money(v: Double?, ccy: String, digits: Int = 2): String =
        if (v == null || v.isNaN()) "—" else (if (v < 0) "−" else "") + ccySymbol(ccy) + num(abs(v), digits)

    fun signedMoney(v: Double?, ccy: String, digits: Int = 2): String =
        if (v == null || v.isNaN()) "—" else (if (v > 0) "+" else if (v < 0) "−" else "") + ccySymbol(ccy) + num(abs(v), digits)

    /** 大数：1.23万 / 4.56亿 / 7.89万亿 */
    fun compact(v: Double?): String {
        if (v == null || v.isNaN()) return "—"
        val a = abs(v)
        val sign = if (v < 0) "−" else ""
        return sign + when {
            a >= 1e12 -> num(a / 1e12, 2) + "万亿"
            a >= 1e8 -> num(a / 1e8, 2) + "亿"
            a >= 1e4 -> num(a / 1e4, 2) + "万"
            a == a.roundToLong().toDouble() -> num(a, 0)
            else -> num(a, 2)
        }
    }

    /** 价格：小于 1 显示 4 位小数 */
    fun price(v: Double?) = if (v != null && abs(v) < 1 && v != 0.0) num(v, 4) else num(v, 2)

    private fun fmt(pattern: String, tz: TimeZone = TimeZone.getDefault()) = SimpleDateFormat(pattern, Locale.CHINA).apply { timeZone = tz }

    fun dateTime(tsSec: Long?): String = if (tsSec == null || tsSec <= 0) "—" else fmt("yyyy-MM-dd HH:mm").format(Date(tsSec * 1000))
    fun date(tsSec: Long?): String = if (tsSec == null || tsSec <= 0) "—" else fmt("yyyy-MM-dd").format(Date(tsSec * 1000))
    fun time(tsSec: Long?): String = if (tsSec == null || tsSec <= 0) "—" else fmt("HH:mm").format(Date(tsSec * 1000))

    /** 本地日期键 yyyy-MM-dd，用于日历分组 */
    fun dayKey(tsSec: Long): String = fmt("yyyy-MM-dd").format(Date(tsSec * 1000))

    private val WEEK = arrayOf("周日", "周一", "周二", "周三", "周四", "周五", "周六")

    /** “10月22日 周四” */
    fun dayTitle(dayKey: String): String {
        val d = fmt("yyyy-MM-dd").parse(dayKey) ?: return dayKey
        val c = Calendar.getInstance().apply { time = d }
        return "${c.get(Calendar.MONTH) + 1}月${c.get(Calendar.DAY_OF_MONTH)}日 ${WEEK[c.get(Calendar.DAY_OF_WEEK) - 1]}"
    }

    fun today(): String = fmt("yyyy-MM-dd").format(Date())

    /** 美东时间的今天（交易记录默认日期） */
    fun todayNewYork(): String = fmt("yyyy-MM-dd", TimeZone.getTimeZone("America/New_York")).format(Date())

    /** “3 分钟前” */
    fun ago(tsSec: Double?, nowSec: Double = System.currentTimeMillis() / 1000.0): String {
        if (tsSec == null || tsSec <= 0) return "—"
        val d = (nowSec - tsSec).toLong()
        return when {
            d < 60 -> "刚刚"
            d < 3600 -> "${d / 60} 分钟前"
            d < 86400 -> "${d / 3600} 小时前"
            else -> date(tsSec.toLong())
        }
    }

    /** 解析 “4.6%”、“-0.2K”、“1.2M” 这类经济数据数值 */
    fun parseEconNumber(s: String?): Double? {
        if (s.isNullOrBlank()) return null
        val m = Regex("""^\s*([<>]?)\s*(-?[\d,]*\.?\d+)\s*([%KMBT]?)""", RegexOption.IGNORE_CASE).find(s) ?: return null
        return m.groupValues[2].replace(",", "").toDoubleOrNull()
    }
}
