"""美股实时行情引擎：Finnhub / Alpaca / Polygon 可同时使用，凑出更多免费额度。

- 每家按自己的免费额度分到一批股票（WebSocket 逐笔推送）；
- 其余股票（以及某家断线期间它负责的股票）由“美股行情”采集器（新浪 → 腾讯 → Yahoo）每几秒轮询，
  两边的价格在这里合并，统一推送；
- 只保留每只股票的最新价，每 0.5 秒把“有变化的股票”合并成一条消息推送给浏览器；
- 会员新增自选股时，不断线直接追加订阅；
- 超过 5 分钟没有任何浏览器在线就断开连接、停止轮询，有人访问时自动恢复。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .. import cache, settings, universe

log = logging.getLogger("realtime")
IDLE_DISCONNECT = 300
ET = ZoneInfo("America/New_York")
WS_PROVIDERS = ["finnhub", "alpaca", "polygon"]
DEFAULT_LIMIT = {"finnhub": 50, "alpaca": 30, "polygon": 1000}
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

# 最新成交：symbol -> [价格, 毫秒时间戳]
last: dict[str, list[float]] = {}
# 每只股票当前由哪家 WebSocket 提供（已连接时）
source_of: dict[str, str] = {}
_dirty: set[str] = set()
_flusher_task: asyncio.Task | None = None


def tick(sym: str, price: float, ts: int, polled: bool = False) -> None:
    """记录最新价；价格有变化才加入下一批推送。"""
    cur = last.get(sym)
    if cur is None or ts >= cur[1] or polled:
        if cur is None or cur[0] != price:
            _dirty.add(sym)
        last[sym] = [price, ts]


def ws_covered(sym: str) -> bool:
    """该股票是否正由已连接的 WebSocket 供应商实时推送（是则轮询价不覆盖它）。"""
    return sym in source_of


async def _flusher() -> None:
    n = 0
    while True:
        await asyncio.sleep(0.5)
        n += 1
        if _dirty:
            batch = {s: last[s] for s in _dirty if s in last}
            _dirty.clear()
            cache.publish("ticks", batch)  # 只推送有变化的股票
        if n % 4 == 0:
            cache.put("rt:last", last)


def start_flusher() -> None:
    global _flusher_task
    if _flusher_task is None or _flusher_task.done():
        _flusher_task = asyncio.create_task(_flusher(), name="rt:flusher")


def _iso_ms(s: str) -> int:
    try:
        return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return int(time.time() * 1000)


def providers() -> list[str]:
    raw = settings.get_list("sources.realtime.providers")
    return [p for p in (x.lower() for x in raw) if p in WS_PROVIDERS]


def limit_of(name: str) -> int:
    n = int(settings.get(f"sources.realtime.{name}_limit") or 0)
    return n if n > 0 else DEFAULT_LIMIT.get(name, 50)




# ---------------- 供应商适配 ----------------
class Adapter:
    name = ""

    def __init__(self) -> None:
        self.url = ""

    def ready(self) -> str:
        """未配置好时返回原因。"""
        return ""

    async def handshake(self, ws: Any) -> None:
        pass

    async def subscribe(self, ws: Any, syms: list[str]) -> None:
        raise NotImplementedError

    async def unsubscribe(self, ws: Any, syms: list[str]) -> None:
        raise NotImplementedError

    def parse(self, raw: str) -> list[tuple[str, float, int]]:
        raise NotImplementedError


class Finnhub(Adapter):
    name = "finnhub"

    def __init__(self) -> None:
        self.key = settings.get("sources.realtime.finnhub_key")
        self.url = f"wss://ws.finnhub.io?token={self.key}"

    def ready(self) -> str:
        return "" if self.key else "还没有填写 Finnhub API Key"

    async def subscribe(self, ws: Any, syms: list[str]) -> None:
        for s in syms:
            await ws.send(json.dumps({"type": "subscribe", "symbol": s}))

    async def unsubscribe(self, ws: Any, syms: list[str]) -> None:
        for s in syms:
            await ws.send(json.dumps({"type": "unsubscribe", "symbol": s}))

    def parse(self, raw: str) -> list[tuple[str, float, int]]:
        m = json.loads(raw)
        if m.get("type") == "trade":
            return [(t["s"], float(t["p"]), int(t["t"])) for t in m.get("data") or []]
        if m.get("type") == "error":
            raise RuntimeError(m.get("msg") or "Finnhub 返回错误")
        return []


class Alpaca(Adapter):
    name = "alpaca"

    def __init__(self) -> None:
        self.key = settings.get("sources.realtime.alpaca_key_id")
        self.secret = settings.get("sources.realtime.alpaca_secret")
        self.url = f"wss://stream.data.alpaca.markets/v2/{settings.get('sources.realtime.alpaca_feed')}"

    def ready(self) -> str:
        return "" if self.key and self.secret else "还没有填写 Alpaca 的 Key ID 和 Secret"

    async def handshake(self, ws: Any) -> None:
        await ws.recv()
        await ws.send(json.dumps({"action": "auth", "key": self.key, "secret": self.secret}))
        resp = json.loads(await ws.recv())
        if not any(m.get("msg") == "authenticated" for m in resp):
            raise RuntimeError(f"Alpaca 认证失败：{resp}")

    async def subscribe(self, ws: Any, syms: list[str]) -> None:
        if syms:
            await ws.send(json.dumps({"action": "subscribe", "trades": syms}))

    async def unsubscribe(self, ws: Any, syms: list[str]) -> None:
        if syms:
            await ws.send(json.dumps({"action": "unsubscribe", "trades": syms}))

    def parse(self, raw: str) -> list[tuple[str, float, int]]:
        out = []
        for m in json.loads(raw):
            if m.get("T") == "t":
                out.append((m["S"], float(m["p"]), _iso_ms(m["t"])))
            elif m.get("T") == "error":
                raise RuntimeError(f"Alpaca {m.get('code')}: {m.get('msg')}")
        return out


class Polygon(Adapter):
    name = "polygon"

    def __init__(self) -> None:
        self.key = settings.get("sources.realtime.polygon_key") or settings.get("sources.darkpool_rt.api_key")
        self.url = settings.get("sources.realtime.polygon_ws")

    def ready(self) -> str:
        return "" if self.key else "还没有填写 Polygon API Key"

    async def handshake(self, ws: Any) -> None:
        await ws.recv()
        await ws.send(json.dumps({"action": "auth", "params": self.key}))
        resp = json.loads(await ws.recv())
        if not any(m.get("status") == "auth_success" for m in resp):
            raise RuntimeError(f"Polygon 认证失败：{resp}")

    async def subscribe(self, ws: Any, syms: list[str]) -> None:
        if syms:
            await ws.send(json.dumps({"action": "subscribe", "params": ",".join(f"T.{s}" for s in syms)}))

    async def unsubscribe(self, ws: Any, syms: list[str]) -> None:
        if syms:
            await ws.send(json.dumps({"action": "unsubscribe", "params": ",".join(f"T.{s}" for s in syms)}))

    def parse(self, raw: str) -> list[tuple[str, float, int]]:
        return [(m["sym"], float(m["p"]), int(m["t"])) for m in json.loads(raw) if m.get("ev") == "T"]


ADAPTERS = {"finnhub": Finnhub, "alpaca": Alpaca, "polygon": Polygon}


# ---------------- 引擎 ----------------
class WsConn:
    """一家 WebSocket 供应商的连接。"""

    def __init__(self, engine: "Engine", name: str) -> None:
        self.engine = engine
        self.name = name
        self.adapter = ADAPTERS[name]()
        self.connected = False
        self.want: set[str] = set()
        self.subscribed: set[str] = set()
        self.changed = asyncio.Event()
        self.note = ""

    async def run(self) -> None:
        import websockets
        backoff = 1
        while True:
            if cache.idle_seconds() > IDLE_DISCONNECT:
                self.note = "无人访问，已暂停"
                await cache.wait_for_client()
            try:
                async with websockets.connect(self.adapter.url, ping_interval=20, max_size=2**23, open_timeout=15) as ws:
                    await self.adapter.handshake(ws)
                    self.subscribed = set()
                    self.connected = True
                    self.note = "已连接"
                    self.engine.reassign()
                    backoff = 1
                    await self._session(ws)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self.note = f"断线：{type(e).__name__}: {e}"[:160]
                log.warning("realtime %s error: %s", self.name, e)
            finally:
                if self.connected:
                    self.connected = False
                    self.engine.reassign()  # 断线期间它负责的股票交给轮询
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 120)

    async def _sync(self, ws: Any) -> None:
        add, drop = sorted(self.want - self.subscribed), sorted(self.subscribed - self.want)
        if drop:
            await self.adapter.unsubscribe(ws, drop)
        if add:
            await self.adapter.subscribe(ws, add)
        self.subscribed = set(self.want)

    async def _session(self, ws: Any) -> None:
        reader = asyncio.create_task(self._read(ws))
        try:
            await self._sync(ws)
            while True:
                self.changed.clear()
                waiter = asyncio.create_task(self.changed.wait())
                done, _ = await asyncio.wait({reader, waiter}, timeout=30, return_when=asyncio.FIRST_COMPLETED)
                waiter.cancel()
                if reader in done:
                    reader.result()
                    return
                if self.changed.is_set():
                    await self._sync(ws)
                if cache.idle_seconds() > IDLE_DISCONNECT:
                    return
        finally:
            reader.cancel()

    async def _read(self, ws: Any) -> None:
        async for raw in ws:
            for sym, price, ts in self.adapter.parse(raw):
                self.engine.tick(sym, price, ts)


class Engine:
    def __init__(self, http: Any) -> None:
        self.http = http
        self.conns: dict[str, WsConn] = {}
        self.skipped: list[str] = []

    def tick(self, sym: str, price: float, ts: int, polled: bool = False) -> None:
        tick(sym, price, ts, polled)

    def reassign(self) -> None:
        """把股票按顺序分给已连接的 WebSocket 供应商；没分到的由行情采集器轮询。"""
        order = providers()
        cap = sum(limit_of(p) for p in order if p in self.conns)
        syms = universe.realtime_symbols(max(cap, 1))
        i = 0
        source_of.clear()
        for p in order:
            c = self.conns.get(p)
            if not c:
                continue
            n = limit_of(p) if c.connected else 0
            new = set(syms[i:i + n])
            i += n
            if new != c.want:
                c.want = new
                c.changed.set()
            for s in new:
                source_of[s] = p
        self.status()

    def status(self) -> None:
        parts = [f"{p}：{c.note or '连接中'}，{len(c.want)} 只（额度 {limit_of(p)}）" for p, c in self.conns.items()]
        parts += self.skipped
        parts.append("其余股票由“美股行情”采集器每几秒轮询（新浪 → 腾讯 → Yahoo）")
        ok = any(c.connected for c in self.conns.values()) or not self.conns
        cache.set_status("realtime", ok, "；".join(parts))

    async def run(self) -> None:
        try:
            import websockets  # noqa: F401
            has_ws = True
        except ImportError:
            has_ws = False
        tasks = []
        for p in providers():
            if not has_ws:
                self.skipped.append(f"{p}：缺少 websockets 库")
                continue
            c = WsConn(self, p)
            if (why := c.adapter.ready()):
                self.skipped.append(f"{p}：{why}，已跳过")
                continue
            self.conns[p] = c
            tasks.append(asyncio.create_task(c.run(), name=f"rt:{p}"))
        self.reassign()
        if not tasks:
            return
        changed = universe.listener()
        try:
            while True:
                try:
                    await asyncio.wait_for(changed.wait(), timeout=10)
                    changed.clear()
                    self.reassign()
                except asyncio.TimeoutError:
                    self.status()
                for t in tasks:
                    if t.done() and not t.cancelled() and t.exception():
                        raise t.exception()  # type: ignore[misc]
        finally:
            universe.drop_listener(changed)
            source_of.clear()
            for t in tasks:
                t.cancel()


state: dict[str, Any] = {}  # runner 注入 http 客户端


async def run() -> None:
    await Engine(state["http"]).run()
