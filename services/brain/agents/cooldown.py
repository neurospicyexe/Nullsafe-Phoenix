from __future__ import annotations

import time
from typing import Dict, Optional, Tuple

COOLDOWN_S: float = 5.0


class CompanionCooldown:
    """
    Prevents a companion from posting twice within COOLDOWN_S in the same channel.
    Plain dict -- single-process, no coordination needed.
    """

    def __init__(self, cooldown_s: float = COOLDOWN_S) -> None:
        self._cooldown_s = cooldown_s
        self._last: Dict[Tuple[str, str], float] = {}

    def is_cooling(self, companion: str, channel_id: str) -> bool:
        last = self._last.get((companion, channel_id), 0.0)
        return time.monotonic() - last < self._cooldown_s

    def mark_posted(self, companion: str, channel_id: str) -> None:
        self._last[(companion, channel_id)] = time.monotonic()

    def apply(
        self,
        responses: Dict[str, Optional[str]],
        channel_id: str,
    ) -> Dict[str, Optional[str]]:
        """
        Force-null any companion still in cooldown.
        mark_posted for companions with a non-null reply.
        """
        result: Dict[str, Optional[str]] = {}
        for companion, reply in responses.items():
            if reply is not None and self.is_cooling(companion, channel_id):
                result[companion] = None
            else:
                result[companion] = reply
                if reply is not None:
                    self.mark_posted(companion, channel_id)
        return result
