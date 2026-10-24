"""前台接口：站点配置、数据、用户注册登录、诊断上报、付款（预留）。"""
from __future__ import annotations

import asyncio
import hashlib
import re
import secrets
import time
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response, StreamingResponse
from starlette.routing import Route

import ipaddress
import json

from . import auth, cache, security, settings, store, track
from .collectors.calendar import COLS, serialize as ser_event
from .common import body_of, client_ip, err, ok, raw_json

state: dict[str, Any] = {}  # main.py 注入 finra 采集器


# ================= 站点配置 =================
def _slot(name: str) -> dict[str, str] | None:
    provider = settings.get(f"ads.{name}_provider")
    if provider == "none":
        return None
    if provider == "google":
        slot = settings.get(f"ads.{name}_slot")
        return {"provider": "google", "slot": slot} if slot and settings.get("ads.google_client") else None
    code = settings.get(f"ads.{name}_code")
    return {"provider": provider, "code": code} if code.strip() else None


def ads_config(user: dict[str, Any] | None) -> dict[str, Any] | None:
    if not settings.get("ads.enabled"):
        return None
    if settings.get("membership.enabled") and settings.get("membership.no_ads") and auth.is_member(user):
        return None
    slots = {k: v for k in ("footer", "inline", "side") if (v := _slot(k))}
    if not slots:
        return None
    return {"google_client": settings.get("ads.google_client"), "slots": slots}


def ads_active() -> bool:
    return bool(settings.get("ads.enabled"))


def email_verify_required() -> bool:
    return bool(settings.get("register.email_verify")) and security.smtp_configured()


async def site(request: Request):
    user = await auth.current_user(request)
    ts_flags = {k: security.turnstile_active(f"turnstile.{k}") for k in ("on_register", "on_login", "on_forgot")}
    return ok({
        "name": settings.get("site.name"),
        "name_en": settings.get("site.name_en"),
        "copyright": settings.get("site.copyright"),
        "icp": settings.get("site.icp"),
        "announcement": settings.get("site.announcement"),
        "register": {"enabled": settings.get("register.enabled"), "email_verify": email_verify_required()},
        "password_reset": security.smtp_configured(),
        "turnstile": {"site_key": settings.get("turnstile.site_key") if any(ts_flags.values()) else "", **ts_flags},
        "ads": ads_config(user),
        # 会员模式关闭时只告诉前台 enabled=false，不下发任何会员相关文案
        "membership": {
            "enabled": True,
            "gated": settings.get("membership.gated") or [],
            "notice": settings.get("membership.notice"),
            "buy_hint": settings.get("membership.buy_hint"),
        } if settings.get("membership.enabled") else {"enabled": False},
        "telemetry": settings.get("telemetry.enabled"),
        "telemetry_sample": settings.get("telemetry.sample_api"),
        "portfolio": {"enabled": settings.get("portfolio.enabled"), "access": settings.get("portfolio.access")},
        "ai_import": _ai_site(),
        "user": auth.public_user(user) if user else None,
    })


def _ai_site() -> dict[str, Any]:
    from . import ai_import
    return {"enabled": ai_import.available(), "vision": ai_import.vision_available(), "members_only": ai_import.members_only()}


async def ads_txt(request: Request):
    return PlainTextResponse(settings.get("ads.ads_txt") or "", headers={"Cache-Control": "public, max-age=3600"})


# ================= 会员限制 =================
async def locked(request: Request, section: str) -> bool:
    if not settings.get("membership.enabled") or section not in (settings.get("membership.gated") or []):
        return False
    return not auth.is_member(await auth.current_user(request))


def members_only() -> Response:
    return err(403, "members_only", notice=settings.get("membership.notice"))


