"""
Pydantic contracts for WebMind v0 scaffold.

These models lock names and shapes for Slice 2 work:
- continuity reads (mind_orient / mind_ground)
- session handoffs
- mind threads
- continuity notes
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

AgentId = Literal["drevan", "cypher", "gaia"]
ActorType = Literal["human", "agent", "system"]
SourceType = Literal["discord", "webui", "system", "autonomy", "api"]
ThreadStatus = Literal["open", "paused", "resolved", "archived"]
ThreadLane = Literal["bond", "life", "growth", "creative", "ops"]
NoteType = Literal["continuity", "reflection", "memory_anchor", "ops"]
Salience = Literal["low", "normal", "high"]
StateHint = Literal["supportive", "practical", "reflective", "autonomous"]


class WriteMetadata(BaseModel):
    """Required metadata for WebMind writes."""

    actor: ActorType
    source: SourceType
    correlation_id: Optional[str] = None


class SessionHandoffWriteRequest(BaseModel):
    """Request contract for writing session handoffs."""

    agent_id: AgentId
    thread_id: Optional[str] = None
    title: str = Field(..., min_length=1, max_length=200)
    summary: str = Field(..., min_length=1)
    next_steps: str = Field(..., min_length=1)
    open_loops: str = Field(..., min_length=1)
    state_hint: Optional[StateHint] = None
    metadata: WriteMetadata


class SessionHandoffRecord(BaseModel):
    """Stored/retrieved session handoff record."""

    handoff_id: str
    agent_id: AgentId
    thread_id: Optional[str] = None
    title: str
    summary: str
    next_steps: str
    open_loops: str
    state_hint: Optional[str] = None
    actor: ActorType
    source: SourceType
    correlation_id: Optional[str] = None
    created_at: str

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, v: str) -> str:
        datetime.fromisoformat(v.replace("Z", "+00:00"))
        return v


class MindThreadUpsertRequest(BaseModel):
    """Create/update contract for persistent mind threads."""

    agent_id: AgentId
    thread_key: Optional[str] = None
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    status: Optional[ThreadStatus] = None
    priority: int = Field(5, ge=1, le=10)
    lane: Optional[ThreadLane] = None
    metadata: WriteMetadata


class MindThreadRecord(BaseModel):
    """Stored/retrieved thread record."""

    thread_key: str
    agent_id: AgentId
    title: str
    description: Optional[str] = None
    status: ThreadStatus
    priority: int
    lane: Optional[ThreadLane] = None
    last_touched_at: str
    created_at: str
    updated_at: str
    created_by_actor: ActorType
    updated_by_actor: ActorType
    source: SourceType
    correlation_id: Optional[str] = None


class MindThreadEventRecord(BaseModel):
    """Append-only event record for thread changes."""

    event_id: str
    thread_key: str
    agent_id: AgentId
    event_type: Literal["created", "updated", "status_changed", "note_added"]
    event_summary: str
    payload_json: Dict[str, Any] = Field(default_factory=dict)
    actor: ActorType
    source: SourceType
    correlation_id: Optional[str] = None
    created_at: str


class ContinuityNoteWriteRequest(BaseModel):
    """Append-only continuity note contract."""

    agent_id: AgentId
    thread_key: Optional[str] = None
    note_type: NoteType
    content: str = Field(..., min_length=1)
    salience: Salience = "normal"
    metadata: WriteMetadata


class ContinuityNoteRecord(BaseModel):
    """Stored/retrieved continuity note."""

    note_id: str
    agent_id: AgentId
    thread_key: Optional[str] = None
    note_type: NoteType
    content: str
    salience: Salience
    actor: ActorType
    source: SourceType
    correlation_id: Optional[str] = None
    created_at: str


class IdentityAnchorSnapshot(BaseModel):
    """Fast-read identity anchor snapshot (cache/read model)."""

    agent_id: AgentId
    identity_version_hash: str
    anchor_summary: str
    constraints_summary: Optional[str] = None
    updated_at: str
    source: str


class MindOrientResponse(BaseModel):
    """Response for continuity recovery view."""

    agent_id: AgentId
    identity_anchor: Optional[IdentityAnchorSnapshot] = None
    latest_handoff: Optional[SessionHandoffRecord] = None
    top_threads: List[MindThreadRecord] = Field(default_factory=list)
    recent_notes: List[ContinuityNoteRecord] = Field(default_factory=list)
    generated_at: str


class MindGroundResponse(BaseModel):
    """Response for actionable grounding view."""

    agent_id: AgentId
    open_threads: List[MindThreadRecord] = Field(default_factory=list)
    recent_handoffs: List[SessionHandoffRecord] = Field(default_factory=list)
    recent_notes: List[ContinuityNoteRecord] = Field(default_factory=list)
    generated_at: str

