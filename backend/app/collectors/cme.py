"""CME 股指期货延迟报价 + 大宗交易（Block Trades）。

报价接口在 CME robots.txt 中对通用爬虫是允许的；CME 有反爬虫防护，若被拦截，
“数据源”页面会显示错误。大宗交易接口地址需确认后通过 CME_BLOCKS_URL 配置。
"""
from __future__ import annotations

import re
import time
from typing import Any

from .. import cache, settings
from ..http import PoliteClient

QUOTE_URL = "https://www.cmegroup.com/CmeWS/mvc/Quotes/Future/{pid}/G"
NAMES = {"ES": "E-mini 标普500", "NQ": "E-mini 纳指100", "YM": "E-mini 道指", "RTY": "E-mini 罗素2000"}


def num(v: Any) -> float | None:
    if v is None:
        return None
    s = re.sub(r"[^\d.\-+]", "", str(v))
    if s in ("", "-", "+", "."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_cme_quotes(js: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for q in (js or {}).get("quotes") or []:
        out.append({
            "contract": q.get("quoteCode") or q.get("code") or "",
            "month": q.get("expirationMonth") or "",
            "last": num(q.get("last")),
            "change": num(q.get("change")),
            "change_pct": num(q.get("percentageChange")),
            "prior_settle": num(q.get("priorSettle")),
            "open": num(q.get("open")),
            "high": num(q.get("high")),
            "low": num(q.get("low")),
            "volume": num(q.get("volume")),
            "updated": re.sub(r"<[^>]+>", " ", q.get("updated") or "").strip(),
        })
    return out


BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
SINA_URL = "https://hq.sinajs.cn/list={codes}"
SINA_HDR = {"Referer": "https://finance.sina.com.cn/", "User-Agent": BROWSER_UA}
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=5d"
YAHOO_HDR = {"User-Agent": BROWSER_UA, "Accept": "application/json"}
SOURCES = ["sina", "yahoo", "cme"]
_SINA_LINE = re.compile(r'var hq_str_(\w+)="([^"]*)"')


def parse_sina_hf(text: str) -> dict[str, dict[str, Any]]:
    """新浪外盘期货 hf_XX：0 最新价, 2 买价, 3 卖价, 4 最高, 5 最低, 6 时间, 7 昨结算, 8 开盘, 9 持仓, 12 日期, 13 名称。"""
    out = {}
    for code, body in _SINA_LINE.findall(text):
        f = body.split(",")
        if not code.startswith("hf_") or len(f) < 13 or not num(f[0]):
            continue
        last, prev = num(f[0]), num(f[7])
        out[code[3:].upper()] = {
            "contract": code[3:].upper(), "month": "主力", "last": last,
            "change": round(last - prev, 4) if last and prev else None,
            "change_pct": round((last / prev - 1) * 100, 3) if last and prev else None,
            "prior_settle": prev, "open": num(f[8]), "high": num(f[4]), "low": num(f[5]), "volume": None,
            "updated": f"{f[12]} {f[6]}".strip(),
        }
    return out


def parse_yahoo_chart(js: dict[str, Any]) -> dict[str, Any] | None:
    res = ((js or {}).get("chart") or {}).get("result") or []
    if not res:
        return None
    m = res[0].get("meta") or {}
    last = num(m.get("regularMarketPrice"))
    prev = num(m.get("previousClose") or m.get("chartPreviousClose"))
    if last is None:
        return None
    t = m.get("regularMarketTime")
    return {
        "contract": str(m.get("symbol") or ""), "month": "主力", "last": last,
        "change": round(last - prev, 4) if prev else None,
        "change_pct": round((last / prev - 1) * 100, 3) if prev else None,
        "prior_settle": prev, "open": None, "high": num(m.get("regularMarketDayHigh")), "low": num(m.get("regularMarketDayLow")),
        "volume": num(m.get("regularMarketVolume")),
        "updated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(t)) if isinstance(t, (int, float)) else "",
    }


class CmeCollector:
    """股指期货报价：按后台设置的顺序依次尝试新浪、雅虎、CME，每个品种取第一个成功的来源。"""

    def __init__(self, http: PoliteClient) -> None:
        self.http = http
        self.bad: dict[str, float] = {}  # 来源连续失败后暂停一段时间，避免每轮都等超时

    @property
    def products(self) -> list[tuple[str, str]]:
        raw = str(settings.get("sources.cme_futures.products") or "")
        return [tuple(x.strip().upper().split(":", 1)) for x in raw.split(",") if ":" in x]  # type: ignore[misc]

    @property
    def order(self) -> list[str]:
        raw = settings.get_list("sources.cme_futures.order") or SOURCES
        return [x.lower() for x in raw if x.lower() in SOURCES]

    async def _sina(self, roots: list[str]) -> dict[str, dict[str, Any]]:
        r = await self.http.get(SINA_URL.format(codes=",".join(f"hf_{x}" for x in roots)), headers=SINA_HDR, min_interval=1, timeout=8)
        return parse_sina_hf(r.content.decode("gbk", errors="replace"))

    async def _yahoo(self, roots: list[str]) -> dict[str, dict[str, Any]]:
        out = {}
        for root in roots:
            r = await self.http.get(YAHOO_URL.format(sym=f"{root}=F"), headers=YAHOO_HDR, min_interval=1, timeout=8)
            if (q := parse_yahoo_chart(r.json())):
                out[root] = q
        return out

    async def _cme(self, roots: list[str]) -> dict[str, list[dict[str, Any]]]:
        pids = dict(self.products)
        out = {}
        for root in roots:
            if root not in pids:
                continue
            r = await self.http.get(QUOTE_URL.format(pid=pids[root]), min_interval=2, timeout=8,
                                    headers={"Accept": "application/json", "User-Agent": BROWSER_UA})
            if (contracts := parse_cme_quotes(r.json())):
                out[root] = contracts
        return out

    async def refresh_quotes(self) -> str:
        roots = [r for r, _ in self.products]
        result: dict[str, Any] = {}
        used, errors = [], []
        for src in self.order:
            todo = [r for r in roots if r not in result]
            if not todo:
                break
            if self.bad.get(src, 0) > time.time():
                continue
            try:
                got = await getattr(self, f"_{src}")(todo)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{src}: {type(e).__name__}: {e}"[:200])
                self.bad[src] = time.time() + 600  # 失败的来源 10 分钟内跳过
                continue
            for root, q in got.items():
                if src == "cme":
                    front = max(q[:3], key=lambda c: c["volume"] or 0)  # 主力合约：前三个里成交量最大
                    result[root] = {"root": root, "name": NAMES.get(root, root), "front": front, "curve": q[:6], "source": "CME"}
                else:
                    result[root] = {"root": root, "name": NAMES.get(root, root), "front": q, "curve": [q], "source": {"sina": "新浪财经", "yahoo": "Yahoo"}[src]}
            if got:
                used.append(f"{src} {len(got)}")
        if not result:
            raise RuntimeError("；".join(errors) or "所有来源都没有数据")
        payload = {"updated": time.time(), "futures": result, "delayed": "cme" in "".join(used)}
        cache.put("futures:cme", payload, topic="futures", push=payload)
        missing = [r for r in roots if r not in result]
        return f"{len(result)} 个品种（{'，'.join(used)}）" + (f"；缺少 {','.join(missing)}" if missing else "") + (f"；{'；'.join(errors)}" if errors else "")

    async def refresh_blocks(self) -> str:
        url = settings.get("sources.cme_blocks.url")
        if not url:
            raise RuntimeError("未填写接口地址")
        r = await self.http.get(url, min_interval=5, headers={"Accept": "application/json"})
        js = r.json()
        items = js if isinstance(js, list) else ((js or {}).get("items") or (js or {}).get("data") or (js or {}).get("blockTrades") or [])
        rows = []
        for it in items[:500]:
            if not isinstance(it, dict):
                continue
            low = {k.lower(): v for k, v in it.items()}
            rows.append({
                "time": low.get("time") or low.get("tradetime") or low.get("tradedate") or "",
                "product": low.get("product") or low.get("productname") or low.get("productcode") or "",
                "contract": low.get("contract") or low.get("symbol") or low.get("contractcode") or "",
                "type": low.get("type") or low.get("tradetype") or "",
                "qty": num(low.get("qty") or low.get("quantity") or low.get("size")),
                "price": num(low.get("price") or low.get("tradeprice") or low.get("netprice")),
            })
        cache.put("futures:blocks", {"updated": time.time(), "rows": rows}, topic="futures_blocks")
        return f"{len(rows)} 笔"
