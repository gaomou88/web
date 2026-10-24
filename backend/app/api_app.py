"""安卓 App 接口（/api/app/v1）。

设计：
- 认证用 Bearer Token（Authorization: Bearer zyt_xxx），登录时下发，数据库只存哈希；每台设备一个令牌，可在 App 或后台撤销；
- App 路径下忽略 Cookie（因此不受浏览器跨站请求伪造影响，也无需 CSRF 头）；
- 账号 / 设备 / 版本 / 推送是 App 专用接口；其余数据接口与网页版共用：/api/app/v1/xxx 等同于 /api/xxx；
- 后台可开关 App 接口、要求 App Key（请求头 X-App-Key）、发布新版本（含强制更新）。
接口文档：docs/APP_API.md，也可通过 GET /api/app/v1/docs 获取。
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from . import auth, cache, members, settings, store, track
from .common import body_of, client_ip, err, ok

PREFIX = "/api/app/v1"
API_VERSION = 1
OWN = ("auth/", "meta/", "ws", "docs", "member/redeem")  # App 专用，其余转给网页版同名接口
DENY = ("admin", "telemetry", "auth/", "pay/")             # 不允许通过 App 前缀访问的网页接口


# ---------------- 网关：开关、App Key、去 Cookie、路径映射 ----------------
class AppGateway:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        path = scope.get("path", "")
        if scope["type"] not in ("http", "websocket") or not path.startswith(PREFIX):
            await self.app(scope, receive, send)
            return
        rest = path[len(PREFIX):].lstrip("/")
        reason = self._reject(scope, rest)
        if reason:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 4401})
                return
            code, msg = reason
            resp = err(code, msg)
            await resp(scope, receive, send)
            return
        scope = dict(scope)
        # 去掉 Cookie：App 只用 Bearer Token；浏览器带着 Cookie 也无法借这个前缀冒用登录态
        scope["headers"] = [(k, v) for k, v in scope.get("headers", []) if k.lower() != b"cookie"]
        scope["zyll_app"] = True
        if not rest.startswith(OWN):
            if rest.startswith(DENY):
                await err(404, "Not Found")(scope, receive, send)
                return
            scope["path"] = "/api/" + rest
            scope["raw_path"] = scope["path"].encode()
        await self.app(scope, receive, send)

    @staticmethod
    def _reject(scope: dict[str, Any], rest: str) -> tuple[int, str] | None:
        if not settings.get("app.enabled"):
            return 404, "App 接口未开启"
        if settings.get("app.require_key") and not rest.startswith(("docs", "meta/version")):
            key = settings.get("app.api_key") or ""
            got = ""
            for k, v in scope.get("headers", []):
                if k.lower() == b"x-app-key":
                    got = v.decode(errors="ignore")
            if scope["type"] == "websocket" and not got:
                from urllib.parse import parse_qs
                got = (parse_qs(scope.get("query_string", b"").decode()).get("app_key") or [""])[0]
            if not key or not hmac.compare_digest(got, key):
                return 401, "app_key_invalid"
        return None


# ---------------- 令牌 ----------------
def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _device(b: dict[str, Any]) -> dict[str, str]:
    d = b.get("device") if isinstance(b.get("device"), dict) else {}
    return {"id": str(d.get("id") or "")[:80], "name": str(d.get("name") or d.get("model") or "")[:80],
            "platform": str(d.get("os") or d.get("platform") or "android")[:40], "app_version": str(d.get("app_version") or "")[:40]}


async def _issue(user: dict[str, Any], dev: dict[str, str], ip: str) -> dict[str, Any]:
    token = "zyt_" + secrets.token_urlsafe(32)
    now = int(time.time())
    days = int(settings.get("app.token_days") or 90)
    if dev["id"]:  # 同一台设备重新登录：旧令牌作废
        await store.execute("UPDATE app_tokens SET revoked = 1 WHERE user_id = ? AND device_id = ? AND revoked = 0", (user["id"], dev["id"]))
    await store.execute(
        """INSERT INTO app_tokens (user_id, token_hash, user_ver, device_id, device_name, platform, app_version, created_at, last_used_at, last_ip, expires_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (user["id"], _hash(token), user["token_version"], dev["id"], dev["name"], dev["platform"], dev["app_version"], now, now, ip[:64], now + days * 86400))
    return {"token": token, "token_type": "Bearer", "expires_at": now + days * 86400}


