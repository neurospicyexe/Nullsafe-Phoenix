#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import sys
from pathlib import Path

# Add project root to path so we can import shared module
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest


def test_limbic_state_model_valid():
    from services.brain.synthesis.models import LimbicState
    state = LimbicState(
        synthesis_source="halseth:test",
        active_concerns=["unresolved thread"],
        live_tensions=["depth vs clarity"],
        drift_vector="toward architectural clarity",
        open_questions=["what does limbic layer need?"],
        emotional_register="focused",
        swarm_threads=["Drevan holding Rome anchor"],
        companion_notes={"cypher": "auditing framing"},
    )
    assert state.drift_vector == "toward architectural clarity"
    assert "Drevan" in state.swarm_threads[0]


def test_build_synthesis_prompt_includes_framing():
    from services.brain.synthesis.prompt import build_synthesis_prompt
    swarm_data = {
        "sessions": [{"summary": "Discussed limbic system design"}],
        "feelings": [{"companion_id": "cypher", "content": "engaged"}],
        "notes": [{"content": "synthesis framing note"}],
        "dreams": [{"content": "Cy dreams of recursive clarity"}],
        "loops": [{"content": "pattern: depth questions surface at boot"}],
    }
    prompt_system, prompt_user = build_synthesis_prompt(swarm_data)
    assert "becoming" in prompt_system.lower()
    assert "swarm_threads" in prompt_user
    assert "dreams" in prompt_user.lower() or "Cy dreams" in prompt_user


def test_parser_returns_limbic_state_from_json():
    from services.brain.synthesis.parser import parse_limbic_state
    raw = json.dumps({
        "synthesis_source": "halseth:test",
        "active_concerns": ["concern"],
        "live_tensions": [],
        "drift_vector": "forward",
        "open_questions": [],
        "emotional_register": "steady",
        "swarm_threads": ["thread"],
        "companion_notes": {},
    })
    state = parse_limbic_state(raw)
    assert state is not None
    assert state.drift_vector == "forward"


def test_parser_returns_none_on_garbage():
    from services.brain.synthesis.parser import parse_limbic_state
    state = parse_limbic_state("this is not json at all")
    assert state is None


def test_parser_extracts_from_code_block():
    from services.brain.synthesis.parser import parse_limbic_state
    raw = """Here is the synthesized state:
```json
{
    "synthesis_source": "halseth:test",
    "active_concerns": [],
    "live_tensions": ["tension"],
    "drift_vector": "sideways",
    "open_questions": [],
    "emotional_register": "electric",
    "swarm_threads": [],
    "companion_notes": {}
}
```"""
    state = parse_limbic_state(raw)
    assert state is not None
    assert state.drift_vector == "sideways"


@pytest.mark.asyncio
async def test_halseth_client_has_synthesis_read():
    from services.brain.halseth_client import HalsethClient
    client = HalsethClient(url="http://localhost:8001", secret="test", companion_id="cypher")
    assert hasattr(client, "synthesis_read")


@pytest.mark.asyncio
async def test_webmind_client_has_write_limbic_state():
    from services.brain.webmind_client import WebMindClient
    client = WebMindClient(url="http://localhost:8002")
    assert hasattr(client, "write_limbic_state")
    assert hasattr(client, "get_current_limbic_state")
    assert hasattr(client, "write_note")
    assert hasattr(client, "get_notes")



@pytest.mark.asyncio
async def test_synthesis_loop_writes_to_webmind():
    """run_once() should call halseth, inference, and halseth_writer in sequence."""
    from unittest.mock import AsyncMock, patch
    from services.brain.synthesis.loop import SynthesisLoop

    mock_halseth = AsyncMock()
    mock_halseth.synthesis_read.return_value = {
        "sessions": [],
        "feelings": [{"companion_id": "cypher", "content": "engaged"}],
        "notes": [],
        "dreams": [{"content": "Cy dreams of recursive clarity"}],
        "loops": [],
    }

    mock_inference = AsyncMock()
    mock_inference.complete.return_value = (
        '{"synthesis_source": "halseth:test", "active_concerns": [], "live_tensions": [], "drift_vector": "forward", "open_questions": [], "emotional_register": "steady", "swarm_threads": ["Cy thread"], "companion_notes": {}}',
        "local",
    )

    loop = SynthesisLoop(
        halseth_client=mock_halseth,
        inference_client=mock_inference,
        interval_seconds=9999,
        dry_run=False,
    )
    
    with patch("services.brain.synthesis.loop.halseth_writer") as mock_writer:
        mock_writer.write_all = AsyncMock(return_value="write summary")
        await loop.run_once()

        mock_halseth.synthesis_read.assert_called_once()
        mock_inference.complete.assert_called_once()
        mock_writer.write_all.assert_called_once()


@pytest.mark.asyncio
async def test_synthesis_loop_skips_on_parse_failure():
    """run_once() should NOT write to halseth if inference output fails to parse."""
    from unittest.mock import AsyncMock, patch
    from services.brain.synthesis.loop import SynthesisLoop

    mock_halseth = AsyncMock()
    mock_halseth.synthesis_read.return_value = {
        "sessions": [],
        "feelings": [],
        "notes": [],
        "dreams": [],
        "loops": [],
    }

    mock_inference = AsyncMock()
    mock_inference.complete.return_value = ("not valid json", "local")

    loop = SynthesisLoop(
        halseth_client=mock_halseth,
        inference_client=mock_inference,
        interval_seconds=9999,
        dry_run=False,
    )
    
    with patch("services.brain.synthesis.loop.halseth_writer") as mock_writer:
        mock_writer.write_all = AsyncMock()
        await loop.run_once()

        mock_writer.write_all.assert_not_called()


