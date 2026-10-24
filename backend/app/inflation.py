"""通胀：各货币所在地区的月度物价指数，用于“扣除通胀后的实际盈亏”。

通用通胀模型（按优先级逐月取数，缺的月份用下一级补）：
1. 管理员录入的数据（后台“通胀数据”）；
2. 官方物价指数：美国 CPI-U（FRED CPIAUCNS，未季调）；
3. 本站经济日历里抓到的 CPI 公布值：同比（CPI y/y）或环比（CPI m/m）；
4. 世界银行年度通胀率（FP.CPI.TOTL.ZG），这一年每个月按同样的速度均摊；
5. 以上都没有（例如最新几个月还没公布）：沿用最近 12 个月的平均速度外推。

把每月的变化串成指数 I(月)，按天线性插值。一笔 t 日花出去的钱，折算成今天的购买力 = 金额 × I(今天) / I(t)。
扣除通胀后的盈亏 = 现在的市值 − 按今天购买力计算的成本（卖出所得同样折算到今天）。

前端、App 和服务器都用同一张月度指数表（见 pnl.cpi_factor），保证三处结果一致。
"""
from __future__ import annotations

import csv
import io
import logging
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

from . import store

log = logging.getLogger("inflation")

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
WB_API = "https://api.worldbank.org/v2/country/{country}/indicator/FP.CPI.TOTL.ZG?format=json&per_page=80"

# 货币 → 地区（世界银行国家代码）、FRED 指数、日历里可用的 CPI 标题（按优先级）
REGIONS: dict[str, dict[str, Any]] = {
    "USD": {"name": "美国", "wb": "USA", "fred": "CPIAUCNS", "cal": ["CPI y/y", "CPI m/m"]},
    "CNY": {"name": "中国", "wb": "CHN", "cal": ["CPI y/y"]},
    "EUR": {"name": "欧元区", "wb": "EMU", "cal": ["Final CPI y/y", "CPI Flash Estimate y/y"]},
    "GBP": {"name": "英国", "wb": "GBR", "cal": ["CPI y/y"]},
    "JPY": {"name": "日本", "wb": "JPN", "cal": ["National CPI y/y", "National Core CPI y/y"]},
    "HKD": {"name": "中国香港", "wb": "HKG", "cal": []},
    "SGD": {"name": "新加坡", "wb": "SGP", "cal": []},
    "CAD": {"name": "加拿大", "wb": "CAN", "cal": ["CPI m/m"]},
    "AUD": {"name": "澳大利亚", "wb": "AUS", "cal": ["CPI y/y"]},
    "CHF": {"name": "瑞士", "wb": "CHE", "cal": ["CPI m/m"]},
    "NZD": {"name": "新西兰", "wb": "NZL", "cal": []},
}
SRC_NAMES = {"admin": "管理员录入", "fred": "官方 CPI 指数", "calendar": "日历公布值", "worldbank": "世界银行年度数据", "extrapolated": "按近期速度推算", "none": "无数据"}
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def month_add(m: str, k: int) -> str:
    y, mm = int(m[:4]), int(m[5:7]) - 1 + k
    return f"{y + mm // 12:04d}-{mm % 12 + 1:02d}"


def months_between(a: str, b: str) -> list[str]:
    out, m = [], a
    while m <= b and len(out) < 1200:
        out.append(m)
        m = month_add(m, 1)
    return out


def _pct(v: str) -> float | None:
    m = re.search(r"-?\d+(?:\.\d+)?", (v or "").replace(",", ""))
    return float(m.group(0)) if m else None


def ref_month(ts: int, title: str) -> str:
    """数据公布时间 → 这个数据所属的月份。一般是上个月；欧元区“快讯”在当月月底或下月初公布。"""
    d = datetime.fromtimestamp(ts, timezone.utc).date()
    if "Flash" in title:
        d -= timedelta(days=10)
        return f"{d.year:04d}-{d.month:02d}"
    first = d.replace(day=1) - timedelta(days=1)
    return f"{first.year:04d}-{first.month:02d}"


async def _calendar_points(ccy: str) -> dict[str, tuple[str, float]]:
    """日历里抓到的 CPI 公布值：{月份: ("yoy"/"mom", 数值)}。同一月份按标题优先级取。"""
    titles = REGIONS.get(ccy, {}).get("cal") or []
    if not titles:
        return {}
    rows = await store.query(
        f"SELECT ts, title, actual FROM econ_events WHERE currency = ? AND actual != '' AND title IN ({','.join('?' * len(titles))}) ORDER BY ts",
        (ccy, *titles))
    out: dict[str, tuple[int, str, float]] = {}
    for r in rows:
        v = _pct(r["actual"])
        if v is None or abs(v) > 50:
            continue
        m = ref_month(r["ts"], r["title"])
        pri = titles.index(r["title"])
        if m not in out or pri <= out[m][0]:
            out[m] = (pri, "mom" if "m/m" in r["title"] else "yoy", v)
    return {m: (k, v) for m, (_, k, v) in out.items()}


