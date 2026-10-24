"""后台接口（/zylladmin）：安装向导、登录（密码 + 谷歌验证器）、设置、数据源、用户、管理员、诊断。"""
from __future__ import annotations

import json
import logging
import os
import secrets
import time
from typing import Any, Awaitable, Callable

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from . import auth, cache, mailtpl, members, runlog, security, settings, store, track
from .common import body_of, client_ip, err, ok
from .qr import QrCode

state: dict[str, Any] = {}  # main.py 注入采集管理器
_pending: dict[str, dict[str, Any]] = {}  # 待确认的 2FA 绑定：token -> {...}

SOURCE_TITLES = {g["source"]: g["title"] for g in settings.GROUPS if g.get("source")}
EXTRA_TITLES = {"turnstile": "Cloudflare 人机验证", "smtp": "邮件发送", "finra_ats_ondemand": "FINRA 个股按需查询"}


def _new_pending(**data: Any) -> dict[str, Any]:
    now = time.time()
    for k in [k for k, v in _pending.items() if v["exp"] < now]:
        _pending.pop(k, None)
    token = secrets.token_urlsafe(24)
    secret = security.new_totp_secret()
    _pending[token] = {"secret": secret, "exp": now + 900, **data}
    uri = security.totp_uri(secret, data.get("username", "admin"))
    return {"token": token, "secret": secret, "uri": uri, "qr": QrCode(uri).svg(scale=5)}


def admin_required(fn: Callable[[Request, dict[str, Any]], Awaitable[Response]]):
    async def wrapper(request: Request) -> Response:
        admin = await auth.current_admin(request)
        if not admin:
            return err(401, "请先登录后台")
        return await fn(request, admin)
    return wrapper


def pub_admin(a: dict[str, Any]) -> dict[str, Any]:
    return {"id": a["id"], "username": a["username"], "created_at": a["created_at"], "last_login_at": a["last_login_at"]}


# ================= 安装向导 / 登录 =================
async def admin_state(request: Request):
    admin = await auth.current_admin(request)
    return ok({
        "installed": await auth.admin_installed(),
        "install_token_required": bool(os.environ.get("ZYLL_INSTALL_TOKEN")),
        "admin": pub_admin(admin) if admin else None,
        "site_name": settings.get("site.name"),
        "turnstile": settings.get("turnstile.site_key") if security.turnstile_active("turnstile.on_admin_login") else "",
    })


async def install_start(request: Request):
    if await auth.admin_installed():
        return err(409, "已经安装过了，请直接登录")
    if auth.rate_limited(f"install:{client_ip(request)}", limit=20):
        return err(429, "尝试次数过多，请稍后再试")
    b = await body_of(request)
    need = os.environ.get("ZYLL_INSTALL_TOKEN")
    if need and not secrets.compare_digest(str(b.get("install_token", "")), need):
        return err(403, "安装口令不正确")
    username = str(b.get("username", "")).strip()
    if not auth.USERNAME_RE.match(username):
        return err(400, "用户名 2-64 位，只能包含字母、数字和 _ . - @")
    if not auth.valid_password(b.get("password")):
        return err(400, "密码至少 8 位")
    return ok(_new_pending(purpose="install", username=username, password_hash=auth.hash_password(b["password"])))


