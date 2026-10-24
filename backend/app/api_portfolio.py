"""持仓分析（原“自选”）+ 连汇盈亏。

服务器负责：保存自选股和交易记录、提供股价（实时 + Cboe 昨收）、提供当前汇率和“昨日美股收盘时”的汇率。
盈亏在浏览器里实时计算（股价或汇率一变动立即重算，不占服务器资源）。
"""
from __future__ import annotations

import csv
import io
import re
import time
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from . import auth, cache, history, holidays, inflation, lists, settings, store, universe
from .collectors import realtime
from .collectors.fx import rates_at, rates_since
from .common import body_of, err, ok

ET = ZoneInfo("America/New_York")
SYM_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
CURRENCIES = ["CNY", "HKD", "SGD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "USD"]


def currencies() -> list[str]:
    """常用货币在前，其余为外汇交易中心当前有报价的全部货币。"""
    rates = (cache.get("fx:now") or {}).get("rates") or {}
    return CURRENCIES + sorted(c for c in rates if c not in CURRENCIES)
state: dict[str, Any] = {}  # main.py 注入行情采集器 market


# ================= 美股交易日（已计入休市日和提前收盘）=================
def session_info(now: datetime | None = None) -> dict[str, Any]:
    """当前美股交易日（交易日美东 4:00 盘前开始算新的一天）和上一交易日收盘时刻（正常 16:00，提前收盘日 13:00）。"""
    t = (now or datetime.now(ET)).astimezone(ET)
    d = t.date()
    if not holidays.us_trading_day(d) or t.hour < 4:
        d = holidays.prev_us_trading_day(d)  # 休市日或凌晨 4 点前：仍属于上一个交易日
    prev = holidays.prev_us_trading_day(d)
    ref = datetime(prev.year, prev.month, prev.day, holidays.us_close_hour(prev), 0, tzinfo=ET)
    return {"session_date": d.isoformat(), "prev_date": prev.isoformat(), "ref_ts": int(ref.timestamp()),
            "market": holidays.today_status(t)}


# ================= 权限 =================
async def _user_or_error(request: Request) -> tuple[dict[str, Any] | None, Response | None]:
    if not settings.get("portfolio.enabled"):
        return None, err(403, "disabled")
    user = await auth.current_user(request)
    if not user:
        return None, err(401, "请先登录")
    # 会员模式关闭 = 没有会员限制，自选对所有登录用户开放
    if settings.get("membership.enabled") and settings.get("portfolio.access") == "members" and not auth.is_member(user):
        return None, err(403, "members_only", notice="持仓分析与连汇盈亏仅对会员开放")
    return user, None


def _quote(sym: str, sess: dict[str, Any]) -> dict[str, Any]:
    """行情采集器的快照（昨收已按盘前/盘中区分好）+ 最新成交价（WebSocket 或轮询，取更新的）。"""
    q = state["market"].snapshot(sym) or {}
    out = {"price": q.get("live"), "prev_close": q.get("prev_close"), "volume": q.get("volume"), "name": q.get("name"),
           "delayed": False, "ts": q.get("ts")}
    rt = realtime.last.get(sym)
    if rt and (out["ts"] is None or rt[1] >= out["ts"]):
        out.update(price=rt[0], ts=rt[1])
    return out


# ================= 读取 =================
async def get_portfolio(request: Request):
    user, e = await _user_or_error(request)
    if e:
        return e
    uid = user["id"]
    pf = await store.query_one("SELECT base_currency, fx_mode, inflation, include_fx FROM pf_settings WHERE user_id = ?", (uid,))
    symbols = await store.query("SELECT symbol, note, target, stop, sort, created_at FROM pf_symbols WHERE user_id = ? ORDER BY sort, created_at", (uid,))
    trades = await store.query("SELECT id, symbol, side, trade_date, shares, price, ccy, fx, fee, note, funding, batch FROM pf_trades WHERE user_id = ? ORDER BY trade_date, id", (uid,))
    cash = await store.query("SELECT id, grp, kind, trade_date, ccy, amount, note, batch FROM cash_moves WHERE user_id = ? ORDER BY trade_date, id", (uid,))
    sess = session_info()
    fx_now = cache.get("fx:now")
    fx_prev = await rates_at(sess["ref_ts"])
    prev_ts, prev_approx = sess["ref_ts"], False
    if fx_prev is None:
        # 刚部署还没有昨收时刻的快照：用最早的一条记录作基准（会在页面上注明）
        found = await rates_since(sess["ref_ts"])
        if found:
            prev_ts, fx_prev = found
            prev_approx = True
    pf = pf or {"base_currency": settings.get("portfolio.default_currency"), "fx_mode": "mid", "inflation": 0, "include_fx": 1}
    pf = {**pf, "inflation": bool(pf.get("inflation")), "include_fx": bool(pf.get("include_fx", 1))}
    # 扣除通胀用的月度物价指数表（交易用到的货币 + 本币），总是返回，切换开关时不用重新请求
    infl_ccys = {t["ccy"] or pf["base_currency"] for t in trades} | {pf["base_currency"]}
    infl = await inflation.tables_for(infl_ccys, trades[0]["trade_date"] if trades else None)
    return ok({
        "settings": pf,
        "inflation": infl,
        "today": date.today().isoformat(),
        "currencies": currencies(),
        "symbols": symbols,
        "trades": trades,
        "cash": cash,
        "quotes": {s["symbol"]: _quote(s["symbol"], sess) for s in symbols},
        "fx": {"now": fx_now, "prev": fx_prev, "ref_ts": sess["ref_ts"], "prev_ts": prev_ts, "prev_approx": prev_approx},
        "session": sess,
        "realtime": True,
        "limits": {"symbols": settings.get("portfolio.max_symbols"), "trades": settings.get("portfolio.max_trades")},
    })


# ================= 自选股 =================
async def add_symbol(request: Request):
    user, e = await _user_or_error(request)
    if e:
        return e
    b = await body_of(request)
    sym = str(b.get("symbol", "")).strip().upper()
    if not SYM_RE.match(sym):
        return err(400, "股票代码格式不正确")
    n = (await store.query_one("SELECT COUNT(*) AS n FROM pf_symbols WHERE user_id = ?", (user["id"],)))["n"]
    if n >= int(settings.get("portfolio.max_symbols")):
        return err(400, f"持仓分析最多 {settings.get('portfolio.max_symbols')} 只股票")
    if await store.query_one("SELECT 1 FROM pf_symbols WHERE user_id = ? AND symbol = ?", (user["id"], sym)):
        return err(409, "已在持仓分析中")
    market = state["market"]
    if not market.snapshot(sym) and await market.fetch_one(sym) is None:  # 新代码先确认能查到报价
        return err(400, f"找不到美股代码 {sym}")
    await store.execute("INSERT INTO pf_symbols (user_id, symbol, sort, created_at) VALUES (?, ?, ?, ?)",
                        (user["id"], sym, n, int(time.time())))
    await lists.mirror_to_quotes(user["id"], sym)  # 行情“我的个股”同步添加
    await universe.refresh()  # 实时行情会自动追加订阅
    return ok({"symbol": sym, "quote": _quote(sym, session_info())})


async def patch_symbol(request: Request):
    user, e = await _user_or_error(request)
    if e:
        return e
    sym = request.path_params["symbol"].upper()
    b = await body_of(request)

    def num(v: Any) -> float | None:
        if v in (None, ""):
            return None
        x = float(v)
        if x < 0:
            raise ValueError
        return x

    try:
        fields = {}
        if "note" in b:
            fields["note"] = str(b["note"])[:200]
        if "target" in b:
            fields["target"] = num(b["target"])
        if "stop" in b:
            fields["stop"] = num(b["stop"])
        if "sort" in b:
            fields["sort"] = int(b["sort"])
    except (TypeError, ValueError):
        return err(400, "数值格式不正确")
    if fields:
        sets = ", ".join(f"{k} = ?" for k in fields)
        await store.execute(f"UPDATE pf_symbols SET {sets} WHERE user_id = ? AND symbol = ?", (*fields.values(), user["id"], sym))
    return ok({"ok": True})


async def reorder(request: Request):
    user, e = await _user_or_error(request)
    if e:
        return e
    order = [str(s).upper() for s in (await body_of(request)).get("symbols", [])][:500]
    await store.executemany("UPDATE pf_symbols SET sort = ? WHERE user_id = ? AND symbol = ?",
                            [(i, user["id"], s) for i, s in enumerate(order)])
    return ok({"ok": True})


async def delete_symbol(request: Request):
    user, e = await _user_or_error(request)
    if e:
        return e
    sym = request.path_params["symbol"].upper()
    await store.execute("DELETE FROM pf_symbols WHERE user_id = ? AND symbol = ?", (user["id"], sym))
    await store.execute("DELETE FROM pf_trades WHERE user_id = ? AND symbol = ?", (user["id"], sym))
    await lists.removed_from_portfolio(user["id"], sym)
    await universe.refresh()
    return ok({"ok": True})


# ================= 交易记录 =================
def _parse_trade(b: dict[str, Any], default_ccy: str) -> dict[str, Any]:
    side = str(b.get("side", "buy"))
    ccy = str(b.get("ccy") or default_ccy).upper()
    if ccy not in currencies():
        raise ValueError("不支持的货币")
    if side not in ("buy", "sell"):
        raise ValueError("买卖方向不正确")
    try:
        d = date.fromisoformat(str(b.get("trade_date", "")))
    except ValueError as e:
        raise ValueError("日期格式不正确") from e
    if d > date.today() + timedelta(days=1) or d.year < 1990:
        raise ValueError("日期不正确")
    try:
        shares, price, fx = float(b["shares"]), float(b["price"]), float(b["fx"])
        fee = float(b.get("fee") or 0)
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError("股数、价格、汇率、手续费必须是数字") from e
    if shares <= 0 or price <= 0 or fx <= 0 or fee < 0:
        raise ValueError("股数、价格、汇率必须大于 0，手续费不能为负")
    if ccy == "USD":
        fx = 1.0
    if fx > 1e6 or price > 1e7 or shares > 1e10:
        raise ValueError("数值超出合理范围")
    funding = str(b.get("funding") or "ccy")
    if funding not in ("ccy", "usd"):
        raise ValueError("资金来源不正确")
    if ccy == "USD":
        funding = "ccy"
    return {"side": side, "trade_date": d.isoformat(), "shares": shares, "price": price, "ccy": ccy, "fx": fx, "fee": fee,
            "note": str(b.get("note") or "")[:200], "funding": funding}


async def _check_oversell(uid: int, sym: str, extra: dict[str, Any] | None = None, skip_id: int | None = None) -> str | None:
    """按日期顺序检查：任何时刻卖出都不能超过当时用同一货币买入、仍持有的股数。"""
    rows = await store.query("SELECT id, side, trade_date, shares, ccy FROM pf_trades WHERE user_id = ? AND symbol = ? ORDER BY trade_date, id", (uid, sym))
    rows = [r for r in rows if r["id"] != skip_id]
    if extra:
        rows.append({"id": 10**12, **extra})
        rows.sort(key=lambda r: (r["trade_date"], r["id"]))
    qty: dict[str, float] = {}
    for r in rows:
        c = r["ccy"]
        qty[c] = qty.get(c, 0.0) + (r["shares"] if r["side"] == "buy" else -r["shares"])
        if qty[c] < -1e-9:
            return f"{r['trade_date']} 卖出后用 {c} 买入的持股为负，请检查股数、日期或货币对"
    return None


async def _base_ccy(uid: int) -> str:
    row = await store.query_one("SELECT base_currency FROM pf_settings WHERE user_id = ?", (uid,))
    return row["base_currency"] if row else settings.get("portfolio.default_currency")


async def add_trade(request: Request):
    user, e = await _user_or_error(request)
    if e:
        return e
    b = await body_of(request)
    sym = str(b.get("symbol", "")).strip().upper()
    if not await store.query_one("SELECT 1 FROM pf_symbols WHERE user_id = ? AND symbol = ?", (user["id"], sym)):
        return err(400, "请先把该股票加入持仓分析")
    try:
        t = _parse_trade(b, await _base_ccy(user["id"]))
    except ValueError as ex:
        return err(400, str(ex))
    n = (await store.query_one("SELECT COUNT(*) AS n FROM pf_trades WHERE user_id = ?", (user["id"],)))["n"]
    if n >= int(settings.get("portfolio.max_trades")):
        return err(400, "交易记录已达上限")
    if (msg := await _check_oversell(user["id"], sym, t)):
        return err(400, msg)
    await store.execute(
        "INSERT INTO pf_trades (user_id, symbol, side, trade_date, shares, price, ccy, fx, fee, note, funding, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (user["id"], sym, t["side"], t["trade_date"], t["shares"], t["price"], t["ccy"], t["fx"], t["fee"], t["note"], t["funding"], int(time.time())))
    history.invalidate(user["id"])
    return ok({"ok": True})


async def patch_trade(request: Request):
    user, e = await _user_or_error(request)
    if e:
        return e
    tid = int(request.path_params["tid"])
    row = await store.query_one("SELECT * FROM pf_trades WHERE id = ? AND user_id = ?", (tid, user["id"]))
    if not row:
        return err(404, "记录不存在")
    try:
        t = _parse_trade({**row, **(await body_of(request))}, row["ccy"])
    except ValueError as ex:
        return err(400, str(ex))
    if (msg := await _check_oversell(user["id"], row["symbol"], t, skip_id=tid)):
        return err(400, msg)
    await store.execute("UPDATE pf_trades SET side=?, trade_date=?, shares=?, price=?, ccy=?, fx=?, fee=?, note=?, funding=? WHERE id = ?",
                        (t["side"], t["trade_date"], t["shares"], t["price"], t["ccy"], t["fx"], t["fee"], t["note"], t["funding"], tid))
    history.invalidate(user["id"])
    return ok({"ok": True})


async def delete_trade(request: Request):
    user, e = await _user_or_error(request)
    if e:
        return e
    tid = int(request.path_params["tid"])
    row = await store.query_one("SELECT symbol FROM pf_trades WHERE id = ? AND user_id = ?", (tid, user["id"]))
    if not row:
        return err(404, "记录不存在")
    if (msg := await _check_oversell(user["id"], row["symbol"], skip_id=tid)):
        return err(400, f"删除后会出现卖空：{msg}")
    await store.execute("DELETE FROM pf_trades WHERE id = ? AND user_id = ?", (tid, user["id"]))
    history.invalidate(user["id"])
    return ok({"ok": True})


# ================= 总资本：资金记录 =================
def _amount(v: Any) -> float:
    x = float(v)
    if not (x > 0) or x > 1e13:
        raise ValueError
    return round(x, 6)


def _parse_cash(b: dict[str, Any]) -> list[dict[str, Any]]:
    """入金 / 出金：一条；换汇：两条（卖出的货币为负、买入的货币为正）。"""
    kind = str(b.get("kind", ""))
    try:
        d = date.fromisoformat(str(b.get("trade_date", "")))
    except ValueError as e:
        raise ValueError("日期格式不正确") from e
    if d > date.today() + timedelta(days=1) or d.year < 1990:
        raise ValueError("日期不正确")
    note = str(b.get("note") or "")[:200]
    cur = currencies()
    if kind in ("deposit", "withdraw", "dividend", "interest", "fee", "tax"):  # 后四种主要来自导入的券商结单
        ccy = str(b.get("ccy", "")).upper()
        if ccy not in cur:
            raise ValueError("不支持的货币")
        try:
            amt = _amount(b.get("amount"))
        except (TypeError, ValueError) as e:
            raise ValueError("金额必须大于 0") from e
        return [{"kind": kind, "trade_date": d.isoformat(), "ccy": ccy, "amount": amt if kind in ("deposit", "dividend", "interest") else -amt, "note": note}]
    if kind == "fx":
        a, c = str(b.get("from_ccy", "")).upper(), str(b.get("to_ccy", "")).upper()
        if a not in cur or c not in cur:
            raise ValueError("不支持的货币")
        if a == c:
            raise ValueError("换出和换入的货币不能相同")
        try:
            fa, ta = _amount(b.get("from_amount")), _amount(b.get("to_amount"))
        except (TypeError, ValueError) as e:
            raise ValueError("换出和换入金额都必须大于 0") from e
        return [{"kind": "fx", "trade_date": d.isoformat(), "ccy": a, "amount": -fa, "note": note},
                {"kind": "fx", "trade_date": d.isoformat(), "ccy": c, "amount": ta, "note": note}]
    raise ValueError("类型不正确")


async def _save_cash(uid: int, rows: list[dict[str, Any]], grp: str | None = None) -> str:
    import secrets
    grp = grp or secrets.token_hex(8)
    now = int(time.time())

    def run(c):
        c.execute("DELETE FROM cash_moves WHERE user_id = ? AND grp = ?", (uid, grp))
        c.executemany("INSERT INTO cash_moves (user_id, grp, kind, trade_date, ccy, amount, note, created_at) VALUES (?,?,?,?,?,?,?,?)",
                      [(uid, grp, r["kind"], r["trade_date"], r["ccy"], r["amount"], r["note"], now) for r in rows])
    await store.run(run)  # 同一事务：换汇的两条要么都写入要么都不写
    history.invalidate(uid)
    return grp


async def add_cash(request: Request):
    user, e = await _user_or_error(request)
    if e:
        return e
    try:
        rows = _parse_cash(await body_of(request))
    except ValueError as ex:
        return err(400, str(ex))
    n = (await store.query_one("SELECT COUNT(*) AS n FROM cash_moves WHERE user_id = ?", (user["id"],)))["n"]
    if n + len(rows) > int(settings.get("portfolio.max_trades")):
        return err(400, "资金记录已达上限")
    return ok({"grp": await _save_cash(user["id"], rows)})


async def put_cash(request: Request):
    user, e = await _user_or_error(request)
    if e:
        return e
    grp = request.path_params["grp"][:32]
    if not await store.query_one("SELECT 1 FROM cash_moves WHERE user_id = ? AND grp = ?", (user["id"], grp)):
        return err(404, "记录不存在")
    try:
        rows = _parse_cash(await body_of(request))
    except ValueError as ex:
        return err(400, str(ex))
    await _save_cash(user["id"], rows, grp)
    return ok({"grp": grp})


async def delete_cash(request: Request):
    user, e = await _user_or_error(request)
    if e:
        return e
    await store.execute("DELETE FROM cash_moves WHERE user_id = ? AND grp = ?", (user["id"], request.path_params["grp"][:32]))
    history.invalidate(user["id"])
    return ok({"ok": True})


async def get_history(request: Request):
    user, e = await _user_or_error(request)
    if e:
        return e
    pf = await store.query_one("SELECT base_currency FROM pf_settings WHERE user_id = ?", (user["id"],))
    base = pf["base_currency"] if pf else settings.get("portfolio.default_currency")
    rates = (cache.get("fx:now") or {}).get("rates")
    # 新加的股票 / 货币：先补一次日线（已有的会跳过，最近试过的 3 小时内不重复请求）
    http = state["market"].http
    syms = [r["symbol"] for r in await store.query("SELECT DISTINCT symbol FROM pf_trades WHERE user_id = ?", (user["id"],))]
    ccys = [r["c"] for r in await store.query("SELECT DISTINCT ccy AS c FROM pf_trades WHERE user_id = ? UNION SELECT DISTINCT ccy FROM cash_moves WHERE user_id = ?",
                                              (user["id"], user["id"]))] + [base]
    try:
        await history.update_prices(http, syms, limit=15)
        await history.update_fx(http, [c for c in ccys if c])
    except Exception as ex:  # noqa: BLE001 —— 补数据失败不影响返回已有的历史
        import logging
        logging.getLogger("history").warning("按需补充历史数据失败：%s", ex)
    return ok(await history.compute(user["id"], base, rates))


# ================= 设置 =================
async def put_settings(request: Request):
    """本币只决定汇总显示用哪种货币；每笔交易有自己的货币对，切换本币不改动交易记录。"""
    user, e = await _user_or_error(request)
    if e:
        return e
    b = await body_of(request)
    cur = await store.query_one("SELECT base_currency, fx_mode, inflation, include_fx FROM pf_settings WHERE user_id = ?", (user["id"],)) or {
        "base_currency": settings.get("portfolio.default_currency"), "fx_mode": "mid", "inflation": 0, "include_fx": 1}
    ccy = str(b.get("base_currency", cur["base_currency"])).upper()
    mode = str(b.get("fx_mode", cur["fx_mode"]))
    infl = 1 if b.get("inflation", cur["inflation"]) else 0
    incl = 1 if b.get("include_fx", cur["include_fx"]) else 0
    if ccy not in currencies() or mode not in ("mid", "bid"):
        return err(400, "参数不正确")
    history.invalidate(user["id"])
    await store.execute("INSERT INTO pf_settings (user_id, base_currency, fx_mode, inflation, include_fx) VALUES (?, ?, ?, ?, ?) "
                        "ON CONFLICT(user_id) DO UPDATE SET base_currency = excluded.base_currency, fx_mode = excluded.fx_mode, "
                        "inflation = excluded.inflation, include_fx = excluded.include_fx",
                        (user["id"], ccy, mode, infl, incl))
    return ok({"ok": True})


async def export_csv(request: Request):
    user, e = await _user_or_error(request)
    if e:
        return e
    rows = await store.query("SELECT symbol, side, trade_date, shares, price, ccy, fx, fee, note, funding FROM pf_trades WHERE user_id = ? ORDER BY symbol, trade_date, id", (user["id"],))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["代码", "方向", "日期", "股数", "价格(USD)", "货币对", "成交汇率", "手续费(USD)", "资金来源", "备注"])
    for r in rows:
        w.writerow([r["symbol"], "买入" if r["side"] == "buy" else "卖出", r["trade_date"], r["shares"], r["price"], f"USD/{r['ccy']}", r["fx"], r["fee"],
                    "已换好的美元" if r["funding"] == "usd" else "按成交汇率换汇", r["note"]])
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="zyll-trades.csv"'})


routes = [
    Route("/api/portfolio", get_portfolio),
    Route("/api/portfolio/symbols", add_symbol, methods=["POST"]),
    Route("/api/portfolio/symbols/order", reorder, methods=["PUT"]),
    Route("/api/portfolio/symbols/{symbol}", patch_symbol, methods=["PATCH"]),
    Route("/api/portfolio/symbols/{symbol}", delete_symbol, methods=["DELETE"]),
    Route("/api/portfolio/trades", add_trade, methods=["POST"]),
    Route("/api/portfolio/trades/{tid:int}", patch_trade, methods=["PATCH"]),
    Route("/api/portfolio/trades/{tid:int}", delete_trade, methods=["DELETE"]),
    Route("/api/portfolio/settings", put_settings, methods=["PUT"]),
    Route("/api/portfolio/cash", add_cash, methods=["POST"]),
    Route("/api/portfolio/cash/{grp}", put_cash, methods=["PUT"]),
    Route("/api/portfolio/cash/{grp}", delete_cash, methods=["DELETE"]),
    Route("/api/portfolio/history", get_history),
    Route("/api/portfolio/export.csv", export_csv),
]
