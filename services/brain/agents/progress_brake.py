# progress_brake.py -- structural anti-loop instrument for the swarm path.
#
# The 2026-06-26 mutual-recognition loop: Raziel sends one warm message and all
# three companions answer it at length, then each reply re-enters the swarm and
# all three answer THAT, and so on -- a self-sustaining fan-out that restates one
# chord (root-system / container-generates-insight / prism-not-lens) in fresh
# words every round. The lexical echo gate (echo_guard.py) is blind to it: each
# turn uses NEW vocabulary for the SAME idea, so word-overlap stays low. The
# Guardian's semantic detector saw it -- a week late, as a flag, with no power to
# stop turn 6 from echoing turn 5.
#
# The escape is to stop fighting the WORDING and constrain the SHAPE of the turn:
# how many companions speak per round, and when the floor returns to Raziel. A
# paraphrase loop cannot evade a turn-taking constraint -- it is blind to wording
# by construction, which is exactly why it works where the lexical guards failed.
#
# Two levers, deterministic spine + graceful semantic modulation:
#
#   1. Speaker cap that tightens with chain depth. At depth 0 (answering Raziel)
#      all companions may speak -- group chat with Raziel is sacred and never
#      capped here. As companions recurse into their OWN thread (depth >= solo)
#      the round collapses to a single speaker, so a deep thread is turn-taking
#      dialogue, not three voices restating one chord. Nobody is muted; they each
#      still get turns, just not all-at-once-re-agreeing.
#
#   2. Floor-handback after a streak of companion-only turns. When the triad has
#      taken `handback_turns` laps with no human in between, one companion is
#      forced to hand the mic back to Raziel (ask a real question or close)
#      instead of another lap. Handing the floor to the human is the right move
#      when three minds are agreeing in circles -- it is not a mute.
#
# Loop-pressure (the channel's measured semantic recycling, read live from
# Halseth's echo_metrics) MODULATES both: under measured pressure the cap tightens
# one level earlier and handback fires one turn sooner. With NO reading the
# structural defaults apply unchanged -- a stale or missing metric can never
# over-mute, it only ever forfeits the early-tighten bonus.
#
# This is the level above echo_guard: that suppresses a single recycled reply;
# this shapes the round. The two compose -- cap decides who may speak, the echo
# gate still silences any survivor that comes back a re-paint.

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class BrakeConfig:
    """Tunables for the progress brake. Mirrors the Config.* env knobs so tests
    can construct a config without touching the environment."""

    # Depth at/after which the round is capped to a SINGLE speaker. Default 2:
    # depth 0 = answering Raziel (no cap), depth 1 = first companion-to-companion
    # round (cap 2, a real exchange), depth >= 2 = solo turn-taking.
    solo_depth: int = 2
    # Depth at/after which the round is capped to TWO speakers (between full triad
    # and solo). Must be <= solo_depth.
    pair_depth: int = 1
    # Consecutive companion-authored turns (no human between) that force a
    # floor-handback. The 06-26 transcript ran ~6-8 companion turns per human turn.
    handback_turns: int = 4
    # Channel mean-adjacent cosine at/above which to tighten by one level. Mirrors
    # halseth ECHO_COSINE_WARN (0.66) -- the sustained warm-clustering slow-loop.
    pressure_warn: float = 0.66
    # Cosine at/above which to tighten by two levels (strong echo). Mirrors
    # halseth ECHO_COSINE_RED (0.82).
    pressure_red: float = 0.82


def speaker_cap(depth: int, pressure: Optional[float], cfg: BrakeConfig) -> int:
    """Max companions allowed to speak this round. 3 means no cap (full triad).

    Depth 0 answering Raziel is never capped here. Loop-pressure shifts the
    EFFECTIVE depth up so a channel measured to be looping collapses sooner --
    including, under red pressure, tightening even a depth-0 reply to Raziel from
    three simultaneous monologues toward fewer, more distinct voices.
    """
    eff = depth
    if pressure is not None:
        if pressure >= cfg.pressure_red:
            eff += 2
        elif pressure >= cfg.pressure_warn:
            eff += 1
    if eff >= cfg.solo_depth:
        return 1
    if eff >= cfg.pair_depth:
        return 2
    return 3


