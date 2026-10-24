"""进程内热数据缓存 + 实时推送中心 + 数据源状态。

热数据以预先序列化好的 JSON 字节保存，接口直接原样返回，速度极快。
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

_store: dict[str, bytes] = {}
_expire: dict[str, float] = {}
_status: dict[str, dict[str, Any]] = {}
_subscribers: set[asyncio.Queue[str]] = set()


def dumps(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str).encode()


def put(key: str, obj: Any, *, topic: str | None = None, push: Any = None, ttl: int | None = None) -> None:
    """写缓存；给了 topic 就通知所有在线浏览器。push 是随通知下发的小数据（为空则浏览器自行拉取）。"""
    _store[key] = dumps(obj)
    if ttl:
        _expire[key] = time.time() + ttl
    else:
        _expire.pop(key, None)
    if topic:
        publish(topic, push)


def get_raw(key: str) -> bytes | None:
    exp = _expire.get(key)
    if exp and exp < time.time():
        _store.pop(key, None)
        _expire.pop(key, None)
        return None
    return _store.get(key)


def get(key: str, default: Any = None) -> Any:
    raw = get_raw(key)
    return json.loads(raw) if raw else default


# ---------- 推送 ----------
_last_client_left = [time.time()]
_client_waiters: list[asyncio.Event] = []


_first_client_hooks: list = []


def on_first_client(fn) -> None:
    """有访客从“无人在线”变为“有人在线”时调用（用于唤醒降频的数据源）。"""
    _first_client_hooks.append(fn)


def subscribe() -> asyncio.Queue[str]:
    q: asyncio.Queue[str] = asyncio.Queue(maxsize=300)
    was_idle = not _subscribers
    _subscribers.add(q)
    if was_idle:
        for fn in _first_client_hooks:
            fn()
    for ev in _client_waiters:
        ev.set()
    return q


def unsubscribe(q: asyncio.Queue[str]) -> None:
    _subscribers.discard(q)
    if not _subscribers:
        _last_client_left[0] = time.time()


def idle_seconds() -> float:
    """没有任何浏览器在线的时长（秒）；有人在线时为 0。"""
    return 0.0 if _subscribers else time.time() - _last_client_left[0]


async def wait_for_client() -> None:
    if _subscribers:
        return
    ev = asyncio.Event()
    _client_waiters.append(ev)
    try:
        await ev.wait()
    finally:
        _client_waiters.remove(ev)


def publish(topic: str, data: Any = None) -> None:
    msg = json.dumps({"topic": topic, "data": data}, ensure_ascii=False, separators=(",", ":"), default=str)
    for q in list(_subscribers):
        if q.full():  # 慢客户端丢弃最旧的消息，不拖累别人
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                pass
        q.put_nowait(msg)


def client_count() -> int:
    return len(_subscribers)


# ---------- 数据源状态 ----------
def set_status(source: str, ok: bool, message: str = "", *, disabled: bool = False) -> None:
    now = time.time()
    rec = {**_status.get(source, {}), "ok": ok, "message": message[:300], "checked_at": now, "disabled": disabled}
    if ok:
        rec["last_success"] = now
    _status[source] = rec


def all_status() -> dict[str, Any]:
    return dict(_status)
