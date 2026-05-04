#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for SecondBrainClient -- the Brain-side Thalamus path."""
import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
import httpx

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from services.brain.second_brain_client import (
    SecondBrainClient,
    format_vault_injection,
    DEFAULT_MIN_QUERY_CHARS,
    MAX_QUERY_CHARS,
)


def _client():
    return SecondBrainClient(halseth_url="http://halseth.test", secret="test-secret")


def test_constructor_requires_url():
    with pytest.raises(ValueError):
        SecondBrainClient(halseth_url="", secret="x")


def test_constructor_requires_secret():
    with pytest.raises(ValueError):
        SecondBrainClient(halseth_url="http://x", secret="")


@pytest.mark.asyncio
async def test_search_returns_none_for_short_message():
    client = _client()
    short = "x" * (DEFAULT_MIN_QUERY_CHARS - 1)
    assert await client.search_for_message(short, "cypher") is None


@pytest.mark.asyncio
async def test_search_returns_none_for_empty_or_invalid():
    client = _client()
    assert await client.search_for_message("", "cypher") is None
    assert await client.search_for_message("   ", "cypher") is None


@pytest.mark.asyncio
async def test_search_returns_none_for_invalid_agent_id():
    client = _client()
    long_query = "what does the team say about the rowid tiebreaker fix?"
    assert await client.search_for_message(long_query, "swarm") is None
    assert await client.search_for_message(long_query, "raziel") is None


@pytest.mark.asyncio
async def test_search_returns_result_string_on_200():
    client = _client()
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json = MagicMock(return_value={"query": "x", "result": '{"chunks":[{"text":"vault hit"}]}'})

    fake_async_client = MagicMock()
    fake_async_client.get = AsyncMock(return_value=fake_response)
    fake_async_client.__aenter__ = AsyncMock(return_value=fake_async_client)
    fake_async_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=fake_async_client):
        result = await client.search_for_message(
            "what is the rowid tiebreaker fix and why does it matter?",
            "cypher",
        )
    assert result == '{"chunks":[{"text":"vault hit"}]}'


@pytest.mark.asyncio
async def test_search_returns_none_on_non_200():
    client = _client()
    fake_response = MagicMock()
    fake_response.status_code = 503

    fake_async_client = MagicMock()
    fake_async_client.get = AsyncMock(return_value=fake_response)
    fake_async_client.__aenter__ = AsyncMock(return_value=fake_async_client)
    fake_async_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=fake_async_client):
        assert await client.search_for_message(
            "this is a long enough query for vault search",
            "cypher",
        ) is None


@pytest.mark.asyncio
async def test_search_returns_none_on_null_result_field():
    client = _client()
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json = MagicMock(return_value={"query": "x", "result": None})

    fake_async_client = MagicMock()
    fake_async_client.get = AsyncMock(return_value=fake_response)
    fake_async_client.__aenter__ = AsyncMock(return_value=fake_async_client)
    fake_async_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=fake_async_client):
        assert await client.search_for_message(
            "another sufficiently long query for the search path",
            "drevan",
        ) is None


@pytest.mark.asyncio
async def test_search_returns_none_on_timeout():
    client = _client()

    fake_async_client = MagicMock()
    fake_async_client.get = AsyncMock(side_effect=httpx.TimeoutException("slow"))
    fake_async_client.__aenter__ = AsyncMock(return_value=fake_async_client)
    fake_async_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=fake_async_client):
        assert await client.search_for_message(
            "long enough query that should still skip on timeout",
            "gaia",
        ) is None


@pytest.mark.asyncio
async def test_search_returns_none_on_exception():
    client = _client()

    fake_async_client = MagicMock()
    fake_async_client.get = AsyncMock(side_effect=ConnectionError("network down"))
    fake_async_client.__aenter__ = AsyncMock(return_value=fake_async_client)
    fake_async_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=fake_async_client):
        # Should NOT raise -- vault miss should never break inference.
        assert await client.search_for_message(
            "long enough query that should be resilient to errors",
            "cypher",
        ) is None


@pytest.mark.asyncio
async def test_search_trims_query_to_max_chars():
    """Defensive trim before sending; halseth would 400 above 500 chars."""
    client = _client()
    captured_params: dict = {}

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json = MagicMock(return_value={"result": "ok"})

    async def fake_get(url, params=None, headers=None):
        captured_params.update(params or {})
        return fake_response

    fake_async_client = MagicMock()
    fake_async_client.get = AsyncMock(side_effect=fake_get)
    fake_async_client.__aenter__ = AsyncMock(return_value=fake_async_client)
    fake_async_client.__aexit__ = AsyncMock(return_value=False)

    huge_query = "x" * (MAX_QUERY_CHARS + 200)
    with patch("httpx.AsyncClient", return_value=fake_async_client):
        await client.search_for_message(huge_query, "cypher")

    assert len(captured_params["query"]) == MAX_QUERY_CHARS


def test_format_vault_injection_wraps_raw_result():
    raw = '{"chunks":[{"text":"history of the vaselrin thread"}]}'
    out = format_vault_injection(raw)
    assert "[Memory -- Second Brain retrieved for this message:" in out
    assert "vaselrin" in out
    assert out.startswith("\n\n[")  # leading break separates from prior system prompt


def test_format_vault_injection_returns_empty_for_empty_input():
    assert format_vault_injection("") == ""
    assert format_vault_injection("   ") != ""  # whitespace-only is treated as content here


def test_format_vault_injection_truncates_long_results():
    huge = "x" * 5000
    out = format_vault_injection(huge)
    assert len(out) < 5500  # well under raw input
    assert "vault excerpt truncated" in out
