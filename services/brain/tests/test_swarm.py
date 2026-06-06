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
from services.brain.agents.evaluator import SwarmEvaluator, MAX_DEPTH
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
    packet = _make_packet(depth=MAX_DEPTH)  # at/over the cap -> all-null (cap-relative, won't rot)
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
    mock_drevan.write_continuity_note = AsyncMock()
    mock_cypher = MagicMock()
    mock_cypher.add_companion_note = AsyncMock()
    mock_cypher.write_continuity_note = AsyncMock()

    ev = SwarmEvaluator(CompanionCooldown(), halseth_clients={"drevan": mock_drevan, "cypher": mock_cypher})
    await ev._write_companion_note("drevan", "ch-test", "hello from drevan")

    mock_drevan.add_companion_note.assert_called_once()
    mock_cypher.add_companion_note.assert_not_called()
    assert "ch-test" in mock_drevan.add_companion_note.call_args[0][0]


@pytest.mark.asyncio
async def test_write_companion_note_bridges_to_continuity_note():
    # Finding 2: each responding companion's reply must ALSO land in their own
    # high-salience wm_continuity_notes so Claude.ai orient (which ignores
    # companion_journal) can surface it at the companion's next boot.
    from unittest.mock import AsyncMock, MagicMock
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

    mock_drevan = MagicMock()
    mock_drevan.add_companion_note = AsyncMock()
    mock_drevan.write_continuity_note = AsyncMock()

    ev = SwarmEvaluator(CompanionCooldown(), halseth_clients={"drevan": mock_drevan})
    await ev._write_companion_note("drevan", "ch-99", "the spiral held")

    mock_drevan.write_continuity_note.assert_called_once()
    kwargs = mock_drevan.write_continuity_note.call_args.kwargs
    assert kwargs["agent_id"] == "drevan"
    assert kwargs["salience"] == "high"            # orient only reads high-salience notes
    assert kwargs["source"] == "discord_swarm"
    assert kwargs["thread_key"] == "discord_swarm:ch-99"  # distinct from bot pulse key
    assert "the spiral held" in kwargs["content"]


@pytest.mark.asyncio
async def test_continuity_note_failure_does_not_block_companion_note():
    # The two writes are independent: a continuity-note failure must not swallow
    # the companion_journal write (and vice versa).
    from unittest.mock import AsyncMock, MagicMock
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

    mock = MagicMock()
    mock.add_companion_note = AsyncMock()
    mock.write_continuity_note = AsyncMock(side_effect=RuntimeError("halseth 500"))

    ev = SwarmEvaluator(CompanionCooldown(), halseth_clients={"gaia": mock})
    # Should not raise despite the continuity write throwing.
    await ev._write_companion_note("gaia", "ch-1", "witnessed")

    mock.add_companion_note.assert_called_once()
    mock.write_continuity_note.assert_called_once()


@pytest.mark.asyncio
async def test_write_companion_note_unknown_companion_is_noop():
    from unittest.mock import AsyncMock, MagicMock
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

    mock_cypher = MagicMock()
    mock_cypher.add_companion_note = AsyncMock()
    mock_cypher.write_continuity_note = AsyncMock()

    ev = SwarmEvaluator(CompanionCooldown(), halseth_clients={"cypher": mock_cypher})
    await ev._write_companion_note("gaia", "ch-test", "gaia reply")

    mock_cypher.add_companion_note.assert_not_called()
    mock_cypher.write_continuity_note.assert_not_called()


# ── Slice B: routing split tests ──────────────────────────────────────────────

def test_parse_routing_valid():
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
    ev = SwarmEvaluator(CompanionCooldown())
    companions = ["drevan", "cypher", "gaia"]
    raw = '{"drevan": true, "cypher": false, "gaia": true}'
    result = ev._parse_routing(raw, companions)
    assert result == {"drevan": True, "cypher": False, "gaia": True}


def test_parse_routing_malformed_fails_closed_to_one():
    # Finding 5: malformed routing must NOT make all three speak. With no packet
    # context, fall back to a single default (Drevan, widest lane).
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
    ev = SwarmEvaluator(CompanionCooldown())
    companions = ["drevan", "cypher", "gaia"]
    result = ev._parse_routing("not json at all", companions)
    assert result == {"drevan": True, "cypher": False, "gaia": False}


