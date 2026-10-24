package com.zyll.finance.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class PkceTest {
    @Test
    fun rfc7636Example() {
        // RFC 7636 附录 B 的示例
        assertEquals("E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM", Pkce.challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"))
    }

    @Test
    fun base64UrlWithoutPadding() {
        assertEquals("", Pkce.b64url(ByteArray(0)))
        assertEquals("Zg", Pkce.b64url("f".toByteArray()))
        assertEquals("Zm8", Pkce.b64url("fo".toByteArray()))
        assertEquals("Zm9v", Pkce.b64url("foo".toByteArray()))
        assertEquals("-_8", Pkce.b64url(byteArrayOf(0xfb.toByte(), 0xff.toByte())))
        val v = Pkce.random()
        assertEquals(43, v.length)
        assertTrue(v.matches(Regex("^[A-Za-z0-9_-]+$")))
    }
}
