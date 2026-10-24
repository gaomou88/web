"""实时暗池大单——可插拔付费数据源。

实时逐笔的场外成交（经 FINRA TRF 上报）没有免费源，这里定义统一接口：
新增一家供应商只需实现 DarkPoolProvider.stream()，并在 PROVIDERS 中注册。
未配置（DARKPOOL_PROVIDER 为空）时整个模块不运行，网站只展示免费的 FINRA 数据。
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

from .. import cache, settings, store

log = logging.getLogger("darkpool")


class DarkPoolProvider:
    name = "base"

    def configured(self) -> bool:
        return False

    async def stream(self) -> AsyncIterator[dict[str, Any]]:  # pragma: no cover - 接口
        raise NotImplementedError
        yield {}


class PolygonProvider(DarkPoolProvider):
    """Polygon（现名 Massive）股票逐笔成交 WebSocket。exchange=4 且带 trfi 的成交即场外 TRF 上报成交。"""

    name = "polygon"

    def __init__(self) -> None:
        self.api_key = settings.get("sources.darkpool_rt.api_key")
        self.url = settings.get("sources.darkpool_rt.ws_url")
        self.min_notional = float(settings.get("sources.darkpool_rt.min_notional"))
        self.symbols = settings.get_list("sources.darkpool_rt.symbols") or settings.get_list("sources.market.watchlist")

    def configured(self) -> bool:
        return bool(self.api_key)

    async def stream(self) -> AsyncIterator[dict[str, Any]]:
        import websockets

        async with websockets.connect(self.url, ping_interval=20, max_size=2**23) as ws:
            await ws.recv()
            await ws.send(json.dumps({"action": "auth", "params": self.api_key}))
            resp = json.loads(await ws.recv())
            if not any(m.get("status") == "auth_success" for m in resp):
                raise RuntimeError(f"认证失败：{resp}")
            await ws.send(json.dumps({"action": "subscribe", "params": ",".join(f"T.{x}" for x in self.symbols)}))
            cache.set_status("darkpool_rt", True, f"已连接，订阅 {len(self.symbols)} 只")
            async for raw in ws:
                for m in json.loads(raw):
                    if m.get("ev") != "T" or m.get("x") != 4 or not m.get("trfi"):
                        continue
                    notional = float(m["p"]) * float(m["s"])
                    if notional < self.min_notional:
                        continue
                    yield {
                        "ts": m["t"] / 1000,
                        "symbol": m["sym"],
                        "price": float(m["p"]),
                        "size": float(m["s"]),
                        "notional": notional,
                        "venue": f"TRF {m.get('trfi')}",
                        "conditions": ",".join(str(c) for c in m.get("c") or []),
                    }


PROVIDERS: dict[str, type[DarkPoolProvider]] = {"polygon": PolygonProvider}


def enabled() -> bool:
    return bool(settings.get("sources.darkpool_rt.enabled"))


async def run() -> None:
    cls = PROVIDERS.get(settings.get("sources.darkpool_rt.provider"))
    provider = cls() if cls else None
    if not provider or not provider.configured():
        cache.set_status("darkpool_rt", False, "已启用，但还没有填写 API Key")
        return
    backoff = 1
    while True:
        try:
            async for p in provider.stream():
                backoff = 1
                await store.execute(
                    "INSERT INTO dark_prints (ts, symbol, price, size, notional, venue, conditions, provider) VALUES (?,?,?,?,?,?,?,?)",
                    (p["ts"], p["symbol"], p["price"], p["size"], p["notional"], p["venue"], p["conditions"], provider.name),
                )
                cache.publish("dark_print", p)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            cache.set_status("darkpool_rt", False, f"{type(e).__name__}: {e}")
            log.warning("darkpool stream error: %s", e)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 120)
