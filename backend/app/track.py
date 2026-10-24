"""登录安全记录（防欺诈）与个人数据导出 / 删除（GDPR 第 15、17、20 条）。

法律依据：GDPR 第 6(1)(f) 条“正当利益”——防止账号被盗用和欺诈。
记录内容在隐私政策中公开说明，按后台设置的天数自动删除。
只记录与识别异常登录直接相关的技术信息，不读取浏览器里的其他网站数据，不做画布/音频指纹。
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import time
from typing import Any

from starlette.requests import Request

from . import settings, store
from .common import client_ip

# 前端随登录/注册请求提交的设备信息（白名单 + 长度限制）
DEVICE_KEYS = {
    "tz": 64, "tzOffset": 8, "langs": 120, "platform": 64, "screen": 32, "viewport": 32, "dpr": 8, "colorDepth": 4,
    "cores": 4, "memory": 6, "touch": 4, "webdriver": 6, "cookies": 6, "dnt": 8, "pdf": 6, "uaData": 300,
}
# 用于计算设备标识的稳定字段
HASH_KEYS = ("tz", "langs", "platform", "screen", "dpr", "colorDepth", "cores", "memory", "touch")
_last_cleanup = [0.0]


def clean_device(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    out = {}
    for k, limit in DEVICE_KEYS.items():
        v = raw.get(k)
        if v is None:
            continue
        out[k] = (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v))[:limit]
    return out


def request_meta(request: Request) -> dict[str, str]:
    h = request.headers
    ref = h.get("referer") or ""
    return {
        "ip": client_ip(request),
        "ip_chain": (h.get("x-forwarded-for") or "")[:300],
        "country": (h.get("cf-ipcountry") or "")[:4],
        "ua": (h.get("user-agent") or "")[:400],
        "accept_language": (h.get("accept-language") or "")[:120],
        "sec_ch_ua": (h.get("sec-ch-ua") or "")[:200],
        "sec_ch_platform": (h.get("sec-ch-ua-platform") or "")[:40],
        "sec_ch_mobile": (h.get("sec-ch-ua-mobile") or "")[:4],
        "referer_origin": "/".join(ref.split("/")[:3])[:120],
        "cf_ray": (h.get("cf-ray") or "")[:40],
    }


def device_hash(meta: dict[str, str], device: dict[str, str]) -> str:
    parts = [meta.get("ua", "")] + [device.get(k, "") for k in HASH_KEYS]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def _net(ip: str) -> str:
    """同一网段（IPv4 /24、IPv6 /48）视为同一网络。"""
    try:
        a = ipaddress.ip_address(ip)
        return str(ipaddress.ip_network(f"{ip}/{24 if a.version == 4 else 48}", strict=False))
    except ValueError:
        return ip


async def _risk(realm: str, user_id: int | None, email: str, meta: dict[str, str], dev_hash: str, device: dict[str, str], event: str) -> list[str]:
    flags = []
    if device.get("webdriver") == "true":
        flags.append("自动化浏览器")
    if not device and event in ("login_ok", "register", "login_fail"):
        flags.append("未提交设备信息")
    since = int(time.time()) - 3600
    fails = await store.query_one("SELECT COUNT(*) AS n FROM login_events WHERE realm = ? AND event = 'login_fail' AND ts >= ? AND (email = ? OR ip = ?)",
                                  (realm, since, email, meta["ip"]))
    if fails and fails["n"] >= 3:
        flags.append(f"1 小时内失败 {fails['n']} 次")
    if user_id and event == "login_ok":
        prev = await store.query("SELECT ip, country, device_hash FROM login_events WHERE realm = ? AND user_id = ? AND event = 'login_ok' ORDER BY id DESC LIMIT 50",
                                 (realm, user_id))
        if prev:
            if dev_hash not in {p["device_hash"] for p in prev}:
                flags.append("新设备")
            if meta["country"] and meta["country"] not in {p["country"] for p in prev if p["country"]}:
                flags.append(f"新国家/地区 {meta['country']}")
            if _net(meta["ip"]) not in {_net(p["ip"]) for p in prev}:
                flags.append("新网络")
    return flags


async def log(request: Request, realm: str, event: str, *, user_id: int | None = None, email: str = "",
              reason: str = "", device: Any = None) -> list[str]:
    """记录一次账号事件，返回风险标记（例如“新设备”）。"""
    if not settings.get("privacy.login_log"):
        return []
    meta = request_meta(request)
    dev = clean_device(device)
    dh = device_hash(meta, dev)
    flags = await _risk(realm, user_id, email.lower(), meta, dh, dev, event)
    data = {**{k: v for k, v in meta.items() if k not in ("ip", "ip_chain", "country", "ua")}, "device": dev}
    await store.execute(
        """INSERT INTO login_events (ts, realm, user_id, email, event, reason, ip, ip_chain, country, ua, device_hash, risk, data)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (int(time.time()), realm, user_id, email.lower()[:254], event, reason[:200], meta["ip"], meta["ip_chain"], meta["country"],
         meta["ua"], dh, "，".join(flags), json.dumps(data, ensure_ascii=False)))
    now = time.time()
    if now - _last_cleanup[0] > 3600:
        _last_cleanup[0] = now
        days = max(1, int(settings.get("privacy.login_log_days") or 180))
        await store.execute("DELETE FROM login_events WHERE ts < ?", (int(now) - days * 86400,))
    return flags


