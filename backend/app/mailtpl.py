"""邮件模板：管理员可在后台自定义主题和正文（纯文本，可选 HTML）。

占位符写成 {名称}，可用的占位符见 PLACEHOLDERS；未知的占位符原样保留。
"""
from __future__ import annotations

import html
import re
from typing import Any



def _get(key: str) -> Any:
    from . import settings  # 延迟导入：settings 本身也要读取这里的模板定义
    return settings.get(key)

TEMPLATES: dict[str, dict[str, str]] = {
    "verify": {
        "title": "邮箱验证",
        "subject": "{site_name}：请验证你的邮箱",
        "body": "你好，\n\n请在 {expires_hours} 小时内点击下面的链接完成邮箱验证：\n{link}\n\n如果这不是你的操作，请忽略本邮件。\n\n{site_name}\n{site_url}",
    },
    "reset": {
        "title": "找回密码",
        "subject": "{site_name}：重置密码",
        "body": "你好，\n\n有人（希望是你）申请重置 {email} 的密码。请在 {expires_minutes} 分钟内点击下面的链接设置新密码：\n{link}\n\n重置后所有设备都需要重新登录。如果这不是你的操作，请忽略本邮件，你的密码不会改变。\n\n{site_name}\n{site_url}",
    },
    "welcome": {
        "title": "注册欢迎",
        "subject": "欢迎加入 {site_name}",
        "body": "你好，\n\n你已使用 {email} 注册 {site_name}。\n现在可以登录查看经济日历、美股暗盘和期货数据。\n\n{site_url}\n\n{site_name}",
    },
    "login_alert": {
        "title": "新设备登录提醒",
        "subject": "{site_name}：你的账号在新设备上登录",
        "body": "你好，\n\n你的账号 {email} 于 {time}（UTC）登录。\n设备：{device}\nIP：{ip}  国家/地区：{country}\n提示：{risk}\n\n如果这不是你本人操作，请立即修改密码，并联系我们：{contact}\n\n{site_name}",
    },
    "member": {
        "title": "会员开通通知",
        "subject": "{site_name}：会员已开通",
        "body": "你好，\n\n你的会员已开通，有效期至 {expires}。\n\n{site_url}\n\n{site_name}",
    },
}

PLACEHOLDERS = {
    "site_name": "网站名称", "site_url": "网站地址", "email": "收件人邮箱", "link": "验证 / 重置链接", "expires_minutes": "链接有效分钟数",
    "expires_hours": "链接有效小时数", "time": "时间", "ip": "登录 IP", "country": "国家/地区", "device": "设备（浏览器信息）",
    "risk": "风险提示", "contact": "隐私/客服联系邮箱", "expires": "会员到期日",
}

_PH = re.compile(r"\{(\w+)\}")


def groups() -> list[dict[str, Any]]:
    """后台设置：每个模板一组（开关、主题、纯文本正文、可选 HTML 正文）。"""
    from .settings import F
    ph = "、".join(f"{{{k}}} {v}" for k, v in PLACEHOLDERS.items())
    out = []
    for key, t in TEMPLATES.items():
        fs = []
        if key not in ("verify", "reset"):
            fs.append(F(f"mail.{key}.enabled", "发送这类邮件", "bool", key == "login_alert",
                        "需要先配置上方的 SMTP" + ("；只在检测到新设备或新国家/地区登录时发送" if key == "login_alert" else "")))
        fs += [
            F(f"mail.{key}.subject", "主题", "str", t["subject"]),
            F(f"mail.{key}.body", "正文（纯文本）", "text", t["body"], f"可用占位符：{ph}"),
            F(f"mail.{key}.html", "HTML 正文（可选）", "text", "", "留空则只发纯文本；填写后同时发送 HTML 版本，占位符的值会自动转义"),
        ]
        out.append({"id": f"mail_{key}", "page": "mail", "title": f"邮件模板：{t['title']}", "template": key,
                    "desc": {"verify": "验证注册邮箱时发送（需开启“注册需验证邮箱”）", "reset": "用户点击“忘记密码”时发送"}.get(key, ""), "fields": fs})
    return out


def _fill(tpl: str, values: dict[str, Any], escape: bool) -> str:
    def rep(m: re.Match[str]) -> str:
        k = m.group(1)
        if k not in values:
            return m.group(0)
        v = str(values[k])
        return html.escape(v) if escape else v
    return _PH.sub(rep, tpl)


def common_values(site_url: str = "") -> dict[str, Any]:
    return {
        "site_name": _get("site.name"),
        "site_url": (_get("smtp.site_url") or site_url).rstrip("/"),
        "contact": _get("privacy.contact_email") or _get("smtp.from_addr") or "",
    }


def enabled(key: str) -> bool:
    return key in ("verify", "reset") or bool(_get(f"mail.{key}.enabled"))


def render(key: str, values: dict[str, Any]) -> tuple[str, str, str | None]:
    """返回 (主题, 纯文本正文, HTML 正文或 None)。"""
    t = TEMPLATES[key]
    subject = _fill(_get(f"mail.{key}.subject") or t["subject"], values, False).replace("\n", " ")[:200]
    body = _fill(_get(f"mail.{key}.body") or t["body"], values, False)
    raw_html = (_get(f"mail.{key}.html") or "").strip()
    return subject, body, _fill(raw_html, values, True) if raw_html else None


SAMPLE = {"email": "user@example.com", "link": "https://example.com/api/auth/verify?token=示例", "expires_hours": 24, "expires_minutes": 30,
          "time": "2026-10-22 08:30", "ip": "203.0.113.7", "country": "DE", "device": "Chrome 141 / Windows",
          "risk": "新设备，新网络", "expires": "2027-10-22"}
