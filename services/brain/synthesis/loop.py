#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Brain synthesis loop.

Runs as a background asyncio task started in Brain's FastAPI lifespan.
Stops cleanly when the task is cancelled.
"""

import asyncio
import logging
from typing import Optional

from services.brain.halseth_client import HalsethClient
from services.brain.inference_client import InferenceClient
from services.brain.webmind_client import WebMindClient
from services.brain.synthesis.prompt import build_synthesis_prompt
from services.brain.synthesis.parser import parse_limbic_state

logger = logging.getLogger(__name__)


class SynthesisLoop:
    """
    Background synthesis loop.

    Call start() to begin the loop as an asyncio background task.
    Call stop() to cancel gracefully.
    Call run_once() to execute a single synthesis pass (used in tests).
    """

    def __init__(
        self,
        halseth_client: HalsethClient,
        inference_client: InferenceClient,
        webmind_client: WebMindClient,
        interval_seconds: int = 1200,
    ):
        self._halseth = halseth_client
        self._inference = inference_client
        self._webmind = webmind_client
        self._interval = interval_seconds
        self._task: Optional[asyncio.Task] = None

    async def run_once(self) -> None:
        """
        Execute a single synthesis pass.

        1. Read swarm data from Halseth
        2. Build synthesis prompt
        3. Call inference
        4. Parse output into LimbicState
        5. Write to WebMind (only if parse succeeded)

        Never raises. Logs and returns on any failure.
        """
        logger.info("[synthesis] Starting synthesis pass")

        # 1. Read swarm data
        try:
            swarm_data = await self._halseth.synthesis_read()
        except Exception as e:
            logger.warning(f"[synthesis] Halseth read failed: {e}")
            return

        # 2. Build synthesis prompt
        system_prompt, user_message = build_synthesis_prompt(swarm_data)

        # 3. Call inference
        try:
            raw_output, backend = await self._inference.complete(
                system_prompt=system_prompt,
                user_message=user_message,
                agent_id="swarm",
            )
            logger.info(f"[synthesis] Inference complete via {backend}")
        except Exception as e:
            logger.warning(f"[synthesis] Inference failed: {e}")
            return

        # 4. Parse output
        limbic_state = parse_limbic_state(raw_output)
        if limbic_state is None:
            logger.warning("[synthesis] Parse failed -- skipping WebMind write (last state unchanged)")
            return

        # 5. Write to WebMind
        try:
            result = await self._webmind.write_limbic_state(limbic_state.model_dump())
            if result:
                logger.info(f"[synthesis] LimbicState written: {result.get('state_id', '?')}")
            else:
                logger.warning("[synthesis] WebMind write returned None -- WebMind may be offline")
        except Exception as e:
            logger.warning(f"[synthesis] WebMind write failed: {e}")

    def start(self) -> None:
        """Start the synthesis loop as a background asyncio task."""
        self._task = asyncio.create_task(self._loop(), name="synthesis_loop")
        logger.info(f"[synthesis] Loop started (interval={self._interval}s)")

    def stop(self) -> None:
        """Cancel the synthesis loop task."""
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("[synthesis] Loop stopped")

    async def _loop(self) -> None:
        """Run synthesis passes indefinitely with interval sleep between passes."""
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"[synthesis] Unexpected error in loop: {e}", exc_info=True)
            await asyncio.sleep(self._interval)
