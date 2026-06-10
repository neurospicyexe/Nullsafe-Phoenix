#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Identity loader for Nullsafe Phoenix Brain.

Loads agent identity from YAML files deterministically.
"""

import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

# Identity kernel overlay: refetched at most once per TTL so kernel updates in
# Halseth reach a running Brain without a restart.
KERNEL_TTL_SECONDS = 600
KERNEL_MAX_CHARS = 8000


class AgentIdentity(BaseModel):
    """Agent identity schema."""
    # Reject unknown keys at load time -- a typo like `system_promt` must fail loudly,
    # not silently fall through to stub fragment assembly.
    model_config = ConfigDict(extra="forbid")

    name: str
    role: str
    system_prompt: Optional[str] = None  # Full system prompt -- takes precedence over fragments when present
    anchors: List[str] = Field(default_factory=list)
    cadence: str = ""
    constraints: List[str] = Field(default_factory=list)
    system_prompt_fragments: List[str] = Field(default_factory=list)


class IdentityLoader:
    """
    Loads and caches agent identities from YAML files.

    Identity files are located at: services/brain/identity/data/{agent_id}.yaml
    """

    def __init__(self, identity_dir: Optional[Path] = None):
        """
        Initialize identity loader.

        Args:
            identity_dir: Directory containing identity YAML files.
                         Defaults to services/brain/identity/data/
        """
        if identity_dir is None:
            # Default to services/brain/identity/data relative to this file
            self.identity_dir = Path(__file__).parent / "data"
        else:
            self.identity_dir = Path(identity_dir)

        self._cache: Dict[str, tuple[AgentIdentity, str]] = {}
        # agent_id -> (bundle_text, fetched_at_monotonic)
        self._kernel_cache: Dict[str, tuple[str, float]] = {}
        logger.info(f"Identity loader initialized with directory: {self.identity_dir}")

    def _fetch_kernel_overlay(self, agent_id: str) -> Optional[str]:
        """
        Fetch the canonical identity kernel bundle from Halseth.

        The YAML stays the structural skeleton; the kernel is the canonical flesh,
        synced from the same store every other substrate boots from. Never raises:
        Halseth being unreachable degrades to YAML-only identity (offline-safe).
        """
        url = os.getenv("HALSETH_URL")
        secret = os.getenv("HALSETH_ADMIN_SECRET")
        if not url or not secret:
            return None

        cached = self._kernel_cache.get(agent_id)
        if cached and (time.monotonic() - cached[1]) < KERNEL_TTL_SECONDS:
            return cached[0]

        try:
            resp = httpx.get(
                f"{url.rstrip('/')}/identity/kernel/{agent_id}/bundle",
                headers={"Authorization": f"Bearer {secret}"},
                timeout=5.0,
            )
            resp.raise_for_status()
            bundle = resp.json().get("bundle")
            if isinstance(bundle, str) and len(bundle) > 200:
                self._kernel_cache[agent_id] = (bundle, time.monotonic())
                logger.info(f"Kernel overlay for {agent_id}: {len(bundle)} chars from Halseth")
                return bundle
            logger.warning(f"Kernel overlay for {agent_id}: bundle missing or too short, ignoring")
        except Exception as e:
            logger.warning(f"Kernel overlay fetch failed for {agent_id} (using stale/YAML): {e}")

        # Stale cache beats nothing -- identity continuity over freshness.
        return cached[0] if cached else None

    def load_identity(self, agent_id: str) -> tuple[AgentIdentity, str]:
        """
        Load agent identity from YAML file.

        Args:
            agent_id: Agent identifier (drevan, cypher, gaia)

        Returns:
            Tuple of (AgentIdentity, identity_version_hash)

        Raises:
            FileNotFoundError: If identity file doesn't exist
            ValueError: If YAML is invalid or schema doesn't match
        """
        # Check cache first
        if agent_id in self._cache:
            logger.debug(f"Identity for {agent_id} loaded from cache")
            return self._apply_kernel_overlay(agent_id, *self._cache[agent_id])

        # Load from file
        identity_path = self.identity_dir / f"{agent_id}.yaml"

        if not identity_path.exists():
            raise FileNotFoundError(
                f"Identity file not found for agent '{agent_id}' at {identity_path}"
            )

        logger.info(f"Loading identity for {agent_id} from {identity_path}")

        try:
            with open(identity_path, 'r', encoding='utf-8') as f:
                raw_yaml = f.read()
                data = yaml.safe_load(raw_yaml)

            # Validate schema
            identity = AgentIdentity(**data)

            # Compute identity version hash (SHA256 of file contents)
            identity_version = hashlib.sha256(raw_yaml.encode('utf-8')).hexdigest()[:16]

            # Cache result
            self._cache[agent_id] = (identity, identity_version)

            logger.info(
                f"Loaded identity for {agent_id}: {identity.name} (version: {identity_version})"
            )

            return self._apply_kernel_overlay(agent_id, identity, identity_version)

        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in identity file for {agent_id}: {e}")
        except Exception as e:
            raise ValueError(f"Error loading identity for {agent_id}: {e}")

    def _apply_kernel_overlay(
        self, agent_id: str, identity: AgentIdentity, identity_version: str
    ) -> tuple[AgentIdentity, str]:
        """
        Append the Halseth kernel bundle to system_prompt when available.

        Returns a copy so the cached YAML identity stays pristine; the version
        hash folds in the kernel checksum so consumers see kernel changes.
        """
        overlay = self._fetch_kernel_overlay(agent_id)
        if not overlay:
            return identity, identity_version

        merged = identity.model_copy(deep=True)
        merged.system_prompt = (
            (identity.system_prompt or "").rstrip()
            + "\n\n# IDENTITY KERNEL (canonical, Halseth-synced)\n"
            + overlay[:KERNEL_MAX_CHARS]
        ).strip()
        kernel_hash = hashlib.sha256(overlay.encode("utf-8")).hexdigest()[:8]
        return merged, f"{identity_version}+k{kernel_hash}"

    def construct_prompt_context(self, identity: AgentIdentity) -> str:
        """
        Construct deterministic prompt context from identity fields.

        When system_prompt is present it is returned directly (real identity).
        Falls back to fragment assembly for stub identities.

        Args:
            identity: Agent identity

        Returns:
            Formatted prompt context string
        """
        if identity.system_prompt:
            return identity.system_prompt.strip()

        lines = []

        # Name and role
        lines.append(f"Agent: {identity.name}")
        lines.append(f"Role: {identity.role}")

        # Anchors (identity grounding)
        if identity.anchors:
            lines.append("\nIdentity Anchors:")
            for anchor in identity.anchors:
                lines.append(f"  - {anchor}")

        # Cadence (speaking style)
        if identity.cadence:
            lines.append(f"\nCadence: {identity.cadence}")

        # Constraints (behavioral rules)
        if identity.constraints:
            lines.append("\nConstraints:")
            for constraint in identity.constraints:
                lines.append(f"  - {constraint}")

        # System prompt fragments
        if identity.system_prompt_fragments:
            lines.append("\nSystem Prompt Fragments:")
            for fragment in identity.system_prompt_fragments:
                lines.append(f"  - {fragment}")

        return "\n".join(lines)
