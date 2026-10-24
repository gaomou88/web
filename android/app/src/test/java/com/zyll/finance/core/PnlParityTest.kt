package com.zyll.finance.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.abs
import kotlin.math.max

/**
 * 与服务器 / 网页算法的一致性测试：pnl_cases.json 是用后端 pnl.py 随机生成的 300 组用例和结果，
 * 网页的 pnl.js 也用同一份用例测试过。三端结果必须一致。
 */
class PnlParityTest {

    @Test
    fun matchesServerResults() {
        val text = javaClass.classLoader!!.getResourceAsStream("pnl_cases.json")!!.reader(Charsets.UTF_8).readText()
        @Suppress("UNCHECKED_CAST")
        val cases = MiniJson.parse(text) as List<Map<String, Any?>>
        assertTrue(cases.size >= 100)
        var checked = 0
        for ((i, c) in cases.withIndex()) {
            val trades = (c["trades"] as List<*>).map { it as Map<*, *> }.map {
                Trade(
                    id = (it["id"] as Number).toLong(), symbol = "T", side = it["side"] as String, tradeDate = it["trade_date"] as String,
                    shares = (it["shares"] as Number).toDouble(), price = (it["price"] as Number).toDouble(),
                    ccy = it["ccy"] as String?, fx = (it["fx"] as Number).toDouble(), fee = (it["fee"] as Number?)?.toDouble() ?: 0.0,
                    funding = it["funding"] as String? ?: "ccy",
                )
            }
            val moves = (c["moves"] as List<*>).map { it as Map<*, *> }.mapIndexed { j, it ->
                CashMove(j.toLong(), "g$j", "deposit", it["trade_date"] as String, it["ccy"] as String, (it["amount"] as Number).toDouble())
            }
            val q = c["q"] as Map<*, *>
            val quote = Quote((q["price"] as Number?)?.toDouble(), (q["prev_close"] as Number?)?.toDouble())
            val cpi = (c["cpi"] as Map<*, *>?)?.entries?.associate { (k, v) ->
                k as String to ((v as Map<*, *>)["table"] as List<*>).map { row -> (row as List<*>)[0] as String to (row[1] as Number).toDouble() }
            }
            val res = Pnl.computeSymbol(trades, quote, rates(c["now"]), rates(c["prev"]), c["mode"] as String, c["base"] as String, "2026-10-20",
                deflate = cpi?.let { Pnl.deflator(it, "2026-10-22") })
            @Suppress("UNCHECKED_CAST")
            val py = c["py"] as Map<String, Any?>
            val mine = mapOf(
                "qty" to res.qty, "costBase" to res.costBase, "costReal" to res.costReal, "realized" to res.realized, "realizedPrice" to res.realizedPrice,
                "mvBase" to res.mvBase, "unreal" to res.unreal, "unrealPrice" to res.unrealPrice, "unrealFx" to res.unrealFx,
                "today" to res.today, "todayPrice" to res.todayPrice, "todayFx" to res.todayFx,
            )
            for ((k, v) in py) {
                val expected = (v as Number?)?.toDouble()
                val actual = mine[k]
                if (expected == null) {
                    assertEquals("case $i $k", null, actual)
                } else {
                    assertTrue("case $i $k: expected $expected got $actual", actual != null && close(expected, actual))
                }
                checked++
            }
            @Suppress("UNCHECKED_CAST")
            val pyCash = (c["pycash"] as Map<String, Any?>).mapValues { (it.value as Number).toDouble() }
            val cash = Pnl.cashBalances(trades, moves, c["base"] as String)
            assertEquals("case $i cash keys", pyCash.keys, cash.keys)
            for ((k, v) in pyCash) assertTrue("case $i cash $k", close(v, cash[k]!!))
        }
        assertTrue(checked > 1000)
    }

    @Test
    fun cpiInterpolationMatchesServer() {
        val text = javaClass.classLoader!!.getResourceAsStream("cpi_cases.json")!!.reader(Charsets.UTF_8).readText()
        val c = MiniJson.parse(text) as Map<*, *>
        val table = (c["table"] as List<*>).map { val r = it as List<*>; r[0] as String to (r[1] as Number).toDouble() }
        for (f in c["factors"] as List<*>) {
            val r = f as List<*>
            val got = Pnl.cpiFactor(table, r[0] as String, r[1] as String)
            assertTrue("cpi ${r[0]} ${r[1]}: $got vs ${r[2]}", close((r[2] as Number).toDouble(), got))
        }
        // 7 月花 7000，物价涨 3%：市值不变时扣除通胀后亏 210
        val t = listOf(listOf("2026-07" to 100.0, "2026-08" to 101.0, "2026-09" to 102.0, "2026-10" to 103.0)).first()
        val p = Pnl.computePosition(listOf(Trade(1, "A", "buy", "2026-07-15", 10.0, 100.0, "CNY", 7.0)), Quote(100.0, 100.0), 7.0, 7.0, "2026-10-15",
            deflate = { d -> Pnl.cpiFactor(t, d, "2026-10-15") })
        assertEquals(7210.0, p.costReal, 1e-9)
        assertEquals(-210.0, p.unreal!!, 1e-9)
    }