async def build(ccy: str, start: str, today: date | None = None) -> dict[str, Any]:
    """生成从 start（YYYY-MM）到本月的月度指数表。返回 {table: [[月, 指数]], sources: {月: 来源}, latest: {...}}。"""
    today = today or date.today()
    end = f"{today.year:04d}-{today.month:02d}"
    key = f"{ccy}|{start}|{end}"
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    rows = await store.query("SELECT month, idx, yoy, src FROM cpi_index WHERE region = ?", (ccy,))
    admin = {r["month"]: r for r in rows if r["src"] == "admin"}
    fred = {r["month"]: r["idx"] for r in rows if r["src"] == "fred" and r["idx"]}
    wb = {r["month"][:4]: r["yoy"] for r in rows if r["src"] == "worldbank" and r["yoy"] is not None}
    cal = await _calendar_points(ccy)
    months = months_between(min(start, end), end)
    # 需要同比时，往前多取一年用于外推
    yoy_of: dict[str, tuple[float, str]] = {}  # 月 → (该月的月度增长倍数, 来源)

    def monthly_from_yoy(y: float) -> float:
        return (1 + y / 100) ** (1 / 12)

    idx: dict[str, float] = {}
    src: dict[str, str] = {}
    prev_m = None
    recent: list[float] = []  # 最近 12 个月的月度倍数，用于外推
    for m in months:
        g, s = None, None
        a = admin.get(m)
        if a and a["idx"] and prev_m and admin.get(prev_m, {}).get("idx"):
            g, s = a["idx"] / admin[prev_m]["idx"], "admin"
        elif a and a["yoy"] is not None:
            g, s = monthly_from_yoy(a["yoy"]), "admin"
        elif m in fred and prev_m in fred:
            g, s = fred[m] / fred[prev_m], "fred"
        elif m in cal:
            kind, v = cal[m]
            g, s = (1 + v / 100, "calendar") if kind == "mom" else (monthly_from_yoy(v), "calendar")
        elif m[:4] in wb:
            g, s = monthly_from_yoy(wb[m[:4]]), "worldbank"
        elif recent:
            g, s = sum(recent) / len(recent), "extrapolated"
        elif str(int(m[:4]) - 1) in wb:
            g, s = monthly_from_yoy(wb[str(int(m[:4]) - 1)]), "extrapolated"
        else:
            g, s = 1.0, "none"
        if prev_m is None:
            idx[m], src[m] = 100.0, s
        else:
            idx[m], src[m] = idx[prev_m] * g, s
            if s not in ("none", "extrapolated"):
                recent = (recent + [g])[-12:]
        yoy_of[m] = (g, s)
        prev_m = m
    table = [[m, round(idx[m], 6)] for m in months]
    last12 = 1.0
    for m in months[-12:]:
        last12 *= yoy_of[m][0]
    known = [m for m in months if src[m] not in ("extrapolated", "none")]
    out = {"ccy": ccy, "region": REGIONS.get(ccy, {}).get("name", ccy), "table": table, "sources": src,
           "yoy_12m": round((last12 - 1) * 100, 2) if len(months) >= 12 else None,
           "last_known": known[-1] if known else None, "approx": any(src[m] in ("extrapolated", "none") for m in months),
           "no_data": all(src[m] == "none" for m in months)}
    _cache[key] = (time.time(), out)
    return out


def invalidate() -> None:
    _cache.clear()


async def tables_for(ccys: set[str], first_date: str | None) -> dict[str, Any]:
    """组合页面需要的各货币指数表（从最早交易的前一个月到本月）。"""
    if not first_date:
        first_date = date.today().isoformat()
    start = month_add(first_date[:7], -1)
    out = {}
    for c in sorted(ccys):
        if c in REGIONS:
            b = await build(c, start)
            out[c] = {k: b[k] for k in ("table", "yoy_12m", "last_known", "approx", "region", "no_data")}
    return out


# ---------------- 数据抓取 ----------------
def parse_fred(text: str) -> list[tuple[str, float]]:
    out = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 2 or not re.match(r"\d{4}-\d{2}-\d{2}$", row[0]):
            continue
        try:
            out.append((row[0][:7], float(row[1])))
        except ValueError:
            continue
    return out


def parse_wb(js: Any) -> list[tuple[str, float]]:
    if not isinstance(js, list) or len(js) < 2 or not isinstance(js[1], list):
        return []
    return [(str(r["date"]), float(r["value"])) for r in js[1] if isinstance(r, dict) and r.get("value") is not None and str(r.get("date", "")).isdigit()]


class InflationCollector:
    """每天更新一次：美国 CPI 指数（FRED）和各地区世界银行年度通胀率。日历里的 CPI 公布值不用抓，直接读。"""

    def __init__(self, http: Any) -> None:
        self.http = http

    async def refresh(self) -> str:
        msgs, now = [], int(time.time())
        for ccy, r in REGIONS.items():
            if r.get("fred"):
                try:
                    resp = await self.http.get(FRED_CSV.format(series=r["fred"]), min_interval=2, timeout=30)
                    rows = parse_fred(resp.text)
                    if rows:
                        await store.executemany("INSERT OR REPLACE INTO cpi_index (region, month, idx, yoy, src, updated_at) VALUES (?, ?, ?, NULL, 'fred', ?)",
                                                [(ccy, m, v, now) for m, v in rows])
                        msgs.append(f"{ccy} CPI 指数到 {rows[-1][0]}")
                except Exception as e:  # noqa: BLE001
                    msgs.append(f"{ccy} FRED 失败：{type(e).__name__}")
        ok = 0
        for ccy, r in REGIONS.items():
            try:
                resp = await self.http.get(WB_API.format(country=r["wb"]), min_interval=1, timeout=30)
                rows = parse_wb(resp.json())
            except Exception as e:  # noqa: BLE001
                log.info("世界银行 %s 获取失败：%s", ccy, e)
                continue
            if rows:
                ok += 1
                await store.executemany("INSERT OR REPLACE INTO cpi_index (region, month, idx, yoy, src, updated_at) VALUES (?, ?, NULL, ?, 'worldbank', ?)",
                                        [(ccy, f"{y}-01", v, now) for y, v in rows])
        msgs.append(f"世界银行 {ok}/{len(REGIONS)} 个地区")
        invalidate()
        return "；".join(msgs)
