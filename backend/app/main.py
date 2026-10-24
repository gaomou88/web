"""Zyll财经：一个进程同时提供前台网页、后台（/zylladmin）、数据接口、实时推送（SSE），并在后台运行采集器。"""
from __future__ import annotations

import contextlib
import asyncio
import logging
import time

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, RedirectResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import api_app, api_market, holidays, lists
from . import api_admin, api_import, api_portfolio, api_public, auth, cache, security, settings, store, universe
from .collectors.finra import FinraCollector
from .collectors.runner import Manager
from .common import err, ok
from .config import get_settings
from .http import PoliteClient

from . import runlog  # noqa: E402

runlog.setup()
log = logging.getLogger("zyll")
cfg = get_settings()

# 不需要防 CSRF 请求头的写接口：浏览器 sendBeacon 无法带自定义头；支付回调来自第三方
CSRF_EXEMPT = ("/api/telemetry",)
TURNSTILE_SRC = "https://challenges.cloudflare.com"


def csp_for(path: str) -> str:
    strict_script = "'self'"
    frame = "'none'"
    if security.turnstile_active("turnstile.on_register") or security.turnstile_active("turnstile.on_login") \
            or security.turnstile_active("turnstile.on_admin_login"):
        strict_script += f" {TURNSTILE_SRC}"
        frame = TURNSTILE_SRC
    if not path.startswith("/zylladmin") and api_public.ads_active():
        # 广告代码需要加载第三方脚本、图片和框架，开启广告时放宽前台的限制（后台始终保持严格）
        return ("default-src 'self'; img-src * data:; style-src 'self' 'unsafe-inline'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' https:; connect-src 'self' https:; "
                "frame-src https:; frame-ancestors 'none'; base-uri 'none'")
    if path.startswith("/zylladmin"):
        frame = f"'self' {frame}" if frame != "'none'" else "'self'"  # 后台的邮件 HTML 预览
    return (f"default-src 'self'; img-src 'self' data:; style-src 'self'; script-src {strict_script}; "
            f"connect-src 'self'; frame-src {frame}; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


def same_origin(request: Request) -> bool:
    """防跨站请求伪造。优先使用浏览器自带的 Sec-Fetch-Site（不受反向代理影响）；
    老浏览器没有这个头时，退回检查自定义请求头 X-Requested-With（跨站请求无法在不预检的情况下携带）。"""
    site = request.headers.get("sec-fetch-site")
    if site:
        return site in ("same-origin", "none")
    return bool(request.headers.get("x-requested-with"))


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # App 接口（/api/app/v1，网关已去掉 Cookie、只认 Bearer Token）不存在跨站请求伪造问题
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and not request.scope.get("zyll_app") \
                and not path.startswith(CSRF_EXEMPT) and not same_origin(request):
            return err(403, "请求来源不正确，请刷新页面后重试")
        t0 = time.perf_counter()
        try:
            resp = await call_next(request)
        except Exception:
            logging.getLogger("http").exception("%s %s 处理出错", request.method, path)
            return err(500, "服务器内部错误，已记录到运行日志")
        took = time.perf_counter() - t0
        if resp.status_code >= 500:
            logging.getLogger("http").error("%s %s 返回 %s", request.method, path, resp.status_code)
        elif took > 3 and not path.startswith("/api/stream"):
            logging.getLogger("http").warning("%s %s 耗时 %.1f 秒", request.method, path, took)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        # 按路径判断（304 协商缓存响应没有 content-type，也要带上最新的 CSP）
        if path == "/api/admin/mail/preview.html":
            pass  # 邮件预览自带更严格的沙箱 CSP
        elif path in ("/", "/index.html", "/zylladmin", "/zylladmin/") or "text/html" in resp.headers.get("content-type", ""):
            resp.headers["Content-Security-Policy"] = csp_for(path)
        if request.url.scheme == "https":
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        if path.startswith("/zylladmin") or path.startswith("/api/admin"):
            resp.headers["X-Robots-Tag"] = "noindex, nofollow"
        if path.startswith(("/js/", "/css/", "/admin/")):
            # 每次向服务器确认是否有新版本（未变化时只返回 304，开销很小），避免反向代理/CDN 缓存旧脚本
            resp.headers["Cache-Control"] = "no-cache"
        elif path in ("/", "/index.html", "/zylladmin"):
            resp.headers["Cache-Control"] = "no-cache"
        return resp


async def admin_page(request: Request):
    if request.url.path != "/zylladmin":
        return RedirectResponse("/zylladmin", status_code=301)
    return FileResponse(cfg.frontend_dir / "admin.html")


async def healthz(request: Request):
    return ok({"ok": True, "clients": cache.client_count()})


@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    def on_loop_error(loop, context):
        logging.getLogger("asyncio").error("后台任务异常：%s", context.get("message"), exc_info=context.get("exception"))
    asyncio.get_running_loop().set_exception_handler(on_loop_error)
    log.info("Zyll财经 启动")
    await store.init()
    await settings.load()
    await holidays.load_from_db()
    await lists.merge_once()
    http = PoliteClient()
    finra = FinraCollector(http)
    api_public.state["finra"] = finra
    await universe.refresh()
    manager = Manager(http, finra)
    api_admin.state["manager"] = manager
    api_portfolio.state["market"] = manager.market
    api_market.state["market"] = manager.market
    manager.start()
    if not await auth.admin_installed():
        log.info("还没有管理员：访问 /zylladmin 进入安装向导。")
    yield
    log.info("正在停止")
    manager.stop()


routes = [
    *api_public.routes,
    *api_admin.routes,
    *api_portfolio.routes,
    *api_import.routes,
    *api_market.routes,
    *api_app.routes,
    Route("/zylladmin", admin_page),
    Route("/zylladmin/", admin_page),
    Route("/healthz", healthz),
    Mount("/", StaticFiles(directory=str(cfg.frontend_dir), html=True), name="web"),
]

web = Starlette(
    routes=routes,
    middleware=[Middleware(SecurityMiddleware), Middleware(GZipMiddleware, minimum_size=800)],
    lifespan=lifespan,
)
app = api_app.AppGateway(web)  # /api/app/v1 前缀的统一处理（开关、App Key、去 Cookie、路径映射）
