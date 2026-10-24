"""解析器单元测试（样例数据来自 2026-10 实测返回）。运行：pytest backend/tests"""
from datetime import datetime, timezone

from app.collectors.calendar import norm_title, parse_feed, parse_ff_page, region_of
from app.collectors.cftc import summarize
from app.collectors.cme import num, parse_cme_quotes
from app.collectors.finra import parse_daily
from app.collectors.market import market_session

FEED = [
    {"title": "CPI m/m", "country": "CAD", "date": "2026-10-19T08:30:00-04:00", "impact": "High", "forecast": "0.2%", "previous": "-0.1%"},
    {"title": "German PPI m/m", "country": "EUR", "date": "2026-10-20T02:00:00-04:00", "impact": "Low", "forecast": "1.5%", "previous": "1.1%"},
    {"title": "IMF Meetings", "country": "All", "date": "2026-10-18T10:15:00-04:00", "impact": "Low", "forecast": "", "previous": ""},
    {"title": "Daylight Saving Time Shift", "country": "GBP", "date": "2026-10-24T21:00:00-04:00", "impact": "Holiday", "forecast": "", "previous": ""},
    {"title": "bad", "country": "USD", "date": "not-a-date"},
]


def test_parse_feed():
    ev = parse_feed(FEED)
    assert len(ev) == 4
    cpi = ev[0]
    assert cpi["ts"] == datetime(2026, 10, 19, 12, 30, tzinfo=timezone.utc)
    assert cpi["impact"] == 3 and cpi["region"] == "CA"
    assert ev[1]["region"] == "DE" and ev[1]["impact"] == 1
    assert ev[2]["is_org"] is True and ev[2]["region"] == "GL"
    assert ev[3]["impact"] == 0


def test_region_and_title():
    assert region_of("EUR", "French Flash Services PMI") == "FR"
    assert region_of("EUR", "ZEW Economic Sentiment") == "EU"
    assert norm_title("CPI m/m") == norm_title("CPI  m/m")


def test_parse_ff_page():
    html = (
        'window.calendarComponentStates[1] = {days: [{"date":"x","events":['
        '{"id":149224,"ebaseId":29,"name":"GDP m\\/m","prefixedName":"CA GDP m\\/m","currency":"CAD",'
        '"dateline":1782822600,"impactName":"high","actual":"0.5%","forecast":"0.4%","previous":"-0.1%",'
        '"revision":"","actualBetterWorse":1},'
        '{"id":149225,"name":"Speech","currency":"USD","dateline":1782830000,"actual":"","forecast":"","previous":"",'
        '"revision":"","actualBetterWorse":0}]}]};'
    )
    ev = parse_ff_page(html)
    assert len(ev) == 2
    assert ev[0]["title"] == "GDP m/m" and ev[0]["actual"] == "0.5%" and ev[0]["surprise"] == 1
    assert ev[0]["ts"].timestamp() == 1782822600


def test_parse_daily():
    text = (
        "Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\n"
        "20261021|AAPL|6483135.735156|46834|12517484.190275|B,Q,N\n"
        "20261021|AAL|17077915.020603|115721|42976216.997944|B,Q,N\n"
        "12345\n"
    )
    rows = parse_daily(text)
    assert len(rows) == 2
    assert rows[0]["symbol"] == "AAPL" and round(rows[0]["short_volume"] / rows[0]["total_volume"], 3) == 0.518


def test_session():
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    assert market_session(datetime(2026, 10, 22, 7, 0, tzinfo=et)) == "pre"
    assert market_session(datetime(2026, 10, 22, 10, 0, tzinfo=et)) == "regular"
    assert market_session(datetime(2026, 10, 22, 17, 0, tzinfo=et)) == "post"
    assert market_session(datetime(2026, 10, 24, 10, 0, tzinfo=et)) == "closed"