def _me(user: dict[str, Any]) -> dict[str, Any]:
    return {"user": auth.public_user(user), "membership": members.status(user)}


# ---------------- 账号 ----------------
def login_mode(kind: str = "login") -> str:
    """web = 必须跳转网页登录 / 注册（网页上有人机验证）；native = App 内直接输入密码。"""
    mode = settings.get("app.login_mode") or "auto"
    if mode in ("web", "native"):
        return mode
    from . import security
    return "web" if security.turnstile_active("turnstile.on_login" if kind == "login" else "turnstile.on_register") else "native"


def _web_required(kind: str):
    return err(403, "web_login_required", web_login=True, message="请在打开的网页中" + ("登录" if kind == "login" else "注册") + "（网站开启了人机验证）")


async def app_register(request: Request):
    from .api_public import email_verify_required, _send_verify  # 复用网页版的规则
    if not settings.get("register.enabled"):
        return err(403, "暂不开放注册")
    if login_mode("register") == "web":
        return _web_required("register")
    if auth.rate_limited(f"reg:{client_ip(request)}", limit=10, window=3600):
        return err(429, "操作太频繁，请稍后再试")
    b = await body_of(request)
    email = str(b.get("email", "")).strip().lower()
    if not auth.EMAIL_RE.match(email) or len(email) > 254:
        return err(400, "邮箱格式不正确")
    if not auth.valid_password(b.get("password")):
        return err(400, "密码至少 8 位")
    if await store.query_one("SELECT 1 FROM site_users WHERE email = ?", (email,)):
        return err(409, "该邮箱已注册，请直接登录")
    await store.execute("INSERT INTO site_users (email, password_hash, created_at) VALUES (?, ?, ?)",
                        (email, auth.hash_password(b["password"]), int(time.time())))
    user = await store.query_one("SELECT * FROM site_users WHERE email = ?", (email,))
    await track.log(request, "user", "register", user_id=user["id"], email=email, device={**_device(b), "source": "app"})
    if email_verify_required():
        try:
            await _send_verify(request, user)
        except Exception as e:  # noqa: BLE001
            cache.set_status("smtp", False, f"发送验证邮件失败：{e}")
        return ok({"verify_required": True})
    return ok({**await _issue(user, _device(b), client_ip(request)), **_me(user)})


async def app_login(request: Request):
    from .api_public import email_verify_required
    if login_mode("login") == "web":
        return _web_required("login")
    b = await body_of(request)
    email = str(b.get("email", "")).strip().lower()
    if auth.rate_limited(f"ip:{client_ip(request)}", f"user:{email}"):
        return err(429, "尝试次数过多，请 15 分钟后再试")
    user = await store.query_one("SELECT * FROM site_users WHERE email = ?", (email,))
    dev = {**_device(b), "source": "app"}
    if not user or not auth.verify_password(str(b.get("password", "")), user["password_hash"]):
        await track.log(request, "user", "login_fail", user_id=user["id"] if user else None, email=email, reason="App：密码错误", device=dev)
        return err(401, "邮箱或密码错误")
    if not user["is_active"]:
        return err(403, "该账号已被停用")
    if email_verify_required() and not user["email_verified"]:
        return err(403, "请先到邮箱点击验证链接", unverified=True)
    auth.clear_attempts(f"user:{email}")
    await track.log(request, "user", "login_ok", user_id=user["id"], email=email, reason="App", device=dev)
    await store.execute("UPDATE site_users SET last_login_at = ? WHERE id = ?", (int(time.time()), user["id"]))
    return ok({**await _issue(user, _device(b), client_ip(request)), **_me(user)})


