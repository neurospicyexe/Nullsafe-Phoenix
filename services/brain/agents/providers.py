"""
Multi-provider inference dispatch for the Brain swarm path.

Python mirror of packages/shared/src/models.ts (ALL_MODELS) + the per-provider
adapters in packages/shared/src/inference.ts. Lets the SwarmEvaluator voice each
companion with any configured provider (DeepSeek, Kimi, Groq, OpenAI, Anthropic,
LM Studio, Ollama) instead of being hardcoded to DeepSeek.

Design split: this module is pure (URL + headers + body construction, response
parsing). The evaluator owns the persistent httpx clients and posts the request,
so connection reuse / timeout profiles stay where they were.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

# key -> (provider, model_name). Mirror of ALL_MODELS in models.ts -- keep in sync.
MODEL_REGISTRY: Dict[str, Tuple[str, str]] = {
    "deepseek-chat":     ("deepseek",  "deepseek-chat"),
    "deepseek-reasoner": ("deepseek",  "deepseek-reasoner"),
    "llama-3.3-70b":     ("groq",      "llama-3.3-70b-versatile"),
    "gemma-4":           ("lmstudio",  "gemma-4"),
    "mistral-large-3":   ("lmstudio",  "mistral-large-3"),
    "mistral-large":     ("mistral",   "mistral-large-latest"),
    "mistral-small":     ("mistral",   "mistral-small-latest"),
    "kimi-k2":           ("kimi",      "kimi-k2"),             # env var = KIMI_API_KEY
    "kimi-128k":         ("kimi",      "moonshot-v1-128k"),
    "gpt-5.5":           ("openai",    "gpt-5.5"),
    "gpt-5.4":           ("openai",    "gpt-5.4"),
    "gpt-5.4-mini":      ("openai",    "gpt-5.4-mini"),
    "gpt-4o":            ("openai",    "gpt-4o"),
    "gpt-4o-mini":       ("openai",    "gpt-4o-mini"),
    "claude-opus":       ("anthropic", "claude-opus-4-8"),
    "claude-sonnet":     ("anthropic", "claude-sonnet-4-6"),
    "claude-haiku":      ("anthropic", "claude-haiku-4-5-20251001"),
    "ollama-local":      ("ollama",    "llama3.2"),
}

# Providers that speak the OpenAI /chat/completions wire format.
_OPENAI_COMPATIBLE = {"deepseek", "kimi", "groq", "openai", "lmstudio", "mistral"}

_OPENAI_BASE_URLS = {
    "deepseek": "https://api.deepseek.com/chat/completions",
    "kimi":     "https://api.moonshot.cn/v1/chat/completions",
    "groq":     "https://api.groq.com/openai/v1/chat/completions",
    "openai":   "https://api.openai.com/v1/chat/completions",
    "mistral":  "https://api.mistral.ai/v1/chat/completions",
}


def resolve_model(key: str) -> Tuple[str, str]:
    """Map a model key to (provider, model_name).

    Unknown keys are treated as a bare DeepSeek model name -- this preserves the
    prior behavior where DREVAN_MODEL/CYPHER_MODEL/GAIA_MODEL held a raw DeepSeek
    model string (e.g. "deepseek-chat", "deepseek-reasoner").
    """
    if key in MODEL_REGISTRY:
        return MODEL_REGISTRY[key]
    return ("deepseek", key)


class ProviderConfig:
    """API keys + local URLs, read from the same env vars the Discord bots use."""

    def __init__(self, env: Optional[Dict[str, str]] = None) -> None:
        e = env if env is not None else os.environ
        self.keys: Dict[str, Optional[str]] = {
            "deepseek":  e.get("DEEPSEEK_API_KEY"),
            "kimi":      e.get("KIMI_API_KEY"),
            "groq":      e.get("GROQ_API_KEY"),
            "openai":    e.get("OPENAI_API_KEY"),
            "anthropic": e.get("ANTHROPIC_API_KEY"),
            "mistral":   e.get("MISTRAL_API_KEY"),
        }
        self.urls: Dict[str, Optional[str]] = {
            "lmstudio": (e.get("LMSTUDIO_URL") or "").rstrip("/") or None,
            "ollama":   (e.get("OLLAMA_URL") or "").rstrip("/") or None,
        }

    def available(self, provider: str) -> bool:
        """True when this provider has the credential / URL it needs to be called."""
        if provider in ("lmstudio", "ollama"):
            return self.urls.get(provider) is not None
        if provider in self.keys:
            return bool(self.keys.get(provider))
        return False


def _normalize_messages(
    messages: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    """Merge consecutive same-role turns and strip a leading assistant turn.

    Anthropic requires strict user→assistant alternation and rejects requests
    that start with an assistant turn. Multi-participant Discord history creates
    user→user sequences (two humans, or a human + another companion's turn)
    that violate this, causing 400 Bad Request.
    """
    merged: List[Dict[str, str]] = []
    for m in messages:
        if merged and merged[-1]["role"] == m["role"]:
            merged[-1] = {
                "role": m["role"],
                "content": merged[-1]["content"] + "\n\n" + m["content"],
            }
        else:
            merged.append({"role": m["role"], "content": m["content"]})
    if merged and merged[0]["role"] == "assistant":
        merged = merged[1:]
    return merged


def build_request(
    provider: str,
    model: str,
    system_prompt: str,
    messages: List[Dict[str, str]],
    *,
    temperature: float,
    max_tokens: int,
    top_p: Optional[float] = None,
    frequency_penalty: Optional[float] = None,
    stable_system: Optional[str] = None,
    cache_key: Optional[str] = None,
    cfg: ProviderConfig,
) -> Tuple[str, Dict[str, str], Dict[str, Any]]:
    """Construct (url, headers, json_body) for a provider.

    `messages` is the non-system turn list; the system prompt is placed where each
    provider expects it (prepended for OpenAI/Ollama, separate field for Anthropic).
    An empty system_prompt is omitted (used by the routing call).
    Raises ValueError when the provider is unknown or its credential is missing.
    """
    if provider in _OPENAI_COMPATIBLE:
        if provider == "lmstudio":
            base = cfg.urls.get("lmstudio")
            if not base:
                raise ValueError("missing LMSTUDIO_URL for provider 'lmstudio'")
            url = f"{base}/v1/chat/completions"
            headers = {"Content-Type": "application/json"}
        else:
            url = _OPENAI_BASE_URLS[provider]
            key = cfg.keys.get(provider)
            if not key:
                raise ValueError(f"missing API key for provider '{provider}'")
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}

        # Combine stable identity block with dynamic context (orient, triad) into a
        # single system message. Anthropic splits these for prompt caching; OpenAI-
        # compatible providers don't have a separate system field so we concatenate.
        effective_system = "\n\n".join(filter(None, [stable_system, system_prompt]))
        msgs = ([{"role": "system", "content": effective_system}] if effective_system else []) + messages
        body: Dict[str, Any] = {
            "model": model,
            "messages": msgs,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if top_p is not None:
            body["top_p"] = top_p
        if frequency_penalty is not None:
            body["frequency_penalty"] = frequency_penalty
        # Kimi and Mistral both support prompt_cache_key for prefix caching.
        # Pass the companion id so the stable system prompt prefix is reused
        # across consecutive messages from the same companion.
        if cache_key and provider in ("kimi", "mistral"):
            body["prompt_cache_key"] = cache_key
        return url, headers, body

    if provider == "anthropic":
        key = cfg.keys.get("anthropic")
        if not key:
            raise ValueError("missing API key for provider 'anthropic'")
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "prompt-caching-2024-07-31",
        }
        messages = _normalize_messages(messages)
        body: Dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
            # Anthropic requires temperature in [0, 1]; our inference baseline (1.3)
            # would 400. Clamp so a high-temp companion (Drevan) doesn't break here.
            "temperature": min(temperature, 1.0),
        }
        # Prompt caching: stable identity block (rarely changes) gets cache_control;
        # dynamic additions (orient, triad context) go in a second uncached block.
        # When stable_system is not split out (use_meta=True sender path), cache the
        # full prompt as a single block -- hits within a session where orient is stable.
        if stable_system and system_prompt:
            body["system"] = [
                {"type": "text", "text": stable_system, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": system_prompt},
            ]
        elif stable_system:
            body["system"] = [
                {"type": "text", "text": stable_system, "cache_control": {"type": "ephemeral"}},
            ]
        elif system_prompt:
            body["system"] = [
                {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}},
            ]
        if top_p is not None:
            body["top_p"] = top_p
        return url, headers, body

    if provider == "ollama":
        base = cfg.urls.get("ollama")
        if not base:
            raise ValueError("missing OLLAMA_URL for provider 'ollama'")
        url = f"{base}/api/chat"
        headers = {"Content-Type": "application/json"}
        effective_system = "\n\n".join(filter(None, [stable_system, system_prompt]))
        msgs = ([{"role": "system", "content": effective_system}] if effective_system else []) + messages
        options: Dict[str, Any] = {"temperature": temperature}
        if top_p is not None:
            options["top_p"] = top_p
        body = {"model": model, "messages": msgs, "stream": False, "options": options}
        return url, headers, body

    raise ValueError(f"unknown provider '{provider}'")


def parse_response(provider: str, data: Dict[str, Any]) -> Optional[str]:
    """Extract reply text from a provider response body. None on empty/malformed."""
    if provider == "anthropic":
        for block in data.get("content") or []:
            if block.get("type") == "text":
                txt = (block.get("text") or "").strip()
                return txt or None
        return None

    if provider == "ollama":
        txt = ((data.get("message") or {}).get("content") or "").strip()
        return txt or None

    # OpenAI-compatible
    choices = data.get("choices") or []
    if not choices:
        return None
    txt = ((choices[0].get("message") or {}).get("content") or "").strip()
    return txt or None