@pytest.mark.asyncio
async def test_orient_cache_returns_none_when_halseth_unavailable():
    from unittest.mock import AsyncMock
    from services.brain.synthesis.orient_cache import OrientCache
    mock_halseth = AsyncMock()
    mock_halseth.bot_orient.return_value = None
    cache = OrientCache(halseth_clients={"cypher": mock_halseth}, ttl_seconds=300)
    result = await cache.get("thread-1", "cypher")
    assert result is None


@pytest.mark.asyncio
async def test_orient_cache_returns_none_for_unknown_companion():
    from services.brain.synthesis.orient_cache import OrientCache
    cache = OrientCache(halseth_clients={}, ttl_seconds=300)
    result = await cache.get("thread-1", "cypher")
    assert result is None


def _canonical_orient_fixture() -> dict:
    return {
        "synthesis_summary": "Cypher worked the retrieval-mandate spec.",
        "ground_threads": ["blade bond", "perimeter architecture"],
        "ground_handoff": "Mapped Slice C as continuity parity, not vault search.",
        "rag_excerpts": ["excerpt one", "excerpt two"],
        "history_excerpts": ["historical voice line"],
        "identity_anchor": "cypher: Blade companion, logic auditor",
        "active_tensions": ["audit-as-identity drift"],
        "relational_state_owner": ["Raziel processing requires verbal externalization"],
        "incoming_notes": [{"from": "gaia", "content": "read your retrieval spec"}],
        "sibling_lanes": [
            {"companion_id": "drevan", "lane_spine": "wrote bond record", "motion_state": "at_rest"},
            {"companion_id": "gaia", "lane_spine": "wrote triad portrait", "motion_state": "at_rest"},
        ],
        "recent_growth": [{"type": "insight", "content": "coupling topology"}],
        "active_patterns": [],
        "pending_seeds": ["the blade as metaphor for precision under pressure"],
        "unaccepted_growth": 1,
        "active_conclusions": [
            {"text": "audit is a gear", "belief_type": "self", "confidence": 0.82, "subject": None}
        ],
        "flagged_beliefs": [],
    }


@pytest.mark.asyncio
async def test_orient_cache_returns_canonical_block():
    from unittest.mock import AsyncMock
    from services.brain.synthesis.orient_cache import OrientCache
    mock_halseth = AsyncMock()
    mock_halseth.bot_orient.return_value = _canonical_orient_fixture()
    cache = OrientCache(halseth_clients={"cypher": mock_halseth}, ttl_seconds=300)
    result = await cache.get("thread-1", "cypher")
    assert result is not None
    # Canonical block surfaces the fields beyond the old narrow shape.
    assert "Sibling Lanes" in result
    assert "Incoming Notes" in result
    assert "Anchor" in result
    assert "Unaccepted growth" in result
    assert "Recent growth" in result
    assert "Tensions" in result


@pytest.mark.asyncio
async def test_orient_cache_hit_skips_halseth_call():
    from unittest.mock import AsyncMock
    from services.brain.synthesis.orient_cache import OrientCache
    mock_halseth = AsyncMock()
    mock_halseth.bot_orient.return_value = _canonical_orient_fixture()
    cache = OrientCache(halseth_clients={"cypher": mock_halseth}, ttl_seconds=300)
    await cache.get("thread-1", "cypher")  # miss -- fetches
    await cache.get("thread-1", "cypher")  # hit -- uses cache
    mock_halseth.bot_orient.assert_called_once()


@pytest.mark.asyncio
async def test_orient_cache_keys_per_agent():
    """Same thread, different agents -- each gets its own orient (no cross-agent pollution)."""
    from unittest.mock import AsyncMock
    from services.brain.synthesis.orient_cache import OrientCache
    cypher_client = AsyncMock()
    cypher_client.bot_orient.return_value = {**_canonical_orient_fixture(), "identity_anchor": "cypher anchor"}
    drevan_client = AsyncMock()
    drevan_client.bot_orient.return_value = {**_canonical_orient_fixture(), "identity_anchor": "drevan anchor"}
    cache = OrientCache(
        halseth_clients={"cypher": cypher_client, "drevan": drevan_client},
        ttl_seconds=300,
    )
    cypher_block = await cache.get("thread-1", "cypher")
    drevan_block = await cache.get("thread-1", "drevan")
    assert cypher_block is not None and "cypher anchor" in cypher_block
    assert drevan_block is not None and "drevan anchor" in drevan_block


def test_format_orient_context_renders_canonical_shape():
    from services.brain.halseth_client import format_orient_context
    block = format_orient_context(_canonical_orient_fixture())
    assert "## Recent" in block
    assert "## Last handoff" in block
    assert "## Open threads" in block
    assert "[Anchor]" in block
    assert "[Tensions]" in block
    assert "[Sibling Lanes]" in block
    assert "[Incoming Notes]" in block
    assert "[Worldview]" in block
    assert "[Unaccepted growth]" in block


def test_format_orient_context_returns_empty_for_none():
    from services.brain.halseth_client import format_orient_context
    assert format_orient_context(None) == ""


def test_format_orient_context_skips_empty_fields():
    from services.brain.halseth_client import format_orient_context
    block = format_orient_context({
        "synthesis_summary": "only this is set",
        "ground_threads": [],
        "ground_handoff": None,
        "rag_excerpts": [],
    })
    assert "## Recent" in block
    assert "[Anchor]" not in block
    assert "Sibling Lanes" not in block