def test_parse_routing_malformed_prefers_addressed():
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
    ev = SwarmEvaluator(CompanionCooldown())
    companions = ["drevan", "cypher", "gaia"]
    packet = _make_packet(metadata={"channel_id": "ch", "history": [], "addressed_companion": "gaia"})
    result = ev._parse_routing("garbage", companions, packet)
    assert result == {"drevan": False, "cypher": False, "gaia": True}


def test_parse_routing_malformed_falls_to_lane_match():
    # "debugging" is in cypher's VOICE_SUMMARIES -> cypher alone, not a pile-on.
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
    ev = SwarmEvaluator(CompanionCooldown())
    companions = ["drevan", "cypher", "gaia"]
    packet = _make_packet(message="help me with debugging this", metadata={"channel_id": "ch", "history": []})
    result = ev._parse_routing("not json", companions, packet)
    assert result["cypher"] is True
    assert sum(1 for v in result.values() if v) == 1


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


# ── Finding 1: bot-assembled system prompt + temperature passthrough ──────────


def _make_infer_evaluator():
    """SwarmEvaluator whose identity loader returns a sentinel system prompt,
    so tests can tell identity-loader output apart from metadata passthrough."""
    from unittest.mock import MagicMock
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
    loader = MagicMock()
    loader.load_identity.return_value = (MagicMock(), "v1")
    loader.construct_prompt_context.return_value = "IDENTITY_LOADER_PROMPT"
    return SwarmEvaluator(CompanionCooldown(), identity_loader=loader)


def _capture_post(ev):
    """Patch the inference HTTP client; return a dict that captures the last
    request body so the system prompt + temperature sent can be asserted."""
    from unittest.mock import AsyncMock, MagicMock
    captured: dict = {}

    async def fake_post(url, headers=None, json=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value={"choices": [{"message": {"content": "ok reply"}}]})
        return resp

    ev._inference_http.post = AsyncMock(side_effect=fake_post)
    return captured


@pytest.mark.asyncio
async def test_infer_uses_bot_system_prompt_for_sender():
    ev = _make_infer_evaluator()
    captured = _capture_post(ev)
    packet = _make_packet(
        agent_id="cypher",
        metadata={
            "channel_id": "ch-test",
            "history": [],
            "system_prompt": "BOT_ASSEMBLED_WITH_SOMA",
            "temperature": 0.95,
        },
    )
    await ev._infer_companion("cypher", packet)
    system_sent = captured["json"]["messages"][0]["content"]
    assert "BOT_ASSEMBLED_WITH_SOMA" in system_sent
    assert "IDENTITY_LOADER_PROMPT" not in system_sent
    # dynamic temperature from the bot is honored, not the static companion temp
    assert captured["json"]["temperature"] == 0.95


@pytest.mark.asyncio
async def test_infer_ignores_bot_prompt_for_peer_companion():
    # Packet sent by cypher; drevan is a peer in the swarm and must NOT inherit
    # cypher's sender-specific assembled prompt (wrong identity + SOMA).
    ev = _make_infer_evaluator()
    captured = _capture_post(ev)
    packet = _make_packet(
        agent_id="cypher",
        metadata={
            "channel_id": "ch-test",
            "history": [],
            "system_prompt": "CYPHER_ASSEMBLED_PROMPT",
            "temperature": 0.95,
        },
    )
    await ev._infer_companion("drevan", packet)
    system_sent = captured["json"]["messages"][0]["content"]
    assert "IDENTITY_LOADER_PROMPT" in system_sent
    assert "CYPHER_ASSEMBLED_PROMPT" not in system_sent
    # peer falls back to its own static temperature, not the sender's dynamic one
    assert captured["json"]["temperature"] == ev._companion_temps["drevan"]


