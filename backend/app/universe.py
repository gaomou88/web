"""需要实时行情的股票集合：会员自选股 + 用户在“行情”页添加的个股 + 后台关注股票。"""
from __future__ import annotations

import asyncio

from . import settings, store

_counts: dict[str, int] = {}
_quote_counts: dict[str, int] = {}
_listeners: list[asyncio.Event] = []


async def refresh() -> None:
    rows = await store.query("SELECT symbol, COUNT(*) AS n FROM pf_symbols GROUP BY symbol")
    _counts.clear()
    _counts.update({r["symbol"]: r["n"] for r in rows})
    rows = await store.query("SELECT code, COUNT(*) AS n FROM user_quotes WHERE kind = 'stock' GROUP BY code")
    _quote_counts.clear()
    _quote_counts.update({r["code"]: r["n"] for r in rows})
    for ev in list(_listeners):
        ev.set()


def listener() -> asyncio.Event:
    ev = asyncio.Event()
    _listeners.append(ev)
    return ev


def drop_listener(ev: asyncio.Event) -> None:
    if ev in _listeners:
        _listeners.remove(ev)


def portfolio_symbols() -> list[str]:
    """按关注人数从多到少排序。"""
    return [s for s, _ in sorted(_counts.items(), key=lambda kv: (-kv[1], kv[0]))]


def quote_symbols() -> list[str]:
    return [s for s, _ in sorted(_quote_counts.items(), key=lambda kv: (-kv[1], kv[0]))]


def market_symbols() -> list[str]:
    """优先会员自选股，其次用户在行情页添加的个股，最后后台关注股票。"""
    return list(dict.fromkeys(portfolio_symbols() + quote_symbols() + settings.get_list("sources.market.watchlist")))


def realtime_symbols(limit: int) -> list[str]:
    return market_symbols()[:limit]