# ================= 数据 =================
async def calendar(request: Request):
    q = request.query_params
    now = int(time.time())
    try:
        start, end = int(q["start"]), int(q["end"])
    except (KeyError, ValueError):
        return raw_json(cache.get_raw("cal:window"), b"[]")
    if start >= now - 8 * 86400 and end <= now + 15 * 86400:
        return raw_json(cache.get_raw("cal:window"), b"[]")
    if end - start > 62 * 86400:
        return err(400, "查询范围最多 62 天")
    rows = await store.query(f"SELECT {', '.join(COLS)} FROM econ_events WHERE ts >= ? AND ts <= ? AND hidden = 0 ORDER BY ts", (start, end))
    return ok([ser_event(r) for r in rows])


async def calendar_next(request: Request):
    """接下来的“非常重要”事件（不受日历窗口限制，下周日程也能找到）。"""
    return raw_json(cache.get_raw("cal:next"), b"[]")


def _num(v: str) -> float | None:
    m = re.search(r"-?\d+(?:\.\d+)?", (v or "").replace(",", ""))
    if not m:
        return None
    x = float(m.group(0))
    unit = (v or "").strip()[-1:].upper()
    return x * {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}.get(unit, 1)


async def calendar_event(request: Request):
    """单个事件的详情：历史预测值 / 实际值（同一国家同一指标）+ 中文释义。"""
    from .collectors.calendar import title_key
    from .glossary import explain
    ev = await store.query_one(f"SELECT {', '.join(COLS)} FROM econ_events WHERE id = ?", (request.path_params["eid"][:64],))
    if not ev:
        return err(404, "事件不存在")
    key = title_key(ev["title"])
    rows = await store.query(f"SELECT {', '.join(COLS)} FROM econ_events WHERE currency = ? AND ts <= ? AND hidden = 0 ORDER BY ts DESC LIMIT 400",
                             (ev["currency"], ev["ts"] + 1))
    hist = [r for r in rows if title_key(r["title"]) == key][:24]
    hist.reverse()
    unit = ""
    for r in hist:
        for v in (r["actual"], r["forecast"]):
            if v and not unit:
                m = re.search(r"[%KMBT]$", v.strip())
                unit = m.group(0) if m else ""
    return ok({
        "event": ser_event(ev), "unit": unit, **explain(ev["title"]),
        "history": [{"ts": r["ts"], "actual": r["actual"], "forecast": r["forecast"], "previous": r["previous"],
                     "a": _num(r["actual"]), "f": _num(r["forecast"])} for r in hist],
    })


SYM_RE = re.compile(r"^[A-Z][A-Z0-9.\-/]{0,9}$")
_ats_lock: dict[str, float] = {}


async def dp_daily(request: Request):
    return raw_json(cache.get_raw("finra:daily:summary"))


async def dp_watch(request: Request):
    """关注列表：登录用户用自己的自选（与“自选”“行情”同步），未登录用后台的关注股票。"""
    from . import lists
    user = await auth.current_user(request)
    syms = await lists.user_symbols(user["id"]) if user else []
    synced = bool(syms)
    if not syms:
        syms = settings.get_list("sources.market.watchlist")
    out = await state["finra"].watch_rows(syms[:200])
    return ok({**out, "synced": synced})


async def dp_ats(request: Request):
    if await locked(request, "darkpool_ats"):
        return members_only()
    return raw_json(cache.get_raw("finra:ats:firms"))


async def dp_symbol(request: Request):
    if await locked(request, "darkpool_stock"):
        return members_only()
    symbol = request.path_params["symbol"].upper()
    if not SYM_RE.match(symbol):
        return err(400, "代码格式不正确")
    finra = state["finra"]
    history = await finra.symbol_history(symbol)
    ats = cache.get(f"finra:ats:sym:{symbol}")
    if ats is None and settings.get("sources.finra_ats.enabled") and time.time() - _ats_lock.get(symbol, 0) > 600:
        _ats_lock[symbol] = time.time()  # 同一代码 10 分钟内只向 FINRA 查询一次
        try:
            ats = await finra.fetch_symbol_ats(symbol)
        except Exception as e:  # noqa: BLE001 —— 前台不展示错误，记到数据源状态里
            cache.set_status("finra_ats_ondemand", False, f"{symbol}: {e}")
            ats = None
    return ok({"symbol": symbol, "history": history, "ats": ats})


