#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nullsafe Phoenix v2 - Workstation Brain Service

FastAPI service for agent intelligence and decision-making.
NEVER depends on Redis, NEVER talks to Discord.
"""

import logging
from datetime import datetime, timezone
from typing import Dict

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from shared.contracts import AgentReply, ThoughtPacket
from services.brain.identity.loader import IdentityLoader
from services.brain.agents.router import AgentRouter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Nullsafe Phoenix Brain",
    version="v2-day-one",
    description="Workstation Brain service for agent intelligence"
)

# Initialize identity loader and agent router
identity_loader = IdentityLoader()
agent_router = AgentRouter(identity_loader)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "brain",
        "version": "v2-day-one",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.post("/chat")
async def chat(packet: ThoughtPacket) -> AgentReply:
    """
    Process ThoughtPacket and return AgentReply.

    Routing:
    - Check for override prefix in message ("Drevan:", "Cypher:", "Gaia:")
    - Use thread_id mapping if exists
    - Fall back to packet.agent_id
    """
    logger.info(f"Processing packet {packet.packet_id} for thread {packet.thread_id}")

    try:
        # Route to correct agent and get response
        reply = await agent_router.route_and_process(packet)

        logger.info(
            f"Packet {packet.packet_id} processed successfully by {reply.agent_id}"
        )

        return reply

    except Exception as e:
        logger.error(
            f"Error processing packet {packet.packet_id}: {e}",
            exc_info=True
        )

        # Return error reply
        return AgentReply(
            packet_id=packet.packet_id,
            agent_id=packet.agent_id,
            status="error",
            reply_text=f"Error processing message: {str(e)}",
            trace={
                "error": str(e),
                "packet_id": packet.packet_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
