"""自选股历史：每日收盘价、每日汇率、按交易记录回算每天的市值和盈亏（用于总市值折线图和各项分析）。

- 收盘价：Yahoo 日线（近 6 个月）；之后每个交易日收盘后，行情采集器的收盘价也会写入；
- 汇率：Yahoo 的 USD/xxx 日收盘（1 美元 = 多少该货币）；取不到时用本站记录的外汇交易中心快照，再不行用当前汇率（标为近似）；
- 每天的数据 = 截至当天的交易记录 + 当天收盘价 + 当天汇率，用与前端相同的算法（pnl.py）计算。
"""
from __future__ import annotations

import bisect
import logging
import time
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from . import holidays, inflation, pnl, store, universe

log = logging.getLogger("history")
ET = ZoneInfo("America/New_York")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=6mo&interval=1d"
DAYS = 92
_cache: dict[int, tuple[float, str, dict[str, Any]]] = {}


def last_closed_session(now: datetime | None = None) -> date:
    """最近一个已经收盘的美股交易日。"""
    t = (now or datetime.now(ET)).astimezone(ET)
    d = t.date()
    if holidays.us_trading_day(d) and t.hour * 60 + t.minute >= holidays.us_close_hour(d) * 60 + 5:
        return d
    return holidays.prev_us_trading_day(d)