async def dp_prints(request: Request):
    if await locked(request, "darkpool_prints"):
        return members_only()
    enabled = bool(settings.get("sources.darkpool_rt.enabled") and settings.get("sources.darkpool_rt.api_key"))
    meta = {"enabled": enabled, "min_notional": settings.get("sources.darkpool_rt.min_notional")}
    try:
        limit = max(1, min(int(request.query_params.get("limit", "200")), 1000))
    except ValueError:
        limit = 200
    rows = await store.query("SELECT ts, symbol, price, size, notional, venue FROM dark_prints ORDER BY ts DESC LIMIT ?", (limit,))
    return ok({"meta": meta, "prints": rows})


async def holidays_api(request: Request):
    from . import holidays
    raw = cache.get_raw("holidays:window")
    if raw:
        return raw_json(raw)
    return ok({"items": [], "today": holidays.today_status()})


async def symbol_search(request: Request):
    from .collectors.symbols import search
    q = request.query_params.get("q", "")[:40]
    return JSONResponse(search(q, 10), headers={"Cache-Control": "public, max-age=300"})


async def futures(request: Request):
    cot = b'"locked"' if await locked(request, "futures_cot") else (cache.get_raw("cftc:tff") or b"null")
    parts = [b'"cme":' + (cache.get_raw("futures:cme") or b"null"),
             b'"blocks":' + (cache.get_raw("futures:blocks") or b"null"),
             b'"cot":' + cot]
    return raw_json(b"{" + b",".join(parts) + b"}")


async def stream(request: Request):
    q = cache.subscribe()

    async def gen():
        try:
            yield "retry: 3000\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=20)
                    yield f"data: {msg}\n\n"
                except asyncio.TimeoutError:
                    if await request.is_disconnected():
                        break
                    yield ": ping\n\n"
        finally:
            cache.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ================= 用户 =================
async def _check_turnstile(request: Request, flag: str, token: Any) -> Response | None:
    if not security.turnstile_active(flag):
        return None
    passed, reason = await security.verify_turnstile(str(token or ""))
    if passed:
        cache.set_status("turnstile", True, "最近一次校验通过")
        return None
    cache.set_status("turnstile", False, f"校验失败：{reason}")  # 详细原因记录到后台
    if "过期" in reason or "先完成" in reason:
        return err(400, reason)
    return err(400, "人机验证暂时无法完成，请稍后重试")


def _site_url(request: Request) -> str:
    return (settings.get("smtp.site_url") or str(request.base_url)).rstrip("/")


async def _send_verify(request: Request, user: dict[str, Any]) -> None:
    token = secrets.token_urlsafe(32)
    await store.execute("DELETE FROM email_tokens WHERE user_id = ? AND purpose = 'verify'", (user["id"],))
    await store.execute("INSERT INTO email_tokens VALUES (?, ?, 'verify', ?)", (token, user["id"], int(time.time()) + 86400))
    link = f"{_site_url(request)}/api/auth/verify?token={token}"
    await security.send_template(user["email"], "verify", {"link": link, "expires_hours": 24}, _site_url(request))


def _mail_later(request: Request, to: str, key: str, values: dict[str, Any]) -> None:
    """后台发送通知邮件，失败只记录到后台状态，不影响用户操作。"""
    from . import mailtpl
    if not (security.smtp_configured() and mailtpl.enabled(key)):
        return

    async def go():
        try:
            await security.send_template(to, key, values, _site_url(request))
        except Exception as e:  # noqa: BLE001
            cache.set_status("smtp", False, f"发送“{key}”邮件失败：{e}")
    asyncio.create_task(go())


async def me(request: Request):
    user = await auth.current_user(request)
    return ok({"user": auth.public_user(user) if user else None})


