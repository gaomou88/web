package com.zyll.finance

import android.app.Application
import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.zyll.finance.data.Zyll
import com.zyll.finance.ui.AppRoot
import com.zyll.finance.ui.theme.ZyllTheme
import kotlinx.coroutines.launch

class ZyllApp : Application() {
    override fun onCreate() {
        super.onCreate()
        Zyll.init(this)
    }
}

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            ZyllTheme {
                AppRoot()
            }
        }
        handleAuth(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleAuth(intent)
    }

    /** 网页登录授权后浏览器跳回来：zyllfinance://auth?code=…&state=… */
    private fun handleAuth(intent: Intent?) {
        val uri = intent?.data ?: return
        if (uri.scheme != "zyllfinance" || uri.host != "auth") return
        intent.setData(null)  // 屏幕旋转等重建时不要重复处理
        Zyll.scope.launch { Zyll.finishWebLogin(uri) }
    }

    /** 前台时连接实时推送，后台断开 */
    override fun onStart() {
        super.onStart()
        Zyll.live.start()
    }

    override fun onStop() {
        super.onStop()
        Zyll.live.stop()
    }
}