    @Test
    fun capitalPercentagesUseGrossAssets() {
        val rates = mapOf("CNY" to Rate(1.0, 1.0), "USD" to Rate(7.0, 7.0), "HKD" to Rate(0.9, 0.9))
        val moves = listOf(
            CashMove(1, "a", "deposit", "2026-01-01", "CNY", 7000.0),
            CashMove(2, "b", "deposit", "2026-01-01", "HKD", -900.0),
        )
        val cap = Pnl.capital(emptyList(), moves, rates, "CNY", "mid", 3000.0)
        assertEquals(10000.0, cap.gross, 1e-6)
        assertEquals(9190.0, cap.net, 1e-6)
        assertEquals(70.0, cap.items.first { it.ccy == "CNY" }.pct!!, 1e-6)
        assertEquals(1, cap.negative.size)
        assertEquals(null, cap.negative[0].pct)
    }

    @Test
    fun usdFundedTradesDrawFromUsdCash() {
        val trades = listOf(
            Trade(1, "AAPL", "buy", "2026-10-02", 10.0, 100.0, "CNY", 7.1, 1.0, funding = "usd"),
            Trade(2, "AAPL", "buy", "2026-10-03", 5.0, 100.0, "CNY", 7.2, 0.0),
        )
        val moves = listOf(
            CashMove(1, "a", "fx", "2026-10-01", "CNY", -7100.0),
            CashMove(2, "a", "fx", "2026-10-01", "USD", 1000.0),
        )
        val cash = Pnl.cashBalances(trades, moves, "CNY")
        assertEquals(-1.0, cash["USD"]!!, 1e-9)              // 1000 − (10×100 + 1)
        assertEquals(-7100.0 - 3600.0, cash["CNY"]!!, 1e-9)  // 第二笔按 7.2 当场换汇
    }

    @Test
    fun formatHelpers() {
        assertEquals("+1,234.50", Fmt.signed(1234.5))
        assertEquals("−¥12.00", Fmt.signedMoney(-12.0, "CNY"))
        assertEquals("1.50亿", Fmt.compact(1.5e8))
        assertEquals("2.30万", Fmt.compact(23000.0))
        assertEquals(4.6, Fmt.parseEconNumber("4.6%")!!, 1e-9)
        assertEquals(-0.2, Fmt.parseEconNumber("-0.2K")!!, 1e-9)
        assertEquals(null, Fmt.parseEconNumber(""))
    }

    private fun close(a: Double, b: Double) = abs(a - b) <= 1e-6 * max(1.0, abs(a))

    private fun rates(v: Any?): Map<String, Rate>? = (v as Map<*, *>?)?.entries?.associate { (k, r) ->
        r as Map<*, *>
        k as String to Rate((r["bid"] as Number).toDouble(), (r["ask"] as Number).toDouble())
    }
}

/** 测试用的极简 JSON 解析器（JVM 单元测试里 Android 的 org.json 不可用）。 */
object MiniJson {
    fun parse(s: String): Any? = P(s).run { val v = value(); ws(); v }

    private class P(val s: String) {
        var i = 0
        fun ws() { while (i < s.length && s[i].isWhitespace()) i++ }
        fun value(): Any? {
            ws()
            return when (val c = s[i]) {
                '{' -> obj()
                '[' -> arr()
                '"' -> str()
                't' -> { i += 4; true }
                'f' -> { i += 5; false }
                'n' -> { i += 4; null }
                else -> if (c == '-' || c.isDigit()) num() else error("bad json at $i")
            }
        }
        fun obj(): Map<String, Any?> {
            val m = LinkedHashMap<String, Any?>(); i++; ws()
            if (s[i] == '}') { i++; return m }
            while (true) {
                ws(); val k = str(); ws(); i++ // ':'
                m[k] = value(); ws()
                if (s[i++] == '}') return m
            }
        }
        fun arr(): List<Any?> {
            val l = ArrayList<Any?>(); i++; ws()
            if (s[i] == ']') { i++; return l }
            while (true) {
                l.add(value()); ws()
                if (s[i++] == ']') return l
            }
        }
        fun str(): String {
            val sb = StringBuilder(); i++
            while (s[i] != '"') {
                if (s[i] == '\\') {
                    i++
                    when (s[i]) {
                        'n' -> sb.append('\n'); 't' -> sb.append('\t'); 'r' -> sb.append('\r'); 'b' -> sb.append('\b'); 'f' -> sb.append('\u000c')
                        'u' -> { sb.append(s.substring(i + 1, i + 5).toInt(16).toChar()); i += 4 }
                        else -> sb.append(s[i])
                    }
                } else sb.append(s[i])
                i++
            }
            i++
            return sb.toString()
        }
        fun num(): Double {
            val st = i
            while (i < s.length && (s[i].isDigit() || s[i] in "+-.eE")) i++
            return s.substring(st, i).toDouble()
        }
    }
}
