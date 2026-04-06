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
    """run_once() should call halseth, inference, and webmind in sequence."""
    from unittest.mock import AsyncMock
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

    mock_webmind = AsyncMock()
    mock_webmind.write_limbic_state.return_value = {"state_id": "abc-123"}

    loop = SynthesisLoop(
        halseth_client=mock_halseth,
        inference_client=mock_inference,
        webmind_client=mock_webmind,
        interval_seconds=9999,
    )
    await loop.run_once()

    mock_halseth.synthesis_read.assert_called_once()
    mock_inference.complete.assert_called_once()
    mock_webmind.write_limbic_state.assert_called_once()


@pytest.mark.asyncio
async def test_synthesis_loop_skips_on_parse_failure():
    """run_once() should NOT write to webmind if inference output fails to parse."""
    from unittest.mock import AsyncMock
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

    mock_webmind = AsyncMock()

    loop = SynthesisLoop(
        halseth_client=mock_halseth,
        inference_client=mock_inference,
        webmind_client=mock_webmind,
        interval_seconds=9999,
    )
    await loop.run_once()

    mock_webmind.write_limbic_state.assert_not_called()
