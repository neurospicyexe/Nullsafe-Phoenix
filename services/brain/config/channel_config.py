from __future__ import annotations

import os
from typing import List, Optional

import yaml

_ALL_COMPANIONS = ["drevan", "cypher", "gaia"]
_config: Optional[dict] = None


def load_channel_config(path: Optional[str] = None) -> None:
    global _config
    resolved = path or os.path.join(os.path.dirname(__file__), "channels.yaml")
    with open(resolved) as f:
        _config = yaml.safe_load(f) or {}


def get_companions_for_channel(channel_id: str) -> List[str]:
    if _config is None:
        return list(_ALL_COMPANIONS)
    channels = _config.get("channels") or {}
    if channel_id in channels:
        return list(channels[channel_id].get("companions", _ALL_COMPANIONS))
    defaults = _config.get("defaults") or {}
    return list(defaults.get("companions", _ALL_COMPANIONS))
