"""汇率：中国外汇交易中心（CFETS）银行间人民币即期报价。

统一换算成“1 单位外币 = 多少人民币”（买价 / 卖价），任意两种货币之间可通过人民币换算交叉汇率。
每分钟保存一次快照，用于计算“昨日美股收盘时的汇率”（今日汇兑损益的基准）。
"""
from __future__ import annotations

import time
from typing import Any

from .. import cache, store
from ..http import PoliteClient

URL = "https://www.chinamoney.com.cn/r/cms/www/chinamoney/data/fx/rfx-sp-quot.json"
HEADERS = {"Referer": "https://www.chinamoney.com.cn/chinese/mkdatapfx/", "Accept": "application/json"}


def _num(v: Any) -> float | None:
    try:
        x = float(str(v).replace(",", ""))
        return x if x > 0 else None
    except (TypeError, ValueError):
        return None


def parse_cfets(js: dict[str, Any]) -> tuple[dict[str, dict[str, float]], str]:
    """返回 ({货币: {bid, ask}}（以人民币计价）, 报价时间)。"""
    rates: dict[str, dict[str, float]] = {"CNY": {"bid": 1.0, "ask": 1.0}}
    for r in (js or {}).get("records") or []:
        pair = str(r.get("ccyPair") or "").upper().replace(" ", "")
        bid, ask = _num(r.get("bidPrc")), _num(r.get("askPrc"))
        if not bid or not ask or "/" not in pair:
            continue
        left, right = pair.split("/", 1)
        if right == "CNY":  # 例如 USD/CNY、100JPY/CNY
            scale = 1.0
            digits = "".join(ch for ch in left if ch.isdigit())
            if digits:
                scale = float(digits)
                left = left[len(digits):]
            rates[left] = {"bid": bid / scale, "ask": ask / scale}
        elif left == "CNY":  # 例如 CNY/MYR：取倒数，买卖价互换
            rates[right] = {"bid": 1 / ask, "ask": 1 / bid}
    data = (js or {}).get("data") or {}
    return rates, str(data.get("showDateCN") or "")


class FxCollector:
    def __init__(self, http: PoliteClient) -> None:
        self.http = http
        self.prev: dict[str, Any] | None = None
        self.last_snapshot = 0
        self.last_cleanup = 0.0

    async def refresh(self) -> str:
        r = await self.http.get(URL, headers=HEADERS, min_interval=3)
        rates, quote_time = parse_cfets(r.json())
        if "USD" not in rates:
            raise RuntimeError("没有取到 USD/CNY 报价，页面结构可能已变化")
        payload = {"source": "CFETS", "time": quote_time, "fetched": time.time(), "rates": rates}
        if not self.prev or self.prev["rates"] != rates:
            cache.put("fx:now", payload, topic="fx", push=payload)
        else:
            cache.put("fx:now", payload)
        self.prev = payload
        minute = int(time.time()) // 60 * 60
        if minute != self.last_snapshot:
            self.last_snapshot = minute
            await store.executemany("INSERT OR REPLACE INTO fx_history VALUES (?, ?, ?, ?)",
                                    [(minute, c, v["bid"], v["ask"]) for c, v in rates.items() if c != "CNY"])
            if time.time() - self.last_cleanup > 86400:
                self.last_cleanup = time.time()
                await store.execute("DELETE FROM fx_history WHERE ts < ?", (int(time.time()) - 20 * 86400,))
        usd = rates["USD"]
        return f"USD/CNY {usd['bid']:.4f}/{usd['ask']:.4f}，{len(rates) - 1} 种货币，报价时间 {quote_time}"


async def rates_at(ts: int) -> dict[str, dict[str, float]] | None:
    """某一时刻（含之前 4 天内）最近的一次汇率快照。"""
    rows = await store.query(
        """SELECT h.ccy, h.bid, h.ask FROM fx_history h
           JOIN (SELECT ccy, MAX(ts) AS ts FROM fx_history WHERE ts <= ? AND ts >= ? GROUP BY ccy) m
             ON h.ccy = m.ccy AND h.ts = m.ts""", (ts, ts - 4 * 86400))
    if not rows:
        return None
    out = {"CNY": {"bid": 1.0, "ask": 1.0}}
    out.update({r["ccy"]: {"bid": r["bid"], "ask": r["ask"]} for r in rows})
    return out


async def rates_since(ts: int) -> tuple[int, dict[str, dict[str, float]]] | None:
    """ts 之后（1 天内）最早的一次快照，用于刚部署、还没有昨收快照时的近似基准。"""
    row = await store.query_one("SELECT MIN(ts) AS t FROM fx_history WHERE ts > ? AND ts <= ?", (ts, ts + 86400))
    if not row or row["t"] is None:
        return None
    rows = await store.query("SELECT ccy, bid, ask FROM fx_history WHERE ts = ?", (row["t"],))
    out = {"CNY": {"bid": 1.0, "ask": 1.0}}
    out.update({r["ccy"]: {"bid": r["bid"], "ask": r["ask"]} for r in rows})
    return row["t"], out