async def install_finish(request: Request):
    b = await body_of(request)
    p = _pending.get(str(b.get("token", "")))
    if not p or p["purpose"] != "install" or p["exp"] < time.time():
        return err(400, "设置已过期，请重新开始")
    step = security.verify_totp(p["secret"], str(b.get("code", "")))
    if step is None:
        return err(400, "动态码不正确，请确认手机时间准确后重试")

    def create(c):
        if c.execute("SELECT COUNT(*) FROM admins").fetchone()[0]:
            return None  # 并发保护
        cur = c.execute("INSERT INTO admins (username, password_hash, totp_secret, last_totp_step, created_at, last_login_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (p["username"], p["password_hash"], p["secret"], step, int(time.time()), int(time.time())))
        return dict(c.execute("SELECT * FROM admins WHERE id = ?", (cur.lastrowid,)).fetchone())

    admin = await store.run(create)
    _pending.pop(str(b.get("token")), None)
    if not admin:
        return err(409, "已经安装过了，请直接登录")
    await track.log(request, "admin", "install", user_id=admin["id"], email=admin["username"], device=b.get("device"))
    resp = ok({"admin": pub_admin(admin)})
    auth.login_admin(resp, request, admin)
    return resp


async def login(request: Request):
    b = await body_of(request)
    username = str(b.get("username", "")).strip()
    if auth.rate_limited(f"aip:{client_ip(request)}", f"admin:{username.lower()}", limit=8):
        return err(429, "尝试次数过多，请 15 分钟后再试")
    if security.turnstile_active("turnstile.on_admin_login"):
        passed, reason = await security.verify_turnstile(str(b.get("turnstile", "")))
        cache.set_status("turnstile", passed, "最近一次校验通过" if passed else f"校验失败：{reason}")
        if not passed:
            return err(400, f"人机验证未通过：{reason}")
    admin = await store.query_one("SELECT * FROM admins WHERE username = ?", (username,))
    dev = b.get("device")
    if not admin or not auth.verify_password(str(b.get("password", "")), admin["password_hash"]):
        await track.log(request, "admin", "login_fail", user_id=admin["id"] if admin else None, email=username,
                        reason="密码错误" if admin else "管理员不存在", device=dev)
        return err(401, "用户名、密码或动态码错误")
    step = security.verify_totp(admin["totp_secret"], str(b.get("code", "")), admin["last_totp_step"])
    if step is None:
        await track.log(request, "admin", "login_fail", user_id=admin["id"], email=username, reason="动态码错误", device=dev)
        return err(401, "用户名、密码或动态码错误")
    await track.log(request, "admin", "login_ok", user_id=admin["id"], email=username, device=dev)
    await store.execute("UPDATE admins SET last_totp_step = ?, last_login_at = ? WHERE id = ?", (step, int(time.time()), admin["id"]))
    auth.clear_attempts(f"admin:{username.lower()}")
    resp = ok({"admin": pub_admin(admin)})
    auth.login_admin(resp, request, admin)
    return resp


async def logout(request: Request):
    resp = ok({"ok": True})
    resp.delete_cookie(auth.ADMIN_COOKIE, path="/")
    return resp


# ================= 概览 / 数据源 =================
@admin_required
async def overview(request: Request, admin: dict[str, Any]):
    now = int(time.time())
    users = await store.query_one(
        """SELECT COUNT(*) AS total,
                  SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS new7,
                  SUM(CASE WHEN member_level > 0 AND (member_expires IS NULL OR member_expires > ?) THEN 1 ELSE 0 END) AS members
           FROM site_users""", (now - 7 * 86400, now))
    tel = await store.query_one(
        """SELECT SUM(CASE WHEN kind = 'error' THEN 1 ELSE 0 END) AS errors,
                  SUM(CASE WHEN kind = 'api' THEN 1 ELSE 0 END) AS api_fail,
                  AVG(CASE WHEN kind = 'load' THEN value END) AS avg_load,
                  SUM(CASE WHEN kind = 'load' THEN 1 ELSE 0 END) AS views
           FROM telemetry WHERE ts >= ?""", (now - 86400,))
    st = cache.all_status()
    return ok({
        "users": {k: users[k] or 0 for k in ("total", "new7", "members")},
        "telemetry": {k: tel[k] or 0 for k in ("errors", "api_fail", "avg_load", "views")},
        "sources": {
            "ok": sum(1 for v in st.values() if v.get("ok")),
            "failed": sum(1 for v in st.values() if not v.get("ok") and not v.get("disabled")),
            "off": sum(1 for v in st.values() if v.get("disabled")),
        },
        "online": cache.client_count(),
        "logs": runlog.counts(),
    })


@admin_required
async def sources(request: Request, admin: dict[str, Any]):
    st = cache.all_status()
    names = list(SOURCE_TITLES) + [k for k in st if k not in SOURCE_TITLES]
    return ok([{"name": n, "title": SOURCE_TITLES.get(n) or EXTRA_TITLES.get(n, n), **st.get(n, {})} for n in names])


@admin_required
async def source_run(request: Request, admin: dict[str, Any]):
    name = request.path_params["name"]
    mgr = state["manager"]
    if name not in mgr.names:
        return err(404, "没有这个数据源")
    mgr.trigger(name)
    return ok({"ok": True})


# ================= 设置 =================
@admin_required
async def settings_get(request: Request, admin: dict[str, Any]):
    return ok(settings.export_for_admin())


@admin_required
async def settings_put(request: Request, admin: dict[str, Any]):
    b = await body_of(request)
    try:
        changed = await settings.update(b.get("values") or {})
    except ValueError as e:
        return err(400, str(e))
    for key in b.get("clear") or []:
        await settings.clear_secret(str(key))
    if changed or b.get("clear"):
        logging.getLogger("admin").info("管理员 %s 修改了设置：%s", admin["username"],
                                        "、".join(sorted(changed | set(b.get("clear") or [])))[:500])
    return ok({"changed": sorted(changed), **settings.export_for_admin()})


@admin_required
async def smtp_test(request: Request, admin: dict[str, Any]):
    b = await body_of(request)
    to = str(b.get("to", "")).strip()
    if not auth.EMAIL_RE.match(to):
        return err(400, "收件邮箱格式不正确")
    if not security.smtp_configured():
        return err(400, "请先填写并保存 SMTP 服务器和发件人地址")
    try:
        await security.send_mail(to, f"{settings.get('site.name')}：测试邮件", "这是一封测试邮件，说明邮件服务配置正确。")
    except Exception as e:  # noqa: BLE001
        return err(400, f"发送失败：{e}")
    return ok({"ok": True})


@admin_required
async def turnstile_test(request: Request, admin: dict[str, Any]):
    passed, msg = await security.test_turnstile_secret()
    cache.set_status("turnstile", passed, msg)
    return ok({"ok": passed, "message": msg})


# ================= 前台用户 =================
def pub_user_admin(u: dict[str, Any], last: dict[str, Any] | None = None) -> dict[str, Any]:
    return {**auth.public_user(u), "is_active": bool(u["is_active"]), "member_level": u["member_level"],
            "created_at": u["created_at"], "last_login_at": u["last_login_at"],
            "last_ip": (last or {}).get("ip", ""), "last_country": (last or {}).get("country", ""), "last_risk": (last or {}).get("risk", "")}


@admin_required
async def users_list(request: Request, admin: dict[str, Any]):
    q = (request.query_params.get("q") or "").strip()
    try:
        offset = max(0, int(request.query_params.get("offset", "0")))
    except ValueError:
        offset = 0
    where, params = ("WHERE email LIKE ?", (f"%{q}%",)) if q else ("", ())
    total = (await store.query_one(f"SELECT COUNT(*) AS n FROM site_users {where}", params))["n"]
    rows = await store.query(f"SELECT * FROM site_users {where} ORDER BY id DESC LIMIT 50 OFFSET ?", (*params, offset))
    ids = [u["id"] for u in rows]
    last: dict[int, dict[str, Any]] = {}
    if ids:
        marks = ",".join("?" * len(ids))
        for r in await store.query(f"""SELECT e.user_id, e.ip, e.country, e.risk FROM login_events e
                JOIN (SELECT user_id, MAX(id) AS id FROM login_events WHERE realm = 'user' AND event = 'login_ok' AND user_id IN ({marks}) GROUP BY user_id) m
                ON e.id = m.id""", tuple(ids)):
            last[r["user_id"]] = r
    return ok({"total": total, "users": [pub_user_admin(u, last.get(u["id"])) for u in rows]})


@admin_required
async def users_patch(request: Request, admin: dict[str, Any]):
    uid = int(request.path_params["uid"])
    if not await store.query_one("SELECT 1 FROM site_users WHERE id = ?", (uid,)):
        return err(404, "用户不存在")
    b = await body_of(request)
    if "password" in b:
        if not auth.valid_password(b["password"]):
            return err(400, "密码至少 8 位")
        await store.execute("UPDATE site_users SET password_hash = ?, token_version = token_version + 1 WHERE id = ?",
                            (auth.hash_password(b["password"]), uid))
    if "is_active" in b:
        await store.execute("UPDATE site_users SET is_active = ?, token_version = token_version + 1 WHERE id = ?", (int(bool(b["is_active"])), uid))
    if "email_verified" in b:
        await store.execute("UPDATE site_users SET email_verified = ? WHERE id = ?", (int(bool(b["email_verified"])), uid))
    if "member_level" in b:
        try:
            level = max(0, int(b["member_level"]))
            expires = int(b["member_expires"]) if b.get("member_expires") else None
        except (TypeError, ValueError):
            return err(400, "会员参数不正确")
        before = await store.query_one("SELECT email, member_level FROM site_users WHERE id = ?", (uid,))
        await members.admin_grant(uid, level, expires, admin["username"])
        if level > 0 and before and not before["member_level"] and security.smtp_configured() and mailtpl.enabled("member"):
            try:
                await security.send_template(before["email"], "member", {
                    "expires": time.strftime("%Y-%m-%d", time.gmtime(expires)) if expires else "永久"}, str(request.base_url))
            except Exception as e:  # noqa: BLE001
                cache.set_status("smtp", False, f"发送会员通知失败：{e}")
    return ok(pub_user_admin(await store.query_one("SELECT * FROM site_users WHERE id = ?", (uid,))))


@admin_required
async def users_delete(request: Request, admin: dict[str, Any]):
    uid = int(request.path_params["uid"])
    await track.delete_user(uid)
    from . import universe
    await universe.refresh()
    return ok({"ok": True})


def _json_download(data: Any, filename: str) -> Response:
    return Response(json.dumps(data, ensure_ascii=False, indent=2), media_type="application/json; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})


@admin_required
async def users_export(request: Request, admin: dict[str, Any]):
    """导出某个用户的全部个人数据（GDPR 查阅/可携带权请求）。"""
    uid = int(request.path_params["uid"])
    data = await track.export_user(uid)
    if not data:
        return err(404, "用户不存在")
    await track.log(request, "admin", "export_user", user_id=admin["id"], email=admin["username"], reason=f"导出用户 {uid}")
    return _json_download(data, f"user-{uid}-data.json")


@admin_required
async def users_export_all(request: Request, admin: dict[str, Any]):
    """一键导出全部用户在服务器上的个人数据。"""
    ids = [r["id"] for r in await store.query("SELECT id FROM site_users ORDER BY id")]
    users = [await track.export_user(i) for i in ids]
    await track.log(request, "admin", "export_all", user_id=admin["id"], email=admin["username"], reason=f"导出 {len(ids)} 个用户")
    return _json_download({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "count": len(users), "users": users},
                          f"all-users-data-{time.strftime('%Y%m%d')}.json")


@admin_required
async def login_events(request: Request, admin: dict[str, Any]):
    q = request.query_params
    where, params = ["1=1"], []
    if q.get("realm") in ("user", "admin"):
        where.append("realm = ?"); params.append(q["realm"])
    if q.get("user_id"):
        where.append("user_id = ?"); params.append(int(q["user_id"]))
    if q.get("q"):
        where.append("(email LIKE ? OR ip LIKE ?)"); params += [f"%{q['q']}%", f"%{q['q']}%"]
    if q.get("risk") == "1":
        where.append("risk != ''")
    try:
        offset = max(0, int(q.get("offset", "0")))
    except ValueError:
        offset = 0
    w = " AND ".join(where)
    total = (await store.query_one(f"SELECT COUNT(*) AS n FROM login_events WHERE {w}", tuple(params)))["n"]
    rows = await store.query(f"SELECT * FROM login_events WHERE {w} ORDER BY id DESC LIMIT 100 OFFSET ?", (*params, offset))
    for r in rows:
        try:
            r["data"] = json.loads(r["data"])
        except ValueError:
            pass
    return ok({"total": total, "events": rows})


# ================= 邮件模板 =================
@admin_required
async def mail_preview(request: Request, admin: dict[str, Any]):
    b = await body_of(request)
    key = str(b.get("key", ""))
    if key not in mailtpl.TEMPLATES:
        return err(400, "没有这个模板")
    subject, body, html_body = mailtpl.render(key, {**mailtpl.common_values(str(request.base_url)), **mailtpl.SAMPLE})
    return ok({"subject": subject, "body": body, "html": html_body})


@admin_required
async def mail_preview_html(request: Request, admin: dict[str, Any]):
    """HTML 正文预览：放在沙箱里，禁止脚本，只允许内联样式和图片。"""
    key = request.query_params.get("key", "")
    if key not in mailtpl.TEMPLATES:
        return err(400, "没有这个模板")
    _, _, html_body = mailtpl.render(key, {**mailtpl.common_values(str(request.base_url)), **mailtpl.SAMPLE})
    return Response(html_body or "<p>（未设置 HTML 正文）</p>", media_type="text/html; charset=utf-8", headers={
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src * data:; sandbox",
        "X-Frame-Options": "SAMEORIGIN", "Cache-Control": "no-store"})


@admin_required
async def mail_test(request: Request, admin: dict[str, Any]):
    b = await body_of(request)
    key, to = str(b.get("key", "")), str(b.get("to", "")).strip()
    if key not in mailtpl.TEMPLATES:
        return err(400, "没有这个模板")
    if not auth.EMAIL_RE.match(to):
        return err(400, "收件邮箱格式不正确")
    if not security.smtp_configured():
        return err(400, "请先填写并保存 SMTP 服务器和发件人地址")
    try:
        await security.send_template(to, key, {**mailtpl.SAMPLE, "email": to}, str(request.base_url))
    except Exception as e:  # noqa: BLE001
        return err(400, f"发送失败：{e}")
    return ok({"ok": True})


# ================= 管理员 =================
@admin_required
async def admins_list(request: Request, admin: dict[str, Any]):
    rows = await store.query("SELECT * FROM admins ORDER BY id")
    return ok({"me": admin["id"], "admins": [pub_admin(a) for a in rows]})


@admin_required
async def admins_create_start(request: Request, admin: dict[str, Any]):
    b = await body_of(request)
    username = str(b.get("username", "")).strip()
    if not auth.USERNAME_RE.match(username):
        return err(400, "用户名 2-64 位，只能包含字母、数字和 _ . - @")
    if not auth.valid_password(b.get("password")):
        return err(400, "密码至少 8 位")
    if await store.query_one("SELECT 1 FROM admins WHERE username = ?", (username,)):
        return err(409, "用户名已存在")
    return ok(_new_pending(purpose="new_admin", username=username, password_hash=auth.hash_password(b["password"])))


@admin_required
async def admins_create_finish(request: Request, admin: dict[str, Any]):
    b = await body_of(request)
    p = _pending.get(str(b.get("token", "")))
    if not p or p["purpose"] != "new_admin" or p["exp"] < time.time():
        return err(400, "设置已过期，请重新开始")
    step = security.verify_totp(p["secret"], str(b.get("code", "")))
    if step is None:
        return err(400, "动态码不正确")
    if await store.query_one("SELECT 1 FROM admins WHERE username = ?", (p["username"],)):
        return err(409, "用户名已存在")
    await store.execute("INSERT INTO admins (username, password_hash, totp_secret, last_totp_step, created_at) VALUES (?, ?, ?, ?, ?)",
                        (p["username"], p["password_hash"], p["secret"], step, int(time.time())))
    _pending.pop(str(b.get("token")), None)
    return ok({"ok": True})


@admin_required
async def admins_delete(request: Request, admin: dict[str, Any]):
    aid = int(request.path_params["aid"])
    if aid == admin["id"]:
        return err(400, "不能删除自己")
    await store.execute("DELETE FROM admins WHERE id = ?", (aid,))
    return ok({"ok": True})


@admin_required
async def me_password(request: Request, admin: dict[str, Any]):
    b = await body_of(request)
    if not auth.verify_password(str(b.get("old_password", "")), admin["password_hash"]):
        return err(400, "原密码错误")
    if security.verify_totp(admin["totp_secret"], str(b.get("code", "")), admin["last_totp_step"]) is None:
        return err(400, "动态码不正确")
    if not auth.valid_password(b.get("new_password")):
        return err(400, "新密码至少 8 位")
    await store.execute("UPDATE admins SET password_hash = ?, token_version = token_version + 1 WHERE id = ?",
                        (auth.hash_password(b["new_password"]), admin["id"]))
    resp = ok({"ok": True})
    auth.login_admin(resp, request, await store.query_one("SELECT * FROM admins WHERE id = ?", (admin["id"],)))
    return resp


@admin_required
async def me_2fa_start(request: Request, admin: dict[str, Any]):
    return ok(_new_pending(purpose="rebind", admin_id=admin["id"], username=admin["username"]))


@admin_required
async def me_2fa_finish(request: Request, admin: dict[str, Any]):
    b = await body_of(request)
    p = _pending.get(str(b.get("token", "")))
    if not p or p["purpose"] != "rebind" or p["admin_id"] != admin["id"] or p["exp"] < time.time():
        return err(400, "设置已过期，请重新开始")
    step = security.verify_totp(p["secret"], str(b.get("code", "")))
    if step is None:
        return err(400, "动态码不正确")
    await store.execute("UPDATE admins SET totp_secret = ?, last_totp_step = ?, token_version = token_version + 1 WHERE id = ?",
                        (p["secret"], step, admin["id"]))
    _pending.pop(str(b.get("token")), None)
    resp = ok({"ok": True})
    auth.login_admin(resp, request, await store.query_one("SELECT * FROM admins WHERE id = ?", (admin["id"],)))
    return resp


# ================= 诊断数据 =================
@admin_required
async def telemetry_summary(request: Request, admin: dict[str, Any]):
    since = int(time.time()) - 14 * 86400
    daily = await store.query(
        """SELECT strftime('%Y-%m-%d', ts, 'unixepoch') AS day,
                  SUM(CASE WHEN kind = 'load' THEN 1 ELSE 0 END) AS views,
                  AVG(CASE WHEN kind = 'load' THEN value END) AS avg_load,
                  SUM(CASE WHEN kind = 'error' THEN 1 ELSE 0 END) AS errors,
                  SUM(CASE WHEN kind = 'api' THEN 1 ELSE 0 END) AS api_fail,
                  SUM(CASE WHEN kind = 'sse' THEN 1 ELSE 0 END) AS sse_drop
           FROM telemetry WHERE ts >= ? GROUP BY day ORDER BY day""", (since,))
    top = await store.query(
        """SELECT kind, message, path, COUNT(*) AS n, MAX(ts) AS last FROM telemetry
           WHERE ts >= ? AND kind IN ('error', 'api') GROUP BY kind, message, path ORDER BY n DESC LIMIT 20""", (since,))
    recent = await store.query("SELECT ts, kind, path, message, value, ua FROM telemetry WHERE kind IN ('error', 'api', 'sse') ORDER BY id DESC LIMIT 50")
    vitals = await store.query(
        """SELECT message AS name, COUNT(*) AS n, AVG(value) AS avg, MAX(value) AS max FROM telemetry
           WHERE ts >= ? AND kind = 'vitals' GROUP BY message ORDER BY message""", (since,))
    apis = await store.query(
        """SELECT path, COUNT(*) AS n, AVG(value) AS avg, MAX(value) AS max FROM telemetry
           WHERE ts >= ? AND kind = 'resource' AND value IS NOT NULL GROUP BY path ORDER BY avg DESC LIMIT 15""", (since,))
    try:
        limit = max(1, min(int(request.query_params.get("raw", "100")), 1000))
    except ValueError:
        limit = 100
    raw = await store.query("SELECT id, ts, kind, path, message, value, ua, sid, ip, data FROM telemetry ORDER BY id DESC LIMIT ?", (limit,))
    for r in raw:
        try:
            r["data"] = json.loads(r["data"] or "{}")
        except ValueError:
            pass
    total = (await store.query_one("SELECT COUNT(*) AS n FROM telemetry"))["n"]
    return ok({"daily": daily, "top": top, "recent": recent, "vitals": vitals, "apis": apis, "raw": raw, "total": total})


# ================= 卡密 =================
def _date_ts(v: Any) -> int | None:
    """“兑换截止日期” YYYY-MM-DD → 当天 23:59:59（UTC+8）。"""
    if not v:
        return None
    from datetime import date as _d, datetime as _dt, timedelta as _td, timezone as _tz
    d = _d.fromisoformat(str(v))
    return int(_dt(d.year, d.month, d.day, 23, 59, 59, tzinfo=_tz(_td(hours=8))).timestamp())


def _card_filter(q: Any) -> tuple[str, list[Any]]:
    where, params = ["1=1"], []
    if q.get("status") in ("unused", "used", "disabled"):
        where.append("status = ?"); params.append(q["status"])
    if q.get("batch"):
        where.append("batch = ?"); params.append(q["batch"])
    if q.get("q"):
        where.append("(code_norm LIKE ? OR used_email LIKE ? OR note LIKE ?)")
        params += [f"%{members.normalize(q['q'])}%", f"%{q['q']}%", f"%{q['q']}%"]
    return " AND ".join(where), params


@admin_required
async def cards_list(request: Request, admin: dict[str, Any]):
    q = request.query_params
    w, params = _card_filter(q)
    try:
        offset = max(0, int(q.get("offset", "0")))
    except ValueError:
        offset = 0
    total = (await store.query_one(f"SELECT COUNT(*) AS n FROM cards WHERE {w}", tuple(params)))["n"]
    rows = await store.query(f"SELECT * FROM cards WHERE {w} ORDER BY id DESC LIMIT 100 OFFSET ?", (*params, offset))
    stats = {r["status"]: r["n"] for r in await store.query("SELECT status, COUNT(*) AS n FROM cards GROUP BY status")}
    batches = await store.query("""SELECT batch, COUNT(*) AS total, SUM(status = 'unused') AS unused, SUM(status = 'used') AS used,
                                   MIN(days) AS days, MAX(created_at) AS created FROM cards GROUP BY batch ORDER BY created DESC LIMIT 200""")
    return ok({"total": total, "cards": rows, "stats": stats, "batches": batches})


@admin_required
async def cards_generate(request: Request, admin: dict[str, Any]):
    b = await body_of(request)
    try:
        codes = await members.generate(int(b.get("count") or 0), int(b.get("days") or 0), str(b.get("batch") or time.strftime("%Y%m%d-%H%M")),
                                       str(b.get("note") or ""), str(b.get("prefix") if b.get("prefix") is not None else "ZYLL"), _date_ts(b.get("valid_until")))
    except (TypeError, ValueError) as e:
        return err(400, str(e) if str(e) else "参数不正确")
    logging.getLogger("admin").info("管理员 %s 生成卡密 %d 张（%s 天，批次 %s）", admin["username"], len(codes), b.get("days"), b.get("batch"))
    return ok({"codes": codes})


@admin_required
async def cards_import(request: Request, admin: dict[str, Any]):
    b = await body_of(request)
    try:
        res = await members.import_codes(str(b.get("text") or "").splitlines(), int(b.get("days") or 0),
                                         str(b.get("batch") or f"导入-{time.strftime('%Y%m%d-%H%M')}"), str(b.get("note") or ""), _date_ts(b.get("valid_until")))
    except (TypeError, ValueError) as e:
        return err(400, str(e) if str(e) else "参数不正确")
    logging.getLogger("admin").info("管理员 %s 导入卡密 %d 张", admin["username"], res["imported"])
    return ok(res)


async def _card_target(b: dict[str, Any]) -> tuple[str, list[Any]]:
    ids = [int(x) for x in (b.get("ids") or []) if str(x).isdigit()][:5000]
    if ids:
        return f"id IN ({','.join('?' * len(ids))})", ids
    if b.get("batch"):
        return "batch = ?", [str(b["batch"])]
    raise ValueError("请选择卡密或批次")


@admin_required
async def cards_set_status(request: Request, admin: dict[str, Any]):
    b = await body_of(request)
    try:
        w, params = await _card_target(b)
    except ValueError as e:
        return err(400, str(e))
    disable = bool(b.get("disabled"))
    # 只改动未使用 / 已停用的，已使用的卡密保持原样（留作记录）
    n = await store.execute(f"UPDATE cards SET status = ? WHERE {w} AND status = ?",
                            ("disabled" if disable else "unused", *params, "unused" if disable else "disabled"))
    return ok({"changed": n})


@admin_required
async def cards_delete(request: Request, admin: dict[str, Any]):
    b = await body_of(request)
    try:
        w, params = await _card_target(b)
    except ValueError as e:
        return err(400, str(e))
    n = await store.execute(f"DELETE FROM cards WHERE {w} AND status != 'used'", tuple(params))
    logging.getLogger("admin").info("管理员 %s 删除卡密 %d 张", admin["username"], n)
    return ok({"deleted": n})


@admin_required
async def cards_export(request: Request, admin: dict[str, Any]):
    import csv
    import io
    w, params = _card_filter(request.query_params)
    rows = await store.query(f"SELECT * FROM cards WHERE {w} ORDER BY id", tuple(params))
    buf = io.StringIO()
    wr = csv.writer(buf)
    wr.writerow(["卡密", "天数(0=永久)", "批次", "状态", "兑换截止", "备注", "生成时间", "使用时间", "使用者"])
    st = {"unused": "未使用", "used": "已使用", "disabled": "已停用"}
    fmt_t = lambda v: time.strftime("%Y-%m-%d %H:%M", time.localtime(v)) if v else ""  # noqa: E731
    for r in rows:
        wr.writerow([r["code"], r["days"], r["batch"], st.get(r["status"], r["status"]), fmt_t(r["valid_until"]), r["note"],
                     fmt_t(r["created_at"]), fmt_t(r["used_at"]), r["used_email"] or ""])
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="cards-{time.strftime("%Y%m%d-%H%M")}.csv"'})


@admin_required
async def app_tokens_list(request: Request, admin: dict[str, Any]):
    rows = await store.query("""SELECT t.id, t.device_name, t.platform, t.app_version, t.created_at, t.last_used_at, t.last_ip, t.expires_at, t.revoked, u.email
                                FROM app_tokens t LEFT JOIN site_users u ON u.id = t.user_id
                                WHERE t.revoked = 0 AND t.expires_at > ? ORDER BY t.last_used_at DESC LIMIT 300""", (int(time.time()),))
    return ok({"devices": rows})


@admin_required
async def app_token_revoke(request: Request, admin: dict[str, Any]):
    await store.execute("UPDATE app_tokens SET revoked = 1 WHERE id = ?", (int(request.path_params["tid"]),))
    return ok({"ok": True})


@admin_required
async def member_log(request: Request, admin: dict[str, Any]):
    rows = await store.query("""SELECT l.*, u.email, c.code FROM member_log l LEFT JOIN site_users u ON u.id = l.user_id
                                LEFT JOIN cards c ON c.id = l.card_id ORDER BY l.id DESC LIMIT 200""")
    return ok({"log": rows})


@admin_required
async def runlog_list(request: Request, admin: dict[str, Any]):
    q = request.query_params
    try:
        since = int(q.get("since", "0"))
        limit = max(1, min(int(q.get("limit", "500")), 3000))
    except ValueError:
        since, limit = 0, 500
    return ok({"items": runlog.query(q.get("level", "INFO"), q.get("q", "")[:100], since, limit), "counts": runlog.counts()})


@admin_required
async def runlog_download(request: Request, admin: dict[str, Any]):
    p = runlog.log_file_path()
    if not p.exists():
        return err(404, "还没有日志文件")
    data = p.read_bytes()[-20 * 1024 * 1024:]
    return Response(data, media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="zyll-{time.strftime("%Y%m%d-%H%M")}.log"'})


@admin_required
async def telemetry_export(request: Request, admin: dict[str, Any]):
    rows = await store.query("SELECT * FROM telemetry ORDER BY id")
    for r in rows:
        try:
            r["data"] = json.loads(r["data"] or "{}")
        except ValueError:
            pass
    return _json_download(rows, f"telemetry-{time.strftime('%Y%m%d')}.json")


@admin_required
async def telemetry_clear(request: Request, admin: dict[str, Any]):
    await store.execute("DELETE FROM telemetry")
    return ok({"ok": True})


@admin_required
async def ai_test(request: Request, admin: dict[str, Any]):
    """测试 AI 接口：用与正式识别相同的方式（JSON 模式、关闭思考、流式）发一个很小的请求（会产生极少的费用）。
    接口报 400 时会自动调整参数重试，并返回调整了哪些参数。"""
    from . import ai_import, llm
    b = await body_of(request)
    kind = "vision" if b.get("kind") == "vision" else "text"
    c = llm.resolve(kind)
    if not (c["base"] and c["key"] and c["model"]):
        return err(400, "请先填写并保存服务商、API Key 和模型（自定义服务商还要填接口地址）")
    t0 = time.time()
    try:
        if kind == "vision":
            # 一张写着数字的小图太复杂，这里用 8×8 白图确认模型能接收图片，并且同时测试 JSON 模式
            png = ai_import._png_gray(8, 8, 8, bytes([255]) * 64, 1)
            msgs = [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + __import__("base64").b64encode(png).decode()}},
                                                 {"type": "text", "text": '这张图片是什么颜色？用 JSON 回答：{"color": "颜色"}'}]}]
            content, usage, _ = await llm.chat("vision", msgs, json_mode=settings.get("ai.mode") == "single", max_tokens=200, timeout=90)
        else:
            content, usage, _ = await llm.chat("text", [{"role": "system", "content": "只输出 JSON。"},
                                                        {"role": "user", "content": '请输出 JSON：{"ok": true}'}], json_mode=True, max_tokens=200, timeout=90)
    except llm.AIError as e:
        return err(400, f"连接失败：{e}")
    rules = await llm._learned(c)
    return ok({"ok": True, "reply": content[:200], "ms": int((time.time() - t0) * 1000), "usage": usage,
               "provider": c["provider"], "base": c["base"], "model": c["model"], "adjusted": rules})


