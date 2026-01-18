#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration for Relay service.
"""

import os
from typing import Optional


class Config:
    """Relay service configuration."""

    # Brain service
    BRAIN_SERVICE_URL: str = os.getenv(
        "BRAIN_SERVICE_URL", "http://localhost:8001"
    )
    BRAIN_TIMEOUT_FAST: int = 5  # Fast path timeout in seconds
    BRAIN_TIMEOUT_DRAINER: int = 30  # Drainer timeout in seconds

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")

    # Queue settings
    MAX_RETRIES: int = 5
    DRAINER_INTERVAL: int = 2  # Seconds between drainer runs
    DEDUPE_TTL: int = 86400  # 24 hours in seconds

    # Redis key prefixes
    QUEUE_INCOMING = "phx:queue:incoming"
    QUEUE_INFLIGHT = "phx:queue:inflight"
    QUEUE_DEADLETTER = "phx:queue:deadletter"
    OUTBOX_DISCORD = "phx:outbox:discord"
    DEDUPE_INGEST_PREFIX = "phx:dedupe:ingest"
    DEDUPE_OUTBOX_PREFIX = "phx:dedupe:outbox"
    BRAIN_STATUS_KEY = "phx:relay:brain_status"
    BRAIN_LAST_SEEN_KEY = "phx:relay:last_seen"

    @staticmethod
    def get_dedupe_ingest_key(packet_id: str) -> str:
        """Get dedupe key for ingest."""
        return f"{Config.DEDUPE_INGEST_PREFIX}:{packet_id}"

    @staticmethod
    def get_dedupe_outbox_key(packet_id: str) -> str:
        """Get dedupe key for outbox."""
        return f"{Config.DEDUPE_OUTBOX_PREFIX}:{packet_id}"
