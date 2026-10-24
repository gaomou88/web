package com.zyll.finance.data

import android.os.Handler
import android.os.Looper
import android.util.Log
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.min

/** 一条实时推送：topic 见接口文档（ticks / snap / indices / rank / calendar / fx / futures ...） */
class LiveEvent(val topic: String, val data: Any?)

/**
 * 实时推送（WebSocket /api/app/v1/ws）。
 * App 在前台时连接（MainActivity.onStart），切到后台断开以省电省流量；断线后自动重连（1s → 30s 退避）。
 */
class Live(private val api: Api) {
    private val _events = MutableSharedFlow<LiveEvent>(extraBufferCapacity = 256, onBufferOverflow = BufferOverflow.DROP_OLDEST)
    val events: SharedFlow<LiveEvent> = _events

    private val _connected = MutableStateFlow(false)
    val connected: StateFlow<Boolean> = _connected

    private val main = Handler(Looper.getMainLooper())
    private var ws: WebSocket? = null
    private var wanted = false
    private var attempt = 0
    private var generation = 0
    private val topics = listOf("ticks", "snap", "indices", "rank", "calendar", "fx", "futures", "holidays", "finra_daily", "finra_ats", "cftc")

    private val reconnect = Runnable { if (wanted) open() }

    @Synchronized
    fun start() {
        if (wanted && ws != null) return
        wanted = true
        attempt = 0
        main.removeCallbacks(reconnect)
        open()
    }

    @Synchronized
    fun stop() {
        wanted = false
        main.removeCallbacks(reconnect)
        generation++
        ws?.close(1000, "background")
        ws = null
        _connected.value = false
    }

    /** 服务器地址或登录状态变了：断开重连 */
    fun restart() {
        stop()
        start()
    }

    @Synchronized
    private fun open() {
        val gen = ++generation
        ws?.cancel()
        val url = api.baseUrl.replaceFirst(Regex("^http"), "ws") + "/ws"
        val req = try {
            api.buildRequest("GET", "/ws").newBuilder().url(url).build()
        } catch (e: Exception) {
            Log.w("Zyll", "实时推送地址无效：$url", e)
            return
        }
        ws = api.client.newWebSocket(req, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                if (gen != generation) return
                attempt = 0
                _connected.value = true
                webSocket.send(JSONObject().put("op", "subscribe").put("topics", JSONArray(topics)).toString())
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                if (gen != generation) return
                try {
                    val o = JSONObject(text)
                    val topic = o.optString("topic")
                    if (topic.isEmpty() || topic.startsWith("_")) return
                    _events.tryEmit(LiveEvent(topic, o.opt("data")))
                } catch (e: Exception) {
                    Log.w("Zyll", "推送消息解析失败", e)
                }
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) = scheduleRetry(gen)

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) = scheduleRetry(gen)
        })
    }

    private fun scheduleRetry(gen: Int) {
        synchronized(this) {
            if (gen != generation) return
            _connected.value = false
            ws = null
            if (!wanted) return
            attempt++
            val delay = min(30_000L, 1000L shl min(attempt, 5))
            main.removeCallbacks(reconnect)
            main.postDelayed(reconnect, delay)
        }
    }
}
