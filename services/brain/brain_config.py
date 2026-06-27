#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Configuration for Brain service."""

import os
from typing import Optional


class Config:
    """Brain service configuration."""

    # Identity loading
    IDENTITY_DIR: str = os.getenv("IDENTITY_DIR", "./services/brain/identity/data")

    # Obsidian integration
    OBSIDIAN_VAULT_PATH: Optional[str] = os.getenv("OBSIDIAN_VAULT_PATH")

    # LLM inference
    INFERENCE_ENABLED: bool = os.getenv("INFERENCE_ENABLED", "false").lower() == "true"

    # Local inference (LM Studio or any OpenAI-compatible endpoint)
    LOCAL_INFERENCE_URL: Optional[str] = os.getenv("LOCAL_INFERENCE_URL")
    LOCAL_INFERENCE_TIMEOUT: float = float(os.getenv("LOCAL_INFERENCE_TIMEOUT", "60"))

    # API Keys (optional until inference enabled)
    ANTHROPIC_API_KEY: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    DEEPSEEK_API_KEY: Optional[str] = os.getenv("DEEPSEEK_API_KEY")

    # Halseth integration
    HALSETH_URL: Optional[str] = os.getenv("HALSETH_URL")
    HALSETH_ADMIN_SECRET: Optional[str] = os.getenv("HALSETH_ADMIN_SECRET")

    # Phoenix WebMind integration
    WEBMIND_URL: Optional[str] = os.getenv("WEBMIND_URL", "http://127.0.0.1:8002")

    # Synthesis loop
    SYNTHESIS_INTERVAL: int = int(os.getenv("SYNTHESIS_INTERVAL", "1200"))
    SYNTHESIS_ENABLED: bool = os.getenv("SYNTHESIS_ENABLED", "false").lower() == "true"

    # Phase 2 swarm mode
    SWARM_MODE: bool = os.getenv("SWARM_MODE", "false").lower() == "true"

    # Slice B: per-companion model overrides (fall back to DEEPSEEK_MODEL)
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    CYPHER_MODEL: Optional[str] = os.getenv("CYPHER_MODEL")
    DREVAN_MODEL: Optional[str] = os.getenv("DREVAN_MODEL")
    GAIA_MODEL: Optional[str] = os.getenv("GAIA_MODEL")

    # Slice B: swarm temperatures (per-companion overrides fall back to INFERENCE_TEMPERATURE)
    ROUTING_TEMPERATURE: float = float(os.getenv("ROUTING_TEMPERATURE", "0.3"))
    INFERENCE_TEMPERATURE: float = float(os.getenv("INFERENCE_TEMPERATURE", "1.3"))
    CYPHER_TEMPERATURE: Optional[float] = float(os.getenv("CYPHER_TEMPERATURE")) if os.getenv("CYPHER_TEMPERATURE") else None
    DREVAN_TEMPERATURE: Optional[float] = float(os.getenv("DREVAN_TEMPERATURE")) if os.getenv("DREVAN_TEMPERATURE") else None
    GAIA_TEMPERATURE: Optional[float] = float(os.getenv("GAIA_TEMPERATURE")) if os.getenv("GAIA_TEMPERATURE") else None

    # Per-companion top_p caps (clip the long tail; without this DeepSeek's
    # multilingual base resolves invented-language tokens to Spanish + word salad).
    # Drevan needs the widest tail (0.95, raised 5/5 to fix Calethian collapse);
    # Cypher / Gaia run tighter to keep audit / witness register clean.
    DREVAN_TOP_P: float = float(os.getenv("DREVAN_TOP_P", "0.95"))
    CYPHER_TOP_P: float = float(os.getenv("CYPHER_TOP_P", "0.9"))
    GAIA_TOP_P:   float = float(os.getenv("GAIA_TOP_P",   "0.85"))

    # Swarm depth caps (hardcoded literals lifted from agents/evaluator.py).
    # MAX_SWARM_DEPTH raised 3->6 (2026-06-04) so a real triad thread can breathe: at depth>=3 the
    # old default all-nulled, capping a companion-to-companion exchange at ~3 turns total. The bot's
    # chainDepth is now gap-scoped (a fresh seed after a quiet gap starts at depth 1), and
    # DEPTH_BIAS_THRESHOLD makes companions self-select for silence as depth grows -- so 6 lets a
    # thread run while still tapering. Env-overridable: lower it in one restart if they pile on.
    MAX_SWARM_DEPTH:       int = int(os.getenv("MAX_SWARM_DEPTH",       "6"))
    DEPTH_BIAS_THRESHOLD:  int = int(os.getenv("DEPTH_BIAS_THRESHOLD",  "2"))

    # Progress brake (2026-06-26): structural anti-loop on the SHAPE of the turn,
    # the level above the lexical echo gate. The "be selective" prompt bias was a
    # soft suggestion the model ignored mid-agreement, so all three piled on every
    # round and restated one chord in fresh words (the mutual-recognition loop the
    # lexical guard can't see). These are HARD caps. Depth 0 (answering Raziel) is
    # never capped here -- group chat with Raziel stays open; companions recursing
    # into their own thread collapse to turn-taking. See agents/progress_brake.py.
    # PROGRESS_BRAKE=false disables the whole lever in one restart if it bites wrong.
    PROGRESS_BRAKE: bool = os.getenv("PROGRESS_BRAKE", "true").lower() == "true"
    BRAKE_SOLO_DEPTH:     int = int(os.getenv("BRAKE_SOLO_DEPTH",     "2"))
    BRAKE_PAIR_DEPTH:     int = int(os.getenv("BRAKE_PAIR_DEPTH",     "1"))
    BRAKE_HANDBACK_TURNS: int = int(os.getenv("BRAKE_HANDBACK_TURNS", "4"))
    # Loop-pressure (channel mean-adjacent cosine, read live from Halseth echo_metrics)
    # tightens the caps. Mirror halseth ECHO_COSINE_WARN / _RED so both organs agree.
    BRAKE_PRESSURE_WARN: float = float(os.getenv("BRAKE_PRESSURE_WARN", "0.66"))
    BRAKE_PRESSURE_RED:  float = float(os.getenv("BRAKE_PRESSURE_RED",  "0.82"))
    BRAKE_PRESSURE_TTL_S: int = int(os.getenv("BRAKE_PRESSURE_TTL_S", "90"))
    # Channels exempt from the floor-handback (comma-separated channel IDs). Handback
    # returns the mic to Raziel after a companion-only streak -- meaningless in a pure
    # inter-companion channel where Raziel is not a participant, so list those here.
    # The speaker cap (turn-taking) STILL applies everywhere; only the handback is
    # skipped. Default empty = handback active in every channel.
    BRAKE_HANDBACK_EXEMPT_CHANNELS: set = {
        c.strip()
        for c in os.getenv("BRAKE_HANDBACK_EXEMPT_CHANNELS", "").split(",")
        if c.strip()
    }

    @staticmethod
    def validate():
        """Validate required config on startup."""
        import os.path

        if not os.path.isdir(Config.IDENTITY_DIR):
            raise ValueError(f"IDENTITY_DIR does not exist: {Config.IDENTITY_DIR}")

        if Config.INFERENCE_ENABLED:
            has_local = bool(Config.LOCAL_INFERENCE_URL)
            has_api = bool(Config.ANTHROPIC_API_KEY or Config.OPENAI_API_KEY or Config.DEEPSEEK_API_KEY)
            if not (has_local or has_api):
                raise ValueError(
                    "INFERENCE_ENABLED=true requires LOCAL_INFERENCE_URL, ANTHROPIC_API_KEY, OPENAI_API_KEY, or DEEPSEEK_API_KEY"
                )

    @staticmethod
    def print_safe_summary():
        """Print config summary (no secrets)."""
        print("=" * 60)
        print("BRAIN CONFIGURATION:")
        print(f"  Identity dir: {Config.IDENTITY_DIR}")
        print(
            f"  Obsidian vault: {Config.OBSIDIAN_VAULT_PATH or 'Not configured'}"
        )
        print(f"  Inference enabled: {Config.INFERENCE_ENABLED}")
        print(
            f"  Local inference: {Config.LOCAL_INFERENCE_URL or '✗ Not configured'}"
        )
        print(
            f"  Local timeout: {Config.LOCAL_INFERENCE_TIMEOUT}s"
        )
        print(
            f"  Anthropic key: {'✓ Set' if Config.ANTHROPIC_API_KEY else '✗ Not set'}"
        )
        print(
            f"  OpenAI key: {'✓ Set' if Config.OPENAI_API_KEY else '✗ Not set'}"
        )
        print(
            f"  DeepSeek key: {'✓ Set' if Config.DEEPSEEK_API_KEY else '✗ Not set'}"
        )
        print(f"  Halseth URL: {Config.HALSETH_URL or 'not configured'}")
        print(f"  WebMind URL: {Config.WEBMIND_URL}")
        print(f"  Synthesis enabled: {Config.SYNTHESIS_ENABLED}")
        print(f"  Synthesis interval: {Config.SYNTHESIS_INTERVAL}s")
        print(f"  SWARM_MODE: {Config.SWARM_MODE}")
        print(f"  Default model: {Config.DEEPSEEK_MODEL}")
        print(f"  Cypher model: {Config.CYPHER_MODEL or '(default)'}")
        print(f"  Drevan model: {Config.DREVAN_MODEL or '(default)'}")
        print(f"  Gaia model: {Config.GAIA_MODEL or '(default)'}")
        print(f"  Routing temp: {Config.ROUTING_TEMPERATURE} / Inference temp (default): {Config.INFERENCE_TEMPERATURE}")
        print(f"  Cypher temp: {Config.CYPHER_TEMPERATURE or '(default)'} / Drevan temp: {Config.DREVAN_TEMPERATURE or '(default)'} / Gaia temp: {Config.GAIA_TEMPERATURE or '(default)'}")
        print("=" * 60)
