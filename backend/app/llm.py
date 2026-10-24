"""调用大模型（OpenAI 兼容的 /chat/completions），带服务商预设和“自适应参数”。

为什么要自适应：各家接口虽然都叫“兼容 OpenAI”，但细节不同，而且模型升级后规则会变，例如
- 千问 3.5 以后的模型默认开启思考，非流式调用或 JSON 模式时要传 enable_thinking=false，否则 400；
  个别模型只能思考（“restricted to True”），这时就不能用 JSON 模式；
- DeepSeek、智谱、豆包、Kimi 用 thinking: {"type": "disabled"} 关闭思考；
- Kimi 关闭思考时温度固定 0.6，传别的值会报错；智谱不接受 temperature=0；
- 各模型 max_tokens 上限不同，超出会报 “Range of max_tokens should be [1, N]”；
- 有的接口图片只认 data URL，有的（智谱）认纯 base64。

做法：按服务商预设先组好参数（默认流式输出，避免长输出超时）；遇到 400 时读出错误原文，
有针对性地去掉 / 改掉对应参数再试，并记住这个模型的规则（存数据库，重启后仍然有效）。
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import re
import urllib.error
import urllib.request
from typing import Any

from . import settings, store

log = logging.getLogger("llm")

# 服务商预设（2026-10 按各家官方文档整理；模型名可以在后台改成任何该服务商支持的模型）
PROVIDERS: dict[str, dict[str, Any]] = {
    "deepseek": {
        "name": "DeepSeek（深度求索）", "base": "https://api.deepseek.com",
        "text": ["deepseek-flash", "deepseek-v4-pro"], "vision": [],
        "thinking_off": {"thinking": {"type": "disabled"}}, "temperature": 0.0,
        "note": "deepseek-chat / deepseek-reasoner 已于 2026-07-24 停用，请用 deepseek-flash（便宜）或 deepseek-v4-pro。官方接口不支持图片。",
    },
    "qwen": {
        "name": "通义千问（阿里云百炼·北京）", "base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "text": ["qwen3.7-plus", "qwen3.8-flash", "qwen3.8-max", "qwen-plus", "qwen-flash"],
        "vision": ["qwen3.7-plus", "qwen3.8-max", "qwen3-vl-plus", "qwen3-vl-flash"],
        "thinking_off": {"enable_thinking": False}, "temperature": 0.1,
        "note": "qwen3.7-plus、qwen3.8-max 文字和图片都能处理，可以选“一个多模态模型”。也可以填业务空间专属地址 https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1。",
    },
    "qwen_intl": {
        "name": "通义千问（阿里云百炼·新加坡国际站）", "base": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "text": ["qwen3.7-plus", "qwen3.8-flash", "qwen3.8-max", "qwen-plus", "qwen-flash"],
        "vision": ["qwen3.7-plus", "qwen3.8-max", "qwen3-vl-plus", "qwen3-vl-flash"],
        "thinking_off": {"enable_thinking": False}, "temperature": 0.1,
        "note": "国际站的 API Key 只能调用国际站地址，和北京的 Key 不通用。",
    },
    "zhipu": {
        "name": "智谱 GLM", "base": "https://open.bigmodel.cn/api/paas/v4",
        "text": ["glm-4.7-flash", "glm-5.1", "glm-5.3"], "vision": ["glm-4.6v", "glm-4.6v-flash", "glm-5v-turbo"],
        "thinking_off": {"thinking": {"type": "disabled"}}, "temperature": 0.1, "image_raw": True,
        "note": "glm-4.7-flash、glm-4.6v-flash 免费。",
    },
    "doubao": {
        "name": "豆包（火山方舟）", "base": "https://ark.cn-beijing.volces.com/api/v3",
        "text": ["doubao-seed-2-1-pro-260915"], "vision": ["doubao-seed-2-1-pro-260915"],
        "thinking_off": {"thinking": {"type": "disabled"}}, "temperature": 0.1,
        "note": "模型名也可以填方舟控制台里的推理接入点 ID（ep-…）。",
    },
    "kimi": {
        "name": "Kimi（月之暗面）", "base": "https://api.moonshot.cn/v1",
        "text": ["kimi-k2.6"], "vision": ["kimi-k2.6"],
        "thinking_off": {"thinking": {"type": "disabled"}}, "temperature": None,
        "note": "kimi-k2.6 文字和图片都能处理。海外账号请把地址改成 https://api.moonshot.ai/v1。",
    },
    "custom": {
        "name": "其他（兼容 OpenAI 接口）", "base": "", "text": [], "vision": [],
        "thinking_off": {}, "temperature": 0.1,
        "note": "填写服务商提供的 OpenAI 兼容地址（到 /v1 这一级，不含 /chat/completions）。",
    },
}

_LEARN: dict[str, dict[str, Any]] = {}  # 每个（地址, 模型）学到的参数规则


class AIError(Exception):
    pass


def provider_options() -> list[list[str]]:
    return [[k, v["name"]] for k, v in PROVIDERS.items()]


def resolve(kind: str) -> dict[str, Any]:
    """kind = text / vision。“一个多模态模型”模式下图片也用文字模型的配置。"""
    if kind == "vision" and settings.get("ai.mode") == "single":
        kind = "text"
    prov = settings.get(f"ai.{kind}_provider") or "custom"
    p = PROVIDERS.get(prov, PROVIDERS["custom"])
    base = (settings.get(f"ai.{kind}_base_url") or "").strip().rstrip("/") or p["base"]
    base = re.sub(r"/chat/completions/?$", "", base)
    return {"kind": kind, "provider": prov, "base": base, "key": settings.get(f"ai.{kind}_api_key") or "",
            "model": (settings.get(f"ai.{kind}_model") or "").strip(), "preset": p}


def configured(kind: str) -> bool:
    c = resolve(kind)
    return bool(c["base"] and c["key"] and c["model"])


def _learn_key(c: dict[str, Any]) -> str:
    return hashlib.sha1(f"{c['base']}|{c['model']}".encode()).hexdigest()[:16]


async def _learned(c: dict[str, Any]) -> dict[str, Any]:
    k = _learn_key(c)
    if k not in _LEARN:
        row = await store.kv_get(f"llm_learn:{k}")
        try:
            _LEARN[k] = json.loads(row[0]) if row else {}
        except ValueError:
            _LEARN[k] = {}
    return _LEARN[k]


async def _remember(c: dict[str, Any], rules: dict[str, Any]) -> None:
    k = _learn_key(c)
    _LEARN[k] = rules
    await store.kv_set(f"llm_learn:{k}", json.dumps(rules))


async def forget_all() -> None:
    """后台修改了模型配置后清空已学到的规则。"""
    _LEARN.clear()
    await store.execute("DELETE FROM kv WHERE key LIKE 'llm_learn:%'")


def build_payload(c: dict[str, Any], rules: dict[str, Any], messages: list[dict[str, Any]], json_mode: bool, max_tokens: int) -> dict[str, Any]:
    p = c["preset"]
    msgs = copy.deepcopy(messages)
    raw = rules.get("image_raw", p.get("image_raw", False))
    for m in msgs:
        if isinstance(m.get("content"), list):
            for part in m["content"]:
                if part.get("type") == "image_url":
                    url = part["image_url"]["url"]
                    if raw and url.startswith("data:"):
                        part["image_url"]["url"] = url.split(",", 1)[1]
    body: dict[str, Any] = {"model": c["model"], "messages": msgs}
    if not rules.get("no_stream"):
        body["stream"] = True
        if not rules.get("no_stream_options"):
            body["stream_options"] = {"include_usage": True}
    limit = rules.get("max_tokens")
    if not rules.get("no_max_tokens"):
        body["max_tokens"] = min(max_tokens, limit) if limit else max_tokens
    temp = p.get("temperature")
    if temp is not None and not rules.get("no_temperature"):
        body["temperature"] = temp
    if not rules.get("thinking_forced") and not rules.get("no_thinking_param"):
        body.update(copy.deepcopy(p.get("thinking_off") or {}))
    if json_mode and not rules.get("no_json") and not rules.get("thinking_forced"):
        body["response_format"] = {"type": "json_object"}
    return body


def adjust(rules: dict[str, Any], msg: str, has_images: bool, json_mode: bool, image_raw: bool = False) -> dict[str, Any] | None:
    """根据 400 错误原文调整参数；返回新的规则，无法判断时返回 None。"""
    m = msg.lower()
    r = dict(rules)
    if ("enable_thinking" in m or "thinking" in m) and ("restricted to true" in m or "must be enabled" in m or "only support" in m and "thinking" in m):
        if r.get("thinking_forced"):
            return None
        r.update(thinking_forced=True, no_json=True)
        return r
    if "json" in m and ("response_format" in m or "json mode" in m or "json_object" in m) and json_mode and not r.get("no_json"):
        r["no_json"] = True
        return r
    mt = re.search(r"max_(?:completion_)?tokens[^\d\[]*\[\s*1\s*,\s*(\d+)\s*\]", m) or re.search(r"max_(?:completion_)?tokens.*?(?:<=|less than|at most|maximum(?: value)? (?:is|of))\s*(\d+)", m)
    if mt:
        n = int(mt.group(1))
        if n and n != r.get("max_tokens"):
            r["max_tokens"] = n
            return r
    if "max_tokens" in m and not r.get("no_max_tokens"):
        r["no_max_tokens"] = True
        return r
    if "temperature" in m and not r.get("no_temperature"):
        r["no_temperature"] = True
        return r
    if "stream_options" in m and not r.get("no_stream_options"):
        r["no_stream_options"] = True
        return r
    if "stream" in m and not r.get("no_stream"):
        r["no_stream"] = True
        return r
    if ("enable_thinking" in m or "thinking" in m) and not r.get("no_thinking_param"):
        r["no_thinking_param"] = True
        return r
    if has_images and any(w in m for w in ("image", "url", "base64", "data uri", "data-uri", "content")) and not r.get("image_tried"):
        r["image_tried"] = True
        r["image_raw"] = not r.get("image_raw", image_raw)
        return r
    if not r.get("minimal"):  # 看不懂的错误：只保留最基本的参数再试一次
        r.update(minimal=True, no_temperature=True, no_thinking_param=True, no_stream_options=True, no_json=r.get("no_json") or False)
        return r
    return None


def _read_stream(resp: Any) -> tuple[str, dict[str, int], str]:
    content, finish, usage = [], "", {"in": 0, "out": 0}
    for raw in resp:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            obj = json.loads(data)
        except ValueError:
            continue
        if obj.get("error"):
            raise AIError(f"HTTP 400 流式输出中返回错误：{json.dumps(obj['error'], ensure_ascii=False)[:300]}")
        for ch in obj.get("choices") or []:
            delta = ch.get("delta") or ch.get("message") or {}
            c = delta.get("content")
            if isinstance(c, list):
                c = "".join(x.get("text", "") for x in c if isinstance(x, dict))
            if c:
                content.append(c)
            if ch.get("finish_reason"):
                finish = ch["finish_reason"]
        u = obj.get("usage")
        if u:
            usage = {"in": int(u.get("prompt_tokens") or 0), "out": int(u.get("completion_tokens") or 0)}
    return "".join(content), usage, finish


def _post(url: str, key: str, payload: dict[str, Any], timeout: float) -> tuple[str, dict[str, int], str]:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}",
                                          "Accept": "text/event-stream, application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if "text/event-stream" in (r.headers.get("Content-Type") or ""):
                return _read_stream(r)
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read()[:600].decode("utf-8", errors="replace")
        hint = {401: "API Key 不正确或与地址不匹配", 402: "账户余额不足", 403: "没有权限使用该模型", 404: "接口地址或模型名称不正确",
                413: "内容太大", 429: "请求太频繁或额度用完"}.get(e.code, "")
        raise AIError(f"HTTP {e.code} {hint}：{body}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise AIError(f"连接失败：{getattr(e, 'reason', e)}") from e
    except ValueError as e:
        raise AIError("AI 接口返回的不是 JSON") from e
    if data.get("error"):
        raise AIError(f"HTTP 400 {json.dumps(data['error'], ensure_ascii=False)[:300]}")
    ch = (data.get("choices") or [{}])[0]
    c = (ch.get("message") or {}).get("content") or ""
    if isinstance(c, list):
        c = "".join(p.get("text", "") for p in c if isinstance(p, dict))
    u = data.get("usage") or {}
    return c, {"in": int(u.get("prompt_tokens") or 0), "out": int(u.get("completion_tokens") or 0)}, ch.get("finish_reason") or ""


async def chat(kind: str, messages: list[dict[str, Any]], json_mode: bool, max_tokens: int = 8000, timeout: float = 180) -> tuple[str, dict[str, int], str]:
    c = resolve(kind)
    if not (c["base"] and c["key"] and c["model"]):
        raise AIError("请先在后台填写接口地址、API Key 和模型")
    rules = await _learned(c)
    has_images = any(isinstance(m.get("content"), list) and any(p.get("type") == "image_url" for p in m["content"]) for m in messages)
    changed = False
    transient = 0
    for _ in range(9):
        payload = build_payload(c, rules, messages, json_mode, max_tokens)
        try:
            out = await asyncio.to_thread(_post, f"{c['base']}/chat/completions", c["key"], payload, timeout)
            if changed:
                await _remember(c, rules)
                log.info("AI 接口 %s / %s 已自动调整参数：%s", c["provider"], c["model"], rules)
            return out
        except AIError as e:
            msg = str(e)
            if re.search(r"HTTP (400|422)", msg):
                new = adjust(rules, msg, has_images, json_mode, bool(c["preset"].get("image_raw")))
                if new is None:
                    raise
                rules, changed = new, True
                continue
            if re.search(r"HTTP (429|5\d\d)|连接失败", msg) and transient < 2:
                transient += 1
                await asyncio.sleep(2 + transient * 4)
                continue
            raise
    raise AIError("AI 接口参数无法自动适配，请在后台“测试连接”查看具体错误")


def list_models(kind: str) -> list[str]:
    """调用 GET {base}/models 获取该账号可用的模型（不是每家都支持）。"""
    c = resolve(kind)
    req = urllib.request.Request(f"{c['base']}/models", headers={"Authorization": f"Bearer {c['key']}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise AIError(f"HTTP {e.code}：{e.read()[:300].decode('utf-8', errors='replace')}") from e
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        raise AIError(f"获取失败：{getattr(e, 'reason', e)}") from e
    items = data.get("data") if isinstance(data, dict) else data
    return sorted({str(x.get("id")) for x in items or [] if isinstance(x, dict) and x.get("id")})


def _on_settings(changed: set[str]) -> None:
    """后台修改了 AI 设置：清空学到的参数规则，下次重新适配（防止一次误判一直生效）。"""
    if any(k.startswith("ai.") and k not in ("ai.enabled", "ai.members_only", "ai.daily_limit", "ai.global_daily_limit") for k in changed):
        try:
            asyncio.get_running_loop().create_task(forget_all())
        except RuntimeError:
            _LEARN.clear()


settings.on_change(_on_settings)