def test_cme():
    assert num("5,123.25") == 5123.25 and num("-") is None and num("+0.25%") == 0.25
    q = parse_cme_quotes({"quotes": [{"quoteCode": "ESZ6", "last": "6,812.50", "change": "-12.25", "volume": "1,234,567",
                                      "updated": "16:59:59 CT<br /> 21 Oct 2026"}]})
    assert q[0]["last"] == 6812.5 and q[0]["volume"] == 1234567 and "<br" not in q[0]["updated"]


def test_cftc():
    row = {"report_date_as_yyyy_mm_dd": "2022-09-13T00:00:00.000", "cftc_contract_market_code": "13874+",
           "market_and_exchange_names": "S&P 500 Consolidated", "open_interest_all": "520609",
           "lev_money_positions_long": "23497", "lev_money_positions_short": "128568",
           "change_in_lev_money_long": "-2932", "change_in_lev_money_short": "11625"}
    s = summarize(row)
    assert s["date"] == "2022-09-13"
    assert s["groups"]["lev_money"]["net"] == 23497 - 128568
    assert s["groups"]["lev_money"]["net_change"] == -2932 - 11625


def test_totp_rfc6238():
    # RFC 6238 测试向量：T=59 秒（计数器 1），8 位结果 94287082 的后 6 位
    from app.security import _hotp
    assert _hotp("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", 1) == "287082"
    assert _hotp("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", 37037036) == "081804"  # T=1111111109 -> 07081804


def test_qr_roundtrip():
    from app.qr import QrCode
    q = QrCode("otpauth://totp/Zyll:admin?secret=JBSWY3DPEHPK3PXP&issuer=Zyll")
    assert q.size == q.ver * 4 + 17 and "<svg" in q.svg()


# ---------------- 第 3 轮：新数据源 ----------------
def test_sina_futures_and_stocks():
    from app.collectors.cme import parse_sina_hf
    from app.collectors.market import parse_sina_stocks, parse_sina_indices, parse_tencent_stocks
    hf = parse_sina_hf('var hq_str_hf_ES="6831.50,,6831.25,6831.75,6850.00,6800.00,07:58:01,6821.50,6825.00,250000,1,2,2026-10-22,S&P,0";\nvar hq_str_hf_XX="";')
    assert hf["ES"]["last"] == 6831.5 and hf["ES"]["prior_settle"] == 6821.5 and abs(hf["ES"]["change"] - 10) < 1e-9 and "XX" not in hf
    f = ["苹果", "230.10", "0.5", "t", "1", "229", "231", "228", "260", "160", "1000", "0", "3.4e12", "6.5", "35"] + ["0"] * 6 + ["231.00", "0.39", "0.9", "x", "0", "229.0"]
    line = f'var hq_str_gb_aapl="{",".join(f)}";\nvar hq_str_gb_brk$b="{",".join(f)}";\nvar hq_str_gb_zzzz="";'
    reg = parse_sina_stocks(line, "regular")
    assert set(reg) == {"AAPL", "BRK.B"}
    q = reg["AAPL"]
    assert q["live"] == 230.10 and q["prev_close"] == 229.0 and q["volume"] == 1000 and q["amount"] == 230100 and q["name"] == "苹果"
    assert abs(q["change_pct"] - (230.10 / 229 - 1) * 100) < 1e-3
    pre = parse_sina_stocks(line, "pre")["AAPL"]   # 盘前：昨收 = 上一交易日收盘（新浪最新价），实时价 = 盘前价
    assert pre["prev_close"] == 230.10 and pre["live"] == 231.00
    post = parse_sina_stocks(line, "post")["AAPL"]  # 盘后：实时价 = 盘后价，昨收不变
    assert post["prev_close"] == 229.0 and post["live"] == 231.00
    idx = parse_sina_indices('var hq_str_gb_$dji="道琼斯,47050.20,0.1,t,1,47000,47100,46900,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,46990.0";')
    assert idx["gb_$dji"]["price"] == 47050.2 and idx["gb_$dji"]["prev_close"] == 46990.0
    tx = "~".join(["200", "苹果", "AAPL.OQ", "230.55", "229.0", "229.5", "5000"] + ["0"] * 26 + ["231", "228"] + ["0"] * 9 + ["34000"])
    t = parse_tencent_stocks(f'v_usAAPL="{tx}";')
    assert t["AAPL"]["live"] == 230.55 and t["AAPL"]["prev_close"] == 229.0 and t["AAPL"]["high"] == 231


