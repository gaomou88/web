"""日历日程库：内置官方日程、抓取合并、改期确认、幽灵事件。运行：pytest backend/tests"""
import asyncio
import time

import pytest

from app import store
from app.collectors.calendar import CalendarCollector
from app.econ_schedule import official_events, to_ts


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(scope="module")
def cal():
    asyncio.set_event_loop(asyncio.new_event_loop())
    run(store.init())
    run(store.execute("DELETE FROM econ_events"))
    run(store.execute("DELETE FROM kv"))
    return CalendarCollector(http=None)


def ev(title, ts, cur="USD", impact=3, **kw):
    return {"title": title, "ts": ts, "currency": cur, "impact": impact, **kw}


def rows(sql, args=()):
    return run(store.query(sql, args))


def test_official_times_and_dst():
    evs = {(e["currency"], e["title"], e["ts"]) for e in official_events()}
    # FOMC 2026-10-28 14:00 美东（夏令时 UTC-4）= 18:00 UTC；2026-12-09 14:00 美东（冬令时 UTC-5）= 19:00 UTC
    assert ("USD", "Federal Funds Rate", 1793210400) in evs and to_ts("2026-10-28", "14:00", "America/New_York") == 1793210400
    assert to_ts("2026-12-09", "14:00", "America/New_York") == 1796842800
    assert ("GBP", "Official Bank Rate", to_ts("2026-11-05", "12:00", "Europe/London")) in evs
    assert len({e["id"] for e in official_events()}) == len(official_events())


def test_seed_is_idempotent(cal):
    msg = run(cal.seed_official())
    n = rows("SELECT COUNT(*) AS n FROM econ_events WHERE source = 'official'")[0]["n"]
    assert n == len(official_events()) and "新增" in msg
    assert run(cal.seed_official()) == ""  # 同一版本只写一次
    run(cal.seed_official(force=True))
    assert rows("SELECT COUNT(*) AS n FROM econ_events")[0]["n"] == n


def test_crawl_only_updates_values_of_official(cal):
    t = to_ts("2026-11-10", "08:30", "America/New_York")
    added, pushed, moved = run(cal.merge_events([ev("CPI m/m", t, forecast="0.3%", previous="0.2%"),
                                                 ev("CPI m/m", t + 3600, cur="CAD", impact=2)]))
    r = rows("SELECT * FROM econ_events WHERE currency='USD' AND title='CPI m/m' AND ts BETWEEN ? AND ?", (t - 86400, t + 86400))
    assert len(r) == 1 and r[0]["source"] == "official" and r[0]["forecast"] == "0.3%" and added == 1 and moved == 0
    # 抓到的时间不同：官方日程不改，只记待确认
    added, pushed, moved = run(cal.merge_events([ev("CPI m/m", t + 3600, forecast="0.4%")]))
    r = rows("SELECT * FROM econ_events WHERE currency='USD' AND title='CPI m/m' AND ts BETWEEN ? AND ?", (t - 86400, t + 86400))
    assert len(r) == 1 and r[0]["ts"] == t and r[0]["pending_ts"] == t + 3600 and r[0]["forecast"] == "0.4%" and moved == 1 and added == 0
    # 公布值
    _, pushed, _ = run(cal.merge_events([ev("CPI m/m", t, actual="0.5%", surprise=1)]))
    assert pushed and pushed[0]["actual"] == "0.5%" and set(pushed[0]) >= {"id", "ts", "actual", "is_org"}
    r = rows("SELECT * FROM econ_events WHERE id = ?", (pushed[0]["id"],))[0]
    assert r["pending_ts"] == 0  # 时间又对上了：清除待确认


