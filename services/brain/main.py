#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nullsafe Phoenix v2 - Workstation Brain Service

FastAPI service for agent intelligence and decision-making.
NEVER depends on Redis, NEVER talks to Discord.
"""

import logging
import os
import uuid as _uuid
from datetime import datetime, timezone
from typing import Dict

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shared.contracts import AgentReply, ThoughtPacket
from services.brain.config import Config
from services.brain.identity.loader import IdentityLoader
from services.brain.agents.router import AgentRouter
from services.brain.inference_client import InferenceClient

# Load environment variables
load_dotenv(".env.brain")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Suppress verbose uvicorn access logs
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

# Initialize FastAPI app
app = FastAPI(
    title="Nullsafe Phoenix Brain",
    version="v2-day-one",
    description="Workstation Brain service for agent intelligence"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("BRAIN_ALLOWED_ORIGIN", "http://127.0.0.1:8000")],
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)

# Validate configuration on startup
try:
    Config.validate()
    Config.print_safe_summary()
except Exception as e:
    logger.error(f"Configuration validation failed: {e}")
    raise

# Initialize identity loader
identity_loader = IdentityLoader()

# Initialize inference client if any backend is configured
_inference_client = None
if Config.LOCAL_INFERENCE_URL or Config.DEEPSEEK_API_KEY:
    _inference_client = InferenceClient(
        local_url=Config.LOCAL_INFERENCE_URL,
        local_timeout=Config.LOCAL_INFERENCE_TIMEOUT,
        deepseek_api_key=Config.DEEPSEEK_API_KEY,
    )
    logger.info(
        f"Inference client ready (local={'yes' if Config.LOCAL_INFERENCE_URL else 'no'}, "
        f"deepseek={'yes' if Config.DEEPSEEK_API_KEY else 'no'})"
    )
else:
    logger.info("No inference backend configured -- stub replies active")

agent_router = AgentRouter(identity_loader, inference_client=_inference_client)


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
        error_id = str(_uuid.uuid4())[:8]
        logger.error(
            f"Error {error_id} processing packet {packet.packet_id}: {e}",
            exc_info=True,
        )
        return AgentReply(
            packet_id=packet.packet_id,
            agent_id=packet.agent_id,
            status="error",
            reply_text=f"Error processing message (ref: {error_id})",
            trace={"error_id": error_id},
        )


if __name__ == "__main__":
    import uvicorn
    brain_host = os.getenv("BRAIN_HOST", "127.0.0.1")
    uvicorn.run(app, host=brain_host, port=8001, access_log=False)
