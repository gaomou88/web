"""CFTC 交易者持仓报告（TFF，金融期货）——机构在美股指数期货、美债期货上的多空持仓。
数据接口：CFTC 公开报告平台（Socrata），免费免 Key。每周五发布（数据截至周二）。
"""
from __future__ import annotations

import json
from typing import Any

from .. import cache, settings, store
from ..http import PoliteClient

TFF_URL = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"

GROUPS = {
    "dealer": ("dealer_positions_long_all", "dealer_positions_short_all", "change_in_dealer_long_all", "change_in_dealer_short_all"),
    "asset_mgr": ("asset_mgr_positions_long", "asset_mgr_positions_short", "change_in_asset_mgr_long", "change_in_asset_mgr_short"),
    "lev_money": ("lev_money_positions_long", "lev_money_positions_short", "change_in_lev_money_long", "change_in_lev_money_short"),
    "other": ("other_rept_positions_long", "other_rept_positions_short", "change_in_other_rept_long", "change_in_other_rept_short"),
    "nonrept": ("nonrept_positions_long_all", "nonrept_positions_short_all", "change_in_nonrept_long_all", "change_in_nonrept_short_all"),
}


def _n(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def summarize(row: dict[str, Any]) -> dict[str, Any]:
    groups = {}
    for g, (lk, sk, clk, csk) in GROUPS.items():
        lo, sh = _n(row.get(lk)), _n(row.get(sk))
        groups[g] = {"long": lo, "short": sh, "net": lo - sh, "net_change": _n(row.get(clk)) - _n(row.get(csk))}
    return {
        "date": row["report_date_as_yyyy_mm_dd"][:10],
        "code": row.get("cftc_contract_market_code", "").strip(),
        "market": row.get("market_and_exchange_names", ""),
        "open_interest": _n(row.get("open_interest_all")),
        "oi_change": _n(row.get("change_in_open_interest_all")),
        "groups": groups,
    }


class CftcCollector:
    def __init__(self, http: PoliteClient) -> None:
        self.http = http

    @property
    def codes(self) -> list[str]:
        return [c for c in settings.get_list("sources.cftc.codes") if c.replace("+", "").isalnum()]

    async def refresh(self) -> str:
        if not self.codes:
            raise RuntimeError("没有配置合约代码")
        codes = ",".join(f"'{c}'" for c in self.codes)
        r = await self.http.get(TFF_URL, params={
            "$where": f"cftc_contract_market_code in ({codes})",
            "$order": "report_date_as_yyyy_mm_dd DESC",
            "$limit": str(len(self.codes) * 26),  # 约半年
        }, min_interval=2)
        rows = r.json() or []
        if not rows:
            raise RuntimeError("没有匹配的合约代码，请检查 CFTC_CODES")
        recs = [summarize(x) for x in rows]
        await store.executemany(
            "INSERT OR IGNORE INTO cftc_tff VALUES (?, ?, ?, ?)",
            [(x["date"], x["code"], x["market"], json.dumps(x)) for x in recs],
        )
        by_code: dict[str, list[dict[str, Any]]] = {}
        for x in recs:
            by_code.setdefault(x["code"], []).append(x)
        out = [{"code": c, "market": v[0]["market"], "latest": v[0], "history": list(reversed(v))} for c, v in by_code.items()]
        out.sort(key=lambda x: self.codes.index(x["code"]) if x["code"] in self.codes else 99)
        cache.put("cftc:tff", {"date": recs[0]["date"], "markets": out}, topic="cftc")
        return f"{len(out)} 个合约，截至 {recs[0]['date']}"
