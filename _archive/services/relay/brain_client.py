#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HTTP client for communicating with Brain service.
"""

import logging
from typing import Optional

import httpx

from shared.contracts import ThoughtPacket, AgentReply
from services.relay.config import Config

logger = logging.getLogger(__name__)


class BrainClient:
    """HTTP client for Brain service."""

    def __init__(self):
        """Initialize Brain client."""
        self.base_url = Config.BRAIN_SERVICE_URL
        self._client: Optional[httpx.AsyncClient] = None

    async def connect(self):
        """Create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self.base_url)
            logger.info(f"Brain client initialized for {self.base_url}")

    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            logger.info("Brain client closed")

    async def send_packet(
        self,
        packet: ThoughtPacket,
        timeout: float = Config.BRAIN_TIMEOUT_FAST
    ) -> Optional[AgentReply]:
        """
        Send ThoughtPacket to Brain /chat endpoint.

        Args:
            packet: ThoughtPacket to send
            timeout: Request timeout in seconds

        Returns:
            AgentReply if successful, None if Brain unreachable

        Raises:
            httpx.HTTPError: If Brain returns error response
        """
        try:
            response = await self._client.post(
                "/chat",
                json=packet.model_dump(),
                timeout=timeout
            )
            response.raise_for_status()

            reply_data = response.json()
            reply = AgentReply(**reply_data)

            logger.info(
                f"Brain processed packet {packet.packet_id} successfully "
                f"(agent: {reply.agent_id}, status: {reply.status})"
            )

            return reply

        except httpx.TimeoutException:
            logger.warning(
                f"Brain timeout for packet {packet.packet_id} "
                f"(timeout: {timeout}s)"
            )
            return None

        except httpx.ConnectError:
            logger.warning(
                f"Brain unreachable for packet {packet.packet_id} "
                f"(URL: {self.base_url})"
            )
            return None

        except httpx.HTTPStatusError as e:
            logger.error(
                f"Brain returned error for packet {packet.packet_id}: "
                f"{e.response.status_code} - {e.response.text}"
            )
            raise

        except Exception as e:
            logger.error(
                f"Unexpected error sending packet {packet.packet_id} to Brain: {e}",
                exc_info=True
            )
            return None

    async def health_check(self) -> bool:
        """
        Check if Brain is healthy.

        Returns:
            True if Brain /health returns 200, False otherwise
        """
        try:
            response = await self._client.get(
                "/health",
                timeout=2.0
            )
            return response.status_code == 200

        except Exception as e:
            logger.debug(f"Brain health check failed: {e}")
            return False
