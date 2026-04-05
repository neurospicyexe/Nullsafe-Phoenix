#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nullsafe Phoenix v2 - Web UI

Thin FastAPI web client that only talks to Relay.
Never talks to Brain directly. No RAG, no tools, no memory graphs.
"""

import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Get Relay API URL from environment
RELAY_API_URL = os.getenv("RELAY_API_URL", "http://localhost:8000")

# Initialize FastAPI app
app = FastAPI(
    title="Nullsafe Phoenix Web UI",
    version="v2-day-one",
    description="Thin web client for Phoenix v2"
)

# Setup templates and static files
templates_dir = Path(__file__).parent / "templates"
static_dir = Path(__file__).parent / "static"

# Create directories if they don't exist
templates_dir.mkdir(exist_ok=True)
static_dir.mkdir(exist_ok=True)

templates = Jinja2Templates(directory=str(templates_dir))
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Serve the main chat page."""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "relay_api_url": RELAY_API_URL
        }
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "web_ui",
        "relay_url": RELAY_API_URL
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("WEB_UI_PORT", "3000"))

    logger.info(f"Starting Phoenix Web UI on port {port}")
    logger.info(f"Relay API URL: {RELAY_API_URL}")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
