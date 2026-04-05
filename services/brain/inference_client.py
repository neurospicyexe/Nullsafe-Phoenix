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
    ) -> tuple[str, str]:
        """
        Generate a completion. Tries each backend in order, returns on first success.

        Returns:
            (reply_text, backend_used)
        """
        if self._local_url:
            result = await self._try_local(system_prompt, user_message, model)
            if result is not None:
                return result, "local"

        if self._deepseek_api_key:
            result = await self._try_deepseek(system_prompt, user_message)
            if result is not None:
                return result, "deepseek"

        logger.warning(f"[{agent_id}] All inference backends failed -- returning stub")
        return self._stub(agent_id), "stub"

    async def _try_local(
        self, system_prompt: str, user_message: str, model: Optional[str]
    ) -> Optional[str]:
        url = f"{self._local_url}/chat/completions"
        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.7,
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
        self, system_prompt: str, user_message: str
    ) -> Optional[str]:
        url = f"{self._deepseek_base}/chat/completions"
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.7,
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
