"""会员与卡密。

- 卡密格式：ZYLL-XXXX-XXXX-XXXX（去掉易混淆的 0/O/1/I/L），兑换时忽略大小写、空格和横线；
- 每张卡密有天数（0 表示永久），可设批次、备注和“卡密有效期”（过期后不能再兑换）；
- 兑换是原子操作：同一张卡密并发兑换只有一个人能成功；
- 续期从“当前到期日”往后加（已过期则从现在加），永久卡把会员变为永久；
- 每次兑换、后台开通都记录在 member_log。
"""
from __future__ import annotations

import re
import secrets
import time
from typing import Any

from . import settings, store

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # 没有 0 O 1 I L
CODE_RE = re.compile(r"^[A-Z0-9]{6,40}$")


def enabled() -> bool:
    return bool(settings.get("membership.enabled"))


def normalize(code: str) -> str:
    return re.sub(r"[\s\-_]", "", str(code or "")).upper()


def new_code(prefix: str = "ZYLL", groups: int = 3) -> str:
    body = "-".join("".join(secrets.choice(ALPHABET) for _ in range(4)) for _ in range(groups))
    prefix = re.sub(r"[^A-Z0-9]", "", (prefix or "").upper())[:8]
    return f"{prefix}-{body}" if prefix else body


async def generate(count: int, days: int, batch: str, note: str = "", prefix: str = "ZYLL", valid_until: int | None = None) -> list[str]:
    if not 1 <= count <= 5000:
        raise ValueError("每次生成 1 到 5000 张")
    if days < 0 or days > 36500:
        raise ValueError("天数不正确（0 表示永久）")
    now = int(time.time())
    codes: list[str] = []
    existing = set()
    while len(codes) < count:
        c = new_code(prefix)
        n = normalize(c)
        if n in existing:
            continue
        existing.add(n)
        codes.append(c)

    def run(conn):
        # 极小概率与库里已有的重复：INSERT OR IGNORE 后检查实际插入数量
        before = conn.total_changes
        conn.executemany("INSERT OR IGNORE INTO cards (code, code_norm, days, batch, note, status, valid_until, created_at) VALUES (?,?,?,?,?,'unused',?,?)",
                         [(c, normalize(c), days, batch[:60], note[:200], valid_until, now) for c in codes])
        return conn.total_changes - before
    inserted = await store.run(run)
    if inserted != len(codes):
        dup = await store.query(f"SELECT code FROM cards WHERE code IN ({','.join('?' * len(codes))})", tuple(codes))
        have = {r["code"] for r in dup}
        codes = [c for c in codes if c in have]
    return codes


async def import_codes(lines: list[str], default_days: int, batch: str, note: str = "", valid_until: int | None = None) -> dict[str, Any]:
    """每行一个卡密，可写成“卡密,天数”。重复的、格式不对的会跳过并报告。"""
    rows, bad, seen = [], [], set()
    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        code, _, d = line.partition(",")
        code = code.strip()
        n = normalize(code)
        try:
            days = int(d.strip()) if d.strip() else default_days
        except ValueError:
            bad.append(f"第 {i} 行：天数不是数字")
            continue
        if not CODE_RE.match(n) or days < 0 or days > 36500:
            bad.append(f"第 {i} 行：格式不正确")
            continue
        if n in seen:
            bad.append(f"第 {i} 行：与前面重复")
            continue
        seen.add(n)
        rows.append((code.upper(), n, days))
    if len(rows) > 20000:
        raise ValueError("一次最多导入 20000 张")
    now = int(time.time())
    dup = []
    if rows:
        existing = await store.query(f"SELECT code_norm FROM cards WHERE code_norm IN ({','.join('?' * len(rows))})", tuple(r[1] for r in rows)) if len(rows) <= 900 else \
            [r for chunk in range(0, len(rows), 900) for r in await store.query(
                f"SELECT code_norm FROM cards WHERE code_norm IN ({','.join('?' * len(rows[chunk:chunk + 900]))})", tuple(x[1] for x in rows[chunk:chunk + 900]))]
        have = {r["code_norm"] for r in existing}
        dup = [r[0] for r in rows if r[1] in have]
        rows = [r for r in rows if r[1] not in have]
        await store.executemany("INSERT OR IGNORE INTO cards (code, code_norm, days, batch, note, status, valid_until, created_at) VALUES (?,?,?,?,?,'unused',?,?)",
                                [(c, n, d, batch[:60], note[:200], valid_until, now) for c, n, d in rows])
    return {"imported": len(rows), "duplicates": dup[:50], "duplicate_count": len(dup), "errors": bad[:50], "error_count": len(bad)}


