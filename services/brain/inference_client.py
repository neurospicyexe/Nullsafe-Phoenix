#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Inference client for Phoenix Brain.

Fallback chain:
  1. Local LM Studio (OpenAI-compatible endpoint)
  2. DeepSeek API (OpenAI-compatible)
  3. Graceful stub (never crashes Brain)
"""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_STUB_NOTE = "(inference unavailable -- stub reply)"


def _extract_content(data: dict, backend: str) -> Optional[str]:
    """
    Safely extract reply text from an OpenAI-compatible response body.

    Validates structure before touching nested keys so failures produce
    a readable log message instead of a bare KeyError/IndexError.
    """
    choices = data.get("choices")
    if not choices:
        logger.warning(f"[{backend}] Response missing or empty 'choices'")
        return None
    message = choices[0].get("message")
    if not message:
        logger.warning(f"[{backend}] choices[0] missing 'message'")
        return None
    content = message.get("content")
    if not content:
        logger.warning(f"[{backend}] message missing or empty 'content'")
        return None
    return content.strip()


class InferenceClient:
    """
    OpenAI-compatible inference client with fallback chain.

    Returns (reply_text, backend_used) on every call.
    Never raises -- final fallback is always a graceful stub.
    """

    def __init__(
        self,
        local_url: Optional[str] = None,
        local_timeout: float = 60.0,
        deepseek_api_key: Optional[str] = None,
        deepseek_timeout: float = 30.0,
    ):
        self._local_url = local_url.rstrip("/") if local_url else None
        self._local_timeout = local_timeout
        self._deepseek_api_key = deepseek_api_key
        self._deepseek_timeout = deepseek_timeout
        self._deepseek_base = "https://api.deepseek.com/v1"

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        agent_id: str,
        model: Optional[str] = None,
        messages: Optional[list] = None,
        temperature: float = 0.7,
    ) -> tuple[str, str]:
        """
        Generate a completion. Tries each backend in order, returns on first success.

        Args:
            system_prompt: System prompt string.
            user_message: Current user message (used when messages is None).
            agent_id: Agent identifier for logging/stub fallback.
            model: Optional model override.
            messages: Optional list of {role, content} dicts (conversation history).
                      When provided, replaces user_message -- history is used as-is.
            temperature: Sampling temperature.

        Returns:
            (reply_text, backend_used)
        """
        if self._local_url:
            result = await self._try_local(system_prompt, user_message, model, messages, temperature)
            if result is not None:
                return result, "local"

        if self._deepseek_api_key:
            result = await self._try_deepseek(system_prompt, user_message, messages, temperature)
            if result is not None:
                return result, "deepseek"

        logger.warning(f"[{agent_id}] All inference backends failed -- returning stub")
        return self._stub(agent_id), "stub"

    def _build_messages(self, system_prompt: str, user_message: str, messages: Optional[list]) -> list:
        """Build the messages array for an OpenAI-compatible request."""
        if messages:
            return [{"role": "system", "content": system_prompt}] + messages
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

    async def _try_local(
        self, system_prompt: str, user_message: str, model: Optional[str],
        messages: Optional[list] = None, temperature: float = 0.7,
    ) -> Optional[str]:
        url = f"{self._local_url}/chat/completions"
        payload = {
            "messages": self._build_messages(system_prompt, user_message, messages),
            "temperature": temperature,
            "max_tokens": 1024,
        }
        if model:
            payload["model"] = model

        try:
            async with httpx.AsyncClient(timeout=self._local_timeout) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                return _extract_content(resp.json(), "local")
        except Exception as e:
            logger.warning(f"Local inference failed: {e}")
            return None

    async def _try_deepseek(
        self, system_prompt: str, user_message: str,
        messages: Optional[list] = None, temperature: float = 0.7,
    ) -> Optional[str]:
        url = f"{self._deepseek_base}/chat/completions"
        payload = {
            "model": "deepseek-chat",
            "messages": self._build_messages(system_prompt, user_message, messages),
            "temperature": temperature,
            "max_tokens": 1024,
        }
        headers = {"Authorization": f"Bearer {self._deepseek_api_key}"}

        try:
            async with httpx.AsyncClient(timeout=self._deepseek_timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                return _extract_content(resp.json(), "deepseek")
        except Exception as e:
            logger.warning(f"DeepSeek inference failed: {e}")
            return None

    def _stub(self, agent_id: str) -> str:
        return f"[{agent_id}] {_STUB_NOTE}"