@pytest.mark.asyncio
async def test_infer_falls_back_to_identity_loader_without_metadata_prompt():
    ev = _make_infer_evaluator()
    captured = _capture_post(ev)
    packet = _make_packet(agent_id="cypher", metadata={"channel_id": "ch-test", "history": []})
    await ev._infer_companion("cypher", packet)
    system_sent = captured["json"]["messages"][0]["content"]
    assert "IDENTITY_LOADER_PROMPT" in system_sent


@pytest.mark.asyncio
async def test_infer_sender_prompt_still_gets_triad_context():
    # Passthrough must not drop the sequential peer block.
    ev = _make_infer_evaluator()
    captured = _capture_post(ev)
    packet = _make_packet(
        agent_id="cypher",
        metadata={"channel_id": "ch-test", "history": [], "system_prompt": "BOT_PROMPT"},
    )
    await ev._infer_companion("cypher", packet, prior_replies=[("drevan", "drevan said this")])
    system_sent = captured["json"]["messages"][0]["content"]
    assert "BOT_PROMPT" in system_sent
    assert "TRIAD CONTEXT" in system_sent
    assert "drevan said this" in system_sent


# ── Finding 3: orient parity for swarm peers ──────────────────────────────────


@pytest.mark.asyncio
async def test_peer_companion_gets_orient_injected():
    from unittest.mock import AsyncMock, MagicMock
    ev = _make_infer_evaluator()
    captured = _capture_post(ev)
    cache = MagicMock()
    cache.get = AsyncMock(return_value="ORIENT_BLOCK_FOR_DREVAN")
    ev._orient_cache = cache

    # Packet sent by cypher; drevan is a peer built from identity -> should get orient.
    packet = _make_packet(agent_id="cypher", thread_id="ch-7", metadata={"channel_id": "ch-7", "history": []})
    await ev._infer_companion("drevan", packet)

    system_sent = captured["json"]["messages"][0]["content"]
    assert "IDENTITY_LOADER_PROMPT" in system_sent
    assert "ORIENT_BLOCK_FOR_DREVAN" in system_sent
    cache.get.assert_awaited_once_with("ch-7", "drevan")


@pytest.mark.asyncio
async def test_sender_with_bot_prompt_skips_orient_injection():
    # The sender's bot-assembled prompt already carries orient; re-injecting would dup.
    from unittest.mock import AsyncMock, MagicMock
    ev = _make_infer_evaluator()
    captured = _capture_post(ev)
    cache = MagicMock()
    cache.get = AsyncMock(return_value="ORIENT_BLOCK")
    ev._orient_cache = cache

    packet = _make_packet(
        agent_id="cypher",
        metadata={"channel_id": "ch", "history": [], "system_prompt": "BOT_PROMPT"},
    )
    await ev._infer_companion("cypher", packet)

    system_sent = captured["json"]["messages"][0]["content"]
    assert "BOT_PROMPT" in system_sent
    assert "ORIENT_BLOCK" not in system_sent
    cache.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_orient_injection_failure_is_non_fatal():
    from unittest.mock import AsyncMock, MagicMock
    ev = _make_infer_evaluator()
    captured = _capture_post(ev)
    cache = MagicMock()
    cache.get = AsyncMock(side_effect=RuntimeError("halseth down"))
    ev._orient_cache = cache

    packet = _make_packet(agent_id="cypher", metadata={"channel_id": "ch", "history": []})
    # Must still post (inference proceeds without orient), not raise.
    await ev._infer_companion("gaia", packet)

    system_sent = captured["json"]["messages"][0]["content"]
    assert "IDENTITY_LOADER_PROMPT" in system_sent


# ── Finding 4a: per-companion provider routing in the swarm ───────────────────


@pytest.mark.asyncio
async def test_infer_routes_companion_to_kimi():
    ev = _make_infer_evaluator()
    captured = _capture_post(ev)
    # Cypher configured for Kimi, key present.
    ev._companion_model_keys["cypher"] = "kimi-k2"
    ev._providers.keys["kimi"] = "test-kimi-key"

    packet = _make_packet(agent_id="cypher", metadata={"channel_id": "ch", "history": []})
    await ev._infer_companion("cypher", packet)

    assert captured["url"] == "https://api.moonshot.cn/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-kimi-key"
    assert captured["json"]["model"] == "kimi-k2"


