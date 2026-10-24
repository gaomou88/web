"""节假日与休市日。

1) 美股（NYSE/Nasdaq）休市日和 13:00 提前收盘：按交易所公布的规则计算，不依赖网络，永远可用；
   后台可补充临时休市日（例如国丧日）。
2) CME 股指期货：美股假日时的提前收盘 / 休市（按 CME 惯例推算）。
3) 中国外汇交易中心（CFETS）：中国法定节假日休市，调休的周末上班——数据从 holiday-cn（国务院通知整理）下载。
4) 各国公众假日：从 Nager.Date 公开接口下载（免费、免 Key），显示在经济日历里；欧元区按 TARGET2 规则计算。

所有结果保存到数据库，查询走内存，供“交易日”判断随时调用。
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from . import cache, settings, store

log = logging.getLogger("holidays")
ET = ZoneInfo("America/New_York")
NAGER_URL = "https://date.nager.at/api/v3/PublicHolidays/{year}/{cc}"
CN_URLS = ["https://cdn.jsdelivr.net/gh/NateScarlet/holiday-cn@master/{year}.json",
           "https://raw.githubusercontent.com/NateScarlet/holiday-cn/master/{year}.json"]
# 经济日历覆盖的国家/地区（与日历的地区代码一致）
COUNTRIES = ["US", "CN", "JP", "GB", "DE", "FR", "IT", "ES", "CA", "AU", "NZ", "CH"]

# 常见假日的中文名
ZH = {
    "New Year's Day": "元旦", "Martin Luther King, Jr. Day": "马丁·路德·金纪念日", "Washington's Birthday": "总统日",
    "Presidents Day": "总统日", "Good Friday": "耶稣受难日", "Easter Monday": "复活节星期一", "Memorial Day": "阵亡将士纪念日",
    "Juneteenth": "六月节", "Juneteenth National Independence Day": "六月节", "Independence Day": "独立日", "Labor Day": "劳动节",
    "Labour Day": "劳动节", "Columbus Day": "哥伦布日", "Veterans Day": "退伍军人节", "Thanksgiving Day": "感恩节",
    "Christmas Day": "圣诞节", "St. Stephen's Day": "节礼日", "Boxing Day": "节礼日", "Early May Bank Holiday": "五月初银行假日",
    "Spring Bank Holiday": "春季银行假日", "Summer Bank Holiday": "夏季银行假日", "Ascension Day": "耶稣升天节",
    "Whit Monday": "圣灵降临节星期一", "German Unity Day": "德国统一日", "Bastille Day": "法国国庆日", "Assumption Day": "圣母升天节",
    "All Saints' Day": "诸圣节", "Armistice Day": "停战纪念日", "Victory in Europe Day": "欧洲胜利日", "Canada Day": "加拿大国庆日",
    "Victoria Day": "维多利亚日", "Civic Holiday": "公民假日", "Thanksgiving": "感恩节", "Remembrance Day": "国殇纪念日",
    "Australia Day": "澳大利亚国庆日", "Anzac Day": "澳新军团日", "King's Birthday": "国王诞辰", "Waitangi Day": "怀唐伊日",
    "Coming of Age Day": "成人节", "Foundation Day": "建国纪念日", "Emperor's Birthday": "天皇诞辰", "Vernal Equinox Day": "春分日",
    "Shōwa Day": "昭和日", "Showa Day": "昭和日", "Constitution Memorial Day": "宪法纪念日", "Greenery Day": "绿之日",
    "Children's Day": "儿童节", "Marine Day": "海之日", "Mountain Day": "山之日", "Respect for the Aged Day": "敬老日",
    "Autumnal Equinox Day": "秋分日", "Sports Day": "体育节", "Culture Day": "文化节", "Labour Thanksgiving Day": "勤劳感谢日",
    "Swiss National Day": "瑞士国庆日", "Epiphany": "主显节", "Liberation Day": "解放日", "Republic Day": "共和国日",
    "Immaculate Conception": "圣母无染原罪节", "National Day": "国庆日", "Corpus Christi": "基督圣体节",
}


# ---------------- 规则计算 ----------------
def easter(y: int) -> date:
    """复活节（公历，Anonymous Gregorian 算法）。"""
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    day = (h + l_ - 7 * m + 114) % 31 + 1
    return date(y, month, day)


def _nth_weekday(y: int, m: int, weekday: int, n: int) -> date:
    d = date(y, m, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _last_weekday(y: int, m: int, weekday: int) -> date:
    d = date(y, m + 1, 1) - timedelta(days=1) if m < 12 else date(y, 12, 31)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def _observed(d: date) -> date | None:
    """周六的节日提前到周五、周日的顺延到周一（NYSE 规则）。"""
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def nyse_schedule(y: int) -> tuple[dict[date, str], dict[date, str]]:
    """返回 ({休市日: 名称}, {13:00 提前收盘日: 原因})。"""
    closed: dict[date, str] = {}
    nyd = date(y, 1, 1)
    if nyd.weekday() == 6:
        closed[date(y, 1, 2)] = "New Year's Day"
    elif nyd.weekday() != 5:  # 元旦逢周六时不提前到上一年 12 月 31 日休市
        closed[nyd] = "New Year's Day"
    closed[_nth_weekday(y, 1, 0, 3)] = "Martin Luther King, Jr. Day"
    closed[_nth_weekday(y, 2, 0, 3)] = "Washington's Birthday"
    closed[easter(y) - timedelta(days=2)] = "Good Friday"
    closed[_last_weekday(y, 5, 0)] = "Memorial Day"
    if y >= 2022:
        closed[_observed(date(y, 6, 19))] = "Juneteenth"
    closed[_observed(date(y, 7, 4))] = "Independence Day"
    closed[_nth_weekday(y, 9, 0, 1)] = "Labor Day"
    thanks = _nth_weekday(y, 11, 3, 4)
    closed[thanks] = "Thanksgiving Day"
    closed[_observed(date(y, 12, 25))] = "Christmas Day"

    early: dict[date, str] = {}
    jul3 = date(y, 7, 3)
    if jul3.weekday() < 5 and jul3 not in closed and date(y, 7, 4).weekday() != 0:
        early[jul3] = "独立日前一天"
    early[thanks + timedelta(days=1)] = "感恩节次日"
    dec24 = date(y, 12, 24)
    if dec24.weekday() < 5 and dec24 not in closed:
        early[dec24] = "平安夜"
    return closed, early


def target_holidays(y: int) -> dict[date, str]:
    """欧元区 TARGET2 系统关闭日（欧洲央行公布的固定规则）。"""
    e = easter(y)
    return {date(y, 1, 1): "New Year's Day", e - timedelta(days=2): "Good Friday", e + timedelta(days=1): "Easter Monday",
            date(y, 5, 1): "Labour Day", date(y, 12, 25): "Christmas Day", date(y, 12, 26): "St. Stephen's Day"}


# ---------------- 内存索引 ----------------
_nyse_closed: dict[date, str] = {}
_nyse_early: dict[date, str] = {}
_cfets_closed: dict[date, str] = {}
_cn_workdays: set[date] = set()
_extra_closed: dict[date, str] = {}


def _ensure_rules(years: range | None = None) -> None:
    for y in years or range(date.today().year - 1, date.today().year + 3):
        if any(d.year == y for d in _nyse_closed):
            continue
        c, e = nyse_schedule(y)
        _nyse_closed.update(c)
        _nyse_early.update(e)


def _load_extra() -> None:
    _extra_closed.clear()
    for line in str(settings.get("sources.holidays.extra_us_closed") or "").replace("，", ",").replace("\n", ",").split(","):
        part = line.strip()
        if not part:
            continue
        d, _, name = part.partition(":")
        try:
            _extra_closed[date.fromisoformat(d.strip())] = name.strip() or "临时休市"
        except ValueError:
            continue


def us_market_closed(d: date) -> str | None:
    """美股当日休市的原因；交易日返回 None。"""
    _ensure_rules(range(d.year, d.year + 1))
    if d.weekday() >= 5:
        return "周末"
    return _extra_closed.get(d) or _nyse_closed.get(d)


def us_early_close(d: date) -> str | None:
    _ensure_rules(range(d.year, d.year + 1))
    return None if us_market_closed(d) else _nyse_early.get(d)


def us_trading_day(d: date) -> bool:
    return us_market_closed(d) is None


def prev_us_trading_day(d: date) -> date:
    d -= timedelta(days=1)
    while not us_trading_day(d):
        d -= timedelta(days=1)
    return d


def us_close_hour(d: date) -> int:
    """当日常规收盘时间（美东小时）：正常 16，提前收盘 13。"""
    return 13 if us_early_close(d) else 16


def cfets_open(d: date) -> bool:
    """外汇交易中心当日是否开市：中国法定假日休市；调休的周末上班。"""
    if d in _cn_workdays:
        return True
    if d.weekday() >= 5:
        return False
    return d not in _cfets_closed


def cme_note(d: date) -> str | None:
    """CME 股指期货在美股假日的安排（按 CME 惯例推算）。"""
    name = us_market_closed(d)
    if name and name != "周末":
        if name in ("Good Friday", "Christmas Day", "New Year's Day"):
            return "CME 股指期货休市"
        return "CME 股指期货美东 13:00 提前收盘"
    if us_early_close(d):
        return "CME 股指期货美东 13:15 提前收盘"
    return None


def today_status(now: datetime | None = None) -> dict[str, Any]:
    t = (now or datetime.now(ET)).astimezone(ET)
    d = t.date()
    closed = us_market_closed(d)
    return {
        "date": d.isoformat(), "us_closed": closed if closed != "周末" else None, "weekend": d.weekday() >= 5,
        "us_closed_zh": ZH.get(closed or "", closed) if closed and closed != "周末" else None,
        "us_early": us_early_close(d), "cme": cme_note(d), "cfets_open": cfets_open(d),
        "next_trading_day": (d if us_trading_day(d) else _next_trading(d)).isoformat(),
    }


def _next_trading(d: date) -> date:
    d += timedelta(days=1)
    while not us_trading_day(d):
        d += timedelta(days=1)
    return d


# ---------------- 下载与入库 ----------------
async def load_from_db() -> int:
    _ensure_rules()
    _load_extra()
    rows = await store.query("SELECT date, region, name, kind FROM holidays WHERE region = 'CFETS'")
    _cfets_closed.clear()
    _cn_workdays.clear()
    for r in rows:
        d = date.fromisoformat(r["date"])
        if r["kind"] == "workday":
            _cn_workdays.add(d)
        else:
            _cfets_closed[d] = r["name"]
    return len(rows)


def _market_rows(y: int) -> list[tuple]:
    closed, early = nyse_schedule(y)
    rows = [(d.isoformat(), "NYSE", n, "closed", f"美股休市（{ZH.get(n, n)}）") for d, n in closed.items()]
    rows += [(d.isoformat(), "NYSE", n, "early", f"美股 13:00 提前收盘（{n}）") for d, n in early.items()]
    for d, n in closed.items():
        rows.append((d.isoformat(), "CME", n, "early" if n not in ("Good Friday", "Christmas Day", "New Year's Day") else "closed", cme_note(d) or ""))
    rows += [(d.isoformat(), "EU", n, "public", ZH.get(n, n)) for d, n in target_holidays(y).items()]
    return rows


class HolidayCollector:
    def __init__(self, http: Any) -> None:
        self.http = http

    async def refresh(self) -> str:
        last = await store.kv_get("holidays:updated")
        if last and time.time() - last[1] < 7 * 86400 and await store.query_one("SELECT 1 FROM holidays LIMIT 1"):
            await load_from_db()
            await self.publish()
            return f"已是最新（{time.strftime('%Y-%m-%d', time.localtime(last[1]))} 更新）"
        y0 = date.today().year
        rows: list[tuple] = []
        for y in (y0 - 1, y0, y0 + 1):
            rows += _market_rows(y)
        ok, fail = 0, []
        # 各国公众假日（Nager.Date）
        for cc in COUNTRIES:
            for y in (y0, y0 + 1):
                try:
                    r = await self.http.get(NAGER_URL.format(year=y, cc=cc), min_interval=0.5, timeout=20, headers={"Accept": "application/json"})
                    for it in r.json() or []:
                        if it.get("global") is False:
                            continue  # 只取全国性假日
                        name = it.get("name") or it.get("localName") or ""
                        rows.append((it["date"], cc, name, "public", ZH.get(name, it.get("localName") or name)))
                    ok += 1
                except Exception as e:  # noqa: BLE001
                    fail.append(f"{cc}{y}: {type(e).__name__}")
        # 中国法定假日与调休（外汇交易中心休市）
        cn_ok = False
        for y in (y0, y0 + 1):
            for url in CN_URLS:
                try:
                    r = await self.http.get(url.format(year=y), min_interval=0.5, timeout=20)
                    for it in (r.json() or {}).get("days") or []:
                        kind = "closed" if it.get("isOffDay") else "workday"
                        rows.append((it["date"], "CFETS", it.get("name") or "", kind,
                                     f"外汇交易中心休市（{it.get('name')}）" if kind == "closed" else f"调休上班（{it.get('name')}）"))
                    cn_ok = True
                    break
                except Exception as e:  # noqa: BLE001
                    fail.append(f"holiday-cn {y}: {type(e).__name__}")
        if not cn_ok:  # 退而使用 Nager 的中国假日作为外汇交易中心休市日（没有调休信息）
            rows += [(r[0], "CFETS", r[2], "closed", f"外汇交易中心休市（{r[4]}）") for r in rows if r[1] == "CN"]

        def replace(c):
            c.execute("DELETE FROM holidays")
            c.executemany("INSERT OR REPLACE INTO holidays (date, region, name, kind, name_zh) VALUES (?, ?, ?, ?, ?)", rows)
        await store.run(replace)
        await store.kv_set("holidays:updated", "ok")
        await load_from_db()
        await self.publish()
        msg = f"{len(rows)} 条（{ok}/{len(COUNTRIES) * 2} 个国家年份下载成功{'，中国调休已更新' if cn_ok else ''}）"
        if fail:
            log.warning("部分假日数据下载失败：%s", "；".join(fail[:10]))
            msg += f"；失败 {len(fail)} 项，美股/期货/欧元区按规则计算不受影响"
        return msg

    async def publish(self) -> None:
        today = date.today()
        rows = await store.query("SELECT date, region, name, kind, name_zh FROM holidays WHERE date >= ? AND date <= ? ORDER BY date",
                                 ((today - timedelta(days=31)).isoformat(), (today + timedelta(days=120)).isoformat()))
        payload = {"items": rows, "today": today_status()}
        cache.put("holidays:window", payload, topic="holidays", push=payload)


async def window(start: date, end: date) -> list[dict[str, Any]]:
    return await store.query("SELECT date, region, name, kind, name_zh FROM holidays WHERE date >= ? AND date <= ? ORDER BY date",
                             (start.isoformat(), end.isoformat()))


def dumps_today() -> str:
    return json.dumps(today_status(), ensure_ascii=False)
