"""“自选”和“行情 → 我的个股”是同一份股票清单的两个视图，这里负责双向同步。

规则：
- 任一处添加，另一处也添加（另一处已达上限时只加到当前处）；
- 在“自选”删除：两处都删除（交易记录也一并删除，前端已二次确认）；
- 在“行情”删除：从行情删除；若该股票在自选里没有交易记录，自选里也删除，有交易记录则保留，避免误删记录。
"""
from __future__ import annotations

import time

from . import settings, store


async def _count(uid: int, table: str) -> int:
    if table == "pf":
        row = await store.query_one("SELECT COUNT(*) AS n FROM pf_symbols WHERE user_id = ?", (uid,))
    else:
        row = await store.query_one("SELECT COUNT(*) AS n FROM user_quotes WHERE user_id = ? AND kind = 'stock'", (uid,))
    return row["n"] if row else 0


async def mirror_to_portfolio(uid: int, sym: str) -> None:
    if await store.query_one("SELECT 1 FROM pf_symbols WHERE user_id = ? AND symbol = ?", (uid, sym)):
        return
    n = await _count(uid, "pf")
    if n >= int(settings.get("portfolio.max_symbols") or 50):
        return
    await store.execute("INSERT OR IGNORE INTO pf_symbols (user_id, symbol, sort, created_at) VALUES (?, ?, ?, ?)", (uid, sym, n, int(time.time())))


async def mirror_to_quotes(uid: int, sym: str) -> None:
    if await store.query_one("SELECT 1 FROM user_quotes WHERE user_id = ? AND kind = 'stock' AND code = ?", (uid, sym)):
        return
    n = await _count(uid, "q")
    if n >= int(settings.get("sources.market.max_stocks") or 30):
        return
    await store.execute("INSERT OR IGNORE INTO user_quotes (user_id, kind, code, sort) VALUES (?, 'stock', ?, ?)", (uid, sym, n))


async def removed_from_quotes(uid: int, sym: str) -> bool:
    """返回 True 表示自选里因有交易记录而保留。"""
    if await store.query_one("SELECT 1 FROM pf_trades WHERE user_id = ? AND symbol = ? LIMIT 1", (uid, sym)):
        return True
    await store.execute("DELETE FROM pf_symbols WHERE user_id = ? AND symbol = ?", (uid, sym))
    return False


async def removed_from_portfolio(uid: int, sym: str) -> None:
    await store.execute("DELETE FROM user_quotes WHERE user_id = ? AND kind = 'stock' AND code = ?", (uid, sym))


async def merge_once() -> None:
    """升级后第一次启动：把两边已有的清单互相补齐。"""
    if await store.kv_get("lists:merged_v1"):
        return
    pf = await store.query("SELECT user_id, symbol FROM pf_symbols")
    q = await store.query("SELECT user_id, code FROM user_quotes WHERE kind = 'stock'")
    for r in pf:
        await mirror_to_quotes(r["user_id"], r["symbol"])
    for r in q:
        await mirror_to_portfolio(r["user_id"], r["code"])
    await store.kv_set("lists:merged_v1", "1")


async def user_symbols(uid: int) -> list[str]:
    a = await store.query("SELECT symbol FROM pf_symbols WHERE user_id = ? ORDER BY sort, created_at", (uid,))
    b = await store.query("SELECT code FROM user_quotes WHERE user_id = ? AND kind = 'stock' ORDER BY sort", (uid,))
    return list(dict.fromkeys([r["symbol"] for r in a] + [r["code"] for r in b]))
