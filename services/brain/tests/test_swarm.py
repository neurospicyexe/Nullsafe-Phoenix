import pytest
import asyncio
import tempfile
import os
import textwrap

from services.brain.config.channel_config import load_channel_config, get_companions_for_channel


def _write_config(content: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    f.write(textwrap.dedent(content))
    f.close()
    return f.name


def test_default_channel_returns_all():
    path = _write_config("""
        defaults:
          companions: [drevan, cypher, gaia]
        channels: {}
    """)
    load_channel_config(path)
    assert get_companions_for_channel("unknown") == ["drevan", "cypher", "gaia"]
    os.unlink(path)


def test_restricted_channel():
    path = _write_config("""
        defaults:
          companions: [drevan, cypher, gaia]
        channels:
          "ch_drevan_only":
            companions: [drevan]
            label: test
    """)
    load_channel_config(path)
    assert get_companions_for_channel("ch_drevan_only") == ["drevan"]
    assert get_companions_for_channel("other") == ["drevan", "cypher", "gaia"]
    os.unlink(path)


from services.brain.agents.dedup import MessageDedup


@pytest.mark.asyncio
async def test_dedup_leader_follower():
    dedup = MessageDedup()
    is_leader1, fut1 = await dedup.get_or_start("msg-abc")
    is_leader2, fut2 = await dedup.get_or_start("msg-abc")

    assert is_leader1 is True
    assert is_leader2 is False
    assert fut1 is fut2


@pytest.mark.asyncio
async def test_dedup_different_messages():
    dedup = MessageDedup()
    is_leader1, _ = await dedup.get_or_start("msg-1")
    is_leader2, _ = await dedup.get_or_start("msg-2")

    assert is_leader1 is True
    assert is_leader2 is True


@pytest.mark.asyncio
async def test_dedup_result_propagation():
    dedup = MessageDedup()
    is_leader, fut = await dedup.get_or_start("msg-xyz")
    _, fut2 = await dedup.get_or_start("msg-xyz")

    sentinel = object()
    fut.set_result(sentinel)
    result = await asyncio.wait_for(fut2, timeout=1.0)
    assert result is sentinel


from services.brain.agents.cooldown import CompanionCooldown


def test_cooldown_blocks_within_window():
    cd = CompanionCooldown(cooldown_s=60.0)
    cd.mark_posted("cypher", "ch1")
    assert cd.is_cooling("cypher", "ch1") is True
    assert cd.is_cooling("drevan", "ch1") is False


def test_cooldown_apply_nulls_cooling_companion():
    cd = CompanionCooldown(cooldown_s=60.0)
    cd.mark_posted("cypher", "ch1")
    responses = {"drevan": "hello", "cypher": "hi", "gaia": None}
    result = cd.apply(responses, "ch1")
    assert result["cypher"] is None
    assert result["drevan"] == "hello"
    assert result["gaia"] is None


def test_cooldown_marks_posted_on_reply():
    cd = CompanionCooldown(cooldown_s=60.0)
    responses = {"drevan": "something", "cypher": None}
    cd.apply(responses, "ch2")
    assert cd.is_cooling("drevan", "ch2") is True
    assert cd.is_cooling("cypher", "ch2") is False


import uuid
import datetime
from services.brain.agents.evaluator import SwarmEvaluator
from shared.contracts import ThoughtPacket


def _make_packet(**kwargs) -> ThoughtPacket:
    defaults = dict(
        packet_id=str(uuid.uuid4()),
        timestamp=datetime.datetime.utcnow().isoformat(),
        source="discord",
        user_id="u1",
        thread_id="ch-test",
        agent_id="cypher",
        message="hello swarm",
        metadata={"channel_id": "ch-test", "history": []},
    )
    defaults.update(kwargs)
    return ThoughtPacket(**defaults)


@pytest.mark.asyncio
async def test_evaluator_depth_cap_returns_all_null():
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
    cd = CompanionCooldown()
    ev = SwarmEvaluator(cd)
    packet = _make_packet(depth=3)
    reply = await ev.evaluate(packet)
    assert all(v is None for v in reply.responses.values())
    assert reply.status == "ok"


def test_evaluator_parse_responses_valid():
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
    cd = CompanionCooldown()
    ev = SwarmEvaluator(cd)
    raw = '{"drevan": "something real", "cypher": null, "gaia": "witness"}'
    result = ev._parse_responses(raw, ["drevan", "cypher", "gaia"])
    assert result["drevan"] == "something real"
    assert result["cypher"] is None
    assert result["gaia"] == "witness"


def test_evaluator_parse_responses_malformed():
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
    cd = CompanionCooldown()
    ev = SwarmEvaluator(cd)
    raw = "this is not json at all"
    result = ev._parse_responses(raw, ["drevan", "cypher", "gaia"])
    assert all(v is None for v in result.values())


def test_evaluator_parse_strips_markdown():
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
    cd = CompanionCooldown()
    ev = SwarmEvaluator(cd)
    raw = '```json\n{"drevan": "hi", "cypher": null, "gaia": null}\n```'
    result = ev._parse_responses(raw, ["drevan", "cypher", "gaia"])
    assert result["drevan"] == "hi"
