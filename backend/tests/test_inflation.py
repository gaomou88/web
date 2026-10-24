"""通胀模型：各级数据源的优先级、指数串联、外推、插值。运行：pytest backend/tests"""
import asyncio
from datetime import date, datetime, timezone

import pytest

from app import inflation as INF
from app import pnl, store


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(scope="module", autouse=True)
def db():
    asyncio.set_event_loop(asyncio.new_event_loop())
    run(store.init())
    run(store.execute("DELETE FROM cpi_index"))
    run(store.execute("DELETE FROM econ_events"))
    INF.invalidate()


def ts(d):
    return int(datetime.fromisoformat(d).replace(tzinfo=timezone.utc).timestamp())


def test_ref_month():
    assert INF.ref_month(ts("2026-11-10T13:30:00"), "CPI y/y") == "2026-10"
    assert INF.ref_month(ts("2026-10-31T09:00:00"), "CPI Flash Estimate y/y") == "2026-10"
    assert INF.ref_month(ts("2026-11-04T10:00:00"), "CPI Flash Estimate y/y") == "2026-10"


def test_parsers():
    assert INF.parse_fred("observation_date,CPIAUCNS\n2026-08-01,325.1\n2026-09-01,.\n2026-09-01,326.0\n") == [("2026-08", 325.1), ("2026-09", 326.0)]
    js = [{"page": 1}, [{"date": "2025", "value": 2.1}, {"date": "2024", "value": None}, {"date": "2023", "value": 3.4}]]
    assert INF.parse_wb(js) == [("2025", 2.1), ("2023", 3.4)]
    assert INF.parse_wb({"message": "x"}) == []


def test_build_priorities():
    rows = [("USD", f"2026-{m:02d}", 300 + m, None, "fred") for m in range(1, 9)]
    rows += [("GBP", "2025-01", None, 3.0, "worldbank"), ("GBP", "2026-01", None, 2.4, "worldbank")]
    rows += [("CNY", "2026-01", None, 0.5, "worldbank"), ("JPY", "2026-03", None, 12.0, "admin")]
    run(store.executemany("INSERT INTO cpi_index (region, month, idx, yoy, src) VALUES (?,?,?,?,?)", rows))
    ev = [("tinf1", ts("2026-07-09T01:30:00"), "CNY", "CN", "CPI y/y", 2, "1.2%"), ("tinf2", ts("2026-08-09T01:30:00"), "CNY", "CN", "CPI y/y", 2, "-0.6%"),
          ("tinf3", ts("2026-10-14T12:30:00"), "USD", "US", "CPI y/y", 3, "3.0%")]
    run(store.executemany("INSERT INTO econ_events (id, ts, currency, region, title, impact, actual) VALUES (?,?,?,?,?,?,?)", ev))
    INF.invalidate()
    today = date(2026, 10, 20)
    us = run(INF.build("USD", "2026-01", today))
    src = us["sources"]
    assert src["2026-02"] == "fred" and src["2026-09"] == "calendar" and src["2026-10"] == "extrapolated"
    tab = dict(us["table"])
    assert abs(tab["2026-08"] / tab["2026-07"] - 308 / 307) < 1e-7                # 官方指数：按真实比值
    assert abs(tab["2026-09"] / tab["2026-08"] - 1.03 ** (1 / 12)) < 1e-6           # 日历同比 3.0% 摊到每月
    cn = run(INF.build("CNY", "2026-01", today))
    assert cn["sources"]["2026-06"] == "calendar" and cn["sources"]["2026-07"] == "calendar" and cn["sources"]["2026-03"] == "worldbank"
    t = dict(cn["table"])
    assert t["2026-07"] < t["2026-06"]                                               # 同比为负：指数下降
    gb = run(INF.build("GBP", "2025-11", today))
    assert gb["sources"]["2025-12"] == "worldbank" and gb["sources"]["2026-05"] == "worldbank" and not gb["no_data"]
    jp = run(INF.build("JPY", "2026-01", today))
    assert jp["sources"]["2026-03"] == "admin" and jp["sources"]["2026-01"] == "none"
    nz = run(INF.build("NZD", "2026-01", today))
    assert nz["no_data"] and all(v == 100 for _, v in nz["table"])


def test_real_pnl_example():
    # 7 月 15 日花 7000 元买入，物价到 10 月 15 日上涨 3%：市值仍是 7000 元时，扣除通胀后亏损 210 元
    table = [["2026-07", 100.0], ["2026-08", 101.0], ["2026-09", 102.0], ["2026-10", 103.0]]
    trades = [{"id": 1, "side": "buy", "trade_date": "2026-07-15", "shares": 10, "price": 100, "fx": 7.0, "fee": 0}]
    p = pnl.compute_position(trades, {"price": 100, "prev_close": 100}, 7.0, 7.0, "2026-10-15",
                             deflate=lambda d: pnl.cpi_factor(table, d, "2026-10-15"))
    assert abs(p["costReal"] - 7210) < 1e-9 and abs(p["unreal"] + 210) < 1e-9 and p["costBase"] == 7000
    # 卖出：卖出所得也按卖出日折算到今天
    trades.append({"id": 2, "side": "sell", "trade_date": "2026-09-15", "shares": 10, "price": 100, "fx": 7.0, "fee": 0})
    p = pnl.compute_position(trades, {"price": 100, "prev_close": 100}, 7.0, 7.0, "2026-10-15",
                             deflate=lambda d: pnl.cpi_factor(table, d, "2026-10-15"))
    assert abs(p["realized"] - (7000 * 103 / 102 - 7210)) < 1e-9 and p["qty"] == 0
    assert pnl.cpi_factor(table, "2026-08-30", "2026-08-30") == 1 and pnl.cpi_factor(None, "2026-08-30", "2026-10-01") == 1
