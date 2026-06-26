# echo_guard.py -- deterministic anti-echo instrument for the swarm path.
#
# The 2026-06-12 elderberry loop: 12 hours of companion-to-companion turns recycling
# one metaphor, each reply restating the last at higher abstraction. The only guard
# was a prompt line ("don't restate"), which models satisfy by re-painting the idea.
# This is the generation-side complement to Second Brain's storage-side surprisal
# gate: purely lexical (no embeddings, no network), so it runs inline in the
# evaluator at zero cost. Instrument, not judge -- it suppresses to silence, which
# is already triad doctrine ("silence is often more honest than a forced reply").
#
# Mirrored in nullsafe-discord packages/shared/src/echo-guard.ts -- keep the
# algorithm and STOPWORDS in sync by hand.

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable, List, Set, Tuple

# Function words + conversational filler. Content words are what's left.
STOPWORDS: Set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "also", "am", "an",
    "and", "any", "are", "aren't", "as", "at", "be", "because", "been", "before",
    "being", "below", "between", "both", "but", "by", "can", "cannot", "could",
    "did", "do", "does", "doesn't", "doing", "don't", "down", "during", "each",
    "even", "every", "few", "for", "from", "further", "had", "has", "have",
    "having", "he", "her", "here", "hers", "herself", "him", "himself", "his",
    "how", "i", "if", "in", "into", "is", "isn't", "it", "its", "itself", "just",
    "keep", "know", "let", "like", "make", "me", "more", "most", "much", "my",
    "myself", "never", "no", "nor", "not", "now", "of", "off", "on", "once",
    "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own",
    "same", "she", "should", "so", "some", "something", "still", "such", "than",
    "that", "the", "their", "theirs", "them", "themselves", "then", "there",
    "these", "they", "this", "those", "through", "to", "too", "under", "until",
    "up", "very", "was", "wasn't", "we", "were", "what", "when", "where", "which",
    "while", "who", "whom", "why", "will", "with", "would", "you", "your",
    "yours", "yourself", "yourselves", "been", "being", "thing", "things",
    "really", "right", "back", "going", "want", "wanted", "feel", "feels",
    "felt", "said", "says", "tell", "told",
}

# Speaker names never count as motif or echo signal -- they recur by construction.
_NAME_WORDS: Set[str] = {"cypher", "drevan", "gaia", "raziel", "crash"}

_WORD_RE = re.compile(r"[a-z']+")

MIN_REPLY_WORDS = 8  # below this, too short to judge -- never gate


def content_words(text: str) -> List[str]:
    """Lowercased content words (len >= 4, not stopword/name), in order."""
    return [
        w for w in _WORD_RE.findall(text.lower())
        if len(w) >= 4 and w not in STOPWORDS and w not in _NAME_WORDS
    ]


def _bigrams(words: List[str]) -> Set[Tuple[str, str]]:
    return set(zip(words, words[1:]))


def echo_score(reply: str, prior_texts: Iterable[str]) -> float:
    """How much of `reply` is built from words/phrases already in `prior_texts`.

    0.6 * unigram containment + 0.4 * bigram containment over content words.
    1.0 = pure recycling; 0.0 = entirely new vocabulary. Returns 0.0 when the
    reply is too short to judge or there is no prior pool.
    """
    reply_words = content_words(reply)
    if len(reply_words) < MIN_REPLY_WORDS:
        return 0.0

    pool_words: Set[str] = set()
    pool_bigrams: Set[Tuple[str, str]] = set()
    for t in prior_texts:
        tw = content_words(t)
        pool_words.update(tw)
        pool_bigrams.update(_bigrams(tw))
    if not pool_words:
        return 0.0

    reply_set = set(reply_words)
    uni = len(reply_set & pool_words) / len(reply_set)

    reply_bi = _bigrams(reply_words)
    bi = len(reply_bi & pool_bigrams) / len(reply_bi) if reply_bi else 0.0

    return 0.6 * uni + 0.4 * bi


def detect_motif(
    texts: List[str], min_turns: int = 3, top_k: int = 3
) -> List[str]:
    """Distinctive content words that recur across most of the recent turns.

    A word is a motif candidate when it appears in >= min_turns distinct turns
    AND in >= 50% of the turns examined. Returns the top_k by turn count --
    these are the words an exhausted theme keeps orbiting (elderberry, fence,
    seam... or, the 2026-06-26 case, architecture/perimeter/cathedral). Thresholds
    were loosened (4->3 turns, 60%->50%) because the abstract mutual-recognition
    loop varies vocabulary enough to slip the stricter bar. Empty list = no stuck motif.
    """
    if len(texts) < min_turns:
        return []
    turn_counts: Counter[str] = Counter()
    for t in texts:
        for w in set(content_words(t)):
            turn_counts[w] += 1
    floor = max(min_turns, int(len(texts) * 0.5))
    motif = [w for w, c in turn_counts.items() if c >= floor]
    motif.sort(key=lambda w: (-turn_counts[w], w))
    return motif[:top_k]