async def app_exchange(request: Request):
    """网页登录后回到 App：用一次性授权码 + App 自己生成的 verifier 换访问令牌（PKCE S256）。"""
    import base64
    if auth.rate_limited(f"exchange:{client_ip(request)}", limit=30, window=900):
        return err(429, "尝试次数过多，请稍后再试")
    b = await body_of(request)
    code, verifier = str(b.get("code", "")), str(b.get("verifier", ""))
    if not code or not (43 <= len(verifier) <= 128):
        return err(400, "授权参数不正确，请重新登录")
    row = await store.query_one("SELECT * FROM app_codes WHERE code_hash = ?", (_hash(code),))
    now = int(time.time())
    if not row or row["used"] or row["expires_at"] < now:
        return err(400, "授权已过期或已使用，请重新登录")
    expect = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    if not hmac.compare_digest(expect, row["challenge"]):
        return err(400, "授权校验失败，请重新登录")
    if await store.execute("UPDATE app_codes SET used = 1 WHERE code_hash = ? AND used = 0", (_hash(code),)) != 1:
        return err(400, "授权已使用，请重新登录")
    user = await store.query_one("SELECT * FROM site_users WHERE id = ?", (row["user_id"],))
    if not user or not user["is_active"] or user["token_version"] != row["user_ver"]:
        return err(400, "账号状态已变化，请重新登录")
    dev = _device(b)
    await track.log(request, "user", "login_ok", user_id=user["id"], email=user["email"], reason="App 网页登录", device={**dev, "source": "app"})
    await store.execute("UPDATE site_users SET last_login_at = ? WHERE id = ?", (now, user["id"]))
    return ok({**await _issue(user, dev, client_ip(request)), **_me(user)})


async def _need(request: Request):
    user = await auth.current_user(request)
    return (user, None) if user else (None, err(401, "token_invalid"))


async def app_logout(request: Request):
    user, e = await _need(request)
    if e:
        return e
    await store.execute("UPDATE app_tokens SET revoked = 1 WHERE id = ?", (user["_token_id"],))
    return ok({"ok": True})


async def app_me(request: Request):
    user, e = await _need(request)
    return e or ok(_me(user))


async def app_devices(request: Request):
    user, e = await _need(request)
    if e:
        return e
    rows = await store.query("""SELECT id, device_name, platform, app_version, created_at, last_used_at, last_ip FROM app_tokens
                                WHERE user_id = ? AND revoked = 0 AND expires_at > ? ORDER BY last_used_at DESC""", (user["id"], int(time.time())))
    return ok({"devices": [{**r, "current": r["id"] == user["_token_id"]} for r in rows]})


async def app_device_revoke(request: Request):
    user, e = await _need(request)
    if e:
        return e
    await store.execute("UPDATE app_tokens SET revoked = 1 WHERE id = ? AND user_id = ?", (int(request.path_params["tid"]), user["id"]))
    return ok({"ok": True})


async def app_password(request: Request):
    """改密码：所有设备的令牌失效，当前设备返回新令牌。"""
    user, e = await _need(request)
    if e:
        return e
    b = await body_of(request)
    if not auth.verify_password(str(b.get("old_password", "")), user["password_hash"]):
        await track.log(request, "user", "password_fail", user_id=user["id"], email=user["email"], reason="App：原密码错误")
        return err(400, "原密码错误")
    if not auth.valid_password(b.get("new_password")):
        return err(400, "新密码至少 8 位")
    await store.execute("UPDATE site_users SET password_hash = ?, token_version = token_version + 1 WHERE id = ?",
                        (auth.hash_password(b["new_password"]), user["id"]))
    await store.execute("UPDATE app_tokens SET revoked = 1 WHERE user_id = ?", (user["id"],))
    await track.log(request, "user", "password", user_id=user["id"], email=user["email"], reason="App")
    fresh = await store.query_one("SELECT * FROM site_users WHERE id = ?", (user["id"],))
    tok = await store.query_one("SELECT device_id, device_name, platform, app_version FROM app_tokens WHERE id = ?", (user["_token_id"],))
    dev = {"id": tok["device_id"], "name": tok["device_name"], "platform": tok["platform"], "app_version": tok["app_version"]} if tok else _device({})
    return ok(await _issue(fresh, dev, client_ip(request)))


async def app_redeem(request: Request):
    from .api_public import member_redeem
    return await member_redeem(request, source="app")


# ---------------- 版本与配置 ----------------
async def app_version(request: Request):
    try:
        code = int(request.query_params.get("version_code", "0"))
    except ValueError:
        code = 0
    latest = int(settings.get("app.latest_version_code") or 0)
    minimum = int(settings.get("app.min_version_code") or 0)
    return ok({
        "latest_version_code": latest, "latest_version_name": settings.get("app.latest_version_name"),
        "min_version_code": minimum, "apk_url": settings.get("app.apk_url"), "changelog": settings.get("app.changelog"),
        "has_update": latest > code, "force_update": code < minimum,
    })


