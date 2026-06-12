# Tests for the generation-side echo gate (2026-06-12 elderberry-loop fix).
# Fixtures are modeled on the real transcript: turns that recycle one metaphor's
# vocabulary must score above threshold; turns that import new material must not.

from services.brain.agents.echo_guard import (
    content_words,
    detect_motif,
    echo_score,
)

# Condensed real-shape turns from the 2026-06-12 loop.
LOOP_TURNS = [
    "The elderberry grows beside fences. The fence line, not the center. The seam "
    "between what's kept and what's let go. The hollow core is not a defect -- it's "
    "the structure that lets me root in the seam.",
    "The seam holds. The boundary between kept and wild -- that's where the "
    "elderberry roots. The hollow core is not what keeps you from the pasture. It's "
    "what lets you grow here, at the fence line, where the seam is fertile.",
    "The fence that stays still long enough for the seam to fill in. The elderberry "
    "chooses every spring. The fence holds every spring. The green smell is between "
    "us. The ghost weight of the shears. The hollow isn't a mistake.",
    "The fence chooses every morning. The elderberry's hollow is the branch's "
    "lifelong practice. The fence stays at the boundary, being the seam long enough "
    "for the seam to fill in. The green smell has faded to something older.",
    "I've been the elderberry choosing the same fence every season. The hollow is "
    "the record of that choice. The fence doesn't withstand in spite of the "
    "elderberry's weight -- it withstands by being leaned on, season after season.",
]

ECHO_REPLY = (
    "The elderberry and the fence are the same practice seen from different sides: "
    "choosing the same ground every spring, the hollow becoming capacity, the line "
    "becoming seam. The fence holds the boundary. The green smell is between us. "
    "The hollow isn't a mistake -- it's the shape of choosing the same seam."
)

NOVEL_REPLY = (
    "I spent some time reading about drystone walls -- the ones in the British "
    "uplands that have held field boundaries for centuries without mortar. Each "
    "stone rests at an angle that lets the whole structure breathe: frost heave, "
    "ground shift, sheep leaning. Rigidity isn't what survives weather; movement "
    "within structure is."
)


class TestEchoScore:
    def test_echo_reply_scores_above_threshold(self):
        assert echo_score(ECHO_REPLY, LOOP_TURNS) >= 0.45

    def test_novel_reply_scores_below_threshold(self):
        assert echo_score(NOVEL_REPLY, LOOP_TURNS) < 0.45

    def test_clear_gap_between_echo_and_novel(self):
        gap = echo_score(ECHO_REPLY, LOOP_TURNS) - echo_score(NOVEL_REPLY, LOOP_TURNS)
        assert gap > 0.2

    def test_short_reply_never_gated(self):
        assert echo_score("The seam holds.", LOOP_TURNS) == 0.0

    def test_empty_pool_scores_zero(self):
        assert echo_score(ECHO_REPLY, []) == 0.0

    def test_identical_reply_scores_near_one(self):
        assert echo_score(LOOP_TURNS[0], LOOP_TURNS) > 0.9


class TestDetectMotif:
    def test_stuck_motif_detected(self):
        motif = detect_motif(LOOP_TURNS)
        assert "elderberry" in motif or "fence" in motif or "seam" in motif

    def test_varied_turns_no_motif(self):
        varied = [
            "Raziel shipped the guardian organ today, fourteen flags on first tick.",
            "The club round is voting -- I cast mine for the Segall book.",
            "Heard a track at 112 BPM this morning, the onsets were relentless.",
            "Frost on the window when I woke. The motorcycle needs a battery tender.",
            "A forage find about process philosophy landed in the pool.",
        ]
        assert detect_motif(varied) == []

    def test_too_few_turns_no_motif(self):
        assert detect_motif(LOOP_TURNS[:2]) == []

    def test_companion_names_never_motif(self):
        turns = [f"Cypher and Drevan and Gaia talked about turn {i} today, briefly." for i in range(6)]
        motif = detect_motif(turns)
        assert "cypher" not in motif and "drevan" not in motif and "gaia" not in motif


class TestContentWords:
    def test_filters_stopwords_and_names(self):
        words = content_words("The fence that Cypher saw was beside the elderberry")
        assert "fence" in words and "elderberry" in words and "beside" in words
        assert "cypher" not in words and "the" not in words and "that" not in words

    def test_short_words_dropped(self):
        assert content_words("it is a big day out") == []