@pytest.mark.asyncio
async def test_infer_falls_back_to_deepseek_when_provider_unconfigured():
    ev = _make_infer_evaluator()
    captured = _capture_post(ev)
    # Gaia configured for Kimi but NO kimi key -> must fall back to deepseek, not mute.
    ev._companion_model_keys["gaia"] = "kimi-k2"
    ev._providers.keys["kimi"] = None

    packet = _make_packet(agent_id="cypher", metadata={"channel_id": "ch", "history": []})
    await ev._infer_companion("gaia", packet)

    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["json"]["model"] == "deepseek-chat"


# ── Live model switching from Discord (cy: model <key>) ───────────────────────


def _client_with_model(model_key):
    from unittest.mock import AsyncMock, MagicMock
    c = MagicMock()
    c.get_active_model = AsyncMock(return_value=model_key)
    return c


@pytest.mark.asyncio
async def test_effective_model_key_honors_discord_override():
    ev = _make_infer_evaluator()
    ev._halseth_clients = {"cypher": _client_with_model("kimi-k2")}
    assert await ev._effective_model_key("cypher") == "kimi-k2"


@pytest.mark.asyncio
async def test_effective_model_key_falls_back_to_env_on_no_override():
    ev = _make_infer_evaluator()
    ev._halseth_clients = {"cypher": _client_with_model(None)}
    ev._companion_model_keys["cypher"] = "deepseek-chat"
    assert await ev._effective_model_key("cypher") == "deepseek-chat"


@pytest.mark.asyncio
async def test_effective_model_key_ignores_unknown_override():
    # A stale / bogus active_model must not silently route to a raw deepseek model.
    ev = _make_infer_evaluator()
    ev._halseth_clients = {"cypher": _client_with_model("not-a-real-key")}
    ev._companion_model_keys["cypher"] = "deepseek-chat"
    assert await ev._effective_model_key("cypher") == "deepseek-chat"


@pytest.mark.asyncio
async def test_active_model_lookup_is_cached():
    ev = _make_infer_evaluator()
    client = _client_with_model("kimi-k2")
    ev._halseth_clients = {"cypher": client}
    await ev._effective_model_key("cypher")
    await ev._effective_model_key("cypher")
    client.get_active_model.assert_awaited_once()  # second call served from cache


@pytest.mark.asyncio
async def test_discord_override_routes_inference_to_kimi():
    # End-to-end: Halseth says cypher=kimi-k2, key present -> swarm inference hits Kimi,
    # overriding the env default (deepseek). This is `cy: model kimi-k2` taking effect live.
    ev = _make_infer_evaluator()
    captured = _capture_post(ev)
    ev._providers.keys["kimi"] = "test-kimi-key"
    ev._halseth_clients = {"cypher": _client_with_model("kimi-k2")}

    packet = _make_packet(agent_id="cypher", metadata={"channel_id": "ch", "history": []})
    await ev._infer_companion("cypher", packet)

    assert captured["url"] == "https://api.moonshot.cn/v1/chat/completions"
    assert captured["json"]["model"] == "kimi-k2"


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


# ── /model force-clear + /status support (Discord slash commands) ─────────────

def test_invalidate_model_cache_clears_entry():
    import time as _t
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
    ev = SwarmEvaluator(CompanionCooldown())
    # Seed a live cache entry as if a prior eval had read Halseth.
    ev._model_cache["cypher"] = (_t.monotonic() + 999, "kimi-k2")

    assert ev.invalidate_model_cache("cypher") is True   # cleared
    assert "cypher" not in ev._model_cache
    assert ev.invalidate_model_cache("cypher") is False  # nothing left to clear


@pytest.mark.asyncio
async def test_model_status_reports_effective_and_cache_flag():
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
    ev = SwarmEvaluator(CompanionCooldown())
    # No halseth client -> override read is a no-op miss; effective key is the default.
    status = await ev.model_status("cypher")
    assert status["companion_id"] == "cypher"
    assert isinstance(status["active_model"], str) and status["active_model"]
    # No halseth client -> no override read, no cache entry written.
    assert status["cached"] is False
    assert status["ttl_remaining_s"] == 0.0
