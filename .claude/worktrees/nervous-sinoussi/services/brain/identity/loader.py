#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Identity loader for Nullsafe Phoenix Brain.

Loads agent identity from YAML files deterministically.
"""

import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AgentIdentity(BaseModel):
    """Agent identity schema."""
    name: str
    role: str
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
        logger.info(f"Identity loader initialized with directory: {self.identity_dir}")

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
            return self._cache[agent_id]

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

            return identity, identity_version

        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in identity file for {agent_id}: {e}")
        except Exception as e:
            raise ValueError(f"Error loading identity for {agent_id}: {e}")

    def construct_prompt_context(self, identity: AgentIdentity) -> str:
        """
        Construct deterministic prompt context from identity fields.

        Args:
            identity: Agent identity

        Returns:
            Formatted prompt context string
        """
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