async def register(request: Request):
    if not settings.get("register.enabled"):
        return err(403, "暂不开放注册")
    if auth.rate_limited(f"reg:{client_ip(request)}", limit=10, window=3600):
        return err(429, "操作太频繁，请稍后再试")
    b = await body_of(request)
    if (bad := await _check_turnstile(request, "turnstile.on_register", b.get("turnstile"))):
        return bad
    email = str(b.get("email", "")).strip().lower()
    if not auth.EMAIL_RE.match(email) or len(email) > 254:
        return err(400, "邮箱格式不正确")
    if not auth.valid_password(b.get("password")):
        return err(400, "密码至少 8 位")
    if await store.query_one("SELECT 1 FROM site_users WHERE email = ?", (email,)):
        await track.log(request, "user", "register_fail", email=email, reason="邮箱已注册", device=b.get("device"))
        return err(409, "该邮箱已注册，请直接登录")
    await store.execute("INSERT INTO site_users (email, password_hash, created_at) VALUES (?, ?, ?)",
                        (email, auth.hash_password(b["password"]), int(time.time())))
    user = await store.query_one("SELECT * FROM site_users WHERE email = ?", (email,))
    await track.log(request, "user", "register", user_id=user["id"], email=email, device=b.get("device"))
    _mail_later(request, email, "welcome", {})
    if email_verify_required():
        try:
            await _send_verify(request, user)
        except Exception as e:  # noqa: BLE001
            cache.set_status("smtp", False, f"发送验证邮件失败：{e}")
            return ok({"verify_required": True, "mail_failed": True})
        return ok({"verify_required": True})
    resp = ok({"user": auth.public_user(user)})
    auth.login_user(resp, request, user)
    return resp


async def login(request: Request):
    b = await body_of(request)
    email = str(b.get("email", "")).strip().lower()
    if auth.rate_limited(f"ip:{client_ip(request)}", f"user:{email}"):
        return err(429, "尝试次数过多，请 15 分钟后再试")
    if (bad := await _check_turnstile(request, "turnstile.on_login", b.get("turnstile"))):
        return bad
    user = await store.query_one("SELECT * FROM site_users WHERE email = ?", (email,))
    dev = b.get("device")
    if not user or not auth.verify_password(str(b.get("password", "")), user["password_hash"]):
        await track.log(request, "user", "login_fail", user_id=user["id"] if user else None, email=email,
                        reason="密码错误" if user else "账号不存在", device=dev)
        return err(401, "邮箱或密码错误")
    if not user["is_active"]:
        await track.log(request, "user", "login_fail", user_id=user["id"], email=email, reason="账号已停用", device=dev)
        return err(403, "该账号已被停用")
    if email_verify_required() and not user["email_verified"]:
        await track.log(request, "user", "login_fail", user_id=user["id"], email=email, reason="邮箱未验证", device=dev)
        return err(403, "请先到邮箱点击验证链接", unverified=True)
    auth.clear_attempts(f"user:{email}")
    flags = await track.log(request, "user", "login_ok", user_id=user["id"], email=email, device=dev)
    if any(f.startswith(("新设备", "新国家")) for f in flags):
        meta = track.request_meta(request)
        _mail_later(request, email, "login_alert", {
            "time": time.strftime("%Y-%m-%d %H:%M", time.gmtime()), "ip": meta["ip"], "country": meta["country"] or "未知",
            "device": meta["ua"][:160], "risk": "，".join(flags)})
    await store.execute("UPDATE site_users SET last_login_at = ? WHERE id = ?", (int(time.time()), user["id"]))
    resp = ok({"user": auth.public_user(user)})
    auth.login_user(resp, request, user)
    return resp


async def logout(request: Request):
    user = await auth.current_user(request)
    if user:
        await track.log(request, "user", "logout", user_id=user["id"], email=user["email"])
    resp = ok({"ok": True})
    resp.delete_cookie(auth.USER_COOKIE, path="/")
    return resp


async def verify_email(request: Request):
    token = request.query_params.get("token", "")
    row = await store.query_one("SELECT * FROM email_tokens WHERE token = ? AND purpose = 'verify'", (token,))
    if not row or row["expires_at"] < time.time():
        return RedirectResponse("/#/verify-failed", status_code=302)
    await store.execute("UPDATE site_users SET email_verified = 1 WHERE id = ?", (row["user_id"],))
    await store.execute("DELETE FROM email_tokens WHERE token = ?", (token,))
    return RedirectResponse("/#/verified", status_code=302)