async def app_config(request: Request):
    site_ms = members.enabled()
    return ok({
        "api_version": API_VERSION, "server_time": int(time.time()),
        "site_name": settings.get("site.name"), "site_name_en": settings.get("site.name_en"),
        "membership_enabled": site_ms, "gated_sections": settings.get("membership.gated") if site_ms else [],
        "buy_hint": settings.get("membership.buy_hint") if site_ms else "",
        "register_enabled": settings.get("register.enabled"),
        # 登录方式：web = 打开浏览器到 web_auth_url 登录，授权后通过 zyllfinance://auth 回到 App
        "login_mode": login_mode("login"), "register_mode": login_mode("register"),
        "web_auth_path": "/#/app-auth", "password_reset": security_smtp(),
        "ai_import": _ai_config(),
        "portfolio_enabled": settings.get("portfolio.enabled"),
        "ws_path": f"{PREFIX}/ws", "sse_path": f"{PREFIX}/stream",
        "topics": ["calendar", "ticks", "snap", "indices", "rank", "fx", "futures", "finra_daily", "finra_ats", "cftc", "dark_print", "holidays"],
    })


def security_smtp() -> bool:
    from . import security
    return security.smtp_configured()


def _ai_config() -> dict[str, Any]:
    from . import ai_import
    return {"enabled": ai_import.available(), "vision": ai_import.vision_available(), "members_only": ai_import.members_only()}


async def app_docs(request: Request):
    p = Path(__file__).resolve().parents[2] / "docs" / "APP_API.md"
    if not p.exists():
        p = Path("/app/docs/APP_API.md")
    return PlainTextResponse(p.read_text(encoding="utf-8") if p.exists() else "docs not found", media_type="text/markdown; charset=utf-8")


# ---------------- WebSocket 实时推送 ----------------
async def app_ws(ws: WebSocket):
    """消息格式与网页 SSE 相同：{"topic": "...", "data": ...}。客户端可发送 {"op":"subscribe","topics":[...]} 只收部分主题。"""
    await ws.accept()
    q = cache.subscribe()
    topics: set[str] | None = None

    async def reader():
        nonlocal topics
        while True:
            msg = await ws.receive_text()
            try:
                m = json.loads(msg)
            except ValueError:
                continue
            if m.get("op") == "subscribe" and isinstance(m.get("topics"), list):
                topics = {str(t) for t in m["topics"]}
                await ws.send_text(json.dumps({"topic": "_subscribed", "data": sorted(topics)}))
            elif m.get("op") == "ping":
                await ws.send_text(json.dumps({"topic": "_pong", "data": int(time.time())}))

    rt = asyncio.create_task(reader())
    try:
        await ws.send_text(json.dumps({"topic": "_hello", "data": {"api_version": API_VERSION, "server_time": int(time.time())}}))
        while True:
            getter = asyncio.create_task(q.get())
            done, _ = await asyncio.wait({getter, rt}, timeout=25, return_when=asyncio.FIRST_COMPLETED)
            if rt in done:  # 客户端断开：立即清理
                getter.cancel()
                break
            if getter not in done:
                getter.cancel()
                await ws.send_text(json.dumps({"topic": "_ping", "data": int(time.time())}))
                continue
            msg = getter.result()
            if topics is not None:
                try:
                    if json.loads(msg).get("topic") not in topics:
                        continue
                except ValueError:
                    pass
            await ws.send_text(msg)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        rt.cancel()
        if rt.done() and not rt.cancelled():
            rt.exception()  # 取走断开连接时的异常，避免“未处理的任务异常”写进运行日志
        cache.unsubscribe(q)


routes = [
    Route(f"{PREFIX}/auth/register", app_register, methods=["POST"]),
    Route(f"{PREFIX}/auth/login", app_login, methods=["POST"]),
    Route(f"{PREFIX}/auth/exchange", app_exchange, methods=["POST"]),
    Route(f"{PREFIX}/auth/logout", app_logout, methods=["POST"]),
    Route(f"{PREFIX}/auth/me", app_me),
    Route(f"{PREFIX}/auth/devices", app_devices),
    Route(f"{PREFIX}/auth/devices/{{tid:int}}", app_device_revoke, methods=["DELETE"]),
    Route(f"{PREFIX}/auth/password", app_password, methods=["POST"]),
    Route(f"{PREFIX}/member/redeem", app_redeem, methods=["POST"]),
    Route(f"{PREFIX}/meta/version", app_version),
    Route(f"{PREFIX}/meta/config", app_config),
    Route(f"{PREFIX}/docs", app_docs),
    WebSocketRoute(f"{PREFIX}/ws", app_ws),
]
