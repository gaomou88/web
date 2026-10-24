"""经济日历。

日程库（防止“下一个重要数据”跳来跳去）：
- 主要经济体的央行决议和重要数据，官方日程内置在 econ_schedule.py，启动时写入并锁定；
- Forex Factory 抓到的其他事件也写入日程库（提前 3 个月按月抓取）；
- 之后的抓取只更新预测值 / 前值 / 公布值。抓到的时间和库里不同：
  锁定的事件（内置、后台录入或管理员锁定的）只记为“待确认”，由管理员在后台“日历日程”决定；
  未锁定的抓取事件连续两次看到同一个新时间、且离公布还有半小时以上才改；
- 同一事件按“货币 + 标题 + 前后 36 小时内”对应，不再因为时间或来源不同产生重复；
- 抓取源删掉的事件自动隐藏，后台删除的事件不会被抓取加回来。

日程 / 预测值 / 前值 / 重要性：Forex Factory 官方公开导出的 JSON（免费、免 Key）。
公布值：Forex Factory 日历页面内嵌的事件数据（请求前检查 robots.txt；
只在“有事件刚到点但还没有公布值”时才去拉，平时不打扰源站）。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from typing import Any

import logging

from .. import cache, settings, store
from ..http import HTTPStatusError, PoliteClient, RateLimited

log = logging.getLogger("calendar")
FEEDS = [
    "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "https://nfs.faireconomy.media/ff_calendar_nextweek.json",
]
FF_PAGE = "https://www.forexfactory.com/calendar?week=this"
FF_PAGE_NEXT = "https://www.forexfactory.com/calendar?week=next"
FF_PAGE_WEEK = "https://www.forexfactory.com/calendar?week={key}"
FF_PAGE_MONTH = "https://www.forexfactory.com/calendar?month={key}"
MONTHS_AHEAD = 3
MATCH_WINDOW = 36 * 3600   # 同一事件：同货币、同标题、时间相差 36 小时以内
# 同一事件在不同阶段 / 不同来源的标题
ALIASES = [{"advancegdpq/q", "prelimgdpq/q", "finalgdpq/q"}, {"monetarypolicystatement", "monetarypolicysummary"},
           {"bocratestatement", "bocmonetarypolicyreport"}]
BACKFILL_WEEKS = 26
BACKFILL_GAP = 60  # 两次历史回填之间至少间隔的秒数
_MON = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def week_key(d) -> str:
    """Forex Factory 的周参数，例如 oct11.2026（以周日为一周开始）。"""
    from datetime import timedelta
    sunday = d - timedelta(days=(d.weekday() + 1) % 7)
    return f"{_MON[sunday.month - 1]}{sunday.day}.{sunday.year}"

IMPACT = {"high": 3, "medium": 2, "low": 1, "holiday": 0, "non-economic": 1}

CURRENCY_REGION = {
    "USD": "US", "EUR": "EU", "CNY": "CN", "JPY": "JP", "GBP": "GB", "CAD": "CA",
    "AUD": "AU", "NZD": "NZ", "CHF": "CH", "ALL": "GL",
}
PREFIX_REGION = [("German ", "DE"), ("French ", "FR"), ("Italian ", "IT"), ("Spanish ", "ES")]

ORG_PAT = re.compile(
    r"\b(IMF|OPEC|G7|G20|ECB|FOMC|Fed(eral)?\b|BOJ|BOE|BOC|PBOC|RBA|RBNZ|SNB|World Bank|OECD|IEA|WTO|"
    r"Eurogroup|ECOFIN|Monetary Policy|Rate Statement|Cash Rate|Interest Rate|Jackson Hole)",
    re.I,
)

COLS = ["id", "ts", "currency", "region", "title", "impact", "forecast", "previous", "actual", "revision", "surprise", "is_org"]


def event_id(currency: str, ts: datetime, title: str) -> str:
    return hashlib.sha1(f"{currency}|{ts.isoformat()}|{title}".encode()).hexdigest()


def norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9%/]+", "", t.lower())


def title_key(t: str) -> str:
    n = norm_title(t)
    for g in ALIASES:
        if n in g:
            return min(g)
    return n


def month_key(d) -> str:
    return f"{_MON[d.month - 1]}.{d.year}"


def region_of(currency: str, title: str) -> str:
    for prefix, reg in PREFIX_REGION:
        if currency == "EUR" and title.startswith(prefix):
            return reg
    return CURRENCY_REGION.get(currency.upper(), currency.upper()[:2])


def parse_feed(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for it in items:
        try:
            ts = datetime.fromisoformat(it["date"]).astimezone(timezone.utc)
        except (KeyError, ValueError, TypeError):
            continue
        cur = (it.get("country") or "").upper()
        title = (it.get("title") or "").strip()
        if not title:
            continue
        out.append({
            "id": event_id(cur, ts, title),
            "ts": ts,
            "currency": cur,
            "region": region_of(cur, title),
            "title": title,
            "impact": IMPACT.get((it.get("impact") or "").lower(), 1),
            "forecast": (it.get("forecast") or "").strip(),
            "previous": (it.get("previous") or "").strip(),
            "is_org": bool(ORG_PAT.search(title)) or cur == "ALL",
        })
    return out


_STR = r'"((?:[^"\\]|\\.)*)"'


def _field(chunk: str, name: str) -> str | None:
    m = re.search(rf'"{name}":{_STR}', chunk)
    if m:
        return json.loads(f'"{m.group(1)}"')
    m = re.search(rf'"{name}":(-?\d+)', chunk)
    return m.group(1) if m else None


def parse_ff_page(html: str) -> list[dict[str, Any]]:
    """从日历页内嵌数据中提取事件（含公布值）。结构变化时尽量降级而不是崩溃。"""
    starts = [m.start() for m in re.finditer(r'\{"id":\d+,', html)]
    events = []
    for i, st in enumerate(starts):
        chunk = html[st: starts[i + 1] if i + 1 < len(starts) else st + 4000]
        dateline = _field(chunk, "dateline")
        currency = _field(chunk, "currency")
        name = _field(chunk, "name") or _field(chunk, "title")
        if not (dateline and currency and name):
            continue
        abw = _field(chunk, "actualBetterWorse")
        imp_name = (_field(chunk, "impactName") or "").lower()
        imp_cls = (_field(chunk, "impactClass") or "").lower()
        if not imp_name and imp_cls:
            imp_name = "high" if "red" in imp_cls else "medium" if "ora" in imp_cls else "low" if "yel" in imp_cls else "holiday" if "gra" in imp_cls else ""
        events.append({
            "impact": IMPACT.get(imp_name) if imp_name else None,
            "currency": currency.upper(),
            "ts": datetime.fromtimestamp(int(dateline), tz=timezone.utc),
            "title": name,
            "actual": (_field(chunk, "actual") or "").strip(),
            "forecast": (_field(chunk, "forecast") or "").strip(),
            "previous": (_field(chunk, "previous") or "").strip(),
            "revision": (_field(chunk, "revision") or "").strip(),
            "surprise": int(abw) if abw and abw.lstrip("-").isdigit() else 0,
        })
    return events


def serialize(row: dict[str, Any]) -> dict[str, Any]:
    return {**{k: row[k] for k in COLS}, "is_org": bool(row["is_org"])}


_seed_lock = asyncio.Lock()


def _ts(v: Any) -> int:
    return int(v.timestamp()) if isinstance(v, datetime) else int(v)


class CalendarCollector:
    def __init__(self, http: PoliteClient) -> None:
        self.http = http
        self.last_full_sync = 0.0
        self.near_release = False  # 是否处于数据公布前 1 分钟到公布后 3 分钟的窗口

    async def _feed(self, url: str, min_gap: int) -> list[dict[str, Any]] | None:
        """按 URL 记录上次成功抓取时间（存数据库，重启也不会重复请求）。未到时间返回 None。"""
        key = f"ff_feed:{url}"
        last = await store.kv_get(key)
        if last and time.time() - last[1] < min_gap:
            return None
        blocked = await store.kv_get("ff_feed:blocked_until")
        if blocked and float(blocked[0]) > time.time():
            raise RateLimited(float(blocked[0]) - time.time())
        try:
            r = await self.http.get(url, min_interval=20)
        except HTTPStatusError as e:
            if e.status_code == 429:
                wait = e.retry_after or 1800
                await store.kv_set("ff_feed:blocked_until", str(time.time() + wait))
                raise RateLimited(wait, f"Forex Factory 限流（HTTP 429），{max(1, round(wait / 60))} 分钟后自动重试；公布值不受影响") from e
            raise
        await store.kv_set(key, "ok")
        return parse_feed(r.json() or [])

    async def refresh_schedule(self) -> str:
        """日程源每小时最多请求一次；下周日程只在周四之后、每 6 小时请求一次（对方限流很严）。"""
        await self.seed_official()
        gap = max(int(settings.get("sources.calendar.interval") or 3600), 900)
        rows = await self._feed(FEEDS[0], gap - 30)
        if rows is None:
            return "本周日程仍在有效期内，无需重新请求"
        if datetime.now(timezone.utc).weekday() >= 3:
            try:
                rows += await self._feed(FEEDS[1], 6 * 3600) or []
            except (HTTPStatusError, RateLimited):
                pass  # 下周数据在周末前可能还没发布
        if not rows:
            return "源返回空数据"
        added, _, moved = await self.merge_events(rows, ghosts=True)
        await self.publish_window()
        return f"{len(rows)} 条事件，新增 {added} 条" + (f"，{moved} 条时间有变化待确认" if moved else "")

    async def seed_official(self, force: bool = False) -> str:
        """把内置的官方日程写入数据库（每个版本只写一次；后台删除 / 修改过的不会被覆盖）。"""
        async with _seed_lock:
            return await self._seed_official(force)

    async def _seed_official(self, force: bool) -> str:
        from ..econ_schedule import VERSION, official_events
        ver = await store.kv_get("cal_seed:version")
        if ver and ver[0] == VERSION and not force:
            return ""
        evs = official_events()
        have = {r["id"] for r in await store.query("SELECT id FROM econ_events WHERE id LIKE 'off:%'")}
        todo = [e for e in evs if e["id"] not in have]
        added = converted = 0
        if todo:
            lo, hi = min(e["ts"] for e in todo) - MATCH_WINDOW, max(e["ts"] for e in todo) + MATCH_WINDOW
            ff = await store.query("SELECT * FROM econ_events WHERE ts BETWEEN ? AND ? AND source = 'ff'", (lo, hi))
            used: set[str] = set()
            now = int(time.time())

            def write(c):
                nonlocal added, converted
                for e in todo:
                    cands = [r for r in ff if r["id"] not in used and r["currency"] == e["currency"]
                             and title_key(r["title"]) == title_key(e["title"]) and abs(r["ts"] - e["ts"]) <= MATCH_WINDOW]
                    old = min(cands, key=lambda r: abs(r["ts"] - e["ts"])) if cands else None
                    vals = {"forecast": "", "previous": "", "actual": "", "revision": "", "surprise": 0, "hidden": 0}
                    if old:  # 抓取来的同一事件：换成官方日程（保留已抓到的数值）
                        used.add(old["id"])
                        vals = {k: old[k] for k in vals}
                        vals["hidden"] = 1 if old["hidden"] == 1 else 0
                        c.execute("DELETE FROM econ_events WHERE id = ?", (old["id"],))
                        converted += 1
                    else:
                        added += 1
                    c.execute("""INSERT OR IGNORE INTO econ_events (id, ts, currency, region, title, impact, forecast, previous, actual, revision,
                                 surprise, is_org, source, locked, hidden, pending_ts, updated_at)
                                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'official', 1, ?, 0, ?)""",
                              (e["id"], e["ts"], e["currency"], region_of(e["currency"], e["title"]), e["title"], e["impact"],
                               vals["forecast"], vals["previous"], vals["actual"], vals["revision"], vals["surprise"],
                               int(bool(ORG_PAT.search(e["title"])) or e["currency"] == "ALL"), vals["hidden"], now))
            await store.run(write)
        await store.kv_set("cal_seed:version", VERSION)
        if added or converted:
            log.info("内置官方日程 %s：新增 %d 条，替换抓取的 %d 条", VERSION, added, converted)
        return f"官方日程新增 {added} 条，替换 {converted} 条"

    async def merge_events(self, items: list[dict[str, Any]], ghosts: bool = False) -> tuple[int, list[dict[str, Any]], int]:
        """把抓到的事件并入日程库。返回（新增条数, 公布值有更新的事件, 时间有变化的条数）。
        ghosts=True：这批数据覆盖了完整区间（整周），区间内没再出现的抓取事件自动隐藏（抓取源已删除或改期）。"""
        items = sorted((e for e in items if e.get("title")), key=lambda e: _ts(e["ts"]))
        if not items:
            return 0, [], 0
        lo, hi = _ts(items[0]["ts"]), _ts(items[-1]["ts"])
        rows = await store.query("SELECT * FROM econ_events WHERE ts BETWEEN ? AND ?", (lo - MATCH_WINDOW, hi + MATCH_WINDOW))
        index: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for r in rows:
            index.setdefault((r["currency"], title_key(r["title"])), []).append(r)
        now = int(time.time())
        used: set[str] = set()
        inserts, updates, pushed = [], [], []
        moved = 0
        for e in items:
            ets = _ts(e["ts"])
            cur = (e.get("currency") or "").upper()
            key = (cur, title_key(e["title"]))
            cands = [r for r in index.get(key, []) if r["id"] not in used and abs(r["ts"] - ets) <= MATCH_WINDOW]
            if not cands:
                if e.get("impact") is None:
                    continue
                row = {"id": event_id(cur, datetime.fromtimestamp(ets, timezone.utc), e["title"]), "ts": ets, "currency": cur,
                       "region": region_of(cur, e["title"]), "title": e["title"], "impact": e["impact"],
                       "forecast": e.get("forecast") or "", "previous": e.get("previous") or "", "actual": e.get("actual") or "",
                       "revision": e.get("revision") or "", "surprise": int(e.get("surprise") or 0),
                       "is_org": int(bool(ORG_PAT.search(e["title"])) or cur == "ALL"), "source": "ff", "locked": 0, "hidden": 0,
                       "pending_ts": 0, "updated_at": now}
                inserts.append(row)
                index.setdefault(key, []).append(row)
                used.add(row["id"])
                continue
            r = min(cands, key=lambda x: (abs(x["ts"] - ets), x["ts"]))
            used.add(r["id"])
            ch: dict[str, Any] = {"updated_at": now}
            for f in ("forecast", "previous"):
                v = (e.get(f) or "").strip()
                if v and v != r[f]:
                    ch[f] = v
            act = (e.get("actual") or "").strip()
            if act and (act != r["actual"] or (e.get("revision") or "") != r["revision"]):
                ch.update(actual=act, revision=e.get("revision") or "", surprise=int(e.get("surprise") or 0))
            if r["source"] == "ff" and e.get("impact") is not None and e["impact"] != r["impact"]:
                ch["impact"] = e["impact"]
            if r["source"] == "official" and r["title"] != e["title"]:
                ch["title"] = e["title"]  # 用抓取源的叫法（例如初值 / 修正值），以后的数据才能对上
            if abs(ets - r["ts"]) > 60:
                if not r["locked"] and r["pending_ts"] == ets and ets > now + 1800 and r["ts"] > now + 1800 and not r["actual"]:
                    ch.update(ts=ets, pending_ts=0)   # 未锁定的事件：连续两次看到同一个新时间才改期（离公布不到半小时不再改）
                elif r["pending_ts"] != ets:
                    ch["pending_ts"] = ets
                    moved += 1
            elif r["pending_ts"]:
                ch["pending_ts"] = 0
            if r["hidden"] == 2:
                ch["hidden"] = 0
            r.update(ch)
            updates.append((r["id"], ch))
            if "actual" in ch:
                pushed.append(serialize({k: r[k] for k in COLS}))
        if ghosts:
            for rs in index.values():
                for r in rs:
                    if (r["id"] not in used and r.get("source") == "ff" and not r.get("hidden") and not r.get("actual")
                            and lo <= r["ts"] <= hi and r["ts"] > now and r.get("updated_at", 0) < now - 6 * 3600):
                        updates.append((r["id"], {"hidden": 2}))

        def write(c):
            if inserts:
                cols = list(inserts[0])
                c.executemany(f"INSERT OR IGNORE INTO econ_events ({', '.join(cols)}) VALUES ({', '.join(':' + k for k in cols)})", inserts)
            for rid, ch in updates:
                c.execute(f"UPDATE econ_events SET {', '.join(f'{k} = ?' for k in ch)} WHERE id = ?", (*ch.values(), rid))
        await store.run(write)
        return len(inserts), pushed, moved

    async def pending_release(self) -> bool:
        """是否有事件已到点（或 2 分钟内到点）但还没有公布值。"""
        now = int(time.time())
        row = await store.query_one(
            "SELECT 1 FROM econ_events WHERE ts <= ? AND ts >= ? AND actual = '' AND impact > 0 AND forecast != '' AND hidden = 0 LIMIT 1",
            (now + 120, now - 45 * 60),
        )
        return row is not None

    async def refresh_actuals(self) -> str:
        # 数据发布前后每分钟检查；另外每 30 分钟完整同步一次（补齐启动前已公布的数据）
        now = int(time.time())
        near = await store.query_one(
            "SELECT 1 FROM econ_events WHERE ts >= ? AND ts <= ? AND actual = '' AND impact > 0 AND hidden = 0 LIMIT 1", (now - 180, now + 60))
        self.near_release = near is not None
        full_due = time.time() - self.last_full_sync > 1800
        pending = self.near_release or await self.pending_release()
        if not full_due and not pending:
            extra = []
            try:  # 空闲时补下周日程和历史数据
                for fn in (self.sync_next_week, self.sync_months, self.backfill_one):
                    if (msg := await fn()):
                        extra.append(msg)
            except Exception as e:  # noqa: BLE001
                log.info("日历补充抓取失败：%s", e)
            if extra:
                await self.publish_window()
            return "当前没有待公布事件" + (f"；{'；'.join(extra)}" if extra else "")
        page = await self._page(FF_PAGE)
        self.last_full_sync = time.time()
        if not page:
            raise RuntimeError("页面结构可能已变化，未提取到事件")
        added, updated, moved = await self.merge_events(page, ghosts=True)
        await self.publish_window(push=updated or None)
        return f"页面 {len(page)} 条，更新 {len(updated)} 条公布值" + (f"，补充日程 {added} 条" if added else "") + (f"，{moved} 条时间待确认" if moved else "")

    async def _page(self, url: str) -> list[dict[str, Any]]:
        r = await self.http.get(url, min_interval=3)
        return parse_ff_page(r.text)

    async def sync_next_week(self) -> str:
        """下周日程：每 6 小时从日历页补一次。"""
        last = await store.kv_get("ff_page:next")
        if last and time.time() - last[1] < 6 * 3600:
            return ""
        page = await self._page(FF_PAGE_NEXT)
        await store.kv_set("ff_page:next", "ok")
        n, _, _ = await self.merge_events(page, ghosts=True)
        return f"下周 {len(page)} 条（新增 {n}）"

    async def sync_months(self, force: bool = False) -> str:
        """未来 3 个月的日程：按月抓取并锁定（每个月每天最多抓一次，每次调用只抓一个月）。"""
        from datetime import date
        today = date.today()
        msgs = []
        for k in range(MONTHS_AHEAD + 1):
            y, m = today.year + (today.month - 1 + k) // 12, (today.month - 1 + k) % 12 + 1
            key = month_key(date(y, m, 1))
            last = await store.kv_get(f"ff_month:{key}")
            if last and not force and time.time() - last[1] < 86400:
                continue
            page = await self._page(FF_PAGE_MONTH.format(key=key))
            await store.kv_set(f"ff_month:{key}", str(len(page)))
            n, _, moved = await self.merge_events(page)
            msgs.append(f"{key} 日程 {len(page)} 条（新增 {n}" + (f"，{moved} 条时间待确认" if moved else "") + "）")
            if not force:
                break  # 平时每次只抓一个月，不给源站添压力
        return "；".join(msgs)

    async def backfill_one(self) -> str:
        """历史数据回填（用于详情页折线图）：空闲时每次补一周，最多回溯 26 周。"""
        last = await store.kv_get("ff_backfill:last")
        if last and time.time() - last[1] < BACKFILL_GAP:
            return ""
        from datetime import date, timedelta
        today = date.today()
        for w in range(1, BACKFILL_WEEKS + 1):
            key = week_key(today - timedelta(weeks=w))
            if await store.kv_get(f"ff_week:{key}"):
                continue
            await store.kv_set("ff_backfill:last", key)
            page = await self._page(FF_PAGE_WEEK.format(key=key))
            n, _, _ = await self.merge_events(page)
            await store.kv_set(f"ff_week:{key}", str(len(page)))
            return f"历史 {key}：{len(page)} 条（新增 {n}）"
        return ""

    async def startup(self) -> None:
        try:
            await self.seed_official()
        except Exception:  # noqa: BLE001
            log.exception("写入内置官方日程失败")
        await self.publish_window()

    async def publish_window(self, push: list[dict[str, Any]] | None = None) -> None:
        now = int(time.time())
        rows = await store.query(
            f"SELECT {', '.join(COLS)} FROM econ_events WHERE ts >= ? AND ts <= ? AND hidden = 0 ORDER BY ts",
            (now - 8 * 86400, now + 15 * 86400),
        )
        cache.put("cal:window", [serialize(r) for r in rows], topic="calendar", push=push)
        # 下一个重要事件：到点后还没公布值的继续保留 30 分钟（页面显示“等待公布”），不会先跳到下一个再跳回来
        nxt = await store.query(
            f"SELECT {', '.join(COLS)} FROM econ_events WHERE ts > ? AND impact = 3 AND hidden = 0 ORDER BY ts LIMIT 40", (now - 1800,))
        cache.put("cal:next", [serialize(r) for r in nxt])