async def resend_verify(request: Request):
    b = await body_of(request)
    email = str(b.get("email", "")).strip().lower()
    if auth.rate_limited(f"resend:{email}", f"resend-ip:{client_ip(request)}", limit=3, window=3600):
        return err(429, "发送太频繁，请稍后再试")
    user = await store.query_one("SELECT * FROM site_users WHERE email = ?", (email,))
    if user and not user["email_verified"] and email_verify_required():
        try:
            await _send_verify(request, user)
        except Exception as e:  # noqa: BLE001
            cache.set_status("smtp", False, f"发送验证邮件失败：{e}")
    return ok({"ok": True})  # 不透露邮箱是否存在


async def change_password(request: Request):
    user = await auth.current_user(request)
    if not user:
        return err(401, "请先登录")
    b = await body_of(request)
    if not auth.verify_password(str(b.get("old_password", "")), user["password_hash"]):
        await track.log(request, "user", "password_fail", user_id=user["id"], email=user["email"], reason="原密码错误")
        return err(400, "原密码错误")
    if not auth.valid_password(b.get("new_password")):
        return err(400, "新密码至少 8 位")
    await track.log(request, "user", "password", user_id=user["id"], email=user["email"])
    await store.execute("UPDATE site_users SET password_hash = ?, token_version = token_version + 1 WHERE id = ?",
                        (auth.hash_password(b["new_password"]), user["id"]))
    user = await store.query_one("SELECT * FROM site_users WHERE id = ?", (user["id"],))
    resp = ok({"ok": True})
    auth.login_user(resp, request, user)
    return resp


# ================= 找回密码 =================
RESET_MINUTES = 30


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def forgot_password(request: Request):
    """发送重置链接。无论邮箱是否存在都返回相同结果，不泄露账号是否注册。"""
    b = await body_of(request)
    email = str(b.get("email", "")).strip().lower()
    if auth.rate_limited(f"forgot-ip:{client_ip(request)}", limit=10, window=3600) or auth.rate_limited(f"forgot:{email}", limit=3, window=3600):
        return err(429, "操作太频繁，请稍后再试")
    if (bad := await _check_turnstile(request, "turnstile.on_forgot", b.get("turnstile"))):
        return bad
    if not security.smtp_configured():
        contact = settings.get("privacy.contact_email")
        return err(503, "网站暂未配置邮件服务，无法通过邮件找回密码" + (f"，请联系 {contact}" if contact else "，请联系管理员"))
    if not auth.EMAIL_RE.match(email):
        return err(400, "邮箱格式不正确")
    user = await store.query_one("SELECT * FROM site_users WHERE email = ?", (email,))
    if user and user["is_active"]:
        token = secrets.token_urlsafe(32)
        await store.execute("DELETE FROM email_tokens WHERE user_id = ? AND purpose = 'reset'", (user["id"],))
        await store.execute("INSERT INTO email_tokens VALUES (?, ?, 'reset', ?)", (_hash_token(token), user["id"], int(time.time()) + RESET_MINUTES * 60))
        link = f"{_site_url(request)}/#/reset/{token}"
        try:
            await security.send_template(email, "reset", {"email": email, "link": link, "expires_minutes": RESET_MINUTES}, _site_url(request))
        except Exception as e:  # noqa: BLE001
            cache.set_status("smtp", False, f"发送重置密码邮件失败：{e}")
            return err(502, "邮件发送失败，请稍后再试")
        await track.log(request, "user", "reset_request", user_id=user["id"], email=email, device=b.get("device"))
    else:
        await track.log(request, "user", "reset_request", email=email, reason="账号不存在或已停用", device=b.get("device"))
    return ok({"sent": True})


