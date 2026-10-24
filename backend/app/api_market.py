"""行情页接口：指数（每人最多 5 个）、个股（登录后自行添加）、成交最多。"""
from __future__ import annotations

import re
import time
from typing import Any

from starlette.requests import Request
from starlette.routing import Route

from . import auth, cache, holidays, lists, settings, store, universe
from .api_public import locked, members_only
from .collectors.market import DEFAULT_INDICES, INDEX_CATALOG, MAX_INDICES, market_session
from .common import body_of, err, ok

state: dict[str, Any] = {}  # main.py 注入 market 采集器
SYM_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def default_indices() -> list[str]:
    codes = [c for c in (settings.get_list("sources.market.default_indices") or DEFAULT_INDICES) if c in INDEX_CATALOG]
    return codes[:MAX_INDICES] or DEFAULT_INDICES


async def _user_lists(uid: int) -> tuple[list[str] | None, list[str]]:
    rows = await store.query("SELECT kind, code FROM user_quotes WHERE user_id = ? ORDER BY sort, rowid", (uid,))
    idx = [r["code"] for r in rows if r["kind"] == "index" and r["code"] in INDEX_CATALOG]
    has_idx = await store.query_one("SELECT 1 FROM kv WHERE key = ?", (f"uq_idx_set:{uid}",))
    return (idx if has_idx else None), [r["code"] for r in rows if r["kind"] == "stock"]


async def get_market(request: Request):
    if await locked(request, "quotes_live"):
        return members_only()
    user = await auth.current_user(request)
    idx_codes, stocks = (None, [])
    if user:
        idx_codes, stocks = await _user_lists(user["id"])
    idx_codes = idx_codes if idx_codes is not None else default_indices()
    m = state["market"]
    if any(c not in m.idx for c in idx_codes):  # 新选的指数还没抓过：立即抓一次
        got = await m.fetch_indices([c for c in idx_codes if c not in m.idx])
        m.idx.update(got)
    missing = [s for s in stocks if not m.snapshot(s)]
    if missing:
        m._store(await m.fetch_stocks(missing))
    return ok({
        "session": market_session(), "market": holidays.today_status(), "updated": time.time(),
        "catalog": [{"code": c, "zh": v["zh"], "en": v["en"], "yahoo": v["yahoo"], "tv": v["tv"]} for c, v in INDEX_CATALOG.items()],
        "max_indices": MAX_INDICES, "max_stocks": int(settings.get("sources.market.max_stocks") or 30),
        "logged_in": bool(user), "indices": idx_codes, "index_quotes": {c: m.idx.get(c) for c in idx_codes},
        "stocks": stocks, "snaps": {s: m.snapshot(s) for s in stocks},
        "rank": cache.get("market:rank") if settings.get("sources.market.rank_enabled") else None,
    })


async def _need_user(request: Request):
    user = await auth.current_user(request)
    if not user:
        return None, err(401, "请先登录")
    if await locked(request, "quotes_live"):
        return None, members_only()
    return user, None


async def put_indices(request: Request):
    user, e = await _need_user(request)
    if e:
        return e
    codes = [str(c).upper() for c in (await body_of(request)).get("codes", [])]
    codes = list(dict.fromkeys(c for c in codes if c in INDEX_CATALOG))
    if not codes:
        return err(400, "至少选择 1 个指数")
    if len(codes) > MAX_INDICES:
        return err(400, f"最多选择 {MAX_INDICES} 个指数")

    def run(c):
        c.execute("DELETE FROM user_quotes WHERE user_id = ? AND kind = 'index'", (user["id"],))
        c.executemany("INSERT INTO user_quotes (user_id, kind, code, sort) VALUES (?, 'index', ?, ?)", [(user["id"], x, i) for i, x in enumerate(codes)])
    await store.run(run)
    await store.kv_set(f"uq_idx_set:{user['id']}", "1")
    return ok({"indices": codes})


async def add_stock(request: Request):
    user, e = await _need_user(request)
    if e:
        return e
    sym = str((await body_of(request)).get("symbol", "")).strip().upper()
    if not SYM_RE.match(sym):
        return err(400, "股票代码格式不正确")
    n = (await store.query_one("SELECT COUNT(*) AS n FROM user_quotes WHERE user_id = ? AND kind = 'stock'", (user["id"],)))["n"]
    limit = int(settings.get("sources.market.max_stocks") or 30)
    if n >= limit:
        return err(400, f"最多添加 {limit} 只个股")
    if await store.query_one("SELECT 1 FROM user_quotes WHERE user_id = ? AND kind = 'stock' AND code = ?", (user["id"], sym)):
        return err(409, "已经添加过了")
    m = state["market"]
    q = m.snapshot(sym) or await m.fetch_one(sym)
    if not q:
        return err(400, f"找不到美股代码 {sym}")
    await store.execute("INSERT INTO user_quotes (user_id, kind, code, sort) VALUES (?, 'stock', ?, ?)", (user["id"], sym, n))
    await lists.mirror_to_portfolio(user["id"], sym)  # 自选同步添加
    await universe.refresh()
    return ok({"symbol": sym, "snap": q})


async def del_stock(request: Request):
    user, e = await _need_user(request)
    if e:
        return e
    sym = request.path_params["symbol"].upper()
    await store.execute("DELETE FROM user_quotes WHERE user_id = ? AND kind = 'stock' AND code = ?", (user["id"], sym))
    kept = await lists.removed_from_quotes(user["id"], sym)
    await universe.refresh()
    return ok({"ok": True, "kept_in_portfolio": kept})


async def order_stocks(request: Request):
    user, e = await _need_user(request)
    if e:
        return e
    syms = [str(s).upper() for s in (await body_of(request)).get("symbols", [])][:200]
    await store.executemany("UPDATE user_quotes SET sort = ? WHERE user_id = ? AND kind = 'stock' AND code = ?",
                            [(i, user["id"], s) for i, s in enumerate(syms)])
    return ok({"ok": True})


routes = [
    Route("/api/market", get_market),
    Route("/api/market/indices", put_indices, methods=["PUT"]),
    Route("/api/market/stocks", add_stock, methods=["POST"]),
    Route("/api/market/stocks/order", order_stocks, methods=["PUT"]),
    Route("/api/market/stocks/{symbol}", del_stock, methods=["DELETE"]),
]