def test_rank_and_spark():
    from app.collectors.market import parse_sina_rank, parse_yahoo_spark
    r = parse_sina_rank("IO.XSRV2.CallbackList['zy']((" + '{count:"2",data:[{symbol:"SOXL",cname:"半导体",price:"30.5",preclose:"30",volume:"100",chg:"1.6"}]}));')
    assert r[0]["symbol"] == "SOXL" and r[0]["amount"] == 3050 and r[0]["change_pct"] == 1.6
    r2 = parse_sina_rank('x(({"count":"1","data":[{"symbol":"F","price":"11","volume":"5"}]}))')
    assert r2[0]["amount"] == 55
    sp = parse_yahoo_spark({"^DJI": {"close": [1, None, 2, 3], "chartPreviousClose": 2.5}})
    assert sp["^DJI"]["price"] == 3 and sp["^DJI"]["prev_close"] == 2.5 and sp["^DJI"]["spark"] == [1, 2, 3]
    sp2 = parse_yahoo_spark({"spark": {"result": [{"symbol": "^VIX", "response": [{"meta": {"regularMarketPrice": 15.2, "previousClose": 15}, "indicators": {"quote": [{"close": [15, 15.2]}]}}]}]}})
    assert sp2["^VIX"]["price"] == 15.2 and sp2["^VIX"]["prev_close"] == 15


def test_holidays_rules():
    from datetime import date, datetime
    from zoneinfo import ZoneInfo
    from app.holidays import nyse_schedule, easter, target_holidays, prev_us_trading_day, us_close_hour
    from app.collectors.market import market_session
    c, e = nyse_schedule(2026)  # 与纽交所官网公布的 2026 年一致
    assert sorted(d.isoformat() for d in c) == ["2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19",
                                               "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25"]
    assert sorted(d.isoformat() for d in e) == ["2026-11-27", "2026-12-24"]
    c25, e25 = nyse_schedule(2025)
    assert date(2025, 4, 18) in c25 and date(2025, 7, 3) in e25
    assert easter(2027) == date(2027, 3, 28) and date(2027, 3, 26) in target_holidays(2027)
    assert prev_us_trading_day(date(2026, 11, 27)) == date(2026, 11, 25)
    assert us_close_hour(date(2026, 11, 27)) == 13
    et = ZoneInfo("America/New_York")
    assert market_session(datetime(2026, 11, 26, 11, 0, tzinfo=et)) == "closed"      # 感恩节
    assert market_session(datetime(2026, 11, 27, 14, 0, tzinfo=et)) == "post"        # 提前收盘后
    assert market_session(datetime(2026, 10, 22, 8, 0, tzinfo=et)) == "pre"


def test_glossary_and_week_key():
    from datetime import date
    from app.glossary import explain
    from app.collectors.calendar import week_key, parse_ff_page
    assert explain("ADP Non-Farm Employment Change")["name_zh"].startswith("ADP")
    assert explain("Unemployment Claims")["effect"] == "down"
    assert explain("Something Unknown")["name_zh"] == ""
    assert week_key(date(2026, 10, 22)) == "oct18.2026" and week_key(date(2026, 10, 18)) == "oct18.2026"
    ev = parse_ff_page('{"id":1,"name":"CPI y/y","currency":"GBP","dateline":1792650000,"impactName":"high","actual":"3.2%","forecast":"3.4%","previous":"3.1%","revision":"","actualBetterWorse":-1}')
    assert ev[0]["impact"] == 3 and ev[0]["surprise"] == -1
    ev2 = parse_ff_page('{"id":2,"name":"X","currency":"USD","dateline":1792650000,"impactClass":"icon icon--ff-impact-ora","actual":""}')
    assert ev2[0]["impact"] == 2


