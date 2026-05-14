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


@pytest.mark.asyncio
async def test_write_companion_note_uses_correct_client():
    from unittest.mock import AsyncMock, MagicMock
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

    mock_drevan = MagicMock()
    mock_drevan.add_companion_note = AsyncMock()
    mock_cypher = MagicMock()
    mock_cypher.add_companion_note = AsyncMock()

    ev = SwarmEvaluator(CompanionCooldown(), halseth_clients={"drevan": mock_drevan, "cypher": mock_cypher})
    await ev._write_companion_note("drevan", "ch-test", "hello from drevan")

    mock_drevan.add_companion_note.assert_called_once()
    mock_cypher.add_companion_note.assert_not_called()
    assert "ch-test" in mock_drevan.add_companion_note.call_args[0][0]


@pytest.mark.asyncio
async def test_write_companion_note_unknown_companion_is_noop():
    from unittest.mock import AsyncMock, MagicMock
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

    mock_cypher = MagicMock()
    mock_cypher.add_companion_note = AsyncMock()

    ev = SwarmEvaluator(CompanionCooldown(), halseth_clients={"cypher": mock_cypher})
    await ev._write_companion_note("gaia", "ch-test", "gaia reply")

    mock_cypher.add_companion_note.assert_not_called()


# ── Slice B: routing split tests ──────────────────────────────────────────────

def test_parse_routing_valid():
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
    ev = SwarmEvaluator(CompanionCooldown())
    companions = ["drevan", "cypher", "gaia"]
    raw = '{"drevan": true, "cypher": false, "gaia": true}'
    result = ev._parse_routing(raw, companions)
    assert result == {"drevan": True, "cypher": False, "gaia": True}


def test_parse_routing_malformed_fails_open():
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
    ev = SwarmEvaluator(CompanionCooldown())
    companions = ["drevan", "cypher", "gaia"]
    result = ev._parse_routing("not json at all", companions)
    assert all(v is True for v in result.values())


def test_parse_routing_strips_markdown():
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
    ev = SwarmEvaluator(CompanionCooldown())
    companions = ["drevan", "cypher"]
    raw = '```json\n{"drevan": true, "cypher": false}\n```'
    result = ev._parse_routing(raw, companions)
    assert result == {"drevan": True, "cypher": False}


@pytest.mark.asyncio
async def test_routing_silenced_companion_skips_inference():
    from unittest.mock import MagicMock
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

    cd = CompanionCooldown(cooldown_s=60.0)
    cd.mark_posted("drevan", "ch-test")  # drevan on cooldown

    ev = SwarmEvaluator(cd, identity_loader=MagicMock())

    inference_calls = []

    async def fake_routing(prompt):
        return '{"drevan": true, "cypher": false, "gaia": true}'

    async def fake_infer(companion_id, pkt, prior_replies=None):
        inference_calls.append(companion_id)
        return f"{companion_id} reply"

    ev._call_routing = fake_routing
    ev._infer_companion = fake_infer

    packet = _make_packet()
    reply = await ev.evaluate(packet)

    # drevan cooled, cypher routed false -- only gaia should infer
    assert "drevan" not in inference_calls
    assert "cypher" not in inference_calls
    assert "gaia" in inference_calls
    assert reply.responses["drevan"] is None
    assert reply.responses["cypher"] is None
    assert reply.responses["gaia"] == "gaia reply"


@pytest.mark.asyncio
async def test_inference_exception_doesnt_blank_others():
    from unittest.mock import MagicMock
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

    ev = SwarmEvaluator(CompanionCooldown(), identity_loader=MagicMock())

    async def fake_routing(prompt):
        return '{"drevan": true, "cypher": true, "gaia": true}'

    async def fake_infer(companion_id, pkt, prior_replies=None):
        if companion_id == "cypher":
            raise RuntimeError("API timeout")
        return f"{companion_id} reply"

    ev._call_routing = fake_routing
    ev._infer_companion = fake_infer

    packet = _make_packet()
    reply = await ev.evaluate(packet)

    assert reply.responses["drevan"] == "drevan reply"
    assert reply.responses["cypher"] is None  # exception -> None
    assert reply.responses["gaia"] == "gaia reply"


# ── Routing prompt: addressed_companion ───────────────────────────────────────

def test_routing_prompt_includes_addressed_companion():
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
    ev = SwarmEvaluator(CompanionCooldown())
    companions = ["drevan", "cypher", "gaia"]
    packet = _make_packet(metadata={"channel_id": "ch-test", "history": [], "addressed_companion": "drevan"})
    prompt = ev._build_routing_prompt(packet, companions)
    assert "drevan must be true" in prompt


def test_routing_prompt_no_address_no_hint():
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
    ev = SwarmEvaluator(CompanionCooldown())
    companions = ["drevan", "cypher", "gaia"]
    packet = _make_packet(metadata={"channel_id": "ch-test", "history": []})
    prompt = ev._build_routing_prompt(packet, companions)
    assert "must be true" not in prompt


def test_routing_prompt_addressed_suppresses_depth_bias():
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
    ev = SwarmEvaluator(CompanionCooldown())
    companions = ["drevan", "cypher", "gaia"]
    packet = _make_packet(
        depth=3,
        metadata={"channel_id": "ch-test", "history": [], "addressed_companion": "drevan"},
    )
    prompt = ev._build_routing_prompt(packet, companions)
    assert "drevan must be true" in prompt
    assert "Strongly prefer false" not in prompt


# ── Sequential inference + peer context ──────────────────────────────────────