@admin_required
async def ai_models(request: Request, admin: dict[str, Any]):
    """获取服务商账号下可用的模型列表（GET /models）；拿不到时返回预设的推荐模型。"""
    from . import llm
    kind = "vision" if request.query_params.get("kind") == "vision" else "text"
    c = llm.resolve(kind)
    preset = c["preset"]["vision" if kind == "vision" else "text"]
    if not c["base"] or not c["key"]:
        return ok({"models": [], "preset": preset, "error": "请先保存接口地址和 API Key"})
    try:
        models = await __import__("asyncio").to_thread(llm.list_models, kind)
    except llm.AIError as e:
        return ok({"models": [], "preset": preset, "error": str(e)[:300]})
    return ok({"models": models[:500], "preset": preset})


@admin_required
async def ai_providers(request: Request, admin: dict[str, Any]):
    from . import llm
    return ok({"providers": {k: {"name": v["name"], "base": v["base"], "text": v["text"], "vision": v["vision"], "note": v["note"]}
                             for k, v in llm.PROVIDERS.items()}})


@admin_required
async def ai_jobs(request: Request, admin: dict[str, Any]):
    rows = await store.query("""SELECT j.id, j.created_at, j.file_type, j.size, j.pages, j.mode, j.status, j.tokens_in, j.tokens_out, j.rows, j.error, j.ms, u.email
                                FROM ai_jobs j LEFT JOIN site_users u ON u.id = j.user_id ORDER BY j.id DESC LIMIT 100""")
    since = int(time.time()) - 86400
    day = await store.query_one("SELECT COUNT(*) AS n, COALESCE(SUM(tokens_in),0) AS ti, COALESCE(SUM(tokens_out),0) AS tout, "
                                "SUM(status='failed') AS failed FROM ai_jobs WHERE created_at > ?", (since,))
    month = await store.query_one("SELECT COUNT(*) AS n, COALESCE(SUM(tokens_in),0) AS ti, COALESCE(SUM(tokens_out),0) AS tout FROM ai_jobs WHERE created_at > ?",
                                  (int(time.time()) - 30 * 86400,))
    imports = await store.query_one("SELECT COUNT(*) AS n, COALESCE(SUM(trades),0) AS trades FROM import_batches WHERE undone = 0")
    return ok({"jobs": rows, "day": day, "month": month, "imports": imports})


