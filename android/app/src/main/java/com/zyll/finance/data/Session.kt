package com.zyll.finance.data

import android.annotation.SuppressLint
import android.content.Context
import android.content.SharedPreferences
import android.provider.Settings
import android.util.Log
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKeys
import com.zyll.finance.BuildConfig
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import java.util.UUID

/**
 * 本地保存的登录状态与 App 设置。
 * - 登录令牌放在 EncryptedSharedPreferences（Android Keystore 加密）；个别机型 Keystore 异常时退回普通存储。
 * - 服务器地址默认取编译时的 BuildConfig.SERVER_URL，可在“我的 → 服务器设置”里修改。
 */
class Session(context: Context) {
    private val ctx = context.applicationContext
    private val plain: SharedPreferences = ctx.getSharedPreferences("zyll", Context.MODE_PRIVATE)
    private val secure: SharedPreferences = try {
        EncryptedSharedPreferences.create(
            "zyll_secure",
            MasterKeys.getOrCreate(MasterKeys.AES256_GCM_SPEC),
            ctx,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    } catch (e: Exception) {
        Log.w("Zyll", "加密存储不可用，改用普通存储", e)
        plain
    }

    private val _token = MutableStateFlow(secure.getString(K_TOKEN, null))
    /** 当前令牌；为 null 表示未登录。界面根据它切换登录状态。 */
    val token: StateFlow<String?> = _token

    private val _serverUrl = MutableStateFlow(plain.getString(K_SERVER, null)?.takeIf { it.isNotBlank() } ?: BuildConfig.SERVER_URL)
    val serverUrl: StateFlow<String> = _serverUrl

    private val _redUp = MutableStateFlow(plain.getBoolean(K_RED_UP, true))
    /** true = 红涨绿跌（默认，与网站一致）；false = 绿涨红跌 */
    val redUp: StateFlow<Boolean> = _redUp

    val isLoggedIn: Boolean get() = _token.value != null

    var email: String?
        get() = secure.getString(K_EMAIL, null)
        set(v) { secure.edit().putString(K_EMAIL, v).apply() }

    var appKey: String
        get() = plain.getString(K_APP_KEY, null) ?: BuildConfig.APP_KEY
        set(v) { plain.edit().putString(K_APP_KEY, v.trim()).apply() }

    fun saveToken(token: String, email: String?) {
        secure.edit().putString(K_TOKEN, token).putString(K_EMAIL, email).apply()
        _token.value = token
    }

    fun clearToken() {
        secure.edit().remove(K_TOKEN).apply()
        _token.value = null
    }

    fun setServerUrl(url: String) {
        val u = url.trim().trimEnd('/')
        plain.edit().putString(K_SERVER, u).apply()
        _serverUrl.value = u.ifBlank { BuildConfig.SERVER_URL }
    }

    fun resetServerUrl() {
        plain.edit().remove(K_SERVER).remove(K_APP_KEY).apply()
        _serverUrl.value = BuildConfig.SERVER_URL
    }

    fun setRedUp(v: Boolean) {
        plain.edit().putBoolean(K_RED_UP, v).apply()
        _redUp.value = v
    }

    /** 设备唯一 ID：服务器用它区分设备（同一设备重新登录会作废旧令牌）。 */
    @SuppressLint("HardwareIds")
    val deviceId: String by lazy {
        val id = try { Settings.Secure.getString(ctx.contentResolver, Settings.Secure.ANDROID_ID) } catch (_: Exception) { null }
        if (!id.isNullOrBlank() && id != "9774d56d682e549c") return@lazy "a-$id"
        plain.getString(K_DEVICE, null) ?: ("r-" + UUID.randomUUID().toString()).also { plain.edit().putString(K_DEVICE, it).apply() }
    }

    /** 网页登录进行中：保存 PKCE 的 verifier 和 state（App 被系统回收后回来也能完成登录） */
    fun savePending(verifier: String, state: String) {
        secure.edit().putString(K_PKCE_V, verifier).putString(K_PKCE_S, state).putString(K_PKCE_T, (System.currentTimeMillis() / 1000).toString()).apply()
    }

    /** 取出并清除；超过 10 分钟的作废 */
    fun takePending(): Pair<String, String>? {
        val v = secure.getString(K_PKCE_V, null)
        val st = secure.getString(K_PKCE_S, null)
        val t = secure.getString(K_PKCE_T, null)?.toLongOrNull() ?: 0
        secure.edit().remove(K_PKCE_V).remove(K_PKCE_S).remove(K_PKCE_T).apply()
        if (v == null || st == null || System.currentTimeMillis() / 1000 - t > 600) return null
        return v to st
    }

    /** 上次提示过的新版本（用户点了“以后再说”就不再弹，强制更新除外） */
    var skippedVersion: Int
        get() = plain.getInt(K_SKIP, 0)
        set(v) { plain.edit().putInt(K_SKIP, v).apply() }

    /** 日历筛选等小设置 */
    fun getString(key: String, def: String): String = plain.getString("ui_$key", def) ?: def
    fun putString(key: String, v: String) = plain.edit().putString("ui_$key", v).apply()

    companion object {
        private const val K_TOKEN = "token"
        private const val K_EMAIL = "email"
        private const val K_SERVER = "server_url"
        private const val K_APP_KEY = "app_key"
        private const val K_RED_UP = "red_up"
        private const val K_DEVICE = "device_id"
        private const val K_SKIP = "skip_version"
        private const val K_PKCE_V = "pkce_verifier"
        private const val K_PKCE_S = "pkce_state"
        private const val K_PKCE_T = "pkce_time"
    }
}