# ---------------- 个人数据导出 / 删除 ----------------
def _ts(v: Any) -> Any:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(v)) if isinstance(v, (int, float)) and v > 1e9 else v


async def export_user(uid: int) -> dict[str, Any] | None:
    """某个用户在服务器上的全部个人数据（不含密码哈希等安全凭据）。"""
    u = await store.query_one("SELECT * FROM site_users WHERE id = ?", (uid,))
    if not u:
        return None
    account = {k: _ts(v) for k, v in u.items() if k not in ("password_hash", "token_version")}
    events = await store.query(
        "SELECT ts, event, reason, ip, ip_chain, country, ua, device_hash, risk, data FROM login_events WHERE realm = 'user' AND (user_id = ? OR email = ?) ORDER BY id",
        (uid, u["email"].lower()))
    for e in events:
        e["ts"] = _ts(e["ts"])
        try:
            e["data"] = json.loads(e["data"])
        except ValueError:
            pass
    return {
        "export_generated_at": _ts(time.time()),
        "controller": settings.get("privacy.controller") or settings.get("site.name"),
        "data_subject": u["email"],
        "account": account,
        "portfolio": {
            "settings": await store.query_one("SELECT base_currency, fx_mode FROM pf_settings WHERE user_id = ?", (uid,)),
            "symbols": [{**r, "created_at": _ts(r["created_at"])} for r in await store.query(
                "SELECT symbol, note, target, stop, sort, created_at FROM pf_symbols WHERE user_id = ? ORDER BY sort", (uid,))],
            "trades": [{**r, "created_at": _ts(r["created_at"])} for r in await store.query(
                "SELECT id, symbol, side, trade_date, shares, price, ccy, fx, fee, note, funding, created_at FROM pf_trades WHERE user_id = ? ORDER BY trade_date, id", (uid,))],
        },
        "cash_moves": await store.query("SELECT kind, trade_date, ccy, amount, note, batch FROM cash_moves WHERE user_id = ? ORDER BY trade_date, id", (uid,)),
        "app_devices": await store.query("SELECT device_name, platform, app_version, created_at, last_used_at, last_ip, revoked FROM app_tokens WHERE user_id = ?", (uid,)),
        "ai_imports": await store.query("SELECT created_at, file_type, size, pages, mode, status, rows, error FROM ai_jobs WHERE user_id = ? ORDER BY id", (uid,)),
        "import_batches": await store.query("SELECT id, created_at, source, trades, cash, undone FROM import_batches WHERE user_id = ? ORDER BY created_at", (uid,)),
        "membership_log": await store.query("SELECT ts, source, days, old_expires, new_expires FROM member_log WHERE user_id = ? ORDER BY id", (uid,)),
        "market_lists": await store.query("SELECT kind, code, sort FROM user_quotes WHERE user_id = ? ORDER BY kind, sort", (uid,)),
        "payments": [{**r, "created_at": _ts(r["created_at"])} for r in await store.query(
            "SELECT provider, plan, amount, currency, status, external_id, created_at FROM payments WHERE user_id = ? ORDER BY id", (uid,))],
        "security_log": events,
        "notes": [
            "诊断数据（性能 Cookie）不与账号关联，IP 已截断，因此无法按账号导出。",
            "Diagnostics data is not linked to accounts and IPs are truncated, so it cannot be exported per account.",
        ],
    }


async def delete_user(uid: int) -> None:
    """删除账号及其全部个人数据。安全日志中的该用户记录一并删除（GDPR 第 17 条）。"""
    u = await store.query_one("SELECT email FROM site_users WHERE id = ?", (uid,))

    def run(c):
        for sql in ("DELETE FROM pf_trades WHERE user_id = ?", "DELETE FROM pf_symbols WHERE user_id = ?",
                    "DELETE FROM pf_settings WHERE user_id = ?", "DELETE FROM email_tokens WHERE user_id = ?",
                    "DELETE FROM user_quotes WHERE user_id = ?", "DELETE FROM cash_moves WHERE user_id = ?",
                    "DELETE FROM app_tokens WHERE user_id = ?", "DELETE FROM member_log WHERE user_id = ?",
                    "DELETE FROM login_events WHERE realm = 'user' AND user_id = ?", "DELETE FROM ai_jobs WHERE user_id = ?",
                    "DELETE FROM import_batches WHERE user_id = ?", "DELETE FROM app_codes WHERE user_id = ?", "DELETE FROM site_users WHERE id = ?"):
            c.execute(sql, (uid,))
        if u:
            c.execute("DELETE FROM login_events WHERE realm = 'user' AND email = ?", (u["email"].lower(),))
    await store.run(run)
