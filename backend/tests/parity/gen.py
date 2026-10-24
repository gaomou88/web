import json, random, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
from app.pnl import compute_symbol, cash_balances, cpi_factor, deflator
rnd = random.Random(42)
CCY = ["CNY", "HKD", "USD", "EUR"]
def rates(s):
    return {"CNY": {"bid": 1, "ask": 1}, "USD": {"bid": 7.1 + s, "ask": 7.1005 + s}, "HKD": {"bid": .91, "ask": .9102}, "EUR": {"bid": 7.7 + s, "ask": 7.705 + s}}
cases = []
for i in range(300):
    trades, held = [], {}
    for j in range(rnd.randint(0, 8)):
        c = rnd.choice(CCY); side = "buy" if held.get(c, 0) <= 0 or rnd.random() < .6 else "sell"
        sh = rnd.choice([1, 5, 10, 33, 100, 2.5]); 
        if side == "sell": sh = min(sh, held[c])
        held[c] = held.get(c, 0) + (sh if side == "buy" else -sh)
        trades.append({"id": j + 1, "side": side, "trade_date": f"2026-10-{rnd.randint(1, 22):02d}", "shares": sh,
                       "price": round(rnd.uniform(5, 500), 2), "ccy": c, "fx": 1 if c == "USD" else round(rnd.uniform(.9, 8), 4), "fee": rnd.choice([0, 1, 2.5]),
                       "funding": "usd" if c != "USD" and rnd.random() < .35 else "ccy"})
    q = {"price": round(rnd.uniform(5, 500), 2), "prev_close": round(rnd.uniform(5, 500), 2)}
    now, prev = rates(rnd.uniform(-.2, .2)), rates(rnd.uniform(-.2, .2))
    base = rnd.choice(["CNY", "HKD", "USD"]); mode = rnd.choice(["mid", "bid"])
    moves = [{"trade_date": f"2026-10-{rnd.randint(1, 22):02d}", "ccy": rnd.choice(CCY), "amount": round(rnd.uniform(-5000, 20000), 2)} for _ in range(rnd.randint(0, 4))]
    # 一半用例扣除通胀：随机的月度物价指数表（部分货币没有表 → 不折算）
    cpi = None
    if i % 2:
        cpi = {}
        for c in CCY:
            if rnd.random() < .8:
                v, tab = 100.0, []
                for m in ["2026-07", "2026-08", "2026-09", "2026-10", "2026-11"]:
                    v *= 1 + rnd.uniform(-.004, .012)
                    tab.append([m, round(v, 6)])
                cpi[c] = {"table": tab}
    py = compute_symbol(trades, q, now, prev, mode, base, "2026-10-20", deflate=deflator(cpi, "2026-10-22") if cpi else None)
    cases.append({"trades": trades, "q": q, "now": now, "prev": prev, "base": base, "mode": mode, "moves": moves, "cpi": cpi,
                  "py": {k: py[k] for k in ["qty", "costBase", "costReal", "realized", "realizedPrice", "mvBase", "unreal", "unrealPrice", "unrealFx", "today", "todayPrice", "todayFx"]},
                  "pycash": cash_balances(trades, moves, base)})
# 物价指数插值
tab = [["2026-01", 100], ["2026-02", 100.5], ["2026-03", 101.2], ["2026-04", 100.9]]
factors = [[d, n, cpi_factor(tab, d, n)] for d, n in [("2025-12-01", "2026-04-30"), ("2026-02-03", "2026-03-20"), ("2026-02-15", "2026-02-15"),
                                                       ("2026-03-31", "2026-01-15"), ("2026-02-28", "2026-03-01")]]
json.dump({"table": tab, "factors": factors}, open("cpi_cases.json", "w"))
json.dump(cases, open("cases.json", "w"))
