package com.zyll.finance.data

import android.os.Build
import com.zyll.finance.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import okhttp3.Call
import okhttp3.Callback
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import java.io.IOException
import java.net.SocketTimeoutException
import java.net.URLEncoder
import java.net.UnknownHostException
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/** 接口错误。status = 0 表示网络问题（没连上服务器）。 */
class ApiException(val status: Int, val detail: String, val body: JSONObject? = null) : Exception(detail) {
    val membersOnly: Boolean get() = status == 403 && detail == "members_only"
    val tokenInvalid: Boolean get() = status == 401 && detail == "token_invalid"

    /** 给用户看的中文说明 */
    val friendly: String
        get() = when {
            tokenInvalid -> "登录已失效，请重新登录"
            status == 401 && detail == "app_key_invalid" -> "App Key 不正确，请在“我的 → 服务器设置”里检查"
            status == 403 && detail == "web_login_required" -> body?.str("message") ?: "请在网页中登录"
            membersOnly -> body?.str("notice") ?: "该内容仅会员可见"
            status == 404 && detail.contains("App 接口") -> "服务器未开启 App 接口，请联系管理员"
            status == 429 -> detail.ifBlank { "操作太频繁，请稍后再试" }
            status == 413 && body == null -> "文件太大：超过了服务器允许的上传大小"
            status == 0 -> detail
            status >= 500 -> "服务器出错了（$status），请稍后再试"
            else -> detail.ifBlank { "请求失败（$status）" }
        }
}

/**
 * 调用服务器的 /api/app/v1 接口。所有方法都是挂起函数，在 IO 线程执行。
 * 返回值是 org.json 的 JSONObject / JSONArray（或 null）。
 */
class Api(private val session: Session) {

    val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .pingInterval(20, TimeUnit.SECONDS)   // 只对 WebSocket 生效
        .retryOnConnectionFailure(true)
        .build()

    /** 收到 401 token_invalid 时回调（清除登录状态）。 */
    var onUnauthorized: (() -> Unit)? = null

    val baseUrl: String get() = session.serverUrl.value.trimEnd('/') + "/api/app/v1"

    private val jsonType = "application/json; charset=utf-8".toMediaType()

    fun deviceJson(): JSONObject = JSONObject()
        .put("id", session.deviceId)
        .put("name", listOf(Build.MANUFACTURER, Build.MODEL).filter { !it.isNullOrBlank() }.joinToString(" ").take(60))
        .put("os", "Android ${Build.VERSION.RELEASE}")
        .put("app_version", BuildConfig.VERSION_NAME)

    fun buildRequest(method: String, path: String, body: Any? = null, auth: Boolean = true): Request {
        val url = (baseUrl + path).toHttpUrlOrNull() ?: throw ApiException(0, "服务器地址不正确：${session.serverUrl.value}")
        val b = Request.Builder().url(url)
            .header("Accept", "application/json")
            .header("User-Agent", "ZyllApp/${BuildConfig.VERSION_NAME} (Android ${Build.VERSION.RELEASE})")
        session.appKey.takeIf { it.isNotBlank() }?.let { b.header("X-App-Key", it) }
        if (auth) session.token.value?.let { b.header("Authorization", "Bearer $it") }
        val rb = when (body) {
            null -> if (method == "GET" || method == "DELETE") null else "{}".toRequestBody(jsonType)
            is JSONObject, is JSONArray -> body.toString().toRequestBody(jsonType)
            else -> body.toString().toRequestBody(jsonType)
        }
        return b.method(method, rb).build()
    }

    suspend fun call(method: String, path: String, body: Any? = null, auth: Boolean = true): Any? {
        val req = buildRequest(method, path, body, auth)
        val resp = try {
            client.newCall(req).await()
        } catch (e: UnknownHostException) {
            throw ApiException(0, "找不到服务器，请检查网络或服务器地址")
        } catch (e: SocketTimeoutException) {
            throw ApiException(0, "连接服务器超时，请稍后再试")
        } catch (e: IOException) {
            throw ApiException(0, "网络连接失败：${e.message ?: e.javaClass.simpleName}")
        }
        return withContext(Dispatchers.IO) {
            resp.use { r ->
                val text = r.body?.string().orEmpty()
                val parsed: Any? = try { parse(text) } catch (_: JSONException) { null }
                if (!r.isSuccessful) {
                    val obj = parsed as? JSONObject
                    val detail = obj?.str("detail") ?: text.take(200)
                    val ex = ApiException(r.code, detail, obj)
                    if (ex.tokenInvalid) onUnauthorized?.invoke()
                    throw ex
                }
                if (parsed == null && text.isNotBlank()) throw ApiException(r.code, "服务器返回的数据无法解析（是否填错了服务器地址？）")
                parsed
            }
        }
    }

    /** 上传文件原始内容（AI 导入），body 直接是文件字节 */
    suspend fun upload(path: String, bytes: ByteArray, mime: String): Any? {
        val url = (baseUrl + path).toHttpUrlOrNull() ?: throw ApiException(0, "服务器地址不正确")
        val req = buildRequest("POST", path).newBuilder().url(url)
            .post(bytes.toRequestBody(mime.ifBlank { "application/octet-stream" }.toMediaType())).build()
        val resp = try {
            client.newCall(req).await()
        } catch (e: IOException) {
            throw ApiException(0, "上传失败：${e.message ?: e.javaClass.simpleName}")
        }
        return withContext(Dispatchers.IO) {
            resp.use { r ->
                val text = r.body?.string().orEmpty()
                val parsed: Any? = try { parse(text) } catch (_: JSONException) { null }
                if (!r.isSuccessful) {
                    val obj = parsed as? JSONObject
                    val ex = ApiException(r.code, obj?.str("detail") ?: text.take(200), obj)
                    if (ex.tokenInvalid) onUnauthorized?.invoke()
                    throw ex
                }
                parsed
            }
        }
    }

    suspend fun get(path: String, auth: Boolean = true) = call("GET", path, null, auth)
    suspend fun post(path: String, body: Any? = null, auth: Boolean = true) = call("POST", path, body, auth)
    suspend fun put(path: String, body: Any?) = call("PUT", path, body)
    suspend fun patch(path: String, body: Any?) = call("PATCH", path, body)
    suspend fun delete(path: String) = call("DELETE", path, null)

    suspend fun obj(path: String, auth: Boolean = true): JSONObject = get(path, auth) as? JSONObject ?: JSONObject()
    suspend fun arr(path: String): JSONArray = get(path) as? JSONArray ?: JSONArray()

    companion object {
        fun enc(s: String): String = URLEncoder.encode(s, "UTF-8")

        fun parse(text: String): Any? {
            val t = text.trim()
            if (t.isEmpty() || t == "null") return null
            return if (t.startsWith("[")) JSONArray(t) else JSONObject(t)
        }
    }
}

/** 把 OkHttp 的异步调用变成可取消的挂起函数 */
suspend fun Call.await(): Response = suspendCancellableCoroutine { cont ->
    enqueue(object : Callback {
        override fun onResponse(call: Call, response: Response) {
            cont.resume(response)
        }

        override fun onFailure(call: Call, e: IOException) {
            if (!cont.isCancelled) cont.resumeWithException(e)
        }
    })
    cont.invokeOnCancellation { runCatching { cancel() } }
}