def test_unlocked_ff_event_moves_after_two_sightings(cal):
    t = int(time.time()) + 5 * 86400
    run(cal.merge_events([ev("Some Speech", t, impact=2)]))
    run(cal.merge_events([ev("Some Speech", t + 7200, impact=2)]))
    r = rows("SELECT * FROM econ_events WHERE title='Some Speech'")
    assert len(r) == 1 and r[0]["ts"] == t and r[0]["pending_ts"] == t + 7200   # 第一次：只记下
    run(cal.merge_events([ev("Some Speech", t + 7200, impact=2)]))
    r = rows("SELECT * FROM econ_events WHERE title='Some Speech'")
    assert len(r) == 1 and r[0]["ts"] == t + 7200 and r[0]["pending_ts"] == 0  # 第二次：改期
    # 来源之间时间不一致（来回跳）：不会改
    run(cal.merge_events([ev("Some Speech", t + 9000, impact=2)]))
    run(cal.merge_events([ev("Some Speech", t + 7200, impact=2)]))
    run(cal.merge_events([ev("Some Speech", t + 9000, impact=2)]))
    assert rows("SELECT ts FROM econ_events WHERE title='Some Speech'")[0]["ts"] == t + 7200
    # 锁定后不再自动改
    run(store.execute("UPDATE econ_events SET locked = 1 WHERE title='Some Speech'"))
    run(cal.merge_events([ev("Some Speech", t + 3600, impact=2)]))
    run(cal.merge_events([ev("Some Speech", t + 3600, impact=2)]))
    r = rows("SELECT * FROM econ_events WHERE title='Some Speech'")[0]
    assert r["ts"] == t + 7200 and r["pending_ts"] == t + 3600


def test_same_title_twice_in_a_day_stays_two_events(cal):
    t = int(time.time()) + 10 * 86400
    run(cal.merge_events([ev("Fed Chair Speaks", t), ev("Fed Chair Speaks", t + 20 * 3600)]))
    run(cal.merge_events([ev("Fed Chair Speaks", t + 20 * 3600), ev("Fed Chair Speaks", t)]))
    assert sorted(r["ts"] for r in rows("SELECT ts FROM econ_events WHERE title='Fed Chair Speaks'")) == [t, t + 20 * 3600]


def test_ghost_hidden_and_admin_delete_respected(cal):
    now = int(time.time())
    t = now + 2 * 86400
    run(cal.merge_events([ev("Ghost Event", t + 100, cur="EUR"), ev("Keep A", t, cur="EUR"), ev("Keep B", t + 200, cur="EUR")]))
    run(store.execute("UPDATE econ_events SET updated_at = ? WHERE currency='EUR'", (now - 7 * 3600,)))
    run(cal.merge_events([ev("Keep A", t, cur="EUR"), ev("Keep B", t + 200, cur="EUR")], ghosts=True))
    assert rows("SELECT hidden FROM econ_events WHERE title='Ghost Event'")[0]["hidden"] == 2
    # 又出现了：恢复
    run(cal.merge_events([ev("Ghost Event", t + 100, cur="EUR")]))
    assert rows("SELECT hidden FROM econ_events WHERE title='Ghost Event'")[0]["hidden"] == 0
    # 管理员删除（hidden=1）后，抓取不会加回来
    run(store.execute("UPDATE econ_events SET hidden = 1 WHERE title='Keep A'"))
    run(cal.merge_events([ev("Keep A", t, cur="EUR")]))
    r = rows("SELECT hidden FROM econ_events WHERE title='Keep A'")
    assert len(r) == 1 and r[0]["hidden"] == 1


def test_next_keeps_due_event_until_released(cal):
    from app import cache
    now = int(time.time())
    run(store.execute("UPDATE econ_events SET hidden = 1 WHERE impact = 3"))
    run(cal.merge_events([ev("Due Now", now - 300, cur="JPY"), ev("Later", now + 3600, cur="JPY")]))
    run(cal.publish_window())
    import json
    nxt = json.loads(cache.get_raw("cal:next"))
    assert [e["title"] for e in nxt[:2]] == ["Due Now", "Later"]
