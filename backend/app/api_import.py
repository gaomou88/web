"""AI 导入券商结单的接口（网页与 App 共用，App 通过 /api/app/v1/portfolio/import/... 访问）。"""
from __future__ import annotations

import time

from starlette.requests import Request
from starlette.routing import Route

from . import ai_import, auth, settings, store, track
from .api_portfolio import _user_or_error, currencies, state
from .common import body_of, err, ok


async def import_config(request: Request):
    user, e = await _user_or_error(request)
    if e:
        return e
    cfg = await ai_import.config_for(user)
    moves = await store.query("SELECT grp, kind, trade_date, ccy, amount FROM cash_moves WHERE user_id = ?", (user["id"],))
    pools = {}
    for c in sorted({m["ccy"] for m in moves if m["ccy"] != "USD"}):
        pool = ai_import.fx_pool(moves, c)
        if pool:
            rate, _ = ai_import.cost_rate(pool, "9999-12-31")
            pools[c] = {"records": len(pool), "rate": round(rate, 6), "first": pool[0][0], "last": pool[-1][0]}
    pf = await store.query_one("SELECT base_currency FROM pf_settings WHERE user_id = ?", (user["id"],))
    cfg.update(fx_pools=pools, base=(pf or {}).get("base_currency") or settings.get("portfolio.default_currency"), currencies=currencies())
    return ok(cfg)


async def upload(request: Request):
    user, e = await _user_or_error(request)
    if e:
        return e
    if not ai_import.available():
        return err(404, "网站暂未开启 AI 导入")
    if ai_import.members_only() and not auth.is_member(user):
        return err(403, "members_only", notice="AI 导入仅对会员开放")
    if request.query_params.get("consent") != "1":
        return err(400, "请先阅读并同意把文件内容交给 AI 服务识别")
    limit = int(settings.get("ai.daily_limit") or 0)
    if limit and await ai_import.usage_today(user["id"]) >= limit:
        return err(429, f"今天的识别次数已用完（每天 {limit} 次），明天再试")
    glimit = int(settings.get("ai.global_daily_limit") or 0)
    if glimit and await ai_import.usage_today() >= glimit:
        return err(429, "今天全站的识别次数已用完，请明天再试")
    if ai_import.running_for(user["id"]) >= 3:
        return err(429, "同时最多识别 3 个文件，请等前面的完成")
    max_bytes = int(settings.get("ai.max_file_mb") or 10) * 1024 * 1024
    if int(request.headers.get("content-length") or 0) > max_bytes:
        return err(413, f"文件不能超过 {max_bytes // 1024 // 1024} MB")
    buf = bytearray()
    async for chunk in request.stream():
        buf += chunk
        if len(buf) > max_bytes:
            return err(413, f"文件不能超过 {max_bytes // 1024 // 1024} MB")
    if len(buf) < 20:
        return err(400, "文件是空的")
    data = bytes(buf)
    ftype = ai_import.sniff(data)
    if ftype in ("xls",):
        return err(400, "不支持旧版 .xls，请在 Excel 里“另存为 .xlsx”或 CSV 后再上传")
    if ftype in ("heic",):
        return err(400, "不支持 HEIC 照片，请在手机上截图或改存为 JPG 后再上传")
    if ftype in ("zip", "unknown"):
        return err(400, "不支持这种文件，请上传 PDF、Excel（.xlsx）、CSV 或截图")
    if ftype in ("png", "jpg", "webp") and not ai_import.vision_available():
        return err(400, "网站目前只支持文字版 PDF、Excel 或 CSV，暂不支持图片")
    name = (request.query_params.get("name") or "")[:80]
    jid = await ai_import.start(user["id"], data, ftype, state["market"].http if "market" in state else None, name)
    await track.log(request, "user", "ai_import", user_id=user["id"], email=user["email"], reason=f"{ftype} {len(data) // 1024}KB")
    return ok({"job": jid})


