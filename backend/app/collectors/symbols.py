"""美股代码表（用于输入联想）：Nasdaq Trader 公开的全部美股代码（含 NYSE、ETF），每天更新一次。

主来源：nasdaqtraded.txt（竖线分隔）；失败时改用 SEC 的 company_tickers.json。
代码表保存在数据库，启动时载入内存，搜索不访问数据库。
"""
from __future__ import annotations

import time
from typing import Any

from .. import settings, store
from ..http import PoliteClient

NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqtraded.txt"
SEC_URL = "https://www.sec.gov/files/company_tickers.json"

# 内存索引：[(代码, 名称, 名称小写, 交易所, 是否ETF)]
_index: list[tuple[str, str, str, str, int]] = []
EXCHANGES = {"N": "NYSE", "A": "NYSE American", "P": "NYSE Arca", "Q": "NASDAQ", "Z": "Cboe BZX", "V": "IEX"}


def parse_nasdaq(text: str) -> list[tuple[str, str, str, int]]:
    lines = text.splitlines()
    if not lines or "Symbol" not in lines[0]:
        return []
    head = lines[0].split("|")
    col = {name: i for i, name in enumerate(head)}
    out = []
    for line in lines[1:]:
        f = line.split("|")
        if len(f) < len(head) or line.startswith("File Creation Time"):
            continue
        sym = f[col["Symbol"]].strip().upper()
        if not sym or "$" in sym or f[col.get("Test Issue", 7)] == "Y":
            continue
        name = f[col["Security Name"]].strip()
        exch = EXCHANGES.get(f[col.get("Listing Exchange", 3)].strip(), f[col.get("Listing Exchange", 3)].strip())
        etf = 1 if f[col.get("ETF", 5)].strip() == "Y" else 0
        out.append((sym, name[:120], exch, etf))
    return out


def parse_sec(js: dict[str, Any]) -> list[tuple[str, str, str, int]]:
    out = []
    for v in (js or {}).values():
        sym = str(v.get("ticker") or "").upper().replace("-", ".")
        if sym:
            out.append((sym, str(v.get("title") or "")[:120], "", 0))
    return out


async def load_index() -> int:
    rows = await store.query("SELECT symbol, name, exchange, etf FROM us_symbols")
    _index[:] = sorted(((r["symbol"], r["name"], r["name"].lower(), r["exchange"], r["etf"]) for r in rows), key=lambda x: x[0])
    return len(_index)


def search(q: str, limit: int = 10) -> list[dict[str, Any]]:
    """代码前缀优先（完全匹配最前），其次名称包含关键词。"""
    q = q.strip()
    if not q:
        return []
    qu, ql = q.upper(), q.lower()
    exact, prefix, by_name = [], [], []
    for sym, name, low, exch, etf in _index:
        if sym == qu:
            exact.append((sym, name, exch, etf))
        elif sym.startswith(qu):
            if len(prefix) < limit:
                prefix.append((sym, name, exch, etf))
        elif len(ql) >= 2 and ql in low and len(by_name) < limit:
            by_name.append((sym, name, exch, etf))
    prefix.sort(key=lambda x: (len(x[0]), x[0]))
    return [{"symbol": s, "name": n, "exchange": e, "etf": bool(t)} for s, n, e, t in (exact + prefix + by_name)[:limit]]


class SymbolsCollector:
    def __init__(self, http: PoliteClient) -> None:
        self.http = http

    async def refresh(self) -> str:
        if not _index:
            await load_index()
        last = await store.kv_get("symbols:updated")
        if _index and last and time.time() - last[1] < 20 * 3600:
            return f"已有 {len(_index)} 个代码（{time.strftime('%Y-%m-%d', time.localtime(last[1]))} 更新）"
        rows: list[tuple[str, str, str, int]] = []
        src = "Nasdaq Trader"
        try:
            r = await self.http.get(NASDAQ_URL, min_interval=5, timeout=40)
            rows = parse_nasdaq(r.text)
        except Exception:  # noqa: BLE001
            rows = []
        if len(rows) < 1000:
            src = "SEC"
            contact = settings.get("crawler.bot_contact") or "admin@localhost"
            r = await self.http.get(SEC_URL, min_interval=5, timeout=40,
                                    headers={"User-Agent": f"{settings.get('crawler.bot_token') or 'ZyllBot'} {contact}"})
            rows = parse_sec(r.json())
        if len(rows) < 1000:
            raise RuntimeError(f"代码表数量异常（{len(rows)}），保留旧数据")

        def replace(c):
            c.execute("DELETE FROM us_symbols")
            c.executemany("INSERT OR REPLACE INTO us_symbols VALUES (?, ?, ?, ?)", rows)
        await store.run(replace)
        await store.kv_set("symbols:updated", src)
        n = await load_index()
        return f"{n} 个代码（来源 {src}）"
