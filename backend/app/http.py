"""采集用 HTTP 客户端（只用 Python 自带库）。

按后台设置决定是否检查 robots.txt；无论是否检查，都按域名限速并如实标明爬虫身份。
"""
from __future__ import annotations

import asyncio
import gzip
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from typing import Any
from urllib.robotparser import RobotFileParser

from . import settings

ROBOTS_TTL = 6 * 3600


class RobotsDisallowed(Exception):
    pass


class HTTPStatusError(Exception):
    def __init__(self, status_code: int, url: str, headers: dict[str, str] | None = None, body: bytes = b"") -> None:
        snippet = body[:300].decode("utf-8", errors="replace").strip() if body else ""
        super().__init__(f"HTTP {status_code}: {url}" + (f" —— {snippet}" if snippet else ""))
        self.status_code = status_code
        self.headers = headers or {}
        self.body = body

    @property
    def retry_after(self) -> float | None:
        """服务器要求的等待秒数（Retry-After 头），没有则为 None。"""
        v = self.headers.get("retry-after", "")
        try:
            return max(float(v), 1.0)
        except ValueError:
            return None


class RateLimited(Exception):
    """被对方限流：采集器按 wait 秒后重试，不计为故障。"""

    def __init__(self, wait: float, msg: str = "") -> None:
        super().__init__(msg or f"被对方限流，{int(wait // 60) or 1} 分钟后重试")
        self.wait = wait


class Response:
    def __init__(self, status: int, body: bytes, headers: dict[str, str]) -> None:
        self.status_code = status
        self.content = body
        self.headers = headers

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.content) if self.content else None


def _blocking_request(method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: float) -> Response:
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw, status = r.read(), r.status
            hdrs = {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        raw = e.read() if e.fp else b""
        status = e.code
        hdrs = {k.lower(): v for k, v in (e.headers or {}).items()}
    enc = hdrs.get("content-encoding", "")
    if enc == "gzip":
        raw = gzip.decompress(raw)
    elif enc == "deflate":
        raw = zlib.decompress(raw)
    return Response(status, raw, hdrs)


def user_agent() -> str:
    token = settings.get("crawler.bot_token") or "ZyllBot"
    contact = settings.get("crawler.bot_contact")
    return f"{token}/1.0" + (f" (+{contact})" if contact else "")


class PoliteClient:
    def __init__(self) -> None:
        self._robots: dict[str, tuple[float, RobotFileParser | None, bool]] = {}
        self._robots_lock: dict[str, asyncio.Lock] = {}
        self._host_lock: dict[str, asyncio.Lock] = {}
        self._last_hit: dict[str, float] = {}

    async def _raw(self, method: str, url: str, headers: dict[str, str] | None = None, body: bytes | None = None, timeout: float = 25) -> Response:
        h = {"User-Agent": user_agent(), "Accept-Encoding": "gzip, deflate", **(headers or {})}
        return await asyncio.to_thread(_blocking_request, method, url, h, body, timeout)

    async def allowed(self, url: str) -> bool:
        if not settings.get("crawler.respect_robots"):
            return True
        parts = urllib.parse.urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        lock = self._robots_lock.setdefault(origin, asyncio.Lock())
        async with lock:
            entry = self._robots.get(origin)
            if entry is None or time.time() - entry[0] > ROBOTS_TTL:
                try:
                    r = await self._raw("GET", origin + "/robots.txt", timeout=15)
                    if r.status_code == 200:
                        rp = RobotFileParser()
                        rp.parse(r.text.splitlines())
                        entry = (time.time(), rp, False)
                    elif 400 <= r.status_code < 500:
                        entry = (time.time(), None, True)
                    else:
                        entry = (time.time(), None, False)
                except Exception:  # noqa: BLE001 —— 连不上时 5 分钟后重试
                    entry = (time.time() - ROBOTS_TTL + 300, None, False)
                self._robots[origin] = entry
        _, parser, allow_all = entry
        if allow_all:
            return True
        if parser is None:
            return False
        return parser.can_fetch(settings.get("crawler.bot_token") or "ZyllBot", url)

    async def get(self, url: str, *, params: dict[str, str] | None = None, **kw: Any) -> Response:
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        return await self.request("GET", url, **kw)

    async def request(self, method: str, url: str, *, json_body: Any = None, headers: dict[str, str] | None = None,
                      min_interval: float = 1.0, timeout: float = 25) -> Response:
        if not await self.allowed(url):
            raise RobotsDisallowed(url)
        host = urllib.parse.urlsplit(url).netloc
        lock = self._host_lock.setdefault(host, asyncio.Lock())
        async with lock:
            wait = self._last_hit.get(host, 0) + min_interval - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_hit[host] = time.monotonic()
        body = None
        h = dict(headers or {})
        if json_body is not None:
            body = json.dumps(json_body).encode()
            h.setdefault("Content-Type", "application/json")
        r = await self._raw(method, url, h, body, timeout)
        if r.status_code >= 400:
            raise HTTPStatusError(r.status_code, url, r.headers, r.content)
        return r
