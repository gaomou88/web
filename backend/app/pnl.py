"""连汇盈亏计算（Python 版），与前端 frontend/js/pnl.js 逐行对应，用于计算历史每日市值。

两边算法必须保持一致；tests 里有用同一批用例对比两边结果的一致性测试。
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable

SUM_KEYS = ["qty", "costUsd", "costBase", "costReal", "realized", "realizedPrice", "mvUsd", "mvBase", "unreal", "unrealPrice", "unrealFx",
            "today", "todayPrice", "todayFx"]
SCALE_KEYS = {"costBase", "costReal", "realized", "realizedPrice", "mvBase", "unreal", "unrealPrice", "unrealFx", "today", "todayPrice", "todayFx"}


def _day_num(day: str) -> int:
    return date(int(day[:4]), int(day[5:7]), int(day[8:10])).toordinal()


def cpi_index_at(table: list[list[Any]] | None, day: str) -> float | None:
    """月度物价指数表 [[YYYY-MM, 指数], ...]（按月连续）在某一天的值：每月 15 日为该月的值，之间按天线性插值，两端取端点。"""
    if not table:
        return None
    x = _day_num(day)
    pts = [(_day_num(f"{m}-15"), float(v)) for m, v in table]
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    lo, hi = 0, len(pts) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if pts[mid][0] <= x:
            lo = mid
        else:
            hi = mid
    (x0, y0), (x1, y1) = pts[lo], pts[hi]
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def cpi_factor(table: list[list[Any]] | None, day: str, now_day: str) -> float:
    """day 那天的 1 元相当于 now_day 的多少元（物价上涨 → 大于 1）。没有数据时为 1。"""
    a, b = cpi_index_at(table, day), cpi_index_at(table, now_day)
    return b / a if a and b else 1.0


def deflator(tables: dict[str, Any] | None, now_day: str) -> Callable[[str], Callable[[str], float] | None]:
    """按货币返回折算函数：deflator(tables, 今天)(货币)(日期) = 该日期的钱折算到今天的倍数。"""
    def for_ccy(ccy: str):
        t = (tables or {}).get(ccy)
        table = t.get("table") if isinstance(t, dict) else t
        if not table:
            return None
        return lambda day: cpi_factor(table, day, now_day)
    return for_ccy


def usd_to(rates: dict[str, Any] | None, ccy: str, mode: str = "mid") -> float | None:
    """1 美元 = 多少 ccy。rates 为外汇交易中心格式 {货币: {bid, ask}}（以人民币计价）。"""
    if not rates:
        return None
    if ccy == "USD":
        return 1.0
    usd, base = rates.get("USD"), rates.get(ccy)
    if not usd or not base:
        return None
    if mode == "bid":
        return usd["bid"] / base["ask"]
    return ((usd["bid"] + usd["ask"]) / 2) / ((base["bid"] + base["ask"]) / 2)


def compute_position(trades: list[dict[str, Any]], quote: dict[str, Any] | None, fx_now: float | None,
                     fx_prev: float | None, session_date: str, deflate: Callable[[str], float] | None = None) -> dict[str, Any]:
    """deflate(日期)：该日期的钱折算成今天购买力的倍数（扣除通胀时传入）。传入后 unreal / realized / unrealPrice / realizedPrice
    都是扣除通胀后的值；costBase 仍是名义成本，costReal 是按今天购买力计算的成本。今日盈亏不受影响。"""
    lst = sorted(trades, key=lambda t: (t["trade_date"], t.get("id") or 0))
    qty = cost_usd = cost_base = cost_usd_r = cost_base_r = realized = realized_price = 0.0
    today_buy_qty = today_buy_fx_qty = today_buy_cost = today_sell = 0.0
    qty_prev = 0.0
    for t in lst:
        today = t["trade_date"] >= session_date
        if not today:
            qty_prev = qty
        fee = t.get("fee") or 0
        d = deflate(t["trade_date"]) if deflate else 1.0
        if t["side"] == "buy":
            usd = t["shares"] * t["price"] + fee
            qty += t["shares"]; cost_usd += usd; cost_base += usd * t["fx"]
            cost_usd_r += usd * d; cost_base_r += usd * t["fx"] * d
            if today:
                today_buy_qty += t["shares"]; today_buy_fx_qty += t["shares"] * t["fx"]; today_buy_cost += usd * t["fx"]
        else:
            if qty <= 0:
                continue
            q = min(t["shares"], qty)
            avg_usd, avg_base = cost_usd / qty, cost_base / qty
            avg_usd_r, avg_base_r = cost_usd_r / qty, cost_base_r / qty
            avg_fx = cost_base / cost_usd if cost_usd else t["fx"]
            proceeds_usd = q * t["price"] - fee
            proceeds = proceeds_usd * t["fx"]
            realized += proceeds * d - q * avg_base_r
            realized_price += (proceeds_usd * d - q * avg_usd_r) * avg_fx
            cost_usd -= q * avg_usd; cost_base -= q * avg_base; qty -= q
            cost_usd_r -= q * avg_usd_r; cost_base_r -= q * avg_base_r
            if today:
                today_sell += proceeds
        if not today:
            qty_prev = qty
    if qty < 1e-9:
        qty = cost_usd = cost_base = cost_usd_r = cost_base_r = 0.0

    price = (quote or {}).get("price")
    prev_close = (quote or {}).get("prev_close")
    if prev_close is None:
        prev_close = price
    fx_p = fx_prev if fx_prev is not None else fx_now
    out: dict[str, Any] = {
        "qty": qty, "costUsd": cost_usd, "costBase": cost_base, "costReal": cost_base_r, "realized": realized, "realizedPrice": realized_price,
        "avgUsd": cost_usd / qty if qty else None, "avgFx": cost_base / cost_usd if cost_usd else None,
        "price": price, "prevClose": prev_close,
        "mvUsd": None, "mvBase": None, "unreal": None, "unrealPct": None, "unrealPrice": None, "unrealFx": None,
        "today": None, "todayPrice": None, "todayFx": None,
    }
    if price is None or fx_now is None:
        return out
    out["mvUsd"] = qty * price
    out["mvBase"] = out["mvUsd"] * fx_now
    if qty:
        out["unreal"] = out["mvBase"] - cost_base_r
        out["unrealPct"] = out["unreal"] / cost_base_r * 100 if cost_base_r else None
        out["unrealPrice"] = (out["mvUsd"] - cost_usd_r) * out["avgFx"]
        out["unrealFx"] = out["unreal"] - out["unrealPrice"]
    else:
        out["unreal"] = out["unrealPrice"] = out["unrealFx"] = 0.0
    prev_value = qty_prev * (prev_close if prev_close is not None else price) * fx_p
    out["today"] = out["mvBase"] + today_sell - today_buy_cost - prev_value
    kept = max(0.0, qty - today_buy_qty)
    if qty:
        buy_fx = today_buy_fx_qty / today_buy_qty if today_buy_qty else fx_p
        ref_fx = (kept * fx_p + min(today_buy_qty, qty) * buy_fx) / qty
    else:
        ref_fx = fx_p
    out["todayFx"] = out["mvUsd"] * (fx_now - ref_fx)
    out["todayPrice"] = out["today"] - out["todayFx"]
    return out


def compute_symbol(trades: list[dict[str, Any]], quote: dict[str, Any] | None, now: Any, prev: Any, mode: str,
                   base: str, session_date: str, rate=None, deflate=None) -> dict[str, Any]:
    """一只股票（可能多种货币买入）的持仓，折算到本币。
    now / prev 为外汇交易中心报价表；也可以传 rate(ccy) 函数直接给出“1 美元 = 多少 ccy”（历史计算用）。
    deflate(ccy) 返回该货币的通胀折算函数（见 deflator），用于扣除通胀；每笔成本按付款货币所在地的物价折算。"""
    groups: dict[str, list[dict[str, Any]]] = {}
    for t in trades:
        groups.setdefault(t.get("ccy") or base, []).append(t)
    r_now = rate or (lambda c: usd_to(now, c, mode))
    r_prev = (lambda c: None) if rate else (lambda c: usd_to(prev, c, mode))
    to_base = r_now(base)
    parts = []
    for c, lst in groups.items():
        fn = r_now(c)
        p = compute_position(lst, quote, fn, r_prev(c), session_date, deflate(c) if deflate else None)
        k = to_base / fn if fn and to_base else (1.0 if c == base else None)
        parts.append((c, p, k))
    out: dict[str, Any] = {"ccys": [c for c, _, _ in parts]}
    for key in SUM_KEYS:
        total, any_ = 0.0, False
        for _, p, k in parts:
            v = p.get(key)
            if v is None:
                continue
            if key in SCALE_KEYS:
                if k is None:
                    continue
                total += v * k
            else:
                total += v
            any_ = True
        out[key] = total if any_ else (None if parts else 0.0)
    if not parts:
        out.update(qty=0.0, costUsd=0.0, costBase=0.0, costReal=0.0, realized=0.0, realizedPrice=0.0)
    return out


def cash_balances(trades: list[dict[str, Any]], moves: list[dict[str, Any]], base: str, until: str | None = None) -> dict[str, float]:
    """各币种现金：资金记录 + 买卖自动联动（买入扣除，卖出加回）。
    funding = "usd" 的交易（导入的券商记录等）从美元现金扣，其余按该笔交易的货币对从对应货币扣。"""
    bal: dict[str, float] = {}
    for m in moves:
        if until and m["trade_date"] > until:
            continue
        bal[m["ccy"]] = bal.get(m["ccy"], 0.0) + m["amount"]
    for t in trades:
        if until and t["trade_date"] > until:
            continue
        fee = t.get("fee") or 0
        usd = t["shares"] * t["price"] + fee if t["side"] == "buy" else -(t["shares"] * t["price"] - fee)
        if t.get("funding") == "usd":  # 用之前换好的美元：从美元现金扣，汇率只用于计算成本
            c, amt = "USD", usd
        else:                          # 按成交汇率当场换汇：从该笔交易的货币扣
            c, amt = t.get("ccy") or base, usd * t["fx"]
        bal[c] = bal.get(c, 0.0) - amt
    return {c: v for c, v in bal.items() if abs(v) > 1e-9}