async def job_status(request: Request):
    user, e = await _user_or_error(request)
    if e:
        return e
    j = ai_import.JOBS.get(request.path_params["jid"])
    if not j or j["uid"] != user["id"]:
        return err(404, "任务不存在或已过期，请重新上传")
    return ok({"status": j["status"], "step": j["step"], "error": j["error"], "result": j["result"] if j["status"] == "done" else None,
               "elapsed": round(time.time() - j["created"])})


async def merge_jobs(request: Request):
    """多个文件分别识别完成后合并成一份预览（文件之间互相去重）。"""
    user, e = await _user_or_error(request)
    if e:
        return e
    body = await body_of(request)
    jids = body.get("jobs") if isinstance(body.get("jobs"), list) else []
    jids = [str(x)[:40] for x in jids][:10]
    if len(jids) < 2:
        return err(400, "至少需要两个文件")
    try:
        mid = await ai_import.merge_jobs(user["id"], jids, state["market"].http if "market" in state else None)
    except ai_import.UserError as ex:
        return err(400, str(ex))
    return ok({"job": mid, "result": ai_import.JOBS[mid]["result"]})


async def _plan(request: Request, commit: bool):
    user, e = await _user_or_error(request)
    if e:
        return e
    try:
        res = await ai_import.plan(user["id"], await body_of(request), commit=commit)
    except ai_import.PlanError as ex:
        return err(400, str(ex), errors=ex.rows)
    if commit:
        await track.log(request, "user", "import_commit", user_id=user["id"], email=user["email"],
                        reason=f"{res['summary']['trades']} 笔交易，{res['summary']['cash']} 笔资金，批次 {res['batch']}")
    return ok(res)


async def plan_import(request: Request):
    return await _plan(request, False)


async def commit_import(request: Request):
    return await _plan(request, True)


async def batches(request: Request):
    user, e = await _user_or_error(request)
    if e:
        return e
    rows = await store.query("SELECT id, created_at, source, trades, cash, undone, period_start, period_end, broker, skipped FROM import_batches"
                             " WHERE user_id = ? ORDER BY created_at DESC LIMIT 50", (user["id"],))
    return ok({"batches": rows})


async def undo_batch(request: Request):
    user, e = await _user_or_error(request)
    if e:
        return e
    try:
        await ai_import.undo(user["id"], request.path_params["bid"][:40])
    except ai_import.PlanError as ex:
        return err(400, str(ex))
    await track.log(request, "user", "import_undo", user_id=user["id"], email=user["email"], reason=request.path_params["bid"][:40])
    return ok({"ok": True})


async def fx_cost(request: Request):
    """用某货币换到的美元的平均成本（1 美元 = 多少该货币），供“用之前换好的美元”这类交易默认填写成交汇率。"""
    user, e = await _user_or_error(request)
    if e:
        return e
    ccy = request.query_params.get("ccy", "").upper()
    d = request.query_params.get("date") or "9999-12-31"
    moves = await store.query("SELECT grp, kind, trade_date, ccy, amount FROM cash_moves WHERE user_id = ?", (user["id"],))
    pool = ai_import.fx_pool(moves, ccy)
    rate, borrowed = ai_import.cost_rate(pool, d)
    return ok({"ccy": ccy, "rate": round(rate, 6) if rate else None, "records": len(pool), "borrowed": borrowed})


routes = [
    Route("/api/portfolio/import/config", import_config),
    Route("/api/portfolio/import/upload", upload, methods=["POST"]),
    Route("/api/portfolio/import/job/{jid}", job_status),
    Route("/api/portfolio/import/merge", merge_jobs, methods=["POST"]),
    Route("/api/portfolio/import/plan", plan_import, methods=["POST"]),
    Route("/api/portfolio/import/commit", commit_import, methods=["POST"]),
    Route("/api/portfolio/import/batches", batches),
    Route("/api/portfolio/import/batches/{bid}", undo_batch, methods=["DELETE"]),
    Route("/api/portfolio/fx-cost", fx_cost),
]