async def reset_password(request: Request):
    b = await body_of(request)
    if auth.rate_limited(f"reset-ip:{client_ip(request)}", limit=20, window=3600):
        return err(429, "操作太频繁，请稍后再试")
    token = str(b.get("token", ""))
    row = await store.query_one("SELECT * FROM email_tokens WHERE token = ? AND purpose = 'reset'", (_hash_token(token),)) if token else None
    if not row or row["expires_at"] < time.time():
        return err(400, "重置链接无效或已过期，请重新申请")
    if not auth.valid_password(b.get("password")):
        return err(400, "新密码至少 8 位")
    user = await store.query_one("SELECT * FROM site_users WHERE id = ?", (row["user_id"],))
    if not user or not user["is_active"]:
        return err(400, "该账号不可用")

    def run(c):
        # 同一事务：改密码、所有网页会话和 App 令牌失效、作废所有重置链接；能收到邮件也就证明了邮箱属于本人
        c.execute("UPDATE site_users SET password_hash = ?, token_version = token_version + 1, email_verified = 1 WHERE id = ?",
                  (auth.hash_password(b["password"]), user["id"]))
        c.execute("UPDATE app_tokens SET revoked = 1 WHERE user_id = ?", (user["id"],))
        c.execute("DELETE FROM email_tokens WHERE user_id = ? AND purpose = 'reset'", (user["id"],))
    await store.run(run)
    auth.clear_attempts(f"user:{user['email']}")
    await track.log(request, "user", "password_reset", user_id=user["id"], email=user["email"], device=b.get("device"))
    fresh = await store.query_one("SELECT * FROM site_users WHERE id = ?", (user["id"],))
    resp = ok({"user": auth.public_user(fresh)})
    auth.login_user(resp, request, fresh)
    return resp


# ================= App 网页登录：授权码（PKCE） =================
CHALLENGE_RE = re.compile(r"^[A-Za-z0-9_-]{43,128}$")


async def app_code(request: Request):
    """已在网页登录的用户确认授权后，给 App 发一次性授权码（5 分钟有效，只能用一次，必须配合 App 自己保管的 verifier 才能换令牌）。"""
    if not settings.get("app.enabled"):
        return err(404, "App 接口未开启")
    user = await auth.current_user(request)
    if not user:
        return err(401, "请先登录")
    b = await body_of(request)
    challenge = str(b.get("challenge", ""))
    if not CHALLENGE_RE.match(challenge):
        return err(400, "授权参数不正确，请回到 App 重新点击登录")
    if auth.rate_limited(f"appcode:{user['id']}", limit=20, window=3600):
        return err(429, "操作太频繁，请稍后再试")
    code = secrets.token_urlsafe(32)
    now = int(time.time())
    await store.execute("DELETE FROM app_codes WHERE expires_at < ?", (now - 3600,))
    await store.execute("INSERT INTO app_codes (code_hash, user_id, user_ver, challenge, device_name, created_at, expires_at) VALUES (?,?,?,?,?,?,?)",
                        (_hash_token(code), user["id"], user["token_version"], challenge, str(b.get("device_name") or "")[:80], now, now + 300))
    await track.log(request, "user", "app_authorize", user_id=user["id"], email=user["email"], reason=str(b.get("device_name") or "")[:80])
    return ok({"code": code, "expires_in": 300})