def test_determine_order_addressed_first():
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
    ev = SwarmEvaluator(CompanionCooldown())
    packet = _make_packet(metadata={"channel_id": "ch-test", "history": [], "addressed_companion": "cypher,drevan"})
    order = ev._determine_order(packet, ["drevan", "cypher", "gaia"])
    # addressed companions first in parse order, gaia ambient last
    assert order[0] == "cypher"
    assert order[1] == "drevan"
    assert "gaia" in order


def test_determine_order_drevan_tiebreaker():
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
    ev = SwarmEvaluator(CompanionCooldown())
    # Message with no lane keywords -- drevan should lead ambient group
    packet = _make_packet(message="xyz abc", metadata={"channel_id": "ch-test", "history": []})
    order = ev._determine_order(packet, ["cypher", "drevan", "gaia"])
    assert order[0] == "drevan"


def test_determine_order_cypher_leads_on_scored_message():
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
    ev = SwarmEvaluator(CompanionCooldown())
    # "debugging" appears literally in cypher's VOICE_SUMMARIES; drevan scores 0 -- cypher must lead
    packet = _make_packet(message="help me with debugging this", metadata={"channel_id": "ch-test", "history": []})
    order = ev._determine_order(packet, ["drevan", "cypher", "gaia"])
    assert order[0] == "cypher"


@pytest.mark.asyncio
async def test_sequential_inference_order_respected():
    from unittest.mock import MagicMock
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

    ev = SwarmEvaluator(CompanionCooldown(), identity_loader=MagicMock())
    call_order = []

    async def fake_routing(prompt):
        return '{"drevan": true, "cypher": true, "gaia": false}'

    async def fake_infer(companion_id, pkt, prior_replies=None):
        call_order.append(companion_id)
        return f"{companion_id} reply"

    ev._call_routing = fake_routing
    ev._infer_companion = fake_infer

    # address cypher first so cypher leads
    packet = _make_packet(
        metadata={"channel_id": "ch-test", "history": [], "addressed_companion": "cypher"}
    )
    reply = await ev.evaluate(packet)

    assert call_order[0] == "cypher"
    assert "drevan" in call_order
    assert "gaia" not in call_order
    assert reply.priority_order[0] == "cypher"


@pytest.mark.asyncio
async def test_peer_context_injected_for_second_companion():
    from unittest.mock import MagicMock
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

    ev = SwarmEvaluator(CompanionCooldown(), identity_loader=MagicMock())
    received_prior: dict = {}

    async def fake_routing(prompt):
        return '{"drevan": true, "cypher": true, "gaia": false}'

    async def fake_infer(companion_id, pkt, prior_replies=None):
        received_prior[companion_id] = list(prior_replies) if prior_replies else None
        return f"{companion_id} reply"

    ev._call_routing = fake_routing
    ev._infer_companion = fake_infer

    packet = _make_packet(
        metadata={"channel_id": "ch-test", "history": [], "addressed_companion": "drevan,cypher"}
    )
    await ev.evaluate(packet)

    # drevan is first -- no prior context
    assert received_prior.get("drevan") is None
    # cypher is second -- should see drevan's reply
    assert received_prior.get("cypher") is not None
    assert received_prior["cypher"][0][0] == "drevan"
    assert received_prior["cypher"][0][1] == "drevan reply"


@pytest.mark.asyncio
async def test_sequential_exception_doesnt_block_next_or_lose_prior():
    from unittest.mock import MagicMock
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

    ev = SwarmEvaluator(CompanionCooldown(), identity_loader=MagicMock())
    received_prior: dict = {}

    async def fake_routing(prompt):
        return '{"drevan": true, "cypher": true, "gaia": true}'

    async def fake_infer(companion_id, pkt, prior_replies=None):
        received_prior[companion_id] = list(prior_replies) if prior_replies else None
        if companion_id == "cypher":
            raise RuntimeError("timeout")
        return f"{companion_id} reply"

    ev._call_routing = fake_routing
    ev._infer_companion = fake_infer

    # drevan leads, cypher second (throws), gaia third
    packet = _make_packet(
        metadata={"channel_id": "ch-test", "history": [], "addressed_companion": "drevan,cypher"}
    )
    reply = await ev.evaluate(packet)

    assert reply.responses["drevan"] == "drevan reply"
    assert reply.responses["cypher"] is None  # threw
    assert reply.responses["gaia"] == "gaia reply"
    # gaia only sees drevan's reply (cypher threw, so no cypher entry in prior_replies)
    assert received_prior["gaia"] is not None
    peer_ids = [pid for pid, _ in received_prior["gaia"]]
    assert "drevan" in peer_ids
    assert "cypher" not in peer_ids


@pytest.mark.asyncio
async def test_priority_order_in_swarm_reply():
    from unittest.mock import MagicMock
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

    ev = SwarmEvaluator(CompanionCooldown(), identity_loader=MagicMock())

    async def fake_routing(prompt):
        return '{"drevan": true, "cypher": true, "gaia": false}'

    async def fake_infer(companion_id, pkt, prior_replies=None):
        return f"{companion_id} reply"

    ev._call_routing = fake_routing
    ev._infer_companion = fake_infer

    packet = _make_packet(
        metadata={"channel_id": "ch-test", "history": [], "addressed_companion": "cypher,drevan"}
    )
    reply = await ev.evaluate(packet)

    assert reply.priority_order == ["cypher", "drevan"]


@pytest.mark.asyncio
async def test_priority_order_empty_when_no_active():
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
    ev = SwarmEvaluator(CompanionCooldown())

    async def fake_routing(prompt):
        return '{"drevan": false, "cypher": false, "gaia": false}'

    ev._call_routing = fake_routing
    packet = _make_packet()
    reply = await ev.evaluate(packet)

    assert reply.priority_order == []
