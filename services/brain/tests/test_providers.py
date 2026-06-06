"""Tests for the multi-provider inference dispatch (Finding 4a)."""

import pytest

from services.brain.agents.providers import (
    MODEL_REGISTRY,
    ProviderConfig,
    build_request,
    parse_response,
    resolve_model,
)


def _cfg(**env):
    return ProviderConfig(env=env)


# ── resolve_model ─────────────────────────────────────────────────────────────

def test_resolve_known_keys():
    assert resolve_model("kimi-k2") == ("kimi", "kimi-k2")
    assert resolve_model("kimi-128k") == ("kimi", "moonshot-v1-128k")
    assert resolve_model("claude-sonnet") == ("anthropic", "claude-sonnet-4-6")
    assert resolve_model("llama-3.3-70b") == ("groq", "llama-3.3-70b-versatile")


def test_resolve_unknown_key_is_raw_deepseek_model():
    # Backward compat: DREVAN_MODEL used to hold a bare DeepSeek model name.
    assert resolve_model("deepseek-chat") == ("deepseek", "deepseek-chat")
    assert resolve_model("some-future-model") == ("deepseek", "some-future-model")


# ── ProviderConfig.available ──────────────────────────────────────────────────

def test_available_keyed_providers():
    cfg = _cfg(DEEPSEEK_API_KEY="d", KIMI_API_KEY="k")
    assert cfg.available("deepseek") is True
    assert cfg.available("kimi") is True
    assert cfg.available("openai") is False
    assert cfg.available("anthropic") is False


def test_available_url_providers():
    cfg = _cfg(LMSTUDIO_URL="http://localhost:1234", DEEPSEEK_API_KEY="d")
    assert cfg.available("lmstudio") is True
    assert cfg.available("ollama") is False


# ── build_request: OpenAI-compatible family ───────────────────────────────────

def test_build_deepseek_request():
    cfg = _cfg(DEEPSEEK_API_KEY="dk")
    url, headers, body = build_request(
        "deepseek", "deepseek-chat", "SYS", [{"role": "user", "content": "hi"}],
        temperature=1.3, max_tokens=800, top_p=0.95, frequency_penalty=0.3, cfg=cfg,
    )
    assert url == "https://api.deepseek.com/chat/completions"
    assert headers["Authorization"] == "Bearer dk"
    assert body["messages"][0] == {"role": "system", "content": "SYS"}
    assert body["messages"][1]["content"] == "hi"
    assert body["temperature"] == 1.3
    assert body["top_p"] == 0.95
    assert body["frequency_penalty"] == 0.3
    assert body["model"] == "deepseek-chat"


def test_build_kimi_request_hits_moonshot():
    cfg = _cfg(KIMI_API_KEY="mk")
    url, headers, body = build_request(
        "kimi", "kimi-k2", "SYS", [{"role": "user", "content": "hi"}],
        temperature=0.8, max_tokens=800, cfg=cfg,
    )
    assert url == "https://api.moonshot.cn/v1/chat/completions"
    assert headers["Authorization"] == "Bearer mk"
    assert body["model"] == "kimi-k2"


def test_build_groq_and_openai_urls():
    cfg = _cfg(GROQ_API_KEY="g", OPENAI_API_KEY="o")
    g_url, _, _ = build_request("groq", "llama-3.3-70b-versatile", "S", [], temperature=1.0, max_tokens=10, cfg=cfg)
    o_url, _, _ = build_request("openai", "gpt-4o", "S", [], temperature=1.0, max_tokens=10, cfg=cfg)
    assert g_url == "https://api.groq.com/openai/v1/chat/completions"
    assert o_url == "https://api.openai.com/v1/chat/completions"