# ================= 我的数据（GDPR 第 15、17、20 条）=================
async def my_export(request: Request):
    user = await auth.current_user(request)
    if not user:
        return err(401, "请先登录")
    await track.log(request, "user", "export", user_id=user["id"], email=user["email"])
    data = await track.export_user(user["id"])
    return Response(json.dumps(data, ensure_ascii=False, indent=2), media_type="application/json; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="my-data.json"', "Cache-Control": "no-store"})


async def my_delete(request: Request):
    user = await auth.current_user(request)
    if not user:
        return err(401, "请先登录")
    b = await body_of(request)
    if not auth.verify_password(str(b.get("password", "")), user["password_hash"]):
        return err(400, "密码错误")
    await track.delete_user(user["id"])
    from . import universe
    await universe.refresh()
    resp = ok({"ok": True})
    resp.delete_cookie(auth.USER_COOKIE, path="/")
    return resp


async def privacy(request: Request):
    g = settings.get
    return ok({
        "controller": g("privacy.controller") or g("site.copyright"), "address": g("privacy.address"),
        "contact": g("privacy.contact_email"), "dpo": g("privacy.dpo"), "eu_rep": g("privacy.eu_rep"),
        "updated": g("privacy.updated"), "extra": g("privacy.extra"),
        "login_log": g("privacy.login_log"), "login_log_days": g("privacy.login_log_days"),
        "telemetry": g("telemetry.enabled"), "telemetry_days": g("telemetry.retention_days"),
        "ads": bool(g("ads.enabled")), "turnstile": any(g(f"turnstile.{k}") for k in ("on_register", "on_login", "on_admin_login")),
        "realtime": bool(g("sources.realtime.enabled")),
        "ai": _ai_privacy(),
    })


def _ai_privacy() -> dict[str, Any] | None:
    """AI 导入开启时，在隐私政策里写明交给了哪家 AI 服务（只写域名）。"""
    from urllib.parse import urlparse
    from . import ai_import
    if not ai_import.available():
        return None
    from . import llm
    hosts = [urlparse(llm.resolve("text")["base"]).hostname]
    if ai_import.vision_available():
        hosts.append(urlparse(llm.resolve("vision")["base"]).hostname)
    return {"providers": [h for h in dict.fromkeys(hosts) if h], "redact": bool(settings.get("ai.redact"))}


# ================= 诊断数据（需访客同意性能 Cookie）=================
_last_cleanup = [0.0]
KINDS = {"load", "error", "api", "sse", "vitals", "view", "longtask", "resource"}


def anon_ip(ip: str) -> str:
    """IPv4 去掉最后一段，IPv6 只保留前 48 位（GDPR：诊断不需要完整 IP）。"""
    try:
        a = ipaddress.ip_address(ip)
        return str(ipaddress.ip_network(f"{ip}/{24 if a.version == 4 else 48}", strict=False).network_address)
    except ValueError:
        return ""


def _clean(v: Any, depth: int = 0) -> Any:
    """只保留简单类型，限制大小，防止被塞入大量数据。"""
    if depth > 3:
        return None
    if isinstance(v, dict):
        return {str(k)[:40]: _clean(x, depth + 1) for k, x in list(v.items())[:60]}
    if isinstance(v, list):
        return [_clean(x, depth + 1) for x in v[:30]]
    if isinstance(v, str):
        return v[:2000]
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    return str(v)[:200]


async def telemetry(request: Request):
    if not settings.get("telemetry.enabled") or "perf" not in request.cookies.get("zy_consent", ""):
        return Response(status_code=204)
    if auth.rate_limited(f"tel:{client_ip(request)}", limit=240, window=600):
        return Response(status_code=204)
    b = await body_of(request)
    ua = (request.headers.get("user-agent") or "")[:300]
    ip = anon_ip(client_ip(request))
    sid = str(b.get("sid") or "")[:32]
    ctx = _clean(b.get("ctx") or {})
    server = {"country": request.headers.get("cf-ipcountry") or "", "lang": (request.headers.get("accept-language") or "")[:80],
              "ch_ua": (request.headers.get("sec-ch-ua") or "")[:200], "ch_platform": request.headers.get("sec-ch-ua-platform") or "",
              "ch_mobile": request.headers.get("sec-ch-ua-mobile") or "", "proto": request.headers.get("x-forwarded-proto") or request.url.scheme,
              "http_version": request.scope.get("http_version", "")}
    now = int(time.time())
    rows = []
    for ev in (b.get("events") or [])[:30]:
        if not isinstance(ev, dict) or ev.get("kind") not in KINDS:
            continue
        try:
            value = float(ev["value"]) if ev.get("value") is not None else None
        except (TypeError, ValueError):
            value = None
        data = {"ctx": ctx, "server": server, "detail": _clean(ev.get("detail"))}
        rows.append((now, ev["kind"], str(ev.get("path", ""))[:200], str(ev.get("message", ""))[:1000], value, ua,
                     json.dumps(data, ensure_ascii=False)[:20000], sid, ip))
    await store.executemany("INSERT INTO telemetry (ts, kind, path, message, value, ua, data, sid, ip) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    if now - _last_cleanup[0] > 3600:
        _last_cleanup[0] = now
        days = max(1, int(settings.get("telemetry.retention_days") or 30))
        await store.execute("DELETE FROM telemetry WHERE ts < ?", (now - days * 86400,))
    return Response(status_code=204)


# ================= 会员：卡密激活 / 续期 =================
async def member_status(request: Request):
    from . import members
    if not members.enabled():
        return err(404, "Not Found")
    user = await auth.current_user(request)
    if not user:
        return err(401, "请先登录")
    log = await store.query("SELECT ts, source, days, old_expires, new_expires FROM member_log WHERE user_id = ? ORDER BY id DESC LIMIT 20", (user["id"],))
    return ok({"status": members.status(user), "history": [{**r, "source": "admin" if r["source"].startswith("admin") else r["source"]} for r in log],
               "buy_hint": settings.get("membership.buy_hint")})


async def member_redeem(request: Request, source: str = "web"):
    from . import members
    if not members.enabled():
        return err(404, "Not Found")
    user = await auth.current_user(request)
    if not user:
        return err(401, "请先登录")
    # 防暴力猜卡密：每个账号、每个 IP 10 分钟内最多 8 次
    if auth.rate_limited(f"redeem:{user['id']}", f"redeem-ip:{client_ip(request)}", limit=8, window=600):
        return err(429, "尝试次数过多，请 10 分钟后再试")
    b = await body_of(request)
    try:
        res = await members.redeem(user, str(b.get("code", "")), source)
    except ValueError as e:
        await track.log(request, "user", "redeem_fail", user_id=user["id"], email=user["email"], reason=str(e))
        return err(400, str(e))
    await track.log(request, "user", "redeem", user_id=user["id"], email=user["email"], reason=f"{res['days'] or '永久'} 天")
    auth.clear_attempts(f"redeem:{user['id']}")
    fresh = await store.query_one("SELECT * FROM site_users WHERE id = ?", (user["id"],))
    return ok({**res, "user": auth.public_user(fresh)})


routes = [
    Route("/api/site", site),
    Route("/ads.txt", ads_txt),
    Route("/api/calendar", calendar),
    Route("/api/calendar/next", calendar_next),
    Route("/api/calendar/event/{eid}", calendar_event),
    Route("/api/darkpool/daily", dp_daily),
    Route("/api/darkpool/ats", dp_ats),
    Route("/api/darkpool/watch", dp_watch),
    Route("/api/darkpool/symbol/{symbol}", dp_symbol),
    Route("/api/darkpool/prints", dp_prints),
    Route("/api/futures", futures),
    Route("/api/symbols/search", symbol_search),
    Route("/api/holidays", holidays_api),
    Route("/api/stream", stream),
    Route("/api/auth/me", me),
    Route("/api/auth/register", register, methods=["POST"]),
    Route("/api/auth/login", login, methods=["POST"]),
    Route("/api/auth/logout", logout, methods=["POST"]),
    Route("/api/auth/verify", verify_email),
    Route("/api/auth/resend", resend_verify, methods=["POST"]),
    Route("/api/auth/password", change_password, methods=["POST"]),
    Route("/api/auth/forgot", forgot_password, methods=["POST"]),
    Route("/api/auth/reset", reset_password, methods=["POST"]),
    Route("/api/auth/app-code", app_code, methods=["POST"]),
    Route("/api/telemetry", telemetry, methods=["POST"]),
    Route("/api/me/export", my_export),
    Route("/api/me/delete", my_delete, methods=["POST"]),
    Route("/api/privacy", privacy),
    Route("/api/member", member_status),
    Route("/api/member/redeem", member_redeem, methods=["POST"]),
]
