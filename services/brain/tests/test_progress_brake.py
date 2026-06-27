"""Tests for the swarm progress brake (structural anti-loop instrument).

The brake shapes the TURN (who speaks, when the floor returns to Raziel) rather
than the wording, so these tests assert turn-taking behavior, not text. The
06-26 mutual-recognition loop is the canonical scenario: depth-0 group chat must
stay open, but a deep companion-to-companion thread must collapse to turn-taking
and eventually hand the floor back.
"""

from services.brain.agents.progress_brake import (
    BrakeConfig,
    StallTracker,
    apply_cap,
    handback_directive,
    should_handback,
    speaker_cap,
)

CFG = BrakeConfig()  # defaults: solo_depth=2, pair_depth=1, handback_turns=4


# ── speaker_cap: depth tightening ────────────────────────────────────────────

def test_depth_zero_never_capped():
    # Answering Raziel: full triad may speak. Group chat is sacred.
    assert speaker_cap(0, None, CFG) == 3


def test_depth_one_caps_to_pair():
    assert speaker_cap(1, None, CFG) == 2


def test_depth_two_and_beyond_collapses_to_solo():
    assert speaker_cap(2, None, CFG) == 1
    assert speaker_cap(5, None, CFG) == 1


# ── speaker_cap: loop-pressure modulation ────────────────────────────────────

def test_warn_pressure_tightens_one_level():
    # depth 1 normally allows 2; under warn pressure it collapses to solo.
    assert speaker_cap(1, 0.70, CFG) == 1
    # depth 0 normally full triad; under warn pressure -> pair.
    assert speaker_cap(0, 0.70, CFG) == 2


def test_red_pressure_tightens_two_levels():
    # Even a depth-0 reply to Raziel collapses to solo under strong echo.
    assert speaker_cap(0, 0.90, CFG) == 1


def test_pressure_below_warn_is_noop():
    assert speaker_cap(0, 0.50, CFG) == 3
    assert speaker_cap(1, 0.50, CFG) == 2


def test_missing_pressure_uses_structural_defaults():
    # A stale/absent metric must never over-mute -- defaults apply unchanged.
    assert speaker_cap(0, None, CFG) == 3
    assert speaker_cap(1, None, CFG) == 2


# ── should_handback ──────────────────────────────────────────────────────────

def test_handback_fires_at_threshold():
    assert should_handback(4, None, CFG) is True
    assert should_handback(3, None, CFG) is False


def test_handback_fires_sooner_under_pressure():
    assert should_handback(3, 0.70, CFG) is True   # threshold 4 -> 3
    assert should_handback(2, 0.70, CFG) is False


def test_handback_never_fires_on_single_exchange():
    # A lone companion-to-companion reply is dialogue, not a loop -- even if a
    # very low handback_turns + pressure tried to drop the bar below 2.
    cfg = BrakeConfig(handback_turns=2)
    assert should_handback(1, 0.90, cfg) is False
    assert should_handback(2, 0.90, cfg) is True


# ── apply_cap: drops least-relevant voices, keeps priority order ─────────────

def test_apply_cap_noop_when_full():
    routing = {"drevan": True, "cypher": True, "gaia": True}
    order = ["cypher", "drevan", "gaia"]
    assert apply_cap(routing, order, 3) == routing


def test_apply_cap_keeps_top_by_priority():
    routing = {"drevan": True, "cypher": True, "gaia": True}
    order = ["cypher", "drevan", "gaia"]  # cypher addressed/leads
    capped = apply_cap(routing, order, 1)
    assert capped == {"drevan": False, "cypher": True, "gaia": False}


def test_apply_cap_pair():
    routing = {"drevan": True, "cypher": True, "gaia": True}
    order = ["gaia", "drevan", "cypher"]
    capped = apply_cap(routing, order, 2)
    assert capped == {"drevan": True, "cypher": False, "gaia": True}


def test_apply_cap_ignores_already_silent():
    routing = {"drevan": False, "cypher": True, "gaia": True}
    order = ["cypher", "drevan", "gaia"]
    capped = apply_cap(routing, order, 1)
    assert capped == {"drevan": False, "cypher": True, "gaia": False}


def test_apply_cap_routed_speaker_missing_from_order_not_dropped():
    # Safety: a routing/order mismatch must not silently silence everyone.
    routing = {"drevan": True}
    order = []  # order failed to include drevan
    assert apply_cap(routing, order, 1) == {"drevan": True}


# ── StallTracker ─────────────────────────────────────────────────────────────

def test_stall_tracker_counts_companion_streak():
    t = StallTracker()
    assert t.observe("ch", author_is_companion=False, now=0.0) == 0   # human
    assert t.observe("ch", author_is_companion=True, now=1.0) == 1
    assert t.observe("ch", author_is_companion=True, now=2.0) == 2
    assert t.observe("ch", author_is_companion=True, now=3.0) == 3


def test_stall_tracker_human_resets():
    t = StallTracker()
    t.observe("ch", True, 1.0)
    t.observe("ch", True, 2.0)
    assert t.observe("ch", author_is_companion=False, now=3.0) == 0
    assert t.streak("ch", 3.0) == 0


def test_stall_tracker_per_channel_isolation():
    t = StallTracker()
    t.observe("a", True, 1.0)
    t.observe("a", True, 2.0)
    assert t.observe("b", True, 2.5) == 1
    assert t.streak("a", 2.5) == 2


def test_stall_tracker_expires_stale_channel():
    t = StallTracker(ttl_s=10.0)
    t.observe("ch", True, 1.0)
    t.observe("ch", True, 2.0)
    # 20s later the streak has expired; a fresh companion turn starts at 1.
    assert t.observe("ch", author_is_companion=True, now=100.0) == 1


# ── Integration: the 06-26 transcript shape ──────────────────────────────────

def test_transcript_scenario_group_chat_then_collapse_then_handback():
    """Raziel speaks (depth 0, full triad answers), the thread recurses into a
    companion-only fan-out (collapses to solo), and after the streak builds the
    floor is handed back to Raziel."""
    t = StallTracker()
    # Raziel's message: depth 0, all three may answer.
    t.observe("ch", author_is_companion=False, now=0.0)
    assert speaker_cap(0, None, CFG) == 3

    # Companion replies recurse. Each re-entry is a companion turn at rising depth.
    streak = 0
    for i, depth in enumerate([1, 2, 3, 4], start=1):
        streak = t.observe("ch", author_is_companion=True, now=float(i))
        # depth >= 2 collapses every round to a single voice (turn-taking).
        if depth >= 2:
            assert speaker_cap(depth, None, CFG) == 1
    # By the 4th companion lap with no human, the floor must hand back.
    assert streak == 4
    assert should_handback(streak, None, CFG) is True
    assert "back to Raziel" in handback_directive(streak)
