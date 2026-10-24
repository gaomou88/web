"""采集管理器：所有数据源作为后台任务运行，后台改设置后立即生效。

- 周期型数据源：每轮开始时读取最新的开关和间隔；后台改动会立即唤醒它。
- 实时流（Alpaca、暗池大单）：相关设置变化时自动重启。
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Awaitable, Callable

from .. import cache, settings
from ..http import HTTPStatusError, PoliteClient, RateLimited, RobotsDisallowed
from . import darkpool_rt, realtime
from .calendar import CalendarCollector
from .cftc import CftcCollector
from .cme import CmeCollector
from .finra import FinraCollector
from .fx import FxCollector
from .market import MarketCollector, market_session
from .symbols import SymbolsCollector
from ..holidays import HolidayCollector
from ..history import HistoryCollector
from ..inflation import InflationCollector

log = logging.getLogger("collector")
STREAMS = {"realtime", "darkpool_rt"}
# 无人访问时可以放慢的数据源（只影响页面展示的行情类）
IDLE_SLOW = {"market": 5, "cme_futures": 4, "fx_cfets": 3}


class Manager:
    def __init__(self, http: PoliteClient, finra: FinraCollector) -> None:
        self.http = http
        self.finra = finra
        realtime.state["http"] = http
        self.cal = CalendarCollector(http)
        cftc = CftcCollector(http)
        cme = CmeCollector(http)
        self.market = market = MarketCollector(http)
        fx = FxCollector(http)
        self.periodic: dict[str, Callable[[], Awaitable[str | None]]] = {
            "calendar": self.cal.refresh_schedule,
            "calendar_actuals": self.cal.refresh_actuals,
            "finra_daily": finra.refresh_daily,
            "finra_ats": finra.refresh_weekly,
            "cftc": cftc.refresh,
            "market": market.refresh,
            "cme_futures": cme.refresh_quotes,
            "cme_blocks": cme.refresh_blocks,
            "fx_cfets": fx.refresh,
            "us_symbols": SymbolsCollector(http).refresh,
            "holidays": HolidayCollector(http).refresh,
            "pf_history": HistoryCollector(http).refresh,
            "inflation": InflationCollector(http).refresh,
        }
        self.streams: dict[str, Callable[[], Awaitable[None]]] = {
            "realtime": realtime.run,
            "darkpool_rt": darkpool_rt.run,
        }
        self.tasks: dict[str, asyncio.Task] = {}
        self.wake: dict[str, asyncio.Event] = {}
        settings.on_change(self._on_settings_change)
        cache.on_first_client(self._wake_idle)

    def _wake_idle(self) -> None:
        for name in IDLE_SLOW:
            if name in self.wake:
                self.wake[name].set()

    @property
    def names(self) -> list[str]:
        return list(self.periodic) + list(self.streams)

    def start(self) -> None:
        realtime.start_flusher()
        asyncio.create_task(self.cal.startup())              # 写入内置官方日程，再用库里已有数据填充页面
        asyncio.create_task(self.finra.publish_daily_summary())
        for name in self.names:
            self._spawn(name)

    def stop(self) -> None:
        for t in self.tasks.values():
            t.cancel()

    def _spawn(self, name: str) -> None:
        old = self.tasks.get(name)
        if old:
            old.cancel()
        self.wake[name] = asyncio.Event()
        coro = self._run_stream(name) if name in STREAMS else self._run_periodic(name)
        self.tasks[name] = asyncio.create_task(coro, name=f"src:{name}")

    def trigger(self, name: str) -> None:
        """立即执行一次（后台“立即刷新”按钮）。"""
        if name in STREAMS:
            self._spawn(name)
        elif name in self.wake:
            self.wake[name].set()

    def _on_settings_change(self, keys: set[str]) -> None:
        touched = {k.split(".")[1] for k in keys if k.startswith("sources.")}
        if "market" in touched:  # 关注列表也被实时流和 ATS 预取使用
            touched |= {"realtime", "darkpool_rt", "finra_ats", "finra_daily"}
        for name in touched:
            if name in STREAMS:
                self._spawn(name)
            elif name in self.wake:
                self.wake[name].set()

    async def _sleep(self, name: str, seconds: float) -> None:
        ev = self.wake[name]
        try:
            await asyncio.wait_for(ev.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass
        ev.clear()

    def _interval(self, name: str) -> float:
        base = float(settings.get(f"sources.{name}.interval") or 60)
        if name == "calendar_actuals" and self.cal.near_release:
            return max(float(settings.get("sources.calendar_actuals.fast_interval") or 5), 3)  # 公布时刻高频检查
        if name == "market" and market_session() == "closed":
            base = max(base * 10, 30)  # 美股休市（含假日）时降低频率
        if name in IDLE_SLOW and cache.idle_seconds() > 120:
            base *= IDLE_SLOW[name]  # 两分钟无人访问时降低频率
        return max(base, 2 if name == "market" else 3)

    async def _run_periodic(self, name: str) -> None:
        if name == "calendar_actuals":
            await self._sleep(name, 15)  # 等日程先加载
        fn = self.periodic[name]
        backoff = 0
        while True:
            wait_override: float | None = None
            if not settings.get(f"sources.{name}.enabled"):
                cache.set_status(name, False, "已在后台关闭", disabled=True)
                await self._sleep(name, 3600)
                continue
            try:
                msg = await fn()
                cache.set_status(name, True, msg or "")
                backoff = 0
            except asyncio.CancelledError:
                raise
            except (RateLimited, HTTPStatusError) as e:
                if isinstance(e, HTTPStatusError) and e.status_code != 429:
                    cache.set_status(name, False, f"{type(e).__name__}: {e}")
                    log.warning("%s failed: %s", name, e)
                    backoff = min(backoff + 1, 6)
                else:
                    # 被限流不算故障：按对方要求的时间（默认 30 分钟）暂停，期间页面继续使用已保存的数据
                    wait_override = e.wait if isinstance(e, RateLimited) else (e.retry_after or 1800)
                    cache.set_status(name, True, f"对方限流，{max(1, round(wait_override / 60))} 分钟后自动重试；期间使用已保存的数据")
            except RobotsDisallowed as e:
                cache.set_status(name, False, f"robots.txt 不允许抓取：{e}")
                backoff = min(backoff + 1, 6)
            except Exception as e:  # noqa: BLE001 —— 采集器必须常驻
                cache.set_status(name, False, f"{type(e).__name__}: {e}")
                log.warning("%s failed: %s", name, e)
                backoff = min(backoff + 1, 6)
            delay = self._interval(name) * (2 ** backoff if backoff else 1)  # 失败时指数退避
            if wait_override:
                delay = max(delay, wait_override)
            await self._sleep(name, min(delay, 7200) + random.uniform(0, 1.5))

    async def _run_stream(self, name: str) -> None:
        if not settings.get(f"sources.{name}.enabled"):
            cache.set_status(name, False, "已在后台关闭", disabled=True)
            return  # 设置变化时会被重新启动
        try:
            await self.streams[name]()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            cache.set_status(name, False, f"{type(e).__name__}: {e}")