def test_yahoo_and_symbols():
    from app.collectors.cme import parse_yahoo_chart
    from app.collectors import symbols as S
    q = parse_yahoo_chart({"chart": {"result": [{"meta": {"symbol": "RTY=F", "regularMarketPrice": 2480.0, "previousClose": 2470.0}}]}})
    assert q["last"] == 2480.0 and abs(q["change"] - 10) < 1e-9
    assert parse_yahoo_chart({"chart": {"result": None}}) is None
    head = "Nasdaq Traded|Symbol|Security Name|Listing Exchange|Market Category|ETF|Round Lot Size|Test Issue|Financial Status|CQS Symbol|NASDAQ Symbol|NextShares"
    rows = S.parse_nasdaq("\n".join([head, "Y|NVDA|NVIDIA Corporation - Common Stock|Q|Q|N|100|N|N||NVDA|N",
                                     "Y|ZZZT|Test|Q|Q|N|100|Y|N||ZZZT|N", "Y|AB$C|Pref|N| |N|100|N|N||AB$C|N",
                                     "Y|SPY|SPDR S&P 500 ETF Trust|P| |Y|100|N|N|SPY|SPY|N", "File Creation Time: x|||||||||||"]))
    assert [r[0] for r in rows] == ["NVDA", "SPY"] and rows[1][3] == 1 and rows[0][2] == "NASDAQ"
    S._index[:] = sorted(((a, b, b.lower(), c, d) for a, b, c, d in rows + [("NVDL", "GraniteShares 2x Long NVDA", "NASDAQ", 1)]))
    assert [x["symbol"] for x in S.search("nvd")] == ["NVDA", "NVDL"]
    assert S.search("nvidia")[0]["symbol"] == "NVDA"
    assert S.search("SPY")[0]["symbol"] == "SPY"


def test_finra_candidate_weeks():
    from datetime import date
    from app.collectors.finra import candidate_weeks, _filters
    w = candidate_weeks(date(2026, 10, 22), 3)
    assert w == ["2026-10-12", "2026-10-05", "2026-09-28"]
    assert _filters(a="1")[0]["compareType"] == "EQUAL"


def test_rate_limit_error():
    from app.http import HTTPStatusError, RateLimited
    e = HTTPStatusError(429, "u", {"retry-after": "120"}, b"slow down")
    assert e.retry_after == 120 and "slow down" in str(e)
    assert HTTPStatusError(429, "u").retry_after is None
    assert "分钟" in str(RateLimited(600))


def test_mail_template_render():
    from app import mailtpl
    vals = {"site_name": "Z<b>", "email": "a@b.c", "link": "L"}
    subject, body, html_body = mailtpl.render("verify", vals)
    assert "Z<b>" in subject and "L" in body and html_body is None
    assert mailtpl._fill("<p>{site_name}{unknown}</p>", vals, True) == "<p>Z&lt;b&gt;{unknown}</p>"


def test_anon_ip_and_device():
    from app.api_public import anon_ip
    from app import track
    assert anon_ip("203.0.113.77") == "203.0.113.0"
    assert anon_ip("2001:db8:abcd:12::1") == "2001:db8:abcd::"
    d = track.clean_device({"tz": "Europe/Berlin", "screen": "1920x1080", "evil": "x" * 9999, "langs": "x" * 999})
    assert "evil" not in d and len(d["langs"]) == 120


