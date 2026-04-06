#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent routing logic for Nullsafe Phoenix Brain.

Handles:
- Thread-based agent routing (thread_id -> active_agent_id mapping)
- Message prefix overrides ("Drevan:", "Cypher:", "Gaia:")
- Identity-aware stub replies
"""

import logging
import re
from datetime import datetime, timezone
from typing import Dict, Optional

from shared.contracts import AgentReply, ThoughtPacket
from services.brain.identity.loader import IdentityLoader
from services.brain.inference_client import InferenceClient

logger = logging.getLogger(__name__)


class AgentRouter:
    """
    Routes ThoughtPackets to appropriate agent handlers.

    Maintains in-memory thread_id -> active_agent_id mapping.
    Supports override via message prefix.
    """

    # Valid agent IDs
    VALID_AGENTS = {"drevan", "cypher", "gaia"}

    # Override patterns (case-insensitive)
    OVERRIDE_PATTERNS = {
        "drevan": re.compile(r"^drevan:\s*", re.IGNORECASE),
        "cypher": re.compile(r"^cypher:\s*", re.IGNORECASE),
        "gaia": re.compile(r"^gaia:\s*", re.IGNORECASE),
    }

    def __init__(self, identity_loader: IdentityLoader, inference_client: Optional[InferenceClient] = None, orient_cache=None):
        """
        Initialize agent router.

        Args:
            identity_loader: Identity loader for loading agent identities
            inference_client: Inference client for LLM completions (optional; falls back to stub)
            orient_cache: OrientCache instance for limbic context injection (optional)
        """
        self.identity_loader = identity_loader
        self.inference_client = inference_client
        self._orient_cache = orient_cache
        self._thread_routing: Dict[str, str] = {}  # thread_id -> active_agent_id

    def detect_override(self, message: str) -> tuple[str | None, str]:
        """
        Detect agent override prefix in message.

        Args:
            message: User message

        Returns:
            Tuple of (override_agent_id, cleaned_message)
            If no override detected, returns (None, original_message)
        """
        for agent_id, pattern in self.OVERRIDE_PATTERNS.items():
            match = pattern.match(message)
            if match:
                # Remove prefix from message
                cleaned_message = pattern.sub("", message).strip()
                logger.info(f"Detected override: {agent_id} (message: '{cleaned_message}')")
                return agent_id, cleaned_message

        return None, message

    def get_active_agent(self, packet: ThoughtPacket) -> tuple[str, str]:
        """
        Determine which agent should handle this packet.

        Routing logic:
        1. Check for override prefix in message ("Drevan:", etc.)
        2. If override detected, update thread mapping and use override
        3. Otherwise, use thread_id mapping if exists
        4. Fall back to packet.agent_id

        Args:
            packet: Incoming ThoughtPacket

        Returns:
            Tuple of (active_agent_id, cleaned_message)
        """
        thread_id = packet.thread_id

        # Check for override prefix
        override_agent, cleaned_message = self.detect_override(packet.message)

        if override_agent:
            # Update thread mapping
            self._thread_routing[thread_id] = override_agent
            logger.info(
                f"Thread {thread_id} routing updated: {override_agent} (via override)"
            )
            return override_agent, cleaned_message

        # Check thread mapping
        if thread_id in self._thread_routing:
            active_agent = self._thread_routing[thread_id]
            logger.info(
                f"Thread {thread_id} using mapped agent: {active_agent}"
            )
            return active_agent, packet.message

        # Fall back to packet.agent_id
        active_agent = packet.agent_id
        logger.info(
            f"Thread {thread_id} using packet agent_id: {active_agent} (no mapping)"
        )

        # Initialize thread mapping
        self._thread_routing[thread_id] = active_agent

        return active_agent, packet.message

    async def route_and_process(self, packet: ThoughtPacket) -> AgentReply:
        """
        Route packet to agent and generate identity-aware stub reply.

        Args:
            packet: Incoming ThoughtPacket

        Returns:
            AgentReply with identity-aware stub response
        """
        # Determine active agent
        active_agent_id, cleaned_message = self.get_active_agent(packet)

        # Load agent identity
        identity, identity_version = self.identity_loader.load_identity(active_agent_id)

        logger.info(
            f"Processing message for {active_agent_id} (identity version: {identity_version})"
        )

        # Generate reply via inference or stub
        if self.inference_client:
            system_prompt = self.identity_loader.construct_prompt_context(identity)
            # Inject limbic context if orient cache is available
            if self._orient_cache:
                limbic_block = await self._orient_cache.get(packet.thread_id, active_agent_id)
                if limbic_block:
                    system_prompt = system_prompt + "\n\n" + limbic_block
            reply_text, backend = await self.inference_client.complete(
                system_prompt, cleaned_message, active_agent_id
            )
        else:
            reply_text = self._generate_stub_reply(identity, cleaned_message)
            backend = "stub"

        # Construct trace with repro_stamp
        repro_stamp = {
            "packet_id": packet.packet_id,
            "agent_id": active_agent_id,
            "identity_version": identity_version,
            "backend": backend,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "thread_routing": {
                "thread_id": packet.thread_id,
                "active_agent": active_agent_id,
                "original_packet_agent": packet.agent_id
            }
        }

        # Return AgentReply
        return AgentReply(
            packet_id=packet.packet_id,
            agent_id=active_agent_id,
            status="ok",
            reply_text=reply_text,
            trace={"repro_stamp": repro_stamp}
        )

    def _generate_stub_reply(self, identity, message: str) -> str:
        """
        Generate identity-aware stub reply (no external LLM calls).

        Demonstrates identity selection by including:
        - Agent name
        - One anchor phrase
        - Echo of user message

        Args:
            identity: Agent identity
            message: User message

        Returns:
            Stub reply text
        """
        # Pick first anchor if available
        anchor_phrase = identity.anchors[0] if identity.anchors else "core identity"

        # Construct stub reply
        reply_parts = [
            f"[{identity.name} speaking]",
            f"Identity anchor: {anchor_phrase}",
            f"You said: \"{message}\"",
            "",
            "(Day One stub - no LLM inference yet)"
        ]

        return "\n".join(reply_parts)
