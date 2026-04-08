#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Configuration for WebMind service."""

import os
from pathlib import Path


class Config:
    """WebMind service configuration."""

    WEBMIND_PORT: int = int(os.getenv("WEBMIND_PORT", "8002"))
    WEBMIND_DB_URL: str = os.getenv("WEBMIND_DB_URL", "sqlite:///./data/webmind.db")
    WEBMIND_AUTH_TOKEN: str | None = os.getenv("WEBMIND_AUTH_TOKEN")
    WEBMIND_LOG_LEVEL: str = os.getenv("WEBMIND_LOG_LEVEL", "INFO")
    # Optional Halseth integration for /life/digest task aggregation
    HALSETH_URL: str | None = os.getenv("HALSETH_URL")
    HALSETH_AUTH_TOKEN: str | None = os.getenv("HALSETH_AUTH_TOKEN")

    @staticmethod
    def validate() -> None:
        """Validate startup configuration."""
        if Config.WEBMIND_PORT <= 0 or Config.WEBMIND_PORT > 65535:
            raise ValueError(f"WEBMIND_PORT must be 1-65535, got {Config.WEBMIND_PORT}")

        if not Config.WEBMIND_DB_URL:
            raise ValueError("WEBMIND_DB_URL must not be empty")

    @staticmethod
    def ensure_dev_paths() -> None:
        """
        Create local directories for default SQLite dev setups.

        Keeps early local runs simple without forcing the full DB layer yet.
        """
        if Config.WEBMIND_DB_URL.startswith("sqlite:///"):
            db_path = Config.WEBMIND_DB_URL.replace("sqlite:///", "", 1)
            path = Path(db_path)
            if path.parent and str(path.parent) not in ("", "."):
                path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def print_safe_summary() -> None:
        """Print config summary without secrets."""
        print("=" * 60)
        print("WEBMIND CONFIGURATION:")
        print(f"  Port: {Config.WEBMIND_PORT}")
        print(f"  DB URL: {Config.WEBMIND_DB_URL}")
        print(f"  Auth token: {'Set' if Config.WEBMIND_AUTH_TOKEN else 'Not set'}")
        print(f"  Log level: {Config.WEBMIND_LOG_LEVEL}")
        print(f"  Halseth URL: {Config.HALSETH_URL or 'Not set (digest will skip task aggregation)'}")
        print(f"  Halseth auth: {'Set' if Config.HALSETH_AUTH_TOKEN else 'Not set'}")
        print("=" * 60)