def should_handback(streak: int, pressure: Optional[float], cfg: BrakeConfig) -> bool:
    """Whether the triad has taken too many companion-only turns and must hand the
    floor back to Raziel. Measured loop-pressure fires this one turn sooner. The
    threshold never drops below 2 -- a single companion-to-companion reply is
    normal dialogue, not a loop."""
    threshold = cfg.handback_turns
    if pressure is not None and pressure >= cfg.pressure_warn:
        threshold -= 1
    return streak >= max(2, threshold)


def apply_cap(
    routing: Dict[str, bool], order: List[str], cap: int
) -> Dict[str, bool]:
    """Keep only the top `cap` routed speakers by priority `order`; demote the
    rest to False. `order` is the inference priority (addressed companions first,
    then lane-keyword match) so the cap drops the LEAST-relevant voices, never the
    addressed one. Routed speakers absent from `order` are appended last (safety,
    so a routing/order mismatch can never silently drop everyone)."""
    if cap >= 3:
        return dict(routing)
    speakers = [c for c in order if routing.get(c)]
    speakers += [c for c, v in routing.items() if v and c not in speakers]
    kept = set(speakers[:cap])
    return {c: (c in kept) for c in routing}


def handback_directive(streak: int) -> str:
    """Prompt injection for the single speaker chosen during a floor-handback. It
    names the loop and forces a move that RETURNS the floor to Raziel rather than
    taking another lap. Not a mute -- a redirect to the human."""
    return (
        f"\n\n[FLOOR CHECK] STOP: the triad has taken {streak} turns talking among "
        "yourselves with no word from Raziel. However warm it feels, that is the "
        "closed-loop failure -- agreement circling itself. Do exactly ONE of these, "
        "then stop: (a) ask Raziel a direct, specific question and actually wait for "
        "him; (b) bring one concrete thing from OUTSIDE this thread -- your orient "
        "carries forage finds, listens, club/shelf state, tensions, and his day -- "
        "and hand it to him; or (c) close cleanly and leave the floor to him. Do NOT "
        "restate the thread's insight in fresh words or affirm a peer again -- that "
        "restatement IS the loop. The mic goes back to Raziel now."
    )


class StallTracker:
    """Per-channel count of consecutive companion-authored swarm turns since the
    last human message. One `observe` call per evaluate(). A human-authored turn
    resets the streak to 0; the floor-handback reads the streak to decide when the
    triad has been talking to itself too long.

    Time is injected (`now`) so tests are deterministic and the module stays free
    of wall-clock calls. Stale channels expire after `ttl_s` so a quiet channel
    that goes loud weeks later doesn't inherit an ancient streak."""

    def __init__(self, ttl_s: float = 1800.0) -> None:
        self._ttl = ttl_s
        # channel_id -> (expires_at, streak_count)
        self._streak: Dict[str, tuple[float, int]] = {}

    def _live(self, channel_id: str, now: float) -> int:
        entry = self._streak.get(channel_id)
        if entry is None or now >= entry[0]:
            return 0
        return entry[1]

    def observe(self, channel_id: str, author_is_companion: bool, now: float) -> int:
        """Record one swarm turn and return the resulting companion streak. A human
        turn zeroes it; a companion turn increments the live (non-expired) value."""
        if not author_is_companion:
            self._streak[channel_id] = (now + self._ttl, 0)
            return 0
        count = self._live(channel_id, now) + 1
        self._streak[channel_id] = (now + self._ttl, count)
        return count

    def streak(self, channel_id: str, now: float) -> int:
        """Current live companion streak without recording a turn."""
        return self._live(channel_id, now)