def test_cash_and_capital_rules():
    from app.pnl import cash_balances, compute_symbol
    trades = [{"id": 1, "symbol": "AAPL", "side": "buy", "trade_date": "2026-08-03", "shares": 100, "price": 150, "ccy": "CNY", "fx": 7.1, "fee": 0},
              {"id": 2, "symbol": "NVDA", "side": "buy", "trade_date": "2026-09-15", "shares": 10, "price": 160, "ccy": "USD", "fx": 1, "fee": 0},
              {"id": 3, "symbol": "NVDA", "side": "sell", "trade_date": "2026-10-01", "shares": 5, "price": 200, "ccy": "USD", "fx": 1, "fee": 1}]
    moves = [{"trade_date": "2026-08-01", "ccy": "CNY", "amount": 200000}, {"trade_date": "2026-08-02", "ccy": "CNY", "amount": -10000},
             {"trade_date": "2026-08-02", "ccy": "USD", "amount": 1400}]
    bal = cash_balances(trades, moves, "CNY")
    assert abs(bal["CNY"] - 83500) < 1e-6 and abs(bal["USD"] - (1400 - 1600 + 999)) < 1e-6
    assert abs(cash_balances(trades, moves, "CNY", until="2026-09-01")["USD"] - 1400) < 1e-6   # 按日期截止
    r = compute_symbol(trades[1:], {"price": 190, "prev_close": 190}, None, None, "mid", "CNY", "9999", rate=lambda c: {"USD": 1, "CNY": 7.0}[c])
    assert abs(r["mvBase"] - 5 * 190 * 7.0) < 1e-6 and abs(r["realized"] - ((5 * 200 - 1) - 5 * 160) * 7.0) < 1e-6


def test_parse_cash_validation():
    from app import api_portfolio as P
    rows = P._parse_cash({"kind": "fx", "trade_date": "2026-09-01", "from_ccy": "CNY", "from_amount": "10000", "to_ccy": "USD", "to_amount": "1400"})
    assert [r["amount"] for r in rows] == [-10000, 1400] and rows[0]["ccy"] == "CNY"
    assert P._parse_cash({"kind": "withdraw", "trade_date": "2026-09-01", "ccy": "CNY", "amount": 5})[0]["amount"] == -5
    for bad in [{"kind": "fx", "trade_date": "2026-09-01", "from_ccy": "CNY", "from_amount": 1, "to_ccy": "CNY", "to_amount": 1},
                {"kind": "deposit", "trade_date": "2026-09-01", "ccy": "CNY", "amount": 0},
                {"kind": "deposit", "trade_date": "2026-09-01", "ccy": "XXX", "amount": 5},
                {"kind": "deposit", "trade_date": "2999-01-01", "ccy": "CNY", "amount": 5},
                {"kind": "nope", "trade_date": "2026-09-01"}]:
        try:
            P._parse_cash(bad)
        except ValueError:
            continue
        raise AssertionError(bad)


def test_history_helpers():
    from datetime import date
    from app.history import parse_chart, trading_days, _Series
    rows = parse_chart({"chart": {"result": [{"meta": {"exchangeTimezoneName": "America/New_York"}, "timestamp": [1792612800, 1792699200],
                                               "indicators": {"quote": [{"close": [10.0, None]}]}}]}})
    assert rows == [("2026-10-21", 10.0)]  # 美东 16:00 收盘时刻
    assert [d.isoformat() for d in trading_days(date(2026, 11, 25), date(2026, 11, 30))] == ["2026-11-25", "2026-11-27", "2026-11-30"]
    s = _Series([("2026-10-01", 1.0), ("2026-10-05", 2.0)])
    assert s.at("2026-09-30") is None and s.at("2026-10-03") == 1.0 and s.at("2026-10-09") == 2.0


def test_card_codes_and_expiry():
    from app import members
    c = members.new_code("ZYLL")
    assert c.startswith("ZYLL-") and len(c) == 19 and not any(ch in c[5:] for ch in "01OIL")  # 随机部分不含易混淆字符
    assert members.normalize(" zyll-abcd efgh_jkmn ") == "ZYLLABCDEFGHJKMN"
    now = 1_800_000_000
    u_none = {"member_level": 0, "member_expires": None}
    assert members._expiry_after(u_none, 30, now) == now + 30 * 86400
    u_active = {"member_level": 1, "member_expires": now + 10 * 86400}
    assert members._expiry_after(u_active, 30, now) == now + 40 * 86400          # 续期从到期日往后加
    u_expired = {"member_level": 1, "member_expires": now - 5 * 86400}
    assert members._expiry_after(u_expired, 30, now) == now + 30 * 86400         # 已过期从现在算
    assert members._expiry_after(u_active, 0, now) is None                         # 永久卡