def trading_days(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if holidays.us_trading_day(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def parse_chart(js: dict[str, Any]) -> list[tuple[str, float]]:
    res = ((js or {}).get("chart") or {}).get("result") or []
    if not res:
        return []
    r = res[0]
    ts = r.get("timestamp") or []
    closes = (((r.get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
    tz = ZoneInfo((r.get("meta") or {}).get("exchangeTimezoneName") or "America/New_York")
    out = []
    for t, c in zip(ts, closes):
        if c is None:
            continue
        out.append((datetime.fromtimestamp(t, tz).date().isoformat(), float(c)))
    return out


async def _fetch_chart(http: Any, sym: str) -> list[tuple[str, float]]:
    r = await http.get(CHART.format(sym=sym), headers={"User-Agent": UA, "Accept": "application/json"}, min_interval=0.3, timeout=15)
    return parse_chart(r.json())


async def update_prices(http: Any, symbols: list[str], limit: int = 40) -> tuple[int, list[str]]:
    """补齐收盘价：已有到最近交易日的跳过，每次最多更新 limit 只。"""
    target = last_closed_session().isoformat()
    done, failed = 0, []
    for sym in symbols:
        if done >= limit:
            break
        row = await store.query_one("SELECT MAX(date) AS d, COUNT(*) AS n FROM px_daily WHERE symbol = ?", (sym,))
        if row and row["d"] and row["d"] >= target and row["n"] >= 40:
            continue
        mark = await store.kv_get(f"px_try:{sym}")
        if mark and time.time() - mark[1] < 3 * 3600:
            continue  # 最近刚试过（例如数据源还没出今天的收盘价）
        await store.kv_set(f"px_try:{sym}", "1")
        try:
            rows = await _fetch_chart(http, sym.replace(".", "-"))
        except Exception as e:  # noqa: BLE001
            failed.append(f"{sym}: {type(e).__name__}")
            continue
        if rows:
            await store.executemany("INSERT OR REPLACE INTO px_daily VALUES (?, ?, ?)", [(sym, d, c) for d, c in rows])
            done += 1
    return done, failed


async def update_fx(http: Any, ccys: list[str]) -> tuple[int, list[str]]:
    target = last_closed_session().isoformat()
    done, failed = 0, []
    for c in ccys:
        if c == "USD":
            continue
        row = await store.query_one("SELECT MAX(date) AS d FROM fx_daily WHERE ccy = ? AND src = 'yahoo'", (c,))
        if row and row["d"] and row["d"] >= target:
            continue
        mark = await store.kv_get(f"fx_try:{c}")
        if mark and time.time() - mark[1] < 3 * 3600:
            continue
        await store.kv_set(f"fx_try:{c}", "1")
        try:
            rows = await _fetch_chart(http, f"{c}=X")
        except Exception as e:  # noqa: BLE001
            failed.append(f"{c}: {type(e).__name__}")
            continue
        if rows:
            await store.executemany("INSERT OR REPLACE INTO fx_daily VALUES (?, ?, ?, 'yahoo')", [(d, c, v) for d, v in rows])
            done += 1
    return done, failed


async def record_closes(snap: dict[str, dict[str, Any]], session: str) -> None:
    """收盘后把行情采集器的收盘价写入日线（Yahoo 不可用时也能逐日积累）。"""
    now = datetime.now(ET)
    d = now.date()
    if session not in ("post", "closed") or not holidays.us_trading_day(d) or now.hour < holidays.us_close_hour(d):
        return
    key = f"px_rec:{d.isoformat()}"
    last = await store.kv_get(key)
    if last and time.time() - last[1] < 1800:
        return
    rows = [(s, d.isoformat(), q["price"]) for s, q in snap.items() if q.get("price")]
    await store.executemany("INSERT OR IGNORE INTO px_daily VALUES (?, ?, ?)", rows)
    await store.kv_set(key, "1")


class HistoryCollector:
    """每小时检查一次：给所有用户自选股补齐日线，给用到的货币补齐日汇率。"""

    def __init__(self, http: Any) -> None:
        self.http = http

    async def refresh(self) -> str:
        syms = universe.portfolio_symbols()
        ccys = [r["c"] for r in await store.query(
            "SELECT DISTINCT ccy AS c FROM pf_trades UNION SELECT DISTINCT base_currency FROM pf_settings UNION SELECT DISTINCT ccy FROM cash_moves")]
        n1, f1 = await update_prices(self.http, syms)
        n2, f2 = await update_fx(self.http, [c for c in ccys if c])
        if f1 or f2:
            log.warning("历史行情部分获取失败：%s", "；".join((f1 + f2)[:8]))
        return f"日线更新 {n1} 只，汇率更新 {n2} 种" + (f"；失败 {len(f1) + len(f2)}" if f1 or f2 else "")


# ---------------- 计算 ----------------
class _Series:
    """按日期取“当天或之前最近一天”的值。"""

    def __init__(self, rows: list[tuple[str, float]]) -> None:
        rows = sorted(rows)
        self.d = [r[0] for r in rows]
        self.v = [r[1] for r in rows]

    def at(self, day: str) -> float | None:
        i = bisect.bisect_right(self.d, day) - 1
        return self.v[i] if i >= 0 else None


async def compute(uid: int, base: str, current_rates: dict[str, Any] | None, days: int = DAYS) -> dict[str, Any]:
    trades = await store.query("SELECT id, symbol, side, trade_date, shares, price, ccy, fx, fee, funding FROM pf_trades WHERE user_id = ? ORDER BY trade_date, id", (uid,))
    moves = await store.query("SELECT trade_date, ccy, amount FROM cash_moves WHERE user_id = ?", (uid,))
    if not trades and not moves:
        return {"points": [], "missing": [], "approx_fx": False}
    end = last_closed_session()
    first = min([t["trade_date"] for t in trades] + [m["trade_date"] for m in moves])
    start = max(date.fromisoformat(first), end - timedelta(days=days))
    days_list = trading_days(start, end)
    key = f"{base}|{len(trades)}|{trades[-1]['id'] if trades else 0}|{len(moves)}|{sum(m['amount'] for m in moves):.4f}|{end}"
    hit = _cache.get(uid)
    if hit and hit[1] == key and time.time() - hit[0] < 600:
        return hit[2]

    symbols = sorted({t["symbol"] for t in trades})
    px: dict[str, _Series] = {}
    for s in symbols:
        rows = await store.query("SELECT date, close FROM px_daily WHERE symbol = ? AND date >= ?", (s, (start - timedelta(days=10)).isoformat()))
        px[s] = _Series([(r["date"], r["close"]) for r in rows])
    ccys = sorted({t["ccy"] or base for t in trades} | {m["ccy"] for m in moves} | {base})
    fx: dict[str, _Series] = {}
    for c in ccys:
        if c == "USD":
            continue
        rows = await store.query("SELECT date, usd_rate FROM fx_daily WHERE ccy = ? AND date >= ?", (c, (start - timedelta(days=10)).isoformat()))
        fx[c] = _Series([(r["date"], r["usd_rate"]) for r in rows])
    approx = False
    infl = await inflation.tables_for({t["ccy"] or base for t in trades} | {base}, first) if trades else {}

    def rate_fn(day: str):
        nonlocal approx

        def r(c: str) -> float | None:
            nonlocal approx
            if c == "USD":
                return 1.0
            v = fx[c].at(day) if c in fx else None
            if v is None:
                approx = True
                return pnl.usd_to(current_rates, c)  # 没有历史汇率时用当前汇率（标为近似）
            return v
        return r

    points, missing = [], set()
    by_sym: dict[str, list[dict[str, Any]]] = {}
    for t in trades:
        by_sym.setdefault(t["symbol"], []).append(t)
    for d in days_list:
        day = d.isoformat()
        r = rate_fn(day)
        mv = cost = unreal = realized = 0.0
        pl_p = pl_r = pl_rp = 0.0   # 只含股价 / 扣除通胀 / 扣除通胀且只含股价 的总盈亏（按当天的购买力）
        u_p = u_r = u_rp = 0.0      # 同上，持仓盈亏部分
        defl = pnl.deflator(infl, day)
        holding: dict[str, float] = {}
        for s, lst in by_sym.items():
            sub = [t for t in lst if t["trade_date"] <= day]
            if not sub:
                continue
            price = px[s].at(day)
            q = {"price": price, "prev_close": price}
            res = pnl.compute_symbol(sub, q, None, None, "mid", base, "9999-12-31", rate=r)
            real = pnl.compute_symbol(sub, q, None, None, "mid", base, "9999-12-31", rate=r, deflate=defl)
            realized += res.get("realized") or 0.0
            pl_p += res.get("realizedPrice") or 0.0
            pl_r += real.get("realized") or 0.0
            pl_rp += real.get("realizedPrice") or 0.0
            if not res.get("qty"):
                continue
            if price is None:
                missing.add(s)
                continue
            mv += res.get("mvBase") or 0.0
            cost += res.get("costBase") or 0.0
            unreal += res.get("unreal") or 0.0
            u_p += res.get("unrealPrice") or 0.0
            u_r += real.get("unreal") or 0.0
            u_rp += real.get("unrealPrice") or 0.0
            holding[s] = res.get("mvBase") or 0.0
        cash = pnl.cash_balances(trades, moves, base, until=day)
        to_base = r(base)
        cash_base = sum(v * to_base / r(c) for c, v in cash.items() if r(c) and to_base)
        points.append({"date": day, "mv": round(mv, 2), "cost": round(cost, 2), "unreal": round(unreal, 2), "realized": round(realized, 2),
                       "total_pl": round(unreal + realized, 2), "pl_p": round(pl_p + u_p, 2), "pl_r": round(pl_r + u_r, 2), "pl_rp": round(pl_rp + u_rp, 2),
                       "u_p": round(u_p, 2), "u_r": round(u_r, 2), "u_rp": round(u_rp, 2),
                       "cash": round(cash_base, 2), "capital": round(mv + cash_base, 2),
                       "holdings": {k: round(v, 2) for k, v in holding.items()}})
    prev = None
    for p in points:
        p["day_pl"] = round(p["total_pl"] - prev, 2) if prev is not None else None
        prev = p["total_pl"]
    out = {"points": points, "missing": sorted(missing), "approx_fx": approx, "end": end.isoformat(),
           "inflation": {c: {k: v[k] for k in ("yoy_12m", "last_known", "approx", "region")} for c, v in infl.items()}}
    _cache[uid] = (time.time(), key, out)
    return out


def invalidate(uid: int) -> None:
    _cache.pop(uid, None)
