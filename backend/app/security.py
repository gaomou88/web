"""安全相关：谷歌验证器（TOTP）、Cloudflare Turnstile、邮件发送。只用 Python 自带库。"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import secrets
import smtplib
import ssl
import struct
import time
import urllib.parse
import urllib.error
import urllib.request
from email.message import EmailMessage

from . import settings

# ---------------- TOTP（RFC 6238，兼容 Google Authenticator）----------------


def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp_uri(secret: str, account: str) -> str:
    issuer = settings.get("site.name") or "Zyll"
    label = urllib.parse.quote(f"{issuer}:{account}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={urllib.parse.quote(issuer)}&algorithm=SHA1&digits=6&period=30"


def _hotp(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    off = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[off:off + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{code:06d}"


def verify_totp(secret: str, code: str, last_step: int = 0) -> int | None:
    """校验 6 位动态码，允许前后各 30 秒误差。返回匹配的时间步（用于防止同一个码重复使用），不匹配返回 None。"""
    code = "".join(ch for ch in str(code) if ch.isdigit())
    if len(code) != 6:
        return None
    now = int(time.time()) // 30
    for step in (now - 1, now, now + 1):
        if step > last_step and hmac.compare_digest(_hotp(secret, step), code):
            return step
    return None


# ---------------- Cloudflare Turnstile ----------------
TURNSTILE_VERIFY = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def turnstile_active(flag: str) -> bool:
    """只有填了 Key、开关打开、且没有被应急环境变量关闭时才生效。"""
    if os.environ.get("ZYLL_DISABLE_TURNSTILE") == "1":
        return False
    return bool(settings.get(flag) and settings.get("turnstile.site_key") and settings.get("turnstile.secret_key"))


TURNSTILE_ERRORS = {
    "missing-input-secret": "没有填写 Secret Key",
    "invalid-input-secret": "Secret Key 不正确（请确认和 Site Key 属于同一个 Turnstile 站点）",
    "missing-input-response": "没有收到验证结果，请先完成人机验证",
    "invalid-input-response": "验证结果无效（可能 Site Key 和 Secret Key 不是同一个站点的）",
    "timeout-or-duplicate": "验证已过期或已被使用，请重新完成人机验证",
    "bad-request": "请求格式错误",
    "internal-error": "Cloudflare 内部错误，请稍后重试",
}


def _siteverify(secret: str, token: str) -> dict:
    data = urllib.parse.urlencode({"secret": secret, "response": token}).encode()
    req = urllib.request.Request(TURNSTILE_VERIFY, data=data, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:  # 4xx 时 Cloudflare 也会返回带错误码的 JSON
        body = e.read() if e.fp else b""
        try:
            return json.loads(body)
        except ValueError:
            raise RuntimeError(f"Cloudflare 返回 HTTP {e.code}") from e


async def verify_turnstile(token: str) -> tuple[bool, str]:
    """返回 (是否通过, 失败原因)。连接失败时重试一次。"""
    if not token:
        return False, TURNSTILE_ERRORS["missing-input-response"]
    secret = settings.get("turnstile.secret_key")
    last_err = ""
    for attempt in range(2):
        try:
            res = await asyncio.to_thread(_siteverify, secret, token)
        except Exception as e:  # noqa: BLE001 —— 网络问题
            last_err = f"服务器无法连接 Cloudflare 校验接口（challenges.cloudflare.com）：{type(e).__name__}: {e}"
            await asyncio.sleep(0.5)
            continue
        if res.get("success"):
            return True, ""
        codes = res.get("error-codes") or []
        reason = "；".join(TURNSTILE_ERRORS.get(c, c) for c in codes) or "Cloudflare 未说明原因"
        return False, reason
    return False, last_err


async def test_turnstile_secret() -> tuple[bool, str]:
    """后台“测试连接”：用一个假的验证结果去调用接口，根据返回的错误码判断网络和 Secret Key 是否正常。"""
    secret = settings.get("turnstile.secret_key")
    if not secret:
        return False, "还没有填写 Secret Key"
    try:
        res = await asyncio.to_thread(_siteverify, secret, "zyll-connectivity-test")
    except Exception as e:  # noqa: BLE001
        return False, f"服务器无法连接 Cloudflare（challenges.cloudflare.com）：{type(e).__name__}: {e}"
    codes = res.get("error-codes") or []
    if "invalid-input-secret" in codes or "missing-input-secret" in codes:
        return False, TURNSTILE_ERRORS["invalid-input-secret"]
    return True, "连接正常，Secret Key 有效"


# ---------------- 邮件 ----------------
def smtp_configured() -> bool:
    return bool(settings.get("smtp.host") and settings.get("smtp.from_addr"))


def _send(to: str, subject: str, body: str, html_body: str | None = None) -> None:
    msg = EmailMessage()
    msg["From"] = settings.get("smtp.from_addr")
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    host, port, mode = settings.get("smtp.host"), int(settings.get("smtp.port")), settings.get("smtp.security")
    user, pw = settings.get("smtp.username"), settings.get("smtp.password")
    ctx = ssl.create_default_context()
    if mode == "ssl":
        server: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=20, context=ctx)
    else:
        server = smtplib.SMTP(host, port, timeout=20)
        if mode == "starttls":
            server.starttls(context=ctx)
    try:
        if user:
            server.login(user, pw)
        server.send_message(msg)
    finally:
        server.quit()


async def send_mail(to: str, subject: str, body: str, html_body: str | None = None) -> None:
    await asyncio.to_thread(_send, to, subject, body, html_body)


async def send_template(to: str, key: str, values: dict, site_url: str = "") -> None:
    """按后台的邮件模板发送。"""
    from . import mailtpl
    subject, body, html_body = mailtpl.render(key, {**mailtpl.common_values(site_url), "email": to, **values})
    await send_mail(to, subject, body, html_body)