# ================= 财经日历日程库 =================
CAL_FIELDS = ["id", "ts", "currency", "region", "title", "impact", "forecast", "previous", "actual", "source", "locked", "hidden", "pending_ts", "updated_at"]
CAL_CCY = {"USD", "EUR", "GBP", "JPY", "CNY", "CAD", "AUD", "NZD", "CHF", "ALL"}


def _cal():
    return state["manager"].cal if "manager" in state else None


async def _cal_publish() -> None:
    if (c := _cal()):
        await c.publish_window()


def _cal_parse(b: dict[str, Any], partial: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if "ts" in b or not partial:
        try:
            ts = int(b.get("ts"))
        except (TypeError, ValueError):
            raise ValueError("时间不正确") from None
        if not 946684800 < ts < 4102444800:
            raise ValueError("时间不正确")
        out["ts"] = ts
    if "currency" in b or not partial:
        cur = str(b.get("currency") or "").strip().upper()
        if cur not in CAL_CCY:
            raise ValueError("货币不正确（USD、EUR、GBP、JPY、CNY、CAD、AUD、NZD、CHF、ALL）")
        out["currency"] = cur
    if "title" in b or not partial:
        title = str(b.get("title") or "").strip()[:120]
        if not title:
            raise ValueError("请填写事件名称（建议与 Forex Factory 的英文名称一致，公布值才能自动对上）")
        out["title"] = title
    if "impact" in b or not partial:
        try:
            imp = int(b.get("impact", 2))
        except (TypeError, ValueError):
            raise ValueError("重要性不正确") from None
        if imp not in (0, 1, 2, 3):
            raise ValueError("重要性只能是 0~3")
        out["impact"] = imp
    for f in ("forecast", "previous", "actual"):
        if f in b:
            out[f] = str(b.get(f) or "").strip()[:30]
    for f in ("locked", "hidden"):
        if f in b:
            out[f] = 1 if b.get(f) else 0
    return out


@admin_required
async def cal_list(request: Request, admin: dict[str, Any]):
    q = request.query_params
    now = int(time.time())
    try:
        start = int(q.get("start") or now - 7 * 86400)
        end = int(q.get("end") or now + 100 * 86400)
    except ValueError:
        return err(400, "时间范围不正确")
    where, args = ["ts BETWEEN ? AND ?"], [start, end]
    if q.get("currency"):
        where.append("currency = ?")
        args.append(q["currency"].upper())
    if q.get("source") in ("official", "ff", "admin"):
        where.append("source = ?")
        args.append(q["source"])
    if q.get("impact"):
        where.append("impact >= ?")
        args.append(int(q["impact"]) if q["impact"].isdigit() else 0)
    if q.get("pending") == "1":
        where.append("pending_ts != 0")
    if q.get("hidden") != "1":
        where.append("hidden = 0")
    if q.get("q"):
        where.append("title LIKE ?")
        args.append(f"%{q['q'][:40]}%")
    rows = await store.query(f"SELECT {', '.join(CAL_FIELDS)} FROM econ_events WHERE {' AND '.join(where)} ORDER BY ts LIMIT 1000", tuple(args))
    stats = await store.query_one("""SELECT SUM(source='official') AS official, SUM(source='ff') AS ff, SUM(source='admin') AS admin,
                                     SUM(pending_ts != 0 AND hidden = 0) AS pending, SUM(hidden != 0) AS hidden, MAX(ts) AS last
                                     FROM econ_events WHERE ts >= ?""", (now - 86400,))
    from .econ_schedule import VERSION
    seed = await store.kv_get("cal_seed:version")
    return ok({"events": rows, "stats": stats, "seed_version": VERSION, "seeded": seed[0] if seed else None})


@admin_required
async def cal_add(request: Request, admin: dict[str, Any]):
    from .collectors.calendar import ORG_PAT, region_of
    try:
        e = _cal_parse(await body_of(request))
    except ValueError as ex:
        return err(400, str(ex))
    eid = "adm:" + secrets.token_hex(10)
    await store.execute("""INSERT INTO econ_events (id, ts, currency, region, title, impact, forecast, previous, actual, is_org, source, locked, updated_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?, 'admin', 1, ?)""",
                        (eid, e["ts"], e["currency"], region_of(e["currency"], e["title"]), e["title"], e["impact"], e.get("forecast", ""),
                         e.get("previous", ""), e.get("actual", ""), int(bool(ORG_PAT.search(e["title"])) or e["currency"] == "ALL"), int(time.time())))
    await _cal_publish()
    return ok({"id": eid})


@admin_required
async def cal_patch(request: Request, admin: dict[str, Any]):
    from .collectors.calendar import region_of
    eid = request.path_params["eid"][:64]
    row = await store.query_one("SELECT * FROM econ_events WHERE id = ?", (eid,))
    if not row:
        return err(404, "事件不存在")
    b = await body_of(request)
    try:
        ch = _cal_parse(b, partial=True)
    except ValueError as ex:
        return err(400, str(ex))
    if b.get("apply_pending"):
        if not row["pending_ts"]:
            return err(400, "没有待确认的时间")
        ch["ts"] = row["pending_ts"]
    if "ts" in ch or b.get("dismiss_pending"):
        ch["pending_ts"] = 0
    if "ts" in ch and "locked" not in ch:
        ch["locked"] = 1   # 手动改过时间：锁定，抓取不再改动
    if "currency" in ch or "title" in ch:
        ch["region"] = region_of(ch.get("currency", row["currency"]), ch.get("title", row["title"]))
    if not ch:
        return err(400, "没有要修改的内容")
    ch["updated_at"] = int(time.time())
    await store.execute(f"UPDATE econ_events SET {', '.join(f'{k} = ?' for k in ch)} WHERE id = ?", (*ch.values(), eid))
    await _cal_publish()
    return ok({"ok": True})


@admin_required
async def cal_delete(request: Request, admin: dict[str, Any]):
    """删除 = 隐藏（保留记录，抓取不会再加回来）；后台手动添加的可以彻底删除。"""
    eid = request.path_params["eid"][:64]
    row = await store.query_one("SELECT source FROM econ_events WHERE id = ?", (eid,))
    if not row:
        return err(404, "事件不存在")
    if request.query_params.get("purge") == "1" and row["source"] == "admin":
        await store.execute("DELETE FROM econ_events WHERE id = ?", (eid,))
    else:
        await store.execute("UPDATE econ_events SET hidden = 1, updated_at = ? WHERE id = ?", (int(time.time()), eid))
    await _cal_publish()
    return ok({"ok": True})


@admin_required
async def cal_bulk(request: Request, admin: dict[str, Any]):
    """批量操作：apply_pending（采用抓取到的时间）/ dismiss_pending / hide / unhide / lock / unlock。"""
    b = await body_of(request)
    ids = [str(x)[:64] for x in (b.get("ids") or [])][:2000]
    action = b.get("action")
    sql = {"apply_pending": "ts = pending_ts, pending_ts = 0", "dismiss_pending": "pending_ts = 0", "hide": "hidden = 1", "unhide": "hidden = 0",
           "lock": "locked = 1", "unlock": "locked = 0"}.get(action)
    if not sql or not ids:
        return err(400, "参数不正确")
    extra = " AND pending_ts != 0" if action == "apply_pending" else ""
    n = await store.run(lambda c: c.execute(f"UPDATE econ_events SET {sql}, updated_at = ? WHERE id IN ({','.join('?' * len(ids))}){extra}",
                                            (int(time.time()), *ids)).rowcount)
    await _cal_publish()
    return ok({"updated": n})


@admin_required
async def cal_import(request: Request, admin: dict[str, Any]):
    """批量导入：CSV，每行 日期,时间,货币,事件名称,重要性[,预测值,前值]；时间按所选时区。同一事件（货币+名称+日期）已存在则更新时间。"""
    import csv
    import io
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from .collectors.calendar import ORG_PAT, region_of, title_key
    b = await body_of(request)
    text = str(b.get("csv") or "")[:500_000]
    try:
        tz = ZoneInfo(str(b.get("tz") or "Asia/Shanghai"))
    except Exception:  # noqa: BLE001
        return err(400, "时区不正确")
    rows, errors = [], []
    for i, rec in enumerate(csv.reader(io.StringIO(text)), 1):
        if not rec or not "".join(rec).strip() or rec[0].strip().lower() in ("date", "日期"):
            continue
        rec = [x.strip() for x in rec] + [""] * 7
        try:
            dt = datetime.strptime(f"{rec[0].replace('/', '-')} {rec[1] or '00:00'}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
            e = _cal_parse({"ts": int(dt.timestamp()), "currency": rec[2], "title": rec[3], "impact": rec[4] or 2,
                            "forecast": rec[5], "previous": rec[6]})
        except ValueError as ex:
            errors.append(f"第 {i} 行：{ex}")
            continue
        rows.append(e)
    if len(rows) > 3000:
        return err(400, "一次最多导入 3000 行")
    if errors and not b.get("skip_errors"):
        return err(400, "有格式不正确的行，未导入", errors=errors[:50])
    now = int(time.time())
    added = updated = 0
    for e in rows:
        day = datetime.fromtimestamp(e["ts"], tz).date()
        lo = int(datetime(day.year, day.month, day.day, tzinfo=tz).timestamp())
        same = [r for r in await store.query("SELECT id, title, source FROM econ_events WHERE currency = ? AND ts BETWEEN ? AND ?",
                                             (e["currency"], lo - 36 * 3600, lo + 60 * 3600)) if title_key(r["title"]) == title_key(e["title"])]
        if same:
            await store.execute("UPDATE econ_events SET ts = ?, impact = ?, locked = 1, pending_ts = 0, hidden = 0, updated_at = ? WHERE id = ?",
                                (e["ts"], e["impact"], now, same[0]["id"]))
            updated += 1
        else:
            await store.execute("""INSERT INTO econ_events (id, ts, currency, region, title, impact, forecast, previous, is_org, source, locked, updated_at)
                                   VALUES (?,?,?,?,?,?,?,?,?, 'admin', 1, ?)""",
                                ("adm:" + secrets.token_hex(10), e["ts"], e["currency"], region_of(e["currency"], e["title"]), e["title"], e["impact"],
                                 e.get("forecast", ""), e.get("previous", ""), int(bool(ORG_PAT.search(e["title"])) or e["currency"] == "ALL"), now))
            added += 1
    await _cal_publish()
    return ok({"added": added, "updated": updated, "errors": errors[:50]})


@admin_required
async def cal_sync(request: Request, admin: dict[str, Any]):
    """立即写入内置官方日程并抓取未来 3 个月的日程。"""
    cal = _cal()
    if not cal:
        return err(503, "采集器未启动")
    msgs = []
    try:
        if (m := await cal.seed_official(force=True)):
            msgs.append(m)
        if (m := await cal.sync_months(force=True)):
            msgs.append(m)
    except Exception as e:  # noqa: BLE001
        msgs.append(f"抓取失败：{e}")
    await cal.publish_window()
    return ok({"messages": msgs})


# ================= 通胀数据 =================
@admin_required
async def infl_list(request: Request, admin: dict[str, Any]):
    from datetime import date
    from . import inflation
    today = date.today()
    start = inflation.month_add(f"{today.year:04d}-{today.month:02d}", -36)
    out = []
    admin_rows = await store.query("SELECT region, month, idx, yoy, updated_at FROM cpi_index WHERE src = 'admin' ORDER BY region, month DESC")
    for ccy, r in inflation.REGIONS.items():
        b = await inflation.build(ccy, start)
        tab = b["table"]
        rows = []
        for i, (m, v) in enumerate(tab):
            mom = (v / tab[i - 1][1] - 1) * 100 if i else None
            yoy = (v / tab[i - 12][1] - 1) * 100 if i >= 12 else None
            rows.append({"month": m, "idx": v, "src": b["sources"].get(m), "mom": mom, "yoy": yoy})
        counts: dict[str, int] = {}
        for row in rows[-24:]:
            counts[row["src"]] = counts.get(row["src"], 0) + 1
        out.append({"ccy": ccy, "region": r["name"], "yoy_12m": b["yoy_12m"], "last_known": b["last_known"], "approx": b["approx"],
                    "counts": counts, "rows": rows[-24:][::-1], "calendar_titles": r.get("cal") or [], "fred": r.get("fred"), "wb": r["wb"]})
    return ok({"regions": out, "admin": admin_rows, "sources": inflation.SRC_NAMES})


@admin_required
async def infl_put(request: Request, admin: dict[str, Any]):
    import re as _re
    from . import inflation
    b = await body_of(request)
    ccy = str(b.get("ccy") or "").upper()
    month = str(b.get("month") or "")
    if ccy not in inflation.REGIONS or not _re.fullmatch(r"(19|20)\d\d-(0[1-9]|1[0-2])", month):
        return err(400, "货币或月份不正确（月份格式 2026-09）")
    try:
        yoy = float(b["yoy"]) if b.get("yoy") not in (None, "") else None
        idx = float(b["idx"]) if b.get("idx") not in (None, "") else None
    except (TypeError, ValueError):
        return err(400, "数值不正确")
    if yoy is None and idx is None:
        return err(400, "请填写同比（%）或指数")
    if yoy is not None and not -50 < yoy < 1000:
        return err(400, "同比数值不合理")
    await store.execute("INSERT OR REPLACE INTO cpi_index (region, month, idx, yoy, src, updated_at) VALUES (?, ?, ?, ?, 'admin', ?)",
                        (ccy, month, idx, yoy, int(time.time())))
    inflation.invalidate()
    return ok({"ok": True})


@admin_required
async def infl_delete(request: Request, admin: dict[str, Any]):
    from . import inflation
    await store.execute("DELETE FROM cpi_index WHERE region = ? AND month = ? AND src = 'admin'",
                        (request.path_params["ccy"].upper()[:3], request.path_params["month"][:7]))
    inflation.invalidate()
    return ok({"ok": True})


routes = [
    Route("/api/admin/state", admin_state),
    Route("/api/admin/install/start", install_start, methods=["POST"]),
    Route("/api/admin/install/finish", install_finish, methods=["POST"]),
    Route("/api/admin/login", login, methods=["POST"]),
    Route("/api/admin/logout", logout, methods=["POST"]),
    Route("/api/admin/overview", overview),
    Route("/api/admin/sources", sources),
    Route("/api/admin/sources/{name}/run", source_run, methods=["POST"]),
    Route("/api/admin/settings", settings_get, methods=["GET"]),
    Route("/api/admin/settings", settings_put, methods=["PUT"]),
    Route("/api/admin/smtp/test", smtp_test, methods=["POST"]),
    Route("/api/admin/turnstile/test", turnstile_test, methods=["POST"]),
    Route("/api/admin/users", users_list),
    Route("/api/admin/users/{uid:int}", users_patch, methods=["PATCH"]),
    Route("/api/admin/users/{uid:int}", users_delete, methods=["DELETE"]),
    Route("/api/admin/users/{uid:int}/export", users_export),
    Route("/api/admin/users/export", users_export_all),
    Route("/api/admin/logins", login_events),
    Route("/api/admin/mail/preview", mail_preview, methods=["POST"]),
    Route("/api/admin/mail/test", mail_test, methods=["POST"]),
    Route("/api/admin/mail/preview.html", mail_preview_html),
    Route("/api/admin/telemetry/export", telemetry_export),
    Route("/api/admin/logs", runlog_list),
    Route("/api/admin/cards", cards_list),
    Route("/api/admin/cards/generate", cards_generate, methods=["POST"]),
    Route("/api/admin/cards/import", cards_import, methods=["POST"]),
    Route("/api/admin/cards/status", cards_set_status, methods=["POST"]),
    Route("/api/admin/cards/delete", cards_delete, methods=["POST"]),
    Route("/api/admin/cards/export.csv", cards_export),
    Route("/api/admin/member-log", member_log),
    Route("/api/admin/app/devices", app_tokens_list),
    Route("/api/admin/ai/test", ai_test, methods=["POST"]),
    Route("/api/admin/ai/jobs", ai_jobs),
    Route("/api/admin/inflation", infl_list),
    Route("/api/admin/inflation", infl_put, methods=["POST"]),
    Route("/api/admin/inflation/{ccy}/{month}", infl_delete, methods=["DELETE"]),
    Route("/api/admin/calendar", cal_list),
    Route("/api/admin/calendar", cal_add, methods=["POST"]),
    Route("/api/admin/calendar/bulk", cal_bulk, methods=["POST"]),
    Route("/api/admin/calendar/import", cal_import, methods=["POST"]),
    Route("/api/admin/calendar/sync", cal_sync, methods=["POST"]),
    Route("/api/admin/calendar/{eid}", cal_patch, methods=["PATCH"]),
    Route("/api/admin/calendar/{eid}", cal_delete, methods=["DELETE"]),
    Route("/api/admin/ai/models", ai_models),
    Route("/api/admin/ai/providers", ai_providers),
    Route("/api/admin/app/devices/{tid:int}", app_token_revoke, methods=["DELETE"]),
    Route("/api/admin/logs/download", runlog_download),
    Route("/api/admin/admins", admins_list, methods=["GET"]),
    Route("/api/admin/admins/start", admins_create_start, methods=["POST"]),
    Route("/api/admin/admins/finish", admins_create_finish, methods=["POST"]),
    Route("/api/admin/admins/{aid:int}", admins_delete, methods=["DELETE"]),
    Route("/api/admin/me/password", me_password, methods=["POST"]),
    Route("/api/admin/me/2fa/start", me_2fa_start, methods=["POST"]),
    Route("/api/admin/me/2fa/finish", me_2fa_finish, methods=["POST"]),
    Route("/api/admin/telemetry", telemetry_summary, methods=["GET"]),
    Route("/api/admin/telemetry", telemetry_clear, methods=["DELETE"]),
]
