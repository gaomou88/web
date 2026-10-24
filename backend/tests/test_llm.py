"""大模型接口自适应：模拟各家接口的 400 错误，确认能自动调整参数并记住。运行：pytest backend/tests"""
import asyncio

import pytest

from app import llm


class Fake:
    """按规则返回错误的假接口。rules: 一组函数 payload -> 错误信息或 None。"""

    def __init__(self, *checks):
        self.checks = checks
        self.calls = []

    def __call__(self, url, key, payload, timeout):
        self.calls.append(payload)
        for chk in self.checks:
            msg = chk(payload)
            if msg:
                raise llm.AIError(f"HTTP 400 ：{msg}")
        return '{"ok": true}', {"in": 1, "out": 1}, "stop"


@pytest.fixture
def env(monkeypatch):
    vals = {"ai.mode": "split", "ai.text_provider": "qwen", "ai.text_base_url": "", "ai.text_api_key": "k", "ai.text_model": "qwen3.7-plus",
            "ai.vision_provider": "zhipu", "ai.vision_base_url": "", "ai.vision_api_key": "k", "ai.vision_model": "glm-4.6v"}
    monkeypatch.setattr(llm.settings, "get", lambda k: vals.get(k))
    kv = {}

    async def kv_get(k):
        return (kv[k], 0) if k in kv else None

    async def kv_set(k, v):
        kv[k] = v
    monkeypatch.setattr(llm.store, "kv_get", kv_get)
    monkeypatch.setattr(llm.store, "kv_set", kv_set)
    llm._LEARN.clear()
    return vals, kv


def run(coro):
    return asyncio.run(coro)


MSG = [{"role": "user", "content": "json"}]


def test_qwen_default_payload(env, monkeypatch):
    f = Fake()
    monkeypatch.setattr(llm, "_post", f)
    out = run(llm.chat("text", MSG, json_mode=True, max_tokens=100))
    assert out[0] == '{"ok": true}'
    p = f.calls[0]
    assert p["enable_thinking"] is False and p["stream"] is True and p["response_format"] == {"type": "json_object"}
    assert p["temperature"] == 0.1 and p["model"] == "qwen3.7-plus"
    assert llm.resolve("text")["base"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"


def test_thinking_only_model(env, monkeypatch):
    # 只能思考的模型：关闭思考报错；思考时 JSON 模式也报错
    def no_off(p):
        return "<400> InternalError.Algo.InvalidParameter: The value of the enable_thinking parameter is restricted to True." if p.get("enable_thinking") is False else None

    def no_json(p):
        return "Json mode response is not supported when enable_thinking is true" if "response_format" in p and p.get("enable_thinking") is not False else None
    f = Fake(no_off, no_json)
    monkeypatch.setattr(llm, "_post", f)
    run(llm.chat("text", MSG, json_mode=True))
    last = f.calls[-1]
    assert "enable_thinking" not in last and "response_format" not in last
    assert len(f.calls) == 2
    # 记住了：下次第一次就成功
    f.calls.clear()
    run(llm.chat("text", MSG, json_mode=True))
    assert len(f.calls) == 1


def test_json_mode_unsupported_and_max_tokens(env, monkeypatch):
    def no_json(p):
        return "response_format type json_object is not supported by this model" if "response_format" in p else None

    def mt(p):
        return "Range of max_tokens should be [1, 4096]" if p.get("max_tokens", 0) > 4096 else None
    f = Fake(no_json, mt)
    monkeypatch.setattr(llm, "_post", f)
    run(llm.chat("text", MSG, json_mode=True, max_tokens=8000))
    assert f.calls[-1]["max_tokens"] == 4096 and "response_format" not in f.calls[-1]


def test_kimi_temperature_and_unknown_thinking(env, monkeypatch):
    vals, _ = env
    vals.update({"ai.text_provider": "custom", "ai.text_base_url": "https://x.example/v1/chat/completions", "ai.text_model": "m"})

    def temp(p):
        return "invalid temperature: only 0.6 is allowed for this model" if "temperature" in p else None
    f = Fake(temp)
    monkeypatch.setattr(llm, "_post", f)
    run(llm.chat("text", MSG, json_mode=False))
    assert llm.resolve("text")["base"] == "https://x.example/v1"  # 去掉了多填的 /chat/completions
    assert "temperature" not in f.calls[-1]


def test_zhipu_image_raw_and_toggle(env, monkeypatch):
    img = [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}}, {"type": "text", "text": "x"}]}]
    f = Fake()
    monkeypatch.setattr(llm, "_post", f)
    run(llm.chat("vision", img, json_mode=False))
    assert f.calls[0]["messages"][0]["content"][0]["image_url"]["url"] == "QUJD"  # 智谱：纯 base64
    assert f.calls[0]["thinking"] == {"type": "disabled"}
    assert img[0]["content"][0]["image_url"]["url"].startswith("data:")  # 不改调用方的数据

    def need_data_url(p):
        u = p["messages"][0]["content"][0]["image_url"]["url"]
        return "Invalid image url: must be a data URI" if not u.startswith("data:") else None
    f2 = Fake(need_data_url)
    monkeypatch.setattr(llm, "_post", f2)
    llm._LEARN.clear()
    run(llm.chat("vision", img, json_mode=False))
    assert f2.calls[-1]["messages"][0]["content"][0]["image_url"]["url"].startswith("data:")


def test_single_mode_uses_text_model_for_images(env):
    vals, _ = env
    vals["ai.mode"] = "single"
    assert llm.resolve("vision")["model"] == "qwen3.7-plus"


def test_unfixable_error_raises(env, monkeypatch):
    f = Fake(lambda p: "model not found")
    monkeypatch.setattr(llm, "_post", f)
    with pytest.raises(llm.AIError):
        run(llm.chat("text", MSG, json_mode=True))
    assert len(f.calls) <= 4


def test_stream_parser():
    lines = [b'data: {"choices":[{"delta":{"content":"{\\"a\\""}}]}\n', b"\n", b": keep-alive\n",
             b'data: {"choices":[{"delta":{"reasoning_content":"hmm"}}]}\n',
             b'data: {"choices":[{"delta":{"content":":1}"},"finish_reason":"stop"}]}\n',
             b'data: {"choices":[],"usage":{"prompt_tokens":5,"completion_tokens":3}}\n', b"data: [DONE]\n"]
    content, usage, finish = llm._read_stream(iter(lines))
    assert content == '{"a":1}' and usage == {"in": 5, "out": 3} and finish == "stop"
