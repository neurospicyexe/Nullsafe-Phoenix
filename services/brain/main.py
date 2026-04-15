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
from contextlib import asynccontextmanager
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
from services.brain.halseth_client import HalsethClient
from services.brain.webmind_client import WebMindClient
from services.brain.synthesis.loop import SynthesisLoop
from services.brain.synthesis.orient_cache import OrientCache

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

# Initial router (no orient cache); lifespan will replace with wired version
agent_router = AgentRouter(identity_loader, inference_client=_inference_client)

_synthesis_loop = None


@asynccontextmanager
async def lifespan(app):
    global _synthesis_loop, agent_router

    # Setup Halseth client (shared by router post-response writes + synthesis loop).
    # WEBMIND_URL defaults to Halseth URL so OrientCache reads from the live data backend.
    halseth_client = None
    if Config.HALSETH_URL:
        halseth_client = HalsethClient(
            url=Config.HALSETH_URL,
            secret=Config.HALSETH_ADMIN_SECRET or "",
            companion_id="cypher",
        )
        logger.info(f"[brain] Halseth client ready: {Config.HALSETH_URL}")

    # Setup webmind client -- point at Halseth URL when no separate WebMind is running.
    # Halseth exposes the same /mind/* endpoints as Phoenix WebMind.
    webmind_url = Config.WEBMIND_URL or Config.HALSETH_URL
    webmind_client = None
    if webmind_url:
        webmind_client = WebMindClient(url=webmind_url)

    # Setup orient cache
    orient_cache = OrientCache(webmind_client=webmind_client) if webmind_client else None

    # Re-initialize agent_router with orient_cache + Halseth client
    agent_router = AgentRouter(
        identity_loader,
        inference_client=_inference_client,
        orient_cache=orient_cache,
        halseth_client=halseth_client,
    )

    # Start synthesis loop if fully configured
    if Config.SYNTHESIS_ENABLED and _inference_client and halseth_client and webmind_client:
        _synthesis_loop = SynthesisLoop(
            halseth_client=halseth_client,
            inference_client=_inference_client,
            webmind_client=webmind_client,
            interval_seconds=Config.SYNTHESIS_INTERVAL,
        )
        _synthesis_loop.start()
        logger.info(f"[synthesis] Loop started (interval={Config.SYNTHESIS_INTERVAL}s)")
    else:
        reasons = []
        if not Config.SYNTHESIS_ENABLED:
            reasons.append("SYNTHESIS_ENABLED=false")
        if not _inference_client:
            reasons.append("no inference backend")
        if not halseth_client:
            reasons.append("HALSETH_URL not set")
        if not webmind_client:
            reasons.append("no WebMind/Halseth URL")
        logger.info(f"[synthesis] Loop not started: {', '.join(reasons)}")

    yield

    # Shutdown
    if _synthesis_loop:
        _synthesis_loop.stop()
        logger.info("[synthesis] Loop stopped on shutdown")


# Initialize FastAPI app with lifespan
app = FastAPI(
    title="Nullsafe Phoenix Brain",
    version="v2-day-one",
    description="Workstation Brain service for agent intelligence",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("BRAIN_ALLOWED_ORIGIN", "http://127.0.0.1:8000")],
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)


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
