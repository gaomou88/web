package com.zyll.finance.core

import java.security.MessageDigest
import java.security.SecureRandom

/**
 * 网页登录用的 PKCE（RFC 7636，S256）：
 * App 生成随机 verifier，只把它的 SHA-256（challenge）交给网页；网页登录授权后把一次性授权码带回 App，
 * App 再用 verifier 去换令牌。授权码即使被别的应用截获，没有 verifier 也换不到令牌。
 */
object Pkce {
    private val rnd = SecureRandom()
    private const val ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"

    /** base64url，无填充（不依赖 java.util.Base64，Android 7 也能用） */
    fun b64url(data: ByteArray): String {
        val sb = StringBuilder((data.size * 4 + 2) / 3)
        var i = 0
        while (i < data.size) {
            val b0 = data[i].toInt() and 0xff
            val b1 = if (i + 1 < data.size) data[i + 1].toInt() and 0xff else -1
            val b2 = if (i + 2 < data.size) data[i + 2].toInt() and 0xff else -1
            sb.append(ALPHABET[b0 shr 2])
            sb.append(ALPHABET[((b0 and 3) shl 4) or (if (b1 >= 0) b1 shr 4 else 0)])
            if (b1 >= 0) sb.append(ALPHABET[((b1 and 15) shl 2) or (if (b2 >= 0) b2 shr 6 else 0)])
            if (b2 >= 0) sb.append(ALPHABET[b2 and 63])
            i += 3
        }
        return sb.toString()
    }

    fun random(bytes: Int = 32): String = ByteArray(bytes).also { rnd.nextBytes(it) }.let { b64url(it) }

    fun challenge(verifier: String): String = b64url(MessageDigest.getInstance("SHA-256").digest(verifier.toByteArray(Charsets.US_ASCII)))
}
