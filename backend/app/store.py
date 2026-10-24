"""SQLite 存储（Python 自带，无需单独的数据库服务）。

所有数据库操作在一个专用线程里串行执行，异步代码通过 run() 调用，不会阻塞网页响应。
"""
from __future__ import annotations

import asyncio
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, TypeVar

from .config import get_settings

T = TypeVar("T")

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    totp_secret TEXT NOT NULL,
    token_version INTEGER NOT NULL DEFAULT 0,
    last_totp_step INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    last_login_at INTEGER
);
CREATE TABLE IF NOT EXISTS site_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    email_verified INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    member_level INTEGER NOT NULL DEFAULT 0,
    member_expires INTEGER,
    token_version INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    last_login_at INTEGER
);
CREATE TABLE IF NOT EXISTS email_tokens (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    purpose TEXT NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    kind TEXT NOT NULL,
    path TEXT NOT NULL DEFAULT '',
    message TEXT NOT NULL DEFAULT '',
    value REAL,
    ua TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_tel_ts ON telemetry(ts);
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    provider TEXT NOT NULL,
    plan TEXT NOT NULL,
    amount REAL NOT NULL,
    currency TEXT NOT NULL,
    status TEXT NOT NULL,
    external_id TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS pf_settings (
    user_id INTEGER PRIMARY KEY,
    base_currency TEXT NOT NULL DEFAULT 'CNY',
    fx_mode TEXT NOT NULL DEFAULT 'mid'
);
CREATE TABLE IF NOT EXISTS pf_symbols (
    user_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    target REAL,
    stop REAL,
    sort INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (user_id, symbol)
);
CREATE TABLE IF NOT EXISTS pf_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    shares REAL NOT NULL,
    price REAL NOT NULL,
    fx REAL NOT NULL,
    fee REAL NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_pf_trades_user ON pf_trades(user_id, symbol);
CREATE TABLE IF NOT EXISTS fx_history (
    ts INTEGER NOT NULL,
    ccy TEXT NOT NULL,
    bid REAL NOT NULL,
    ask REAL NOT NULL,
    PRIMARY KEY (ts, ccy)
);
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS us_symbols (
    symbol TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    exchange TEXT NOT NULL DEFAULT '',
    etf INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS holidays (
    date TEXT NOT NULL,
    region TEXT NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,               -- public / closed / early / workday
    name_zh TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (date, region, name)
);
CREATE TABLE IF NOT EXISTS user_quotes (
    user_id INTEGER NOT NULL,
    kind TEXT NOT NULL,               -- index / stock
    code TEXT NOT NULL,
    sort INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, kind, code)
);
CREATE TABLE IF NOT EXISTS cash_moves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    grp TEXT NOT NULL,                -- 同一笔操作（换汇有两条：卖出 / 买入）
    kind TEXT NOT NULL,               -- deposit 入金 / withdraw 出金 / fx 换汇
    trade_date TEXT NOT NULL,
    ccy TEXT NOT NULL,
    amount REAL NOT NULL,             -- 有正负：流入为正，流出为负
    note TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_cash_user ON cash_moves(user_id, trade_date);
CREATE TABLE IF NOT EXISTS app_codes (          -- App 网页登录的一次性授权码（PKCE）
    code_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    user_ver INTEGER NOT NULL,
    challenge TEXT NOT NULL,
    device_name TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    used INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS ai_jobs (            -- AI 导入的调用记录（不保存文件和识别内容，只用于限额和统计）
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    file_type TEXT NOT NULL DEFAULT '',
    size INTEGER NOT NULL DEFAULT 0,
    pages INTEGER NOT NULL DEFAULT 0,
    mode TEXT NOT NULL DEFAULT '',             -- text / vision
    status TEXT NOT NULL DEFAULT 'running',    -- running / ok / failed
    tokens_in INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    rows INTEGER NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT '',
    ms INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_ai_jobs_user ON ai_jobs(user_id, created_at);
CREATE TABLE IF NOT EXISTS import_batches (     -- 每次导入一批，可整批撤销
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    trades INTEGER NOT NULL DEFAULT 0,
    cash INTEGER NOT NULL DEFAULT 0,
    undone INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS px_daily (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    close REAL NOT NULL,
    PRIMARY KEY (symbol, date)
);
CREATE TABLE IF NOT EXISTS fx_daily (
    date TEXT NOT NULL,
    ccy TEXT NOT NULL,
    usd_rate REAL NOT NULL,           -- 1 美元 = 多少该货币（美东收盘）
    src TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (date, ccy)
);
CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    code_norm TEXT NOT NULL UNIQUE,
    days INTEGER NOT NULL,            -- 0 = 永久
    batch TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'unused',   -- unused / used / disabled
    valid_until INTEGER,              -- 兑换截止时间（为空则不限）
    created_at INTEGER NOT NULL,
    used_at INTEGER,
    used_by INTEGER,
    used_email TEXT
);
CREATE INDEX IF NOT EXISTS ix_cards_batch ON cards(batch, status);
CREATE TABLE IF NOT EXISTS member_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    ts INTEGER NOT NULL,
    source TEXT NOT NULL,             -- web / app / admin:xxx
    card_id INTEGER,
    days INTEGER,
    old_expires INTEGER,
    new_expires INTEGER
);
CREATE INDEX IF NOT EXISTS ix_member_log_user ON member_log(user_id, ts);
CREATE TABLE IF NOT EXISTS app_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    user_ver INTEGER NOT NULL,
    device_id TEXT NOT NULL DEFAULT '',
    device_name TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL DEFAULT '',
    app_version TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    last_used_at INTEGER NOT NULL,
    last_ip TEXT NOT NULL DEFAULT '',
    expires_at INTEGER NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_app_tokens_user ON app_tokens(user_id);
CREATE TABLE IF NOT EXISTS login_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    realm TEXT NOT NULL,              -- user / admin
    user_id INTEGER,
    email TEXT NOT NULL DEFAULT '',
    event TEXT NOT NULL,              -- login_ok / login_fail / register / logout / password / delete ...
    reason TEXT NOT NULL DEFAULT '',
    ip TEXT NOT NULL DEFAULT '',
    ip_chain TEXT NOT NULL DEFAULT '',
    country TEXT NOT NULL DEFAULT '',
    ua TEXT NOT NULL DEFAULT '',
    device_hash TEXT NOT NULL DEFAULT '',
    risk TEXT NOT NULL DEFAULT '',
    data TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_login_ts ON login_events(ts);
CREATE INDEX IF NOT EXISTS ix_login_user ON login_events(realm, user_id, ts);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    token_version INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS econ_events (
    id TEXT PRIMARY KEY,
    ts INTEGER NOT NULL,
    currency TEXT NOT NULL,
    region TEXT NOT NULL,
    title TEXT NOT NULL,
    impact INTEGER NOT NULL,
    forecast TEXT NOT NULL DEFAULT '',
    previous TEXT NOT NULL DEFAULT '',
    actual TEXT NOT NULL DEFAULT '',
    revision TEXT NOT NULL DEFAULT '',
    surprise INTEGER NOT NULL DEFAULT 0,
    is_org INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_events_ts ON econ_events(ts);
CREATE TABLE IF NOT EXISTS cpi_index (          -- 通胀：各地区月度物价指数 / 同比
    region TEXT NOT NULL,                       -- 货币代码：USD / CNY / EUR …
    month TEXT NOT NULL,                        -- YYYY-MM
    idx REAL,                                   -- 指数（如美国 CPI-U），没有则为空
    yoy REAL,                                   -- 同比 %，没有则为空
    src TEXT NOT NULL DEFAULT '',               -- fred / calendar / worldbank / admin
    updated_at INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (region, month, src)
);
CREATE TABLE IF NOT EXISTS finra_short_volume (
    trade_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    short_volume REAL NOT NULL,
    short_exempt REAL NOT NULL,
    total_volume REAL NOT NULL,
    markets TEXT NOT NULL,
    PRIMARY KEY (trade_date, symbol)
);
CREATE INDEX IF NOT EXISTS ix_sv_symbol ON finra_short_volume(symbol, trade_date);
CREATE TABLE IF NOT EXISTS finra_ats_weekly (
    week_start TEXT NOT NULL,
    symbol TEXT NOT NULL,
    mpid TEXT NOT NULL,
    firm TEXT NOT NULL,
    tier TEXT NOT NULL,
    trades INTEGER NOT NULL,
    shares REAL NOT NULL,
    PRIMARY KEY (week_start, symbol, mpid)
);
CREATE TABLE IF NOT EXISTS dark_prints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    symbol TEXT NOT NULL,
    price REAL NOT NULL,
    size REAL NOT NULL,
    notional REAL NOT NULL,
    venue TEXT NOT NULL DEFAULT '',
    conditions TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_prints_ts ON dark_prints(ts);
CREATE TABLE IF NOT EXISTS cftc_tff (
    report_date TEXT NOT NULL,
    code TEXT NOT NULL,
    market TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (report_date, code)
);
"""

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sqlite")
_local = threading.local()


def _conn() -> sqlite3.Connection:
    c = getattr(_local, "conn", None)
    if c is None:
        c = sqlite3.connect(get_settings().db_path, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.execute("PRAGMA foreign_keys=ON")
        _local.conn = c
    return c


def _call(fn: Callable[[sqlite3.Connection], T]) -> T:
    c = _conn()
    try:
        result = fn(c)
        c.commit()
        return result
    except Exception:
        c.rollback()
        raise


async def run(fn: Callable[[sqlite3.Connection], T]) -> T:
    return await asyncio.get_running_loop().run_in_executor(_executor, _call, fn)


async def query(sql: str, params: tuple | dict = ()) -> list[dict[str, Any]]:
    return await run(lambda c: [dict(r) for r in c.execute(sql, params).fetchall()])


async def query_one(sql: str, params: tuple | dict = ()) -> dict[str, Any] | None:
    rows = await query(sql, params)
    return rows[0] if rows else None


async def execute(sql: str, params: tuple | dict = ()) -> int:
    return await run(lambda c: c.execute(sql, params).rowcount)


async def executemany(sql: str, rows: list[tuple] | list[dict]) -> None:
    if rows:
        await run(lambda c: c.executemany(sql, rows))


MIGRATIONS = [
    # (表, 列, 定义)
    ("telemetry", "data", "TEXT NOT NULL DEFAULT '{}'"),
    ("telemetry", "sid", "TEXT NOT NULL DEFAULT ''"),
    ("telemetry", "ip", "TEXT NOT NULL DEFAULT ''"),
    ("pf_trades", "ccy", "TEXT"),
    # funding：ccy = 这笔交易按成交汇率当场换汇（从该货币现金扣）；usd = 用之前换好的美元（从美元现金扣，汇率只作成本汇率）
    ("pf_trades", "funding", "TEXT NOT NULL DEFAULT 'ccy'"),
    ("pf_trades", "batch", "TEXT NOT NULL DEFAULT ''"),
    ("cash_moves", "batch", "TEXT NOT NULL DEFAULT ''"),
    # 导入去重：券商的订单号 / 成交编号（脱敏后的代号）和成交时间
    ("pf_trades", "ext_id", "TEXT NOT NULL DEFAULT ''"),
    ("pf_trades", "ext_time", "TEXT NOT NULL DEFAULT ''"),
    ("import_batches", "period_start", "TEXT NOT NULL DEFAULT ''"),
    ("import_batches", "period_end", "TEXT NOT NULL DEFAULT ''"),
    ("import_batches", "broker", "TEXT NOT NULL DEFAULT ''"),
    ("import_batches", "job", "TEXT NOT NULL DEFAULT ''"),
    ("import_batches", "skipped", "INTEGER NOT NULL DEFAULT 0"),
    # 财经日历日程库：source = official（内置官方日程）/ ff（Forex Factory）/ admin（后台手动）
    ("econ_events", "source", "TEXT NOT NULL DEFAULT 'ff'"),
    ("econ_events", "locked", "INTEGER NOT NULL DEFAULT 0"),      # 1 = 时间已锁定，抓取只更新数值
    ("econ_events", "hidden", "INTEGER NOT NULL DEFAULT 0"),      # 1 = 后台删除（保留记录，防止下次抓取又加回来）
    ("econ_events", "pending_ts", "INTEGER NOT NULL DEFAULT 0"),  # 抓到的时间与锁定时间不同：待管理员确认
    ("econ_events", "updated_at", "INTEGER NOT NULL DEFAULT 0"),
    # 盈亏显示：是否扣除通胀、是否计入汇率
    ("pf_settings", "inflation", "INTEGER NOT NULL DEFAULT 0"),
    ("pf_settings", "include_fx", "INTEGER NOT NULL DEFAULT 1"),
]


def _migrate(c: sqlite3.Connection) -> None:
    c.executescript(SCHEMA)
    for table, col, ddl in MIGRATIONS:
        cols = {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
        if col not in cols:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
    # 旧交易记录没有货币对：按用户当时的本币补上
    c.execute("""UPDATE pf_trades SET ccy = COALESCE(
                   (SELECT base_currency FROM pf_settings s WHERE s.user_id = pf_trades.user_id),
                   (SELECT json_extract(value, '$') FROM settings WHERE key = 'portfolio.default_currency'),
                   'CNY') WHERE ccy IS NULL""")


async def init() -> None:
    await run(_migrate)


async def kv_get(key: str) -> tuple[str, int] | None:
    row = await query_one("SELECT value, updated FROM kv WHERE key = ?", (key,))
    return (row["value"], row["updated"]) if row else None


async def kv_set(key: str, value: str) -> None:
    import time
    await execute("INSERT INTO kv VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated = excluded.updated",
                  (key, value, int(time.time())))
