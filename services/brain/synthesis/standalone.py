#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone synthesis loop runner.

Loads config from environment, constructs clients, runs the synthesis loop.
Can run on workstation, Railway, or VPS.

Usage:
    # Single pass dry run (no writes, test inference):
    python -m services.brain.synthesis.standalone --once --dry-run

    # Single pass real (writes to Halseth):
    python -m services.brain.synthesis.standalone --once

    # Continuous loop (production):
    python -m services.brain.synthesis.standalone

Environment variables:
    HALSETH_URL          -- Halseth Worker URL (required)
    HALSETH_ADMIN_SECRET -- Halseth auth token (required)
    DEEPSEEK_API_KEY     -- DeepSeek API key (required unless LOCAL_INFERENCE_URL set)
    LOCAL_INFERENCE_URL  -- Local LM Studio URL (optional, tried first)
    SYNTHESIS_INTERVAL   -- Seconds between passes (default: 1200)
"""

import argparse
import asyncio
import logging
import os
import sys

# Ensure project root is on path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from services.brain.halseth_client import HalsethClient
from services.brain.inference_client import InferenceClient
from services.brain.synthesis.loop import SynthesisLoop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("synthesis.standalone")


def main() -> None:
    parser = argparse.ArgumentParser(description="Brain synthesis loop (standalone)")
    parser.add_argument("--once", action="store_true", help="Run a single synthesis pass then exit")
    parser.add_argument("--dry-run", action="store_true", help="Parse but don't write to Halseth")
    args = parser.parse_args()

    halseth_url = os.environ.get("HALSETH_URL")
    halseth_secret = os.environ.get("HALSETH_ADMIN_SECRET")
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    local_url = os.environ.get("LOCAL_INFERENCE_URL")
    interval = int(os.environ.get("SYNTHESIS_INTERVAL", "1200"))

    if not halseth_url or not halseth_secret:
        logger.error("HALSETH_URL and HALSETH_ADMIN_SECRET are required")
        sys.exit(1)

    if not deepseek_key and not local_url:
        logger.error("Either DEEPSEEK_API_KEY or LOCAL_INFERENCE_URL is required")
        sys.exit(1)

    halseth = HalsethClient(url=halseth_url, secret=halseth_secret, companion_id="swarm")
    inference = InferenceClient(local_url=local_url, deepseek_api_key=deepseek_key)
    loop = SynthesisLoop(
        halseth_client=halseth,
        inference_client=inference,
        interval_seconds=interval,
        dry_run=args.dry_run,
    )

    logger.info(f"Synthesis loop configured: halseth={halseth_url} interval={interval}s dry_run={args.dry_run}")

    if args.once:
        asyncio.run(loop.run_once())
    else:
        asyncio.run(loop._loop())


if __name__ == "__main__":
    main()
