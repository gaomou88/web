"""FINRA 免费公开数据。

1) 每日场外成交量（Reg SHO Daily Short Sale Volume，合并 TRF/ADF/ORF）
   —— 所有不在交易所撮合的成交（暗池 + 券商内部化），T 日傍晚发布。
2) ATS 周报（OTC Transparency API，免 Key）
   —— 每个暗池（ATS，即“机构”）在每只股票上的成交量；一级股票延迟约 2 周，二级约 4 周。
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import time

from .. import cache, holidays, settings, store
from ..http import HTTPStatusError, PoliteClient

ET = ZoneInfo("America/New_York")
DAILY_URL = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{d}.txt"
ATS_URL = "https://api.finra.org/data/group/otcMarket/name/weeklySummary"
JSON_HDR = {"Accept": "application/json"}


def parse_daily(text: str) -> list[dict[str, Any]]:
    rows = []
    for line in text.splitlines()[1:]:
        p = line.strip().split("|")
        if len(p) < 6 or not p[0].isdigit():
            continue  # 跳过尾行等非数据行
        try:
            rows.append({
                "trade_date": datetime.strptime(p[0], "%Y%m%d").date(),
                "symbol": p[1],
                "short_volume": float(p[2]),
                "short_exempt": float(p[3]),
                "total_volume": float(p[4]),
                "markets": p[5][:16],
            })
        except ValueError:
            continue
    return rows


def _filters(**eq: str) -> list[dict[str, str]]:
    return [{"compareType": "EQUAL", "fieldName": k, "fieldValue": v} for k, v in eq.items()]


def candidate_weeks(today: date, n: int = 10) -> list[str]:
    """最近 n 个周一（从上周开始往前），ATS 周报按周一作为 weekStartDate。"""
    monday = today - timedelta(days=today.weekday())
    return [(monday - timedelta(weeks=i)).isoformat() for i in range(1, n + 1)]


def _ratio_row(r: dict[str, Any]) -> dict[str, Any]:
    tot = r["total_volume"]
    return {"symbol": r["symbol"], "short": r["short_volume"], "total": tot,
            "ratio": r["short_volume"] / tot if tot else 0, "markets": r["markets"]}


class FinraCollector:
    def __init__(self, http: PoliteClient) -> None:
        self.http = http

    @property
    def watchlist(self) -> list[str]:
        return settings.get_list("sources.market.watchlist")

    # ================= 每日 =================
    async def backfill_daily(self, target_days: int = 66, per_run: int = 6) -> int:
        """补齐近约 3 个月的每日文件（用于全市场卖空占比走势），每次最多补几天，避免一次请求太多。"""
        rows = await store.query("SELECT DISTINCT trade_date AS d FROM finra_short_volume ORDER BY d")
        have = {r["d"] for r in rows}
        if len(have) >= target_days:
            return 0
        d = date.fromisoformat(min(have)) if have else datetime.now(ET).date()
        done = 0
        tries = 0
        while done < per_run and tries < per_run * 3 and len(have) + done < target_days:
            d -= timedelta(days=1)
            tries += 1
            if not holidays.us_trading_day(d) or d.isoformat() in have:
                continue
            if await store.kv_get(f"finra_missing:{d.isoformat()}"):
                continue
            try:
                r = await self.http.get(DAILY_URL.format(d=d.strftime("%Y%m%d")), min_interval=2)
            except HTTPStatusError as e:
                if e.status_code in (403, 404):
                    await store.kv_set(f"finra_missing:{d.isoformat()}", "1")
                    continue
                raise
            parsed = parse_daily(r.text)
            if parsed:
                await store.executemany("INSERT OR IGNORE INTO finra_short_volume VALUES (?, ?, ?, ?, ?, ?)",
                                        [(x["trade_date"].isoformat(), x["symbol"], x["short_volume"], x["short_exempt"], x["total_volume"], x["markets"]) for x in parsed])
                done += 1
        return done

    async def refresh_daily(self) -> str:
        latest = await store.query_one("SELECT MAX(trade_date) AS d FROM finra_short_volume")
        last = latest["d"] if latest else None
        today = datetime.now(ET).date()
        for back in range(0, 8):
            d = today - timedelta(days=back)
            if d.weekday() >= 5:
                continue
            if last and d.isoformat() <= last:
                added = await self.backfill_daily()
                if added or not cache.get_raw("finra:daily:summary"):
                    await self.publish_daily_summary()
                return f"已是最新（{last}）" + (f"，回填历史 {added} 天" if added else "")
            try:
                r = await self.http.get(DAILY_URL.format(d=d.strftime("%Y%m%d")), min_interval=2)
            except HTTPStatusError as e:
                if e.status_code in (403, 404):  # 当日文件尚未发布
                    continue
                raise
            rows = parse_daily(r.text)
            if not rows:
                continue
            await store.executemany(
                """INSERT OR IGNORE INTO finra_short_volume VALUES (?, ?, ?, ?, ?, ?)""",
                [(x["trade_date"].isoformat(), x["symbol"], x["short_volume"], x["short_exempt"], x["total_volume"], x["markets"])
                 for x in rows],
            )
            await store.execute("DELETE FROM finra_short_volume WHERE trade_date < ?", ((date.today() - timedelta(days=400)).isoformat(),))
            await self.publish_daily_summary()
            return f"{d} 共 {len(rows)} 只股票"
        return "近 7 天没有找到新文件"

    async def publish_daily_summary(self) -> None:
        latest = await store.query_one("SELECT MAX(trade_date) AS d FROM finra_short_volume")
        d = latest["d"] if latest else None
        if not d:
            return
        top_vol = await store.query(
            "SELECT * FROM finra_short_volume WHERE trade_date = ? ORDER BY total_volume DESC LIMIT 60", (d,))
        top_short = await store.query(
            """SELECT * FROM finra_short_volume WHERE trade_date = ? AND total_volume >= 2000000
               ORDER BY short_volume / total_volume DESC LIMIT 40""", (d,))
        wl = self.watchlist
        marks = ",".join("?" * len(wl)) or "''"
        watch = await store.query(
            f"SELECT * FROM finra_short_volume WHERE trade_date = ? AND symbol IN ({marks})", (d, *wl))
        since = (date.fromisoformat(d) - timedelta(days=90)).isoformat()
        agg = await store.query(
            """SELECT trade_date, SUM(short_volume) AS s, SUM(total_volume) AS t FROM finra_short_volume
               WHERE trade_date >= ? GROUP BY trade_date ORDER BY trade_date""", (since,))
        summary = {
            "date": d,
            "fetched": time.time(),
            "top_volume": [_ratio_row(x) for x in top_vol],
            "top_short_ratio": [_ratio_row(x) for x in top_short],
            "watchlist": sorted((_ratio_row(x) for x in watch), key=lambda r: wl.index(r["symbol"]) if r["symbol"] in wl else 999),
            # 全市场场外卖空占比（类似 DIX 的思路）
            "market": [{"date": a["trade_date"], "short": a["s"], "total": a["t"], "ratio": a["s"] / a["t"] if a["t"] else 0} for a in agg],
        }
        cache.put("finra:daily:summary", summary, topic="finra_daily")

    async def watch_rows(self, symbols: list[str]) -> dict[str, Any]:
        """指定股票在最新一天的场外成交（用于按用户同步的关注列表）。"""
        latest = await store.query_one("SELECT MAX(trade_date) AS d FROM finra_short_volume")
        d = latest["d"] if latest else None
        if not d or not symbols:
            return {"date": d, "rows": [], "missing": symbols}
        marks = ",".join("?" * len(symbols))
        rows = await store.query(f"SELECT * FROM finra_short_volume WHERE trade_date = ? AND symbol IN ({marks})", (d, *symbols))
        got = {r["symbol"]: _ratio_row(r) for r in rows}
        return {"date": d, "rows": [got[s] for s in symbols if s in got], "missing": [s for s in symbols if s not in got]}

    async def symbol_history(self, symbol: str, days: int = 120) -> list[dict[str, Any]]:
        rows = await store.query(
            "SELECT * FROM finra_short_volume WHERE symbol = ? AND trade_date >= ? ORDER BY trade_date",
            (symbol, (date.today() - timedelta(days=days)).isoformat()))
        return [{"date": x["trade_date"], "short": x["short_volume"], "total": x["total_volume"],
                 "ratio": x["short_volume"] / x["total_volume"] if x["total_volume"] else 0} for x in rows]

    # ================= ATS 周报 =================
    async def _post(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        r = await self.http.request("POST", ATS_URL, json_body=body, headers=JSON_HDR, min_interval=1.5)
        data = r.json()
        return data if isinstance(data, list) else []

    async def latest_week(self) -> str | None:
        """FINRA 不允许只按 tier 排序查最新一周（会返回 400），改为从最近的周一往前逐周试探。结果缓存 6 小时。"""
        cached = cache.get("finra:ats:latest_week")
        if cached:
            return cached
        for week in candidate_weeks(datetime.now(ET).date()):
            rows = await self._post({
                "limit": 1,
                "compareFilters": _filters(summaryTypeCode="ATS_W_FIRM", tierIdentifier="T1", weekStartDate=week),
            })
            if rows:
                cache.put("finra:ats:latest_week", week, ttl=6 * 3600)
                return week
        return None

    async def refresh_weekly(self) -> str:
        week = await self.latest_week()
        if not week:
            raise RuntimeError("未获取到 ATS 周报日期")
        rows = []
        for tier in ("T1", "T2", "OTCE"):  # 分级别查询，每次不超过 5000 条
            rows += await self._post({"limit": 5000, "compareFilters": _filters(summaryTypeCode="ATS_W_FIRM", tierIdentifier=tier, weekStartDate=week)})
        firms: dict[str, dict[str, Any]] = defaultdict(lambda: {"shares": 0.0, "trades": 0})
        for r in rows:
            key = r.get("MPID") or r.get("marketParticipantName") or "?"
            f = firms[key]
            f["mpid"] = r.get("MPID") or ""
            f["name"] = r.get("marketParticipantName") or key
            f["shares"] += float(r.get("totalWeeklyShareQuantity") or 0)
            f["trades"] += int(float(r.get("totalWeeklyTradeCount") or 0))
        total = sum(f["shares"] for f in firms.values()) or 1
        ranking = sorted(firms.values(), key=lambda f: f["shares"], reverse=True)
        for f in ranking:
            f["share_pct"] = f["shares"] / total
            f["avg_size"] = f["shares"] / f["trades"] if f["trades"] else 0
        cache.put("finra:ats:firms", {"week": week, "total_shares": total, "firms": ranking, "fetched": time.time()}, topic="finra_ats")
        for sym in self.watchlist:
            await self.fetch_symbol_ats(sym, week)
        return f"周 {week}，{len(ranking)} 家 ATS"

    async def fetch_symbol_ats(self, symbol: str, week: str | None = None) -> dict[str, Any]:
        week = week or await self.latest_week()
        if not week:
            raise RuntimeError("未获取到 ATS 周报日期")
        rows = await self._post({
            "limit": 500,
            "compareFilters": _filters(summaryTypeCode="ATS_W_SMBL_FIRM", issueSymbolIdentifier=symbol, weekStartDate=week),
        })
        recs = [{
            "mpid": (r.get("MPID") or "?")[:16],
            "name": r.get("marketParticipantName") or "",
            "tier": r.get("tierIdentifier") or "",
            "trades": int(float(r.get("totalWeeklyTradeCount") or 0)),
            "shares": float(r.get("totalWeeklyShareQuantity") or 0),
        } for r in rows]
        await store.executemany(
            "INSERT OR REPLACE INTO finra_ats_weekly VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(week, symbol, x["mpid"], x["name"], x["tier"], x["trades"], x["shares"]) for x in recs],
        )
        total = sum(x["shares"] for x in recs) or 1
        out = {
            "symbol": symbol,
            "week": week,
            "fetched": time.time(),
            "total_shares": total if recs else 0,
            "firms": sorted(
                ({**x, "share_pct": x["shares"] / total, "avg_size": x["shares"] / x["trades"] if x["trades"] else 0} for x in recs),
                key=lambda x: x["shares"], reverse=True),
        }
        cache.put(f"finra:ats:sym:{symbol}", out, ttl=6 * 3600)
        return out
