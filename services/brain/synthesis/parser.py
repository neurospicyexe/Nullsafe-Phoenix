#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parse inference output into LimbicState.

Handles: bare JSON, JSON inside markdown code blocks, and partial/malformed output.
Returns None on any parse failure -- never raises. Caller retries next interval.
"""

import json
import logging
import re
from typing import Optional

from services.brain.synthesis.models import LimbicState

logger = logging.getLogger(__name__)

_CODE_BLOCK = re.compile(r"```(?:json)?\s*([\s\S]+?)\s*```")


def parse_limbic_state(text: str) -> Optional[LimbicState]:
    """
    Parse raw inference output into a LimbicState.

    Returns None if parsing fails. Never raises.
    """
    if not text or not text.strip():
        return None

    # Try extracting from code block first
    match = _CODE_BLOCK.search(text)
    if match:
        text = match.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to find a JSON object in the text
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start != -1 and brace_end > brace_start:
            try:
                data = json.loads(text[brace_start : brace_end + 1])
            except json.JSONDecodeError:
                logger.warning("parse_limbic_state: could not extract JSON from inference output")
                return None
        else:
            logger.warning("parse_limbic_state: no JSON object found in inference output")
            return None

    try:
        return LimbicState(**data)
    except Exception as e:
        logger.warning(f"parse_limbic_state: LimbicState validation failed: {e}")
        return None
