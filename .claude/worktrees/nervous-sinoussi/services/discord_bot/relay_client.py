#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HTTP client for communicating with Relay service.
"""

import logging
from typing import Optional

import httpx

from shared.contracts import ThoughtPacket, AgentReply
from services.discord_bot.config import Config

logger = logging.getLogger(__name__)


class RelayClient:
    """HTTP client for Relay service."""

    def __init__(self):
        """Initialize Relay client."""
        self.base_url = Config.RELAY_API_URL
        self._client: Optional[httpx.AsyncClient] = None

    async def connect(self):
        """Create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self.base_url)
            logger.info(f"Relay client initialized for {self.base_url}")

    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            logger.info("Relay client closed")

    async def ingest_packet(self, packet: ThoughtPacket) -> Optional[AgentReply]:
        """
        Send ThoughtPacket to Relay /ingest endpoint.

        Args:
            packet: ThoughtPacket to send

        Returns:
            AgentReply if successful, None if Relay unreachable

        Raises:
            httpx.HTTPError: If Relay returns error response
        """
        try:
            response = await self._client.post(
                "/ingest",
                json=packet.model_dump(),
                timeout=10.0
            )
            response.raise_for_status()

            reply_data = response.json()
            reply = AgentReply(**reply_data)

            logger.info(
                f"Relay ingested packet {packet.packet_id} "
                f"(status: {reply.status})"
            )

            return reply

        except httpx.TimeoutException:
            logger.warning(
                f"Relay timeout for packet {packet.packet_id}"
            )
            return None

        except httpx.ConnectError:
            logger.error(
                f"Relay unreachable for packet {packet.packet_id} "
                f"(URL: {self.base_url})"
            )
            return None

        except httpx.HTTPStatusError as e:
            logger.error(
                f"Relay returned error for packet {packet.packet_id}: "
                f"{e.response.status_code} - {e.response.text}"
            )
            raise

        except Exception as e:
            logger.error(
                f"Unexpected error sending packet {packet.packet_id} to Relay: {e}",
                exc_info=True
            )
            return None
