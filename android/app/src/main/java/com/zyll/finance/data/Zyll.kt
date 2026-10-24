package com.zyll.finance.data

import android.content.Context
import android.content.Intent
import android.net.Uri
import com.zyll.finance.BuildConfig
import com.zyll.finance.core.Pkce
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import org.json.JSONObject

/**
 * 全局状态：服务器配置、当前用户、登录 / 注册 / 退出、版本检查。
 * 在 ZyllApp.onCreate 里初始化，界面通过 StateFlow 观察。
 */
object Zyll {
    lateinit var session: Session
        private set
    lateinit var api: Api
        private set
    lateinit var live: Live
        private set

    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)

    private val _config = MutableStateFlow<SiteConfig?>(null)
    val config: StateFlow<SiteConfig?> = _config

    private val _me = MutableStateFlow<Me?>(null)
    val me: StateFlow<Me?> = _me

    private val _version = MutableStateFlow<VersionInfo?>(null)
    val version: StateFlow<VersionInfo?> = _version

    /** 用户手动“检查更新”时递增：即使之前点过“以后再说”也再次提示 */
    val updatePrompt = MutableStateFlow(0)

    /** 自选 / 行情里的“我的个股”被修改后递增，其他页面据此刷新 */
    val listsVersion = MutableStateFlow(0)

    fun init(context: Context) {
        session = Session(context)
        api = Api(session)
        live = Live(api)
        api.onUnauthorized = { scope.launch { logoutLocal() } }
    }

    val membershipEnabled: Boolean get() = _config.value?.membershipEnabled == true

    /** 启动时 / 切换服务器后调用 */
    suspend fun bootstrap() {
        runCatching { _config.value = SiteConfig.parse(api.obj("/meta/config")) }
        if (session.isLoggedIn) refreshMe()
        checkVersion()
    }

    suspend fun refreshMe() {
        if (!session.isLoggedIn) { _me.value = null; return }
        try {
            _me.value = Me.parse(api.obj("/auth/me"))
        } catch (e: ApiException) {
            if (e.tokenInvalid) logoutLocal()
        }
    }

    suspend fun checkVersion(): VersionInfo? = runCatching {
        VersionInfo.parse(api.obj("/meta/version?version_code=${BuildConfig.VERSION_CODE}", auth = false))
    }.getOrNull()?.also { _version.value = it }

    private fun authBody(email: String, password: String) =
        JSONObject().put("email", email.trim()).put("password", password).put("device", api.deviceJson())

    /** 登录成功返回 null；需要验证邮箱等情况返回提示语 */
    suspend fun login(email: String, password: String): String? = afterAuth(api.post("/auth/login", authBody(email, password), auth = false) as? JSONObject, email)

    suspend fun register(email: String, password: String): String? = afterAuth(api.post("/auth/register", authBody(email, password), auth = false) as? JSONObject, email)

    private suspend fun afterAuth(o: JSONObject?, email: String): String? {
        if (o == null) return "服务器没有返回数据"
        if (o.optBoolean("verify_required")) return "注册成功！请先打开邮箱里的验证链接，然后再登录。"
        val token = o.s("token")
        if (token.isBlank()) return "服务器没有返回登录令牌"
        session.saveToken(token, email.trim())
        _me.value = Me.parse(o)
        listsVersion.value++
        live.restart()
        return null
    }

    /** 给界面的一次性提示（例如网页登录完成 / 失败） */
    val notice = MutableStateFlow<String?>(null)

    /** 在浏览器里打开本站的某个页面，例如 "/#/forgot" */
    fun openWeb(ctx: Context, path: String): Boolean = try {
        ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(session.serverUrl.value.trimEnd('/') + path)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        true
    } catch (_: Exception) {
        notice.value = "没有可以打开网页的应用"
        false
    }

    /**
     * 网页登录：生成 PKCE 参数，打开本站的授权页。用户在网页登录（有人机验证、找回密码）并点“授权登录”后，
     * 网页跳转 zyllfinance://auth?code=…&state=…，由 MainActivity 交给 [finishWebLogin]。
     */
    fun startWebLogin(ctx: Context): Boolean {
        val verifier = Pkce.random(48)
        val state = Pkce.random(16)
        session.savePending(verifier, state)
        val path = (config.value?.webAuthPath ?: "/#/app-auth")
        val device = api.deviceJson().optString("name").ifBlank { "Android" }
        return openWeb(ctx, "$path?challenge=${Pkce.challenge(verifier)}&state=$state&device=${Api.enc(device)}")
    }

    /** 处理 zyllfinance://auth 回调。返回 true 表示已登录。 */
    suspend fun finishWebLogin(uri: Uri): Boolean {
        val pending = session.takePending()
        if (uri.getQueryParameter("error") != null) {
            notice.value = "已取消登录"
            return false
        }
        val code = uri.getQueryParameter("code")
        val state = uri.getQueryParameter("state")
        if (pending == null || code.isNullOrBlank() || state != pending.second) {
            notice.value = "登录已过期，请重新点击“登录”"
            return false
        }
        return try {
            val o = api.post("/auth/exchange", JSONObject().put("code", code).put("verifier", pending.first).put("device", api.deviceJson()), auth = false) as? JSONObject
            val token = o?.str("token")
            if (token == null) {
                notice.value = "登录失败，请重试"
                false
            } else {
                session.saveToken(token, Me.parse(o).email)
                _me.value = Me.parse(o)
                listsVersion.value++
                live.restart()
                notice.value = "登录成功"
                true
            }
        } catch (e: ApiException) {
            notice.value = e.friendly
            false
        }
    }

    val webLoginRequired: Boolean get() = config.value?.loginMode == "web"
    val webRegisterRequired: Boolean get() = config.value?.registerMode == "web"

    suspend fun logout() {
        runCatching { api.post("/auth/logout") }
        logoutLocal()
    }

    fun logoutLocal() {
        session.clearToken()
        _me.value = null
        listsVersion.value++
    }

    suspend fun changePassword(old: String, new: String) {
        val o = api.post("/auth/password", JSONObject().put("old_password", old).put("new_password", new)) as? JSONObject
        o?.str("token")?.let { session.saveToken(it, session.email) }
    }

    suspend fun redeem(code: String): JSONObject {
        val o = api.post("/member/redeem", JSONObject().put("code", code)) as? JSONObject ?: JSONObject()
        refreshMe()
        return o
    }

    /** 修改服务器地址后：清空登录（令牌只对原服务器有效）、重新拉取配置 */
    suspend fun switchServer(url: String, appKey: String) {
        val changed = url.trim().trimEnd('/') != session.serverUrl.value
        session.setServerUrl(url)
        session.appKey = appKey
        if (changed) logoutLocal()
        _config.value = null
        live.restart()
        bootstrap()
    }
}