def _expiry_after(u: dict[str, Any], days: int, now: float) -> int | None:
    """新的到期时间（None = 永久）。"""
    if days == 0:
        return None
    current = u["member_expires"] if u["member_level"] else None
    if u["member_level"] and current is None:
        return None  # 已经是永久会员
    start = max(now, current or 0)
    return int(start + days * 86400)


async def redeem(user: dict[str, Any], code: str, source: str = "web") -> dict[str, Any]:
    n = normalize(code)
    if not CODE_RE.match(n):
        raise ValueError("卡密格式不正确")
    if user["member_level"] and user["member_expires"] is None:
        raise ValueError("你已经是永久会员，无需再激活")
    now = time.time()

    def run(c):
        row = c.execute("SELECT * FROM cards WHERE code_norm = ?", (n,)).fetchone()
        if not row:
            return {"err": "卡密不存在，请检查是否输入正确"}
        row = dict(row)
        if row["status"] == "used":
            return {"err": "这张卡密已经被使用过了"}
        if row["status"] == "disabled":
            return {"err": "这张卡密已停用，请联系客服"}
        if row["valid_until"] and row["valid_until"] < now:
            return {"err": "这张卡密已过兑换有效期"}
        cur = c.execute("UPDATE cards SET status = 'used', used_at = ?, used_by = ?, used_email = ? WHERE id = ? AND status = 'unused'",
                        (int(now), user["id"], user["email"], row["id"]))
        if cur.rowcount != 1:
            return {"err": "这张卡密已经被使用过了"}  # 并发时另一人先兑换成功
        u = dict(c.execute("SELECT * FROM site_users WHERE id = ?", (user["id"],)).fetchone())
        new_exp = _expiry_after(u, row["days"], now)
        old = u["member_expires"] if u["member_level"] else 0
        c.execute("UPDATE site_users SET member_level = 1, member_expires = ? WHERE id = ?", (new_exp, user["id"]))
        c.execute("INSERT INTO member_log (user_id, ts, source, card_id, days, old_expires, new_expires) VALUES (?,?,?,?,?,?,?)",
                  (user["id"], int(now), source, row["id"], row["days"], old, new_exp))
        return {"days": row["days"], "expires": new_exp, "permanent": new_exp is None, "renewed": bool(u["member_level"] and old and old > now)}
    res = await store.run(run)
    if "err" in res:
        raise ValueError(res["err"])
    return res


async def admin_grant(uid: int, level: int, expires: int | None, admin: str) -> None:
    u = await store.query_one("SELECT member_level, member_expires FROM site_users WHERE id = ?", (uid,))
    await store.execute("UPDATE site_users SET member_level = ?, member_expires = ? WHERE id = ?", (level, expires, uid))
    await store.execute("INSERT INTO member_log (user_id, ts, source, card_id, days, old_expires, new_expires) VALUES (?,?,?,?,?,?,?)",
                        (uid, int(time.time()), f"admin:{admin}" if level else f"admin-revoke:{admin}", None, None,
                         (u or {}).get("member_expires"), expires))


def status(u: dict[str, Any] | None) -> dict[str, Any] | None:
    """前台可见的会员状态；会员模式关闭时返回 None（前台不显示任何会员信息）。"""
    if not enabled() or not u:
        return None
    active = bool(u["member_level"]) and (u["member_expires"] is None or u["member_expires"] > time.time())
    return {"active": active, "permanent": active and u["member_expires"] is None,
            "expires": u["member_expires"] if u["member_level"] else None,
            "expired": bool(u["member_level"]) and not active}
