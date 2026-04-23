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
        print("=" * 60)