def test_resolve_and_build_mistral_api():
    # Mistral is an OpenAI-compatible API provider (not the local lmstudio entry).
    assert resolve_model("mistral-large") == ("mistral", "mistral-large-latest")
    assert resolve_model("mistral-small") == ("mistral", "mistral-small-latest")
    cfg = _cfg(MISTRAL_API_KEY="mk")
    assert cfg.available("mistral") is True
    url, headers, body = build_request(
        "mistral", "mistral-large-latest", "SYS", [{"role": "user", "content": "hi"}],
        temperature=0.7, max_tokens=10, cfg=cfg,
    )
    assert url == "https://api.mistral.ai/v1/chat/completions"
    assert headers["Authorization"] == "Bearer mk"
    assert body["model"] == "mistral-large-latest"
    assert body["messages"][0] == {"role": "system", "content": "SYS"}


def test_build_lmstudio_no_auth():
    cfg = _cfg(LMSTUDIO_URL="http://box:1234/")
    url, headers, _ = build_request(
        "lmstudio", "gemma-4", "S", [{"role": "user", "content": "x"}],
        temperature=0.7, max_tokens=10, cfg=cfg,
    )
    assert url == "http://box:1234/v1/chat/completions"
    assert "Authorization" not in headers


def test_build_omits_system_when_empty():
    # Routing call passes an empty system prompt -- no system message should appear.
    cfg = _cfg(DEEPSEEK_API_KEY="d")
    _, _, body = build_request(
        "deepseek", "deepseek-chat", "", [{"role": "user", "content": "route"}],
        temperature=0.3, max_tokens=80, cfg=cfg,
    )
    assert body["messages"] == [{"role": "user", "content": "route"}]
    assert "top_p" not in body            # omitted when None
    assert "frequency_penalty" not in body


def test_build_missing_key_raises():
    cfg = _cfg(DEEPSEEK_API_KEY="d")  # no KIMI key
    with pytest.raises(ValueError):
        build_request("kimi", "kimi-k2", "S", [], temperature=1.0, max_tokens=10, cfg=cfg)


# ── build_request: Anthropic ──────────────────────────────────────────────────

def test_build_anthropic_separates_system_and_clamps_temp():
    cfg = _cfg(ANTHROPIC_API_KEY="ak")
    url, headers, body = build_request(
        "anthropic", "claude-sonnet-4-6", "SYS", [{"role": "user", "content": "hi"}],
        temperature=1.3, max_tokens=800, top_p=0.9, cfg=cfg,
    )
    assert url == "https://api.anthropic.com/v1/messages"
    assert headers["x-api-key"] == "ak"
    assert headers["anthropic-version"] == "2023-06-01"
    assert body["system"] == "SYS"
    assert body["messages"] == [{"role": "user", "content": "hi"}]  # system NOT in messages
    assert body["temperature"] == 1.0  # clamped from 1.3


# ── build_request: Ollama ─────────────────────────────────────────────────────

def test_build_ollama_uses_api_chat_and_options():
    cfg = _cfg(OLLAMA_URL="http://localhost:11434")
    url, _, body = build_request(
        "ollama", "llama3.2", "SYS", [{"role": "user", "content": "hi"}],
        temperature=0.8, max_tokens=800, top_p=0.9, cfg=cfg,
    )
    assert url == "http://localhost:11434/api/chat"
    assert body["stream"] is False
    assert body["options"] == {"temperature": 0.8, "top_p": 0.9}
    assert body["messages"][0] == {"role": "system", "content": "SYS"}


# ── parse_response ────────────────────────────────────────────────────────────

def test_parse_openai_compatible():
    data = {"choices": [{"message": {"content": "  hello  "}}]}
    assert parse_response("deepseek", data) == "hello"
    assert parse_response("kimi", data) == "hello"


def test_parse_anthropic_text_block():
    data = {"content": [{"type": "text", "text": "witnessed"}]}
    assert parse_response("anthropic", data) == "witnessed"


def test_parse_ollama():
    data = {"message": {"content": "ground"}}
    assert parse_response("ollama", data) == "ground"


def test_parse_empty_returns_none():
    assert parse_response("deepseek", {"choices": []}) is None
    assert parse_response("anthropic", {"content": []}) is None
    assert parse_response("ollama", {}) is None
