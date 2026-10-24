"""账号与会话（只用 Python 自带库）。

- 前台用户（邮箱登录）与后台管理员是两套独立的账号和 Cookie。
- 密码：scrypt 加盐哈希；会话：HMAC 签名的 httpOnly Cookie，改密码 / 停用后旧会话立即失效。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from typing import Any

from starlette.requests import Request
from starlette.responses import Response

from . import store
from .config import get_settings

USER_COOKIE = "zy_user"
ADMIN_COOKIE = "zy_admin"
USER_HOURS = 24 * 30
ADMIN_HOURS = 12
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-@]{2,64}$")
_N, _R, _P = 2**14, 8, 1


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, dk = stored.split("$")
        got = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=len(bytes.fromhex(dk)))
        return hmac.compare_digest(got.hex(), dk)
    except (ValueError, TypeError):
        return False


def valid_password(pw: Any) -> bool:
    return isinstance(pw, str) and 8 <= len(pw) <= 256


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _key(kind: str) -> bytes:
    return hmac.new(get_settings().secret_key.encode(), kind.encode(), hashlib.sha256).digest()


def _issue(kind: str, uid: int, ver: int, hours: int) -> str:
    payload = _b64(json.dumps({"k": kind, "uid": uid, "ver": ver, "exp": int(time.time()) + hours * 3600}).encode())
    return f"{payload}.{_b64(hmac.new(_key(kind), payload.encode(), hashlib.sha256).digest())}"


def _read(kind: str, token: str | None) -> dict[str, Any] | None:
    if not token or "." not in token:
        return None
    payload, sig = token.rsplit(".", 1)
    expect = _b64(hmac.new(_key(kind), payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expect):
        return None
    try:
        data = json.loads(_unb64(payload))
    except ValueError:
        return None
    if data.get("k") != kind or data.get("exp", 0) < time.time():
        return None
    return data


def set_cookie(resp: Response, request: Request, name: str, value: str, hours: int) -> None:
    resp.set_cookie(name, value, httponly=True, samesite="lax", secure=request.url.scheme == "https",
                    max_age=hours * 3600, path="/")


# ---------- 前台用户 ----------
def login_user(resp: Response, request: Request, user: dict[str, Any]) -> None:
    set_cookie(resp, request, USER_COOKIE, _issue("user", user["id"], user["token_version"], USER_HOURS), USER_HOURS)


def bearer_token(request: Any) -> str | None:
    h = request.headers.get("authorization") or ""
    return h[7:].strip() if h[:7].lower() == "bearer " and len(h) > 20 else None


async def user_from_token(token: str, ip: str = "") -> dict[str, Any] | None:
    """安卓 App 的访问令牌：数据库只存哈希；改密码 / 停用账号 / 后台撤销后立即失效；使用时自动续期。"""
    import hashlib
    th = hashlib.sha256(token.encode()).hexdigest()
    row = await store.query_one("SELECT * FROM app_tokens WHERE token_hash = ?", (th,))
    now = int(time.time())
    if not row or row["revoked"] or row["expires_at"] < now:
        return None
    u = await store.query_one("SELECT * FROM site_users WHERE id = ?", (row["user_id"],))
    if not u or not u["is_active"] or u["token_version"] != row["user_ver"]:
        return None
    if now - row["last_used_at"] > 300:  # 最多 5 分钟写一次，减少数据库写入
        from . import settings as _s
        days = int(_s.get("app.token_days") or 90)
        await store.execute("UPDATE app_tokens SET last_used_at = ?, last_ip = ?, expires_at = ? WHERE id = ?",
                            (now, ip[:64], now + days * 86400, row["id"]))
    u["_token_id"] = row["id"]
    return u


async def current_user(request: Request) -> dict[str, Any] | None:
    cached = getattr(request.state, "user", "unset") if hasattr(request, "state") else "unset"
    if cached != "unset":
        return cached
    tok = bearer_token(request)
    if tok:
        u = await user_from_token(tok, request.client.host if request.client else "")
    else:
        u = None
        data = _read("user", request.cookies.get(USER_COOKIE))
        if data:
            u = await store.query_one("SELECT * FROM site_users WHERE id = ?", (data["uid"],))
            if not u or not u["is_active"] or u["token_version"] != data.get("ver"):
                u = None
    try:
        request.state.user = u
    except AttributeError:
        pass
    return u


def is_member(u: dict[str, Any] | None) -> bool:
    if not u or not u["member_level"]:
        return False
    return not u["member_expires"] or u["member_expires"] > time.time()


def public_user(u: dict[str, Any]) -> dict[str, Any]:
    """会员模式关闭时不返回任何会员字段（前台完全不出现会员信息）。"""
    from . import members
    out = {"id": u["id"], "email": u["email"], "email_verified": bool(u["email_verified"])}
    st = members.status(u)
    if st is not None:
        out.update(is_member=st["active"], member_expires=st["expires"], membership=st)
    return out


# ---------- 后台管理员 ----------
def login_admin(resp: Response, request: Request, admin: dict[str, Any]) -> None:
    set_cookie(resp, request, ADMIN_COOKIE, _issue("admin", admin["id"], admin["token_version"], ADMIN_HOURS), ADMIN_HOURS)


async def current_admin(request: Request) -> dict[str, Any] | None:
    data = _read("admin", request.cookies.get(ADMIN_COOKIE))
    if not data:
        return None
    a = await store.query_one("SELECT * FROM admins WHERE id = ?", (data["uid"],))
    if not a or a["token_version"] != data.get("ver"):
        return None
    return a


async def admin_installed() -> bool:
    row = await store.query_one("SELECT COUNT(*) AS n FROM admins")
    return bool(row and row["n"])


# ---------- 防暴力破解 ----------
_attempts: dict[str, list[float]] = {}


def rate_limited(*keys: str, limit: int = 10, window: int = 900) -> bool:
    now = time.time()
    blocked = False
    for k in keys:
        hits = [t for t in _attempts.get(k, []) if now - t < window]
        hits.append(now)
        _attempts[k] = hits
        blocked = blocked or len(hits) > limit
    if len(_attempts) > 20000:
        for k in [k for k, v in _attempts.items() if not v or now - v[-1] > window]:
            _attempts.pop(k, None)
    return blocked


def clear_attempts(key: str) -> None:
    _attempts.pop(key, None)
