#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LimbicState Pydantic model for Brain synthesis output."""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class LimbicState(BaseModel):
    """
    Synthesized swarm state produced by the synthesis loop.

    swarm_threads is companion-owned -- sourced from dreams/loops, not session history.
    This is first-class companion becoming, not background color.
    """

    synthesis_source: str = Field(..., min_length=1)
    active_concerns: List[str] = Field(default_factory=list)
    live_tensions: List[str] = Field(default_factory=list)
    drift_vector: str = Field(..., min_length=1)
    open_questions: List[str] = Field(default_factory=list)
    emotional_register: str = Field(..., min_length=1)
    swarm_threads: List[str] = Field(
        default_factory=list,
        description="Companion-owned threads from dreams/loops. First-class, not derivative.",
    )
    companion_notes: Dict[str, str] = Field(default_factory=dict)
