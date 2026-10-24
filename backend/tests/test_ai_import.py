"""AI 导入的纯函数测试：文件识别、表格读取、脱敏、代码规范化、分段、换汇成本。运行：pytest backend/tests"""
import io
import zipfile

import pytest

from app import ai_import as ai


def test_sniff():
    assert ai.sniff(b"%PDF-1.7 ...") == "pdf"
    assert ai.sniff(b"\x89PNG\r\n\x1a\n....") == "png"
    assert ai.sniff(b"\xff\xd8\xff\xe0....") == "jpg"
    assert ai.sniff(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "webp"
    assert ai.sniff(b"\x00\x00\x00\x18ftypheic....") == "heic"
    assert ai.sniff(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1...") == "xls"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a.txt", "x")
    assert ai.sniff(buf.getvalue()) == "zip"
    assert ai.sniff("日期,代码\n2026-10-01,AAPL".encode()) == "text"


def test_decode_and_html():
    assert ai.decode_text("代码".encode("gbk")) == "代码"
    assert ai.decode_text("﻿代码".encode("utf-8")) == "代码"
    t = ai.html_to_text("<html><style>x{}</style><table><tr><td>2026-10-01</td><td>AAPL&amp;</td></tr><tr><td>b</td></tr></table>")
    assert t.splitlines()[0].split("\t")[:2] == ["2026-10-01", "AAPL&"]
    assert "x{}" not in t


def test_xlsx_text_reads_dates_and_shared_strings():
    openpyxl = pytest.importorskip("openpyxl")
    from datetime import date
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "成交"
    ws.append(["成交日期", "代码", "方向", "数量", "价格"])
    ws.append([date(2026, 9, 3), "AAPL", "买入", 10, 220.5])
    ws.cell(row=3, column=2, value="NVDA")
    ws.cell(row=3, column=5, value=118.2)
    ws2 = wb.create_sheet("资金")
    ws2.append(["入金", 1000])
    buf = io.BytesIO()
    wb.save(buf)
    txt = ai.xlsx_text(buf.getvalue())
    lines = txt.splitlines()
    assert lines[0] == "=== 工作表：成交 ==="
    assert lines[2].split("\t") == ["2026-09-03", "AAPL", "买入", "10", "220.5"]
    assert lines[3].split("\t") == ["", "NVDA", "", "", "118.2"]  # 空单元格保留位置
    assert "=== 工作表：资金 ===" in txt and "入金\t1000" in txt


def test_redact_keeps_numbers_and_dates():
    src = ("账户号码 U1234567 姓名：张三\nEmail: zhang.san@example.com 手机 13812345678 身份证 110101199003071234\n"
           "2026-09-03 AAPL 买入 10 220.50 1.99 2206.99\n20260915 NVDA 5 118.20 合计 123456789.00 订单号 987654321012")
    out = ai.redact(src)
    for gone in ("U1234567", "张三", "zhang.san@example.com", "13812345678", "110101199003071234", "987654321012"):
        assert gone not in out
    for kept in ("2026-09-03", "AAPL", "220.50", "2206.99", "20260915", "118.20", "123456789.00"):
        assert kept in out


def test_norm_symbol():
    cases = {"aapl": "AAPL", "AAPL US Equity": "AAPL", "US.AAPL": "AAPL", "NASDAQ:TSLA": "TSLA", "105.MSFT": "MSFT",
             "AAPL.US": "AAPL", "AAPL.O": "AAPL", "BRK B": "BRK.B", "BRK/B": "BRK.B", "BRK-B": "BRK.B", " nvda ": "NVDA"}
    for raw, want in cases.items():
        assert ai.norm_symbol(raw) == want, raw


def test_num_and_date():
    assert ai._num("1,234.50") == 1234.5 and ai._num("(12.5)") == -12.5 and ai._num("$3") == 3.0
    assert ai._num("abc") is None and ai._num(True) is None and ai._num(None) is None
    assert ai._date("2026/9/3") == "2026-09-03" and ai._date("2026-02-30") is None and ai._date("") is None


def test_redact_pseudonym_is_stable():
    a = ai.redact("订单号 987654321012 账户 U1234567")
    b = ai.redact("Order 987654321012")
    code = ai.pseudonym("987654321012")
    assert code in a and code in b and code.startswith("#") and len(code) == 9
    assert ai.pseudonym("U1234567") in a and ai.pseudonym("U1234567") != code


def test_condense_drops_headers_and_legal_text():
    page = ["XX证券 月结单", "第 {n} 页 共 3 页", "日期\t代码\t方向\t数量\t价格"]
    legal = "本结单仅供参考，如有疑问请于收到后七日内与本公司联系，逾期视为确认无误。" * 3
    rows = []
    for n in range(1, 4):
        rows += [x.replace("{n}", str(n)) for x in page]
        rows += [f"2026-09-0{n}\tAAPL\t买入\t10\t220.5", "2026-09-0{n}\tAAPL\t买入\t10\t220.5".replace("{n}", str(n)), "", "   ", legal]
    out = ai.condense("\n".join(rows))
    assert out.count("XX证券 月结单") == 1 and out.count("日期\t代码\t方向\t数量\t价格") == 1
    assert not any("页" in x for x in out) and legal not in out
    assert sum(1 for x in out if "AAPL" in x) == 6  # 成交明细（含完全相同的分笔成交）一行不少


def test_number_chunks_keep_all_lines():
    lines = [f"row {i} " + "x" * 50 for i in range(500)]
    parts = ai.number_chunks(lines, size=2000)
    assert all(len(t) <= 2000 for t, _ in parts)
    got = [ln for t, _ in parts for ln in t.splitlines()]
    assert got == [f"{i + 1}|{x}" for i, x in enumerate(lines)]
    merged = {}
    for _, mp in parts:
        merged.update(mp)
    assert merged[1] == lines[0] and merged[500] == lines[499]


def test_expand_short_keys():
    part = {"b": "IB", "ps": "2026-09-01", "pe": "2026-09-30",
            "t": [{"l": 3, "d": "2026-09-03", "tm": "09:31:05", "s": "AAPL", "sd": "b", "q": 10, "p": 220.5, "o": "#abc"},
                  {"l": 4, "d": "2026-09-04", "s": "0700", "sd": "s", "q": 100, "p": 400, "c": "HKD", "m": "HK"}],
            "c": [{"l": 5, "d": "2026-09-05", "ty": "fx", "fc": "CNY", "fa": 7100, "tc": "USD", "ta": 1000}],
            "x": ["拆股"]}
    e = ai.expand(part, {3: "原文第三行", 5: "换汇行"})
    t = e["trades"][0]
    assert (t["side"], t["currency"], t["market"], t["asset"], t["fee"], t["raw"], t["time"], t["order"]) == ("buy", "USD", "US", "stock", 0, "原文第三行", "09:31:05", "#abc")
    assert e["trades"][1]["currency"] == "HKD" and e["trades"][1]["side"] == "sell" and e["trades"][1]["raw"] == ""
    assert e["cash"][0]["type"] == "fx" and e["cash"][0]["raw"] == "换汇行" and e["notes"] == ["拆股"]
    # 模型用了完整键名也能识别
    e2 = ai.expand({"trades": [{"date": "2026-09-03", "symbol": "AAPL", "side": "buy", "quantity": 1, "price": 2}]}, {})
    assert e2["trades"][0]["symbol"] == "AAPL" and e2["trades"][0]["side"] == "buy"


def _r(q, p, t="", o=""):
    return {"shares": q, "price": p, "time": t, "ext_id": o}


def test_reconcile_rules():
    # 完全相同 → 重复；多出来的一笔 → 新
    res = ai.reconcile([_r(10, 100), _r(5, 101)], [_r(10, 100)])
    assert res[0][0] == "dup" and 1 not in res
    # 时间不同的同量同价不算重复，但当天合计对账会处理
    res = ai.reconcile([_r(10, 100, "09:31")], [_r(10, 100, "10:00")])
    assert res[0][0] == "dup" and "合计" in res[0][1]
    # 手动记了一笔当天合计 30 股，文件里是 3 笔分笔成交 → 全部视为已记录
    res = ai.reconcile([_r(10, 100), _r(10, 100.2), _r(10, 99.8)], [_r(30, 100)])
    assert all(res[i][0] == "dup" for i in range(3))
    # 文件 40 股、已记录 30 股：找出对得上的 30 股，多出的 10 股要用户确认
    res = ai.reconcile([_r(10, 100), _r(20, 100), _r(10, 105)], [_r(30, 100)])
    assert res[0][0] == "dup" and res[1][0] == "dup" and res[2][0] == "partial"
    # 已记录更多 → 文件里的都算已记录
    res = ai.reconcile([_r(10, 100)], [_r(25, 100.1)])
    assert res[0][0] == "dup"
    # 均价差很多 → 对不上，要确认
    res = ai.reconcile([_r(30, 120)], [_r(30, 100)])
    assert res[0][0] == "partial"
    # 订单号相同 → 重复；订单号不同即使量价相同也不能按逐笔匹配
    res = ai.reconcile([_r(10, 100, o="#a"), _r(10, 100, o="#b")], [_r(10, 100, o="#a")])
    assert res[0][0] == "dup" and "订单号" in res[0][1] and 1 not in res  # 另一个订单：新的
    # 没有已记录的 → 全是新的
    assert ai.reconcile([_r(1, 1)], []) == {}


def test_fx_pool_and_cost_rate():
    moves = [
        {"grp": "a", "kind": "fx", "trade_date": "2026-09-01", "ccy": "CNY", "amount": -71000.0},
        {"grp": "a", "kind": "fx", "trade_date": "2026-09-01", "ccy": "USD", "amount": 10000.0},
        {"grp": "b", "kind": "fx", "trade_date": "2026-09-20", "ccy": "CNY", "amount": -36500.0},
        {"grp": "b", "kind": "fx", "trade_date": "2026-09-20", "ccy": "USD", "amount": 5000.0},
        {"grp": "c", "kind": "fx", "trade_date": "2026-09-25", "ccy": "USD", "amount": -1000.0},  # 美元换回人民币：不影响平均成本
        {"grp": "c", "kind": "fx", "trade_date": "2026-09-25", "ccy": "CNY", "amount": 7200.0},
        {"grp": "d", "kind": "deposit", "trade_date": "2026-08-01", "ccy": "CNY", "amount": 200000.0},
    ]
    pool = ai.fx_pool(moves, "CNY")
    assert pool == [("2026-09-01", 71000.0, 10000.0), ("2026-09-20", 36500.0, 5000.0)]
    assert ai.cost_rate(pool, "2026-09-10") == (7.1, False)
    r, borrowed = ai.cost_rate(pool, "2026-10-01")
    assert abs(r - 107500 / 15000) < 1e-12 and not borrowed
    assert ai.cost_rate(pool, "2026-08-15") == (7.1, True)   # 早于第一笔换汇：借用最早一笔
    assert ai.cost_rate([], "2026-08-15") == (None, False)


def test_pdf_text_and_scanned(tmp_path):
    pytest.importorskip("pypdfium2")
    reportlab = pytest.importorskip("reportlab.pdfgen.canvas")
    p = tmp_path / "a.pdf"
    c = reportlab.Canvas(str(p))
    c.drawString(72, 720, "2026-09-03 AAPL BUY 10 220.50 1.99")
    c.showPage()
    c.showPage()  # 空白页：当作扫描页
    c.save()
    texts, imgs = ai.pdf_pages(p.read_bytes(), 30, want_images=True)
    assert "AAPL" in texts[0] and imgs[0] is None
    assert imgs[1] is not None and imgs[1][:8] == b"\x89PNG\r\n\x1a\n"
    with pytest.raises(ai.UserError):
        ai.pdf_pages(p.read_bytes(), 1, want_images=False)  # 超过页数上限


def test_png_encoder_roundtrip():
    from PIL import Image
    png = ai._png_gray(3, 2, 4, bytes([0, 128, 255, 9, 10, 20, 30, 9]), 1)
    im = Image.open(io.BytesIO(png))
    assert im.size == (3, 2) and list(im.get_flattened_data()) if hasattr(im, "get_flattened_data") else list(im.getdata()) == [0, 128, 255, 10, 20, 30]
