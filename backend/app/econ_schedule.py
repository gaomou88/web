"""内置的官方经济数据 / 央行决议日程（2026-10-23 按各机构官网整理）。

用途：主要经济体的重要发布时间是固定的，提前存好并锁定，日历只需要抓取预测值、前值和公布值，
不会因为抓取时有时无而让“下一个重要数据”跳来跳去。抓取源报出的时间与这里不同，只记为“待确认”，
由管理员在后台“日历日程”里决定是否采用。

标题与 Forex Factory 一致，抓到的数据才能对上。时间按当地时区写，自动换算夏令时。
只收录官网已公布的日期；之后的日期由抓取补充（同样锁定），管理员也可以在后台批量导入。

来源：
- FOMC：federalreserve.gov/monetarypolicy/fomccalendars.htm（2027 年为暂定）
- BLS CPI / 非农 / PPI：bls.gov/schedule/2026、bls.gov/schedule/2027
- BEA GDP：bea.gov 发布日程（2026 年三季度 GDP 初值 10 月 29 日）
- ECB：ecb.europa.eu/press/calendars/mgcgc
- 英国央行：bankofengland.co.uk “MPC dates for 2026 / 2027”；英国 CPI：ONS 发布日程
- 日本央行：boj.or.jp 2027 年会议日程（mref260731a）
- 加拿大央行：bankofcanada.ca 2027 年日程（2026-07 发布）
- 澳洲联储：rba.gov.au “Coming up”
- 新西兰联储：rbnz.govt.nz 2026 年 8 月至 2027 年 2 月日程
- 瑞士央行：snb.ch 日程
- 中国国家统计局：stats.gov.cn 2026 年主要统计信息发布日程表；LPR：每月 20 日（节假日顺延）9:15
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

VERSION = "2026-10-23"

# (组名, 货币, 时区, [日期], [(当地时间, 标题, 重要性)])
GROUPS: list[tuple[str, str, str, list[str], list[tuple[str, str, int]]]] = [
    ("FOMC 利率决议", "USD", "America/New_York",
     ["2026-10-28", "2027-01-27", "2027-04-28", "2027-07-28", "2027-10-27"],
     [("14:00", "Federal Funds Rate", 3), ("14:00", "FOMC Statement", 3), ("14:30", "FOMC Press Conference", 3)]),
    ("FOMC 利率决议（含经济预测）", "USD", "America/New_York",
     ["2026-12-09", "2027-03-17", "2027-06-09", "2027-09-15", "2027-12-08"],
     [("14:00", "Federal Funds Rate", 3), ("14:00", "FOMC Statement", 3), ("14:00", "FOMC Economic Projections", 3),
      ("14:30", "FOMC Press Conference", 3)]),
    ("美国非农就业", "USD", "America/New_York",
     ["2026-11-06", "2026-12-04", "2027-01-08", "2027-02-05", "2027-03-05", "2027-04-02", "2027-05-07", "2027-06-04",
      "2027-07-02", "2027-08-06", "2027-09-03", "2027-10-08", "2027-11-05", "2027-12-03"],
     [("08:30", "Non-Farm Employment Change", 3), ("08:30", "Unemployment Rate", 3), ("08:30", "Average Hourly Earnings m/m", 3)]),
    ("美国 CPI", "USD", "America/New_York",
     ["2026-11-10", "2026-12-10", "2027-01-13", "2027-02-11", "2027-03-10", "2027-04-13", "2027-05-12", "2027-06-10",
      "2027-07-14", "2027-08-11", "2027-09-14", "2027-10-14", "2027-11-10", "2027-12-10"],
     [("08:30", "CPI m/m", 3), ("08:30", "CPI y/y", 3), ("08:30", "Core CPI m/m", 3)]),
    ("美国 PPI", "USD", "America/New_York",
     ["2026-11-13", "2026-12-15", "2027-01-14", "2027-02-12", "2027-03-12", "2027-04-14", "2027-05-13", "2027-06-11",
      "2027-07-15", "2027-08-10", "2027-09-10", "2027-10-15", "2027-11-12", "2027-12-15"],
     [("08:30", "PPI m/m", 2), ("08:30", "Core PPI m/m", 2)]),
    ("美国 GDP 初值", "USD", "America/New_York", ["2026-10-29"],
     [("08:30", "Advance GDP q/q", 3), ("08:30", "Advance GDP Price Index q/q", 2)]),
    ("欧洲央行利率决议", "EUR", "Europe/Berlin",
     ["2026-10-29", "2026-12-17", "2027-02-04", "2027-03-18", "2027-04-29", "2027-06-10", "2027-07-22", "2027-09-09",
      "2027-10-28", "2027-12-16"],
     [("14:15", "Main Refinancing Rate", 3), ("14:15", "Monetary Policy Statement", 3), ("14:45", "ECB Press Conference", 3)]),
    ("英国央行利率决议", "GBP", "Europe/London",
     ["2026-11-05", "2026-12-17", "2027-02-04", "2027-03-18", "2027-04-29", "2027-06-17", "2027-07-29", "2027-09-16",
      "2027-11-04", "2027-12-16"],
     [("12:00", "Official Bank Rate", 3), ("12:00", "MPC Official Bank Rate Votes", 3), ("12:00", "Monetary Policy Summary", 3)]),
    ("英国 CPI", "GBP", "Europe/London", ["2026-11-18", "2026-12-16", "2027-01-20"],
     [("07:00", "CPI y/y", 3), ("07:00", "Core CPI y/y", 2)]),
    # 日本央行没有固定公布时间（通常北京时间 11:00 前后），先按 12:00 东京时间，抓到准确时间后由管理员确认
    ("日本央行利率决议", "JPY", "Asia/Tokyo",
     ["2026-10-30", "2026-12-18", "2027-01-22", "2027-03-18", "2027-04-28", "2027-06-11", "2027-07-22", "2027-09-22",
      "2027-10-29", "2027-12-17"],
     [("12:00", "BOJ Policy Rate", 3), ("12:00", "Monetary Policy Statement", 3), ("15:30", "BOJ Press Conference", 3)]),
    ("加拿大央行利率决议", "CAD", "America/Toronto",
     ["2026-10-28", "2026-12-09", "2027-01-27", "2027-03-03", "2027-04-28", "2027-06-02", "2027-07-21", "2027-09-08",
      "2027-10-27", "2027-12-08"],
     [("09:45", "Overnight Rate", 3), ("09:45", "BOC Rate Statement", 3), ("10:30", "BOC Press Conference", 3)]),
    ("澳洲联储利率决议", "AUD", "Australia/Sydney",
     ["2026-11-03", "2026-12-08", "2027-02-09", "2027-03-23", "2027-05-04", "2027-06-22", "2027-08-10", "2027-09-28",
      "2027-11-02", "2027-12-14"],
     [("14:30", "Cash Rate", 3), ("14:30", "RBA Rate Statement", 3), ("15:30", "RBA Press Conference", 3)]),
    ("新西兰联储利率决议", "NZD", "Pacific/Auckland", ["2026-10-28", "2026-12-09", "2027-02-17"],
     [("14:00", "Official Cash Rate", 3), ("14:00", "RBNZ Rate Statement", 3), ("15:00", "RBNZ Press Conference", 3)]),
    ("瑞士央行利率决议", "CHF", "Europe/Zurich", ["2026-12-10", "2027-03-18"],
     [("09:30", "SNB Policy Rate", 3), ("09:30", "SNB Monetary Policy Assessment", 3), ("10:00", "SNB Press Conference", 3)]),
    ("中国 CPI / PPI", "CNY", "Asia/Shanghai", ["2026-11-09", "2026-12-09"],
     [("09:30", "CPI y/y", 2), ("09:30", "PPI y/y", 2)]),
    ("中国 PMI", "CNY", "Asia/Shanghai", ["2026-10-31", "2026-11-30", "2026-12-31"],
     [("09:30", "Manufacturing PMI", 2), ("09:30", "Non-Manufacturing PMI", 2)]),
    ("中国工业 / 社零", "CNY", "Asia/Shanghai", ["2026-11-16", "2026-12-15"],
     [("10:00", "Industrial Production y/y", 2), ("10:00", "Retail Sales y/y", 2)]),
    ("中国 LPR", "CNY", "Asia/Shanghai", ["2026-11-20", "2026-12-21"],
     [("09:15", "1-y Loan Prime Rate", 2), ("09:15", "5-y Loan Prime Rate", 2)]),
]


def official_id(currency: str, day: str, title: str) -> str:
    return "off:" + hashlib.sha1(f"{currency}|{day}|{title}".encode()).hexdigest()[:24]


def to_ts(day: str, hm: str, tz: str) -> int:
    local = datetime.fromisoformat(f"{day}T{hm}:00").replace(tzinfo=ZoneInfo(tz))
    return int(local.astimezone(timezone.utc).timestamp())


def official_events() -> list[dict]:
    out = []
    for group, ccy, tz, days, items in GROUPS:
        for day in days:
            for hm, title, impact in items:
                out.append({"id": official_id(ccy, day, title), "ts": to_ts(day, hm, tz), "currency": ccy, "title": title,
                            "impact": impact, "group": group})
    return out
