"""运行日志：收集程序里所有日志和未处理的异常，后台“运行日志”页查看，排查问题时不用登录服务器。

- 内存里保留最近 3000 条（后台实时查看）；
- 同时写入 /data/logs/zyll.log，按 5 MB 轮转保留 5 个文件（容器重启后仍可下载）；
- 同一条消息 60 秒内重复出现只记一次并计数，避免刷屏。
"""
from __future__ import annotations

import collections
import logging
import logging.handlers
import time
import traceback
from typing import Any

from .config import get_settings

MAX = 3000
_buf: collections.deque[dict[str, Any]] = collections.deque(maxlen=MAX)
_seq = [0]
_recent: dict[tuple[str, str], dict[str, Any]] = {}
LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}


class BufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001
            msg = str(record.msg)
        if record.name.startswith("uvicorn.access"):
            return
        key = (record.name, msg[:300])
        now = time.time()
        prev = _recent.get(key)
        if prev and now - prev["ts"] < 60:
            prev["count"] += 1
            prev["last"] = now
            return
        _seq[0] += 1
        item = {
            "id": _seq[0], "ts": now, "last": now, "count": 1, "level": record.levelname, "logger": record.name,
            "message": msg[:4000],
            "trace": "".join(traceback.format_exception(*record.exc_info))[-6000:] if record.exc_info else "",
            "where": f"{record.module}:{record.lineno}",
        }
        _buf.append(item)
        _recent[key] = item
        if len(_recent) > 2000:
            for k in [k for k, v in _recent.items() if now - v["ts"] > 60]:
                _recent.pop(k, None)


def setup() -> None:
    root = logging.getLogger()
    if any(isinstance(h, BufferHandler) for h in root.handlers):
        return
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)
    root.addHandler(BufferHandler())
    try:
        d = get_settings().data_dir / "logs"
        d.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(d / "zyll.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
        fh.setFormatter(fmt)
        fh.setLevel(logging.INFO)
        root.addHandler(fh)
    except OSError:
        pass
    # uvicorn 的错误日志也汇总进来
    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.propagate = True
    logging.getLogger("zyll").info("运行日志已启动")


def query(level: str = "INFO", q: str = "", since_id: int = 0, limit: int = 500) -> list[dict[str, Any]]:
    lv = LEVELS.get(level.upper(), 20)
    ql = q.lower()
    out = []
    for item in reversed(_buf):
        if item["id"] <= since_id:
            break
        if LEVELS.get(item["level"], 20) < lv:
            continue
        if ql and ql not in item["message"].lower() and ql not in item["logger"].lower() and ql not in item["trace"].lower():
            continue
        out.append(item)
        if len(out) >= limit:
            break
    return out


def counts(window: int = 86400) -> dict[str, int]:
    now = time.time()
    c = {"WARNING": 0, "ERROR": 0}
    for item in _buf:
        if now - item["last"] <= window and item["level"] in ("WARNING", "ERROR", "CRITICAL"):
            c["ERROR" if item["level"] == "CRITICAL" else item["level"]] += item["count"]
    return c


def log_file_path():
    return get_settings().data_dir / "logs" / "zyll.log"
