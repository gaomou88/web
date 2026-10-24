"""美股行情（全站统一来源，已弃用 Cboe）：新浪财经 → 腾讯财经 → Yahoo 依次兜底，全部实时抓取。

- 个股：新浪 gb_ 批量接口（每次最多 60 只），含盘前盘后价、成交量、市值、中文名；
- 指数：用户自选（每人最多 5 个），新浪没有的自动改用 Yahoo；
- 成交最多：新浪美股排行（按成交量）+ 常见活跃股票池，按成交额 / 成交量两种口径排序；
- 价格变化时推送 ticks（与 WebSocket 实时行情合并），完整快照有变化时推送 snap。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .. import cache, holidays, settings, store, universe
from ..http import PoliteClient

log = logging.getLogger("market")
ET = ZoneInfo("America/New_York")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
SINA_HDR = {"Referer": "https://finance.sina.com.cn/", "User-Agent": UA}
SINA_RANK = ("https://stock.finance.sina.com.cn/usstock/api/jsonp.php/IO.XSRV2.CallbackList['zy']/"
             "US_CategoryService.getList?page={page}&num=60&sort={sort}&asc=0&market=&id=")
YAHOO_SPARK = "https://query1.finance.yahoo.com/v8/finance/spark?symbols={syms}&range=1d&interval=5m"

# 指数目录：代码 → 名称和各家代码
INDEX_CATALOG: dict[str, dict[str, str]] = {
    "DJI": {"zh": "道琼斯工业", "en": "Dow Jones", "sina": "gb_$dji", "yahoo": "^DJI", "tv": "DJ:DJI"},
    "NDX": {"zh": "纳斯达克100", "en": "Nasdaq 100", "sina": "gb_$ndx", "yahoo": "^NDX", "tv": "NASDAQ:NDX"},
    "SPX": {"zh": "标普500", "en": "S&P 500", "sina": "gb_$inx", "yahoo": "^GSPC", "tv": "SP:SPX"},
    "RUT": {"zh": "罗素2000", "en": "Russell 2000", "sina": "", "yahoo": "^RUT", "tv": "TVC:RUT"},
    "VIX": {"zh": "VIX 恐慌指数", "en": "VIX", "sina": "", "yahoo": "^VIX", "tv": "TVC:VIX"},
    "IXIC": {"zh": "纳斯达克综合", "en": "Nasdaq Composite", "sina": "gb_$ixic", "yahoo": "^IXIC", "tv": "NASDAQ:IXIC"},
    "SOX": {"zh": "费城半导体", "en": "PHLX Semiconductor", "sina": "", "yahoo": "^SOX", "tv": "NASDAQ:SOX"},
    "NYA": {"zh": "纽约证交所综合", "en": "NYSE Composite", "sina": "", "yahoo": "^NYA", "tv": "NYSE:NYA"},
    "DXY": {"zh": "美元指数", "en": "US Dollar Index", "sina": "", "yahoo": "DX-Y.NYB", "tv": "TVC:DXY"},
    "TNX": {"zh": "10年美债收益率", "en": "10Y Treasury Yield", "sina": "", "yahoo": "^TNX", "tv": "TVC:TNX"},
    "HSI": {"zh": "恒生指数", "en": "Hang Seng", "sina": "", "yahoo": "^HSI", "tv": "TVC:HSI"},
    "SSEC": {"zh": "上证指数", "en": "SSE Composite", "sina": "", "yahoo": "000001.SS", "tv": "SSE:000001"},
    "N225": {"zh": "日经225", "en": "Nikkei 225", "sina": "", "yahoo": "^N225", "tv": "TVC:NI225"},
    "FTSE": {"zh": "英国富时100", "en": "FTSE 100", "sina": "", "yahoo": "^FTSE", "tv": "TVC:UKX"},
    "DAX": {"zh": "德国DAX", "en": "DAX", "sina": "", "yahoo": "^GDAXI", "tv": "XETR:DAX"},
    "STOXX50": {"zh": "欧洲斯托克50", "en": "Euro Stoxx 50", "sina": "", "yahoo": "^STOXX50E", "tv": "TVC:SX5E"},
}
DEFAULT_INDICES = ["DJI", "NDX", "SPX", "RUT", "VIX"]
MAX_INDICES = 5

# 成交活跃股票池（新浪排行接口不可用时也能排出“成交最多”）
POPULAR = """SPY QQQ IWM DIA TQQQ SQQQ SOXL SOXS SPXL SPXS TNA TZA UVXY VXX TLT HYG LQD XLF XLE XLK XLV GLD SLV USO GDX
TSLA NVDA AAPL MSFT AMZN META GOOGL GOOG AMD AVGO PLTR NFLX INTC MU SMCI ARM QCOM TXN MRVL LRCX AMAT KLAC ON TSM ASML
COIN MSTR HOOD SOFI F GM BAC JPM WFC C GS MS V MA PYPL XYZ T VZ PFE MRK JNJ LLY UNH CVS ABBV NIO LCID RIVN XPEV LI
AAL UAL DAL CCL NCLH UBER LYFT BABA PDD JD BIDU GME AMC MARA RIOT CLSK CIFR HUT WULF IONQ RGTI QBTS SOUN BBAI APLD CRWV
OKLO SMR NBIS RKLB ASTS ACHR JOBY UPST AFRM DKNG SNOW SHOP CRM ORCL ADBE CSCO IBM DELL HPE WMT COST TGT KO PEP MCD SBUX
NKE DIS WBD BA XOM CVX OXY SLB HAL KMI ET VALE NU ITUB BBD GRAB SE CPNG TEVA SNAP PINS RBLX U PATH AI TTD ROKU ZM DOCU
CMCSA CHWY W ETSY EBAY KHC KVUE WBA MO PM BMY GILD AMGN MRNA NVO HIMS TSLL NVDL CONL MSTU BITX IBIT FBTC ETHA""".split()


def _f(v: Any) -> float | None:
    try:
        x = float(str(v).replace(",", ""))
        return x if x == x else None  # NaN
    except (TypeError, ValueError):
        return None


def market_session(now: datetime | None = None) -> str:
    """当前美股时段：pre 盘前 / regular 盘中 / post 盘后 / closed 休市（已计入假日和提前收盘）。"""
    t = (now or datetime.now(ET)).astimezone(ET)
    if not holidays.us_trading_day(t.date()):
        return "closed"
    close = holidays.us_close_hour(t.date()) * 60
    m = t.hour * 60 + t.minute
    if 4 * 60 <= m < 9 * 60 + 30:
        return "pre"
    if 9 * 60 + 30 <= m < close:
        return "regular"
    if close <= m < close + 4 * 60:
        return "post"
    return "closed"


def _session_fields(sess: str, price: float | None, prev26: float | None, ext: float | None) -> dict[str, Any]:
    """按时段整理价格：
    - 盘前（新交易日已开始）：新浪的最新价仍是上一交易日收盘价，此时“昨收”应取它，实时价看盘前价；
    - 盘中 / 盘后 / 休市：昨收取上一交易日收盘价，盘后用盘后价作为实时价。"""
    if sess == "pre":
        prev_close = price
        live = ext or price
    else:
        prev_close = prev26
        live = (ext if sess == "post" and ext else price)
    return {"prev_close": prev_close, "live": live}


def parse_sina_stocks(text: str, sess: str) -> dict[str, dict[str, Any]]:
    """新浪美股 gb_xxx：0 中文名, 1 最新价, 2 涨跌幅%, 3 时间, 4 涨跌额, 5 开盘, 6 最高, 7 最低, 8/9 52周高低,
    10 成交量, 12 市值, 13 每股收益, 14 市盈率, 21 盘前盘后价, 22 其涨跌幅%, 24 其时间, 26 昨收。"""
    out = {}
    for code, body in re.findall(r'var hq_str_gb_([\w$.]+)="([^"]*)"', text):
        f = body.split(",")
        if len(f) < 27 or code.startswith("$"):
            continue
        price = _f(f[1])
        if not price:
            continue
        ext = _f(f[21]) or None
        pf = _session_fields(sess, price, _f(f[26]), ext)
        if sess == "regular":
            ext = None  # 盘中不显示上一时段的盘前/盘后价，避免误导
        vol = _f(f[10])
        q = {
            "symbol": code.upper().replace("$", "."), "name": f[0].strip(), "price": price,
            "open": _f(f[5]), "high": _f(f[6]), "low": _f(f[7]), "high52": _f(f[8]), "low52": _f(f[9]),
            "volume": vol, "amount": round(vol * price) if vol else None, "mktcap": _f(f[12]), "pe": _f(f[14]),
            "ext_price": ext, "ext_pct": _f(f[22]) if ext else None, "src": "sina", **pf,
        }
        _derive(q)
        out[q["symbol"]] = q
    return out


def parse_sina_indices(text: str) -> dict[str, dict[str, Any]]:
    out = {}
    for code, body in re.findall(r'var hq_str_(gb_\$\w+)="([^"]*)"', text):
        f = body.split(",")
        if len(f) < 27 or not _f(f[1]):
            continue
        price, prev = _f(f[1]), _f(f[26])
        out[code] = {"price": price, "prev_close": prev, "open": _f(f[5]), "high": _f(f[6]), "low": _f(f[7]), "live": price, "src": "sina"}
    return out


def parse_tencent_stocks(text: str) -> dict[str, dict[str, Any]]:
    """腾讯美股 usXXX（~ 分隔）：1 名称, 2 代码.交易所, 3 最新价, 4 昨收, 5 开盘, 6 成交量, 33 最高, 34 最低, 44 市值（亿美元）。"""
    out = {}
    for _code, body in re.findall(r'v_us([\w.$-]+)="([^"]*)"', text):
        f = body.split("~")
        if len(f) < 35 or not _f(f[3]):
            continue
        sym = f[2].split(".")[0].upper()
        price, vol = _f(f[3]), _f(f[6])
        q = {"symbol": sym, "name": f[1], "price": price, "prev_close": _f(f[4]), "live": price, "open": _f(f[5]),
             "high": _f(f[33]), "low": _f(f[34]), "volume": vol, "amount": round(vol * price) if vol and price else None,
             "mktcap": (_f(f[44]) or 0) * 1e8 if len(f) > 44 and _f(f[44]) else None, "src": "tencent"}
        _derive(q)
        out[sym] = q
    return out


def parse_yahoo_spark(js: Any) -> dict[str, dict[str, Any]]:
    """兼容两种返回格式：{sym: {...}} 或 {"spark": {"result": [...]}}。"""
    out: dict[str, dict[str, Any]] = {}
    items: list[tuple[str, dict[str, Any]]] = []
    if isinstance(js, dict) and "spark" in js:
        for r in (js.get("spark") or {}).get("result") or []:
            resp = (r.get("response") or [{}])[0]
            meta = resp.get("meta") or {}
            closes = (((resp.get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
            items.append((r.get("symbol") or meta.get("symbol"), {"close": closes, "timestamp": resp.get("timestamp") or [],
                                                                  "chartPreviousClose": meta.get("chartPreviousClose"),
                                                                  "previousClose": meta.get("previousClose"),
                                                                  "price": meta.get("regularMarketPrice")}))
    elif isinstance(js, dict):
        items = [(k, v) for k, v in js.items() if isinstance(v, dict)]
    for sym, v in items:
        closes = [c for c in (v.get("close") or []) if c is not None]
        price = _f(v.get("price")) or (closes[-1] if closes else None)
        if price is None:
            continue
        prev = _f(v.get("previousClose")) or _f(v.get("chartPreviousClose"))
        out[sym] = {"price": price, "prev_close": prev, "live": price, "spark": [round(c, 4) for c in closes[-80:]], "src": "yahoo"}
    return out


def parse_sina_rank(text: str) -> list[dict[str, Any]]:
    m = re.search(r"\((\{.*\})\)", text, re.S)
    if not m:
        return []
    raw = m.group(1)
    try:
        js = json.loads(raw)
    except ValueError:
        js = json.loads(re.sub(r'([{,])\s*([A-Za-z_]\w*)\s*:', r'\1"\2":', raw))  # 旧接口的键名没有引号
    out = []
    for it in js.get("data") or []:
        sym = str(it.get("symbol") or "").upper()
        price, vol = _f(it.get("price")), _f(it.get("volume"))
        if not sym or not price:
            continue
        out.append({"symbol": sym, "name": it.get("cname") or it.get("name") or "", "price": price,
                    "prev_close": _f(it.get("preclose")), "volume": vol, "amount": round(vol * price) if vol else None,
                    "change_pct": _f(it.get("chg")), "mktcap": _f(it.get("mktcap"))})
    return out


def _derive(q: dict[str, Any]) -> None:
    live, prev = q.get("live"), q.get("prev_close")
    q["change"] = round(live - prev, 4) if live is not None and prev else None
    q["change_pct"] = round((live / prev - 1) * 100, 3) if live is not None and prev else None


# ---------------- 采集器 ----------------
class MarketCollector:
    def __init__(self, http: PoliteClient) -> None:
        self.http = http
        self.snap: dict[str, dict[str, Any]] = {}
        self.idx: dict[str, dict[str, Any]] = {}
        self.rank: dict[str, Any] = {}
        self.rank_at = 0.0
        self.spark_at = 0.0
        self.bad_until: dict[str, float] = {}

    @property
    def order(self) -> list[str]:
        raw = [x.lower() for x in settings.get_list("sources.market.order")] or ["sina", "tencent", "yahoo"]
        return [x for x in raw if x in ("sina", "tencent", "yahoo")]

    def _usable(self, src: str) -> bool:
        return self.bad_until.get(src, 0) < time.time()

    def _bad(self, src: str, e: Exception) -> None:
        self.bad_until[src] = time.time() + 120
        log.warning("行情来源 %s 失败，2 分钟内改用其他来源：%s", src, e)

    # ----- 个股 -----
    async def fetch_stocks(self, syms: list[str]) -> dict[str, dict[str, Any]]:
        sess = market_session()
        got: dict[str, dict[str, Any]] = {}
        for src in self.order:
            todo = [s for s in syms if s not in got]
            if not todo or not self._usable(src):
                continue
            try:
                for i in range(0, len(todo), 60):
                    chunk = todo[i:i + 60]
                    if src == "sina":
                        r = await self.http.get("https://hq.sinajs.cn/list=" + ",".join("gb_" + s.lower().replace(".", "$").replace("-", "$") for s in chunk),
                                                headers=SINA_HDR, min_interval=0.3, timeout=8)
                        got.update(parse_sina_stocks(r.content.decode("gbk", errors="replace"), sess))
                    elif src == "tencent":
                        r = await self.http.get("https://qt.gtimg.cn/q=" + ",".join("us" + s.replace("-", ".") for s in chunk),
                                                headers={"User-Agent": UA}, min_interval=0.3, timeout=8)
                        got.update(parse_tencent_stocks(r.content.decode("gbk", errors="replace")))
                    else:
                        r = await self.http.get(YAHOO_SPARK.format(syms=",".join(s.replace(".", "-") for s in chunk)),
                                                headers={"User-Agent": UA, "Accept": "application/json"}, min_interval=0.5, timeout=10)
                        for k, v in parse_yahoo_spark(r.json()).items():
                            v["symbol"] = k.replace("-", ".").upper()
                            _derive(v)
                            got[v["symbol"]] = v
            except Exception as e:  # noqa: BLE001
                self._bad(src, e)
        return got

    async def fetch_one(self, sym: str) -> dict[str, Any] | None:
        got = await self.fetch_stocks([sym])
        q = got.get(sym)
        if q:
            self._store({sym: q})
        return q

    def _store(self, got: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        from . import realtime
        changed = {}
        now_ms = int(time.time() * 1000)
        for sym, q in got.items():
            q["ts"] = now_ms
            old = self.snap.get(sym)
            if old is None or any(old.get(k) != q.get(k) for k in ("live", "prev_close", "volume", "ext_price", "high", "low")):
                changed[sym] = q
            self.snap[sym] = q
            if q.get("live") is not None and not realtime.ws_covered(sym):
                realtime.tick(sym, q["live"], now_ms, polled=True)
        return changed

    def snapshot(self, sym: str) -> dict[str, Any] | None:
        return self.snap.get(sym)

    # ----- 指数 -----
    async def fetch_indices(self, codes: list[str]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        sina_codes = {INDEX_CATALOG[c]["sina"]: c for c in codes if INDEX_CATALOG.get(c, {}).get("sina")}
        if sina_codes and "sina" in self.order and self._usable("sina"):
            try:
                r = await self.http.get("https://hq.sinajs.cn/list=" + ",".join(sina_codes), headers=SINA_HDR, min_interval=0.3, timeout=8)
                for sc, q in parse_sina_indices(r.content.decode("gbk", errors="replace")).items():
                    out[sina_codes[sc]] = q
            except Exception as e:  # noqa: BLE001
                self._bad("sina", e)
        need_spark = time.time() - self.spark_at > 60
        todo = [c for c in codes if c in INDEX_CATALOG and (c not in out or need_spark)]
        if todo and self._usable("yahoo"):
            ysyms = {INDEX_CATALOG[c]["yahoo"]: c for c in todo}
            try:
                r = await self.http.get(YAHOO_SPARK.format(syms=",".join(ysyms)), headers={"User-Agent": UA, "Accept": "application/json"},
                                        min_interval=0.5, timeout=10)
                for ys, q in parse_yahoo_spark(r.json()).items():
                    c = ysyms.get(ys)
                    if not c:
                        continue
                    if c in out:  # 新浪已有实时价，只补分时走势
                        out[c]["spark"] = q.get("spark")
                    else:
                        out[c] = q
                if need_spark:
                    self.spark_at = time.time()
            except Exception as e:  # noqa: BLE001
                self._bad("yahoo", e)
        for c, q in out.items():
            if "spark" not in q and self.idx.get(c, {}).get("spark"):
                q["spark"] = self.idx[c]["spark"]
            _derive(q)
            q.update(code=c, name=INDEX_CATALOG[c]["zh"], name_en=INDEX_CATALOG[c]["en"])
        return out

    # ----- 成交最多 -----
    async def refresh_rank(self) -> None:
        pool: dict[str, dict[str, Any]] = {}
        if "sina" in self.order and self._usable("sina"):
            try:
                for page in (1, 2):
                    r = await self.http.get(SINA_RANK.format(page=page, sort="volume"), headers=SINA_HDR, min_interval=0.5, timeout=10)
                    for it in parse_sina_rank(r.content.decode("gbk", errors="replace")):
                        pool[it["symbol"]] = it
            except Exception as e:  # noqa: BLE001
                log.info("新浪排行接口不可用，改用活跃股票池：%s", e)
        # 活跃股票池补充实时数据（成交额排名主要靠它，因为高价股成交量不一定靠前）
        mine = set(universe.market_symbols())  # 这些主循环已经在抓
        extra = [s for s in POPULAR if s not in mine]
        if extra:
            self._store(await self.fetch_stocks(extra))
        for s in POPULAR:
            if s in self.snap:
                pool[s] = {**pool.get(s, {}), **self.snap[s]}
        rows = [r for r in pool.values() if r.get("volume")]
        for r in rows:
            r.setdefault("change_pct", None)
        slim = lambda r: {k: r.get(k) for k in ("symbol", "name", "live", "price", "change_pct", "volume", "amount", "mktcap", "ext_price", "ext_pct")}  # noqa: E731
        self.rank = {
            "updated": time.time(),
            "amount": [slim(r) for r in sorted(rows, key=lambda r: r.get("amount") or 0, reverse=True)[:30]],
            "volume": [slim(r) for r in sorted(rows, key=lambda r: r.get("volume") or 0, reverse=True)[:30]],
            "pool": len(rows),
        }
        cache.put("market:rank", self.rank, topic="rank", push=self.rank)
        self.rank_at = time.time()

    # ----- 主循环 -----
    async def wanted_indices(self) -> list[str]:
        rows = await store.query("SELECT DISTINCT code FROM user_quotes WHERE kind = 'index'")
        codes = list(dict.fromkeys(settings.get_list("sources.market.default_indices") or DEFAULT_INDICES))
        codes += [r["code"] for r in rows if r["code"] not in codes]
        return [c for c in codes if c in INDEX_CATALOG]

    async def refresh(self) -> str:
        syms = universe.market_symbols()
        changed = self._store(await self.fetch_stocks(syms)) if syms else {}
        if changed:
            cache.publish("snap", changed)
        idx = await self.fetch_indices(await self.wanted_indices())
        if idx and idx != self.idx:
            self.idx.update(idx)
            cache.put("market:indices", self.idx, topic="indices", push=idx)
        rank_every = int(settings.get("sources.market.rank_interval") or 30)
        if settings.get("sources.market.rank_enabled") and time.time() - self.rank_at > rank_every * (1 if market_session() != "closed" else 10):
            await self.refresh_rank()
        cache.put("market:snap", self.snap)
        from .. import history
        await history.record_closes(self.snap, market_session())
        if syms and not self.snap and not idx:
            raise RuntimeError("新浪、腾讯、Yahoo 都没有返回数据")
        srcs = {}
        for q in self.snap.values():
            srcs[q.get("src")] = srcs.get(q.get("src"), 0) + 1
        return (f"个股 {len([s for s in syms if s in self.snap])}/{len(syms)}（" + "，".join(f"{k} {v}" for k, v in srcs.items()) +
                f"），指数 {len(idx)}，时段 {market_session()}" + (f"，成交榜 {self.rank.get('pool', 0)} 只" if self.rank else ""))
