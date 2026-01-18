"""
Shared Pydantic contracts for Nullsafe Phoenix v2 Day One Kernel.

ThoughtPacket: Request format for all agent interactions
AgentReply: Response format from agents
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class ThoughtPacket(BaseModel):
    """
    Request packet for agent processing.

    Thread ID Semantics:
    - For Discord: thread_id = channel_id
    - For WebUI: thread_id = session_uuid
    """
    packet_id: str = Field(..., description="UUID4 identifier for this packet")
    timestamp: str = Field(..., description="ISO-8601 timestamp")
    source: Literal["discord", "webui", "system"] = Field(..., description="Origin of the packet")
    user_id: str = Field(..., description="User identifier")
    thread_id: str = Field(..., description="Discord channel/thread ID or web session ID")
    agent_id: Literal["drevan", "cypher", "gaia"] = Field(..., description="Target agent")
    message: str = Field(..., description="User message content")
    metadata: Dict[str, Any] = Field(..., description="Source-specific metadata")

    # Optional fields
    lane: Optional[str] = Field(None, description="Processing lane: immersion|praxis|translation|research")
    policy_profile: Optional[str] = Field("safe_default", description="Policy profile for this interaction")
    priority: Optional[int] = Field(5, description="Priority level (1-10)")
    trace: Optional[Dict[str, Any]] = Field(None, description="Debug trace information")

    @field_validator("packet_id")
    @classmethod
    def validate_packet_id(cls, v: str) -> str:
        """Validate packet_id is a valid UUID4."""
        try:
            uuid_obj = UUID(v, version=4)
            # Ensure it's lowercase for consistency
            return str(uuid_obj)
        except (ValueError, AttributeError) as e:
            raise ValueError(f"packet_id must be a valid UUID4: {e}")

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        """Validate timestamp is ISO-8601 format."""
        try:
            # Attempt to parse as ISO-8601
            datetime.fromisoformat(v.replace('Z', '+00:00'))
            return v
        except (ValueError, AttributeError) as e:
            raise ValueError(f"timestamp must be ISO-8601 format: {e}")

    @model_validator(mode='after')
    def validate_metadata_for_discord(self) -> 'ThoughtPacket':
        """If source is discord, metadata must contain channel_id."""
        if self.source == "discord":
            if not self.metadata.get("channel_id"):
                raise ValueError("metadata.channel_id is required when source='discord'")
        return self

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> 'ThoughtPacket':
        """Deserialize from JSON string."""
        return cls.model_validate_json(json_str)


class AgentReply(BaseModel):
    """
    Response packet from agent processing.

    Status values:
    - ok: Successfully processed
    - queued: Queued for processing
    - error: Processing failed
    - brain_offline: Brain service unavailable
    """
    packet_id: str = Field(..., description="Echo back packet_id from request")
    agent_id: str = Field(..., description="Agent that processed this packet")
    status: Literal["ok", "queued", "error", "brain_offline"] = Field(..., description="Processing status")
    reply_text: str = Field(..., description="Agent reply text (can be empty if queued)")

    # Optional fields
    trace: Optional[Dict[str, Any]] = Field(None, description="Debug trace with repro_stamp")
    writes: Optional[List[Dict[str, Any]]] = Field(None, description="Obsidian write actions performed")

    @field_validator("packet_id")
    @classmethod
    def validate_packet_id(cls, v: str) -> str:
        """Validate packet_id is a valid UUID4."""
        try:
            uuid_obj = UUID(v, version=4)
            return str(uuid_obj)
        except (ValueError, AttributeError) as e:
            raise ValueError(f"packet_id must be a valid UUID4: {e}")

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> 'AgentReply':
        """Deserialize from JSON string."""
        return cls.model_validate_json(json_str)


# Queue envelope for retry tracking
class QueueEnvelope(BaseModel):
    """
    Envelope wrapper for packets in Redis queues.
    Preserves retry state across crashes.
    """
    packet: Dict[str, Any] = Field(..., description="The wrapped ThoughtPacket or AgentReply")
    attempts: int = Field(0, description="Number of processing attempts")
    first_attempt_ts: str = Field(..., description="ISO-8601 timestamp of first attempt")
    last_attempt_ts: str = Field(..., description="ISO-8601 timestamp of last attempt")

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> 'QueueEnvelope':
        """Deserialize from JSON string."""
        return cls.model_validate_json(json_str)
