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

    # API Keys (optional until inference enabled)
    ANTHROPIC_API_KEY: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    DEEPSEEK_API_KEY: Optional[str] = os.getenv("DEEPSEEK_API_KEY")

    @staticmethod
    def validate():
        """Validate required config on startup."""
        import os.path

        if not os.path.isdir(Config.IDENTITY_DIR):
            raise ValueError(f"IDENTITY_DIR does not exist: {Config.IDENTITY_DIR}")

        if Config.INFERENCE_ENABLED:
            if not (Config.ANTHROPIC_API_KEY or Config.OPENAI_API_KEY):
                raise ValueError(
                    "INFERENCE_ENABLED=true requires ANTHROPIC_API_KEY or OPENAI_API_KEY"
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
            f"  Anthropic key: {'✓ Set' if Config.ANTHROPIC_API_KEY else '✗ Not set'}"
        )
        print(
            f"  OpenAI key: {'✓ Set' if Config.OPENAI_API_KEY else '✗ Not set'}"
        )
        print(
            f"  DeepSeek key: {'✓ Set' if Config.DEEPSEEK_API_KEY else '✗ Not set'}"
        )
        print("=" * 60)
