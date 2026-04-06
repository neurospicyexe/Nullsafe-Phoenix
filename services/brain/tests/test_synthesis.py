#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
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
