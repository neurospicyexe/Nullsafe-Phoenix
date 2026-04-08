"""
Pydantic contracts for WebMind v0 scaffold.

These models lock names and shapes across slices:
- Slice 2: continuity reads (mind_orient / mind_ground), session handoffs, mind threads
- Slice 3: life reminders + housekeeping digest
- Slice 4: bond layer (bond_threads, bond_handoffs, bond_notes, bond_state proxy)
- Slice 5: autonomy v0 (schedules, seeds, runs, logs, reflections)
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

AgentId = Literal["drevan", "cypher", "gaia"]
NoteAgentId = Literal["drevan", "cypher", "gaia", "swarm"]
LifeAgentId = Literal["drevan", "cypher", "gaia", "swarm"]
ReminderStatus = Literal["pending", "snoozed", "dismissed"]
Recurrence = Literal["daily", "weekly", "monthly"]
ActorType = Literal["human", "agent", "system"]
SourceType = Literal["discord", "webui", "system", "autonomy", "api", "synthesis_loop"]
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
    """Append-only continuity note contract (full metadata version).

    Reserved for a future slice that adds note_type + salience to the DB schema.
    The live /mind/notes endpoint currently uses ContinuityNoteSimpleWriteRequest.
    Do NOT add a second /mind/notes endpoint until the schema is extended -- it
    would conflict with the existing route.
    """

    agent_id: AgentId
    thread_key: Optional[str] = None
    note_type: NoteType
    content: str = Field(..., min_length=1)
    salience: Salience = "normal"
    metadata: WriteMetadata


class ContinuityNoteRecord(BaseModel):
    """Stored/retrieved continuity note (full metadata version).

    Pair to ContinuityNoteWriteRequest -- reserved for the same future slice.
    """

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


class ContinuityNoteSimpleRecord(BaseModel):
    """Stored note record (simplified -- used by limbic slice endpoints)."""
    note_id: str
    agent_id: NoteAgentId
    note_text: str = Field(..., min_length=1)
    thread_key: Optional[str] = None
    source: SourceType
    created_at: str


class ContinuityNoteSimpleWriteRequest(BaseModel):
    """Simplified note write request for Brain synthesis and conversation notes."""
    agent_id: NoteAgentId
    note_text: str = Field(..., min_length=1)
    thread_key: Optional[str] = None
    source: SourceType = Field(default="synthesis_loop")


class LimbicStateWriteRequest(BaseModel):
    """Request contract for Brain to write a synthesized swarm state."""
    synthesis_source: str = Field(..., min_length=1, max_length=100)
    active_concerns: List[str] = Field(default_factory=list)
    live_tensions: List[str] = Field(default_factory=list)
    drift_vector: str = Field(..., min_length=1, max_length=300)
    open_questions: List[str] = Field(default_factory=list)
    emotional_register: str = Field(..., min_length=1, max_length=200)
    swarm_threads: List[str] = Field(
        default_factory=list,
        description="Companion-owned threads sourced from dreams/loops. First-class content, not session recaps."
    )
    companion_notes: Dict[str, str] = Field(default_factory=dict)


class LimbicStateRecord(BaseModel):
    """Stored/retrieved limbic state record."""
    state_id: str
    generated_at: str
    synthesis_source: str
    active_concerns: List[str]
    live_tensions: List[str]
    drift_vector: str
    open_questions: List[str]
    emotional_register: str
    swarm_threads: List[str]
    companion_notes: Dict[str, str]
    created_at: str


class IdentityAnchorSnapshot(BaseModel):
    """Fast-read identity anchor snapshot (cache/read model)."""

    agent_id: AgentId
    identity_version_hash: str
    anchor_summary: str
    constraints_summary: Optional[str] = None
    updated_at: str
    source: str


class ReminderWriteRequest(BaseModel):
    """Request to create a life reminder."""
    agent_id: LifeAgentId
    title: str = Field(..., min_length=1, max_length=200)
    body: Optional[str] = None
    due_at: str = Field(..., description="ISO 8601 datetime when reminder surfaces")
    recurrence: Optional[Recurrence] = None
    created_by: ActorType = "human"
    source: SourceType = "api"

    @field_validator("due_at")
    @classmethod
    def validate_due_at(cls, v: str) -> str:
        datetime.fromisoformat(v.replace("Z", "+00:00"))
        return v


class ReminderRecord(BaseModel):
    """Stored reminder record."""
    reminder_id: str
    agent_id: LifeAgentId
    title: str
    body: Optional[str] = None
    due_at: str
    recurrence: Optional[Recurrence] = None
    status: ReminderStatus
    dismissed_at: Optional[str] = None
    created_by: ActorType
    source: SourceType
    created_at: str


class HalsethTaskSummary(BaseModel):
    """Lightweight task record surfaced in the digest from Halseth."""
    id: str
    title: str
    status: str
    priority: Optional[str] = None
    due_at: Optional[str] = None
    assigned_to: Optional[str] = None


class LifeDigestResponse(BaseModel):
    """Aggregated life-support view for a companion."""
    agent_id: str
    due_reminders: List[ReminderRecord] = Field(default_factory=list)
    upcoming_reminders: List[ReminderRecord] = Field(default_factory=list)
    open_threads: List[MindThreadRecord] = Field(default_factory=list)
    halseth_tasks: List[HalsethTaskSummary] = Field(default_factory=list)
    halseth_available: bool = False
    generated_at: str


# ---------------------------------------------------------------------------
# Slice 4: Bond Layer contracts
# ---------------------------------------------------------------------------

BondThreadStatus = Literal["open", "paused", "resolved", "archived"]
BondThreadType = Literal["commitment", "repair", "shared_memory", "ongoing"]
BondNoteType = Literal["observation", "repair", "commitment", "gratitude", "rupture"]


class BondThreadWriteRequest(BaseModel):
    """Open or update a relational bond thread."""
    agent_id: AgentId
    toward: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    thread_type: BondThreadType = "commitment"
    priority: int = Field(5, ge=1, le=10)
    created_by: ActorType = "agent"
    source: SourceType = "api"


class BondThreadUpdateRequest(BaseModel):
    """Partial update for an existing bond thread."""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    status: Optional[BondThreadStatus] = None
    priority: Optional[int] = Field(None, ge=1, le=10)
    updated_by: ActorType = "agent"
    source: SourceType = "api"


class BondThreadRecord(BaseModel):
    """Stored bond thread record."""
    thread_key: str
    agent_id: AgentId
    toward: str
    title: str
    description: Optional[str] = None
    status: BondThreadStatus
    thread_type: BondThreadType
    priority: int
    created_by: ActorType
    source: SourceType
    created_at: str
    updated_at: str


class BondHandoffWriteRequest(BaseModel):
    """Write a relational-specific session handoff."""
    agent_id: AgentId
    toward: str = Field(..., min_length=1, max_length=100)
    relational_state: str = Field(..., min_length=1)
    carried_forward: str = Field(..., min_length=1)
    open_threads_summary: Optional[str] = None
    repair_needed: bool = False
    actor: ActorType = "agent"
    source: SourceType = "api"


class BondHandoffRecord(BaseModel):
    """Stored bond handoff summary."""
    handoff_id: str
    agent_id: AgentId
    toward: str
    relational_state: str
    carried_forward: str
    open_threads_summary: Optional[str] = None
    repair_needed: bool
    actor: ActorType
    source: SourceType
    created_at: str


class BondNoteWriteRequest(BaseModel):
    """Append a note about the bond with a specific person."""
    agent_id: AgentId
    toward: str = Field(..., min_length=1, max_length=100)
    note_text: str = Field(..., min_length=1)
    note_type: BondNoteType = "observation"
    thread_key: Optional[str] = None
    actor: ActorType = "agent"
    source: SourceType = "api"


class BondNoteRecord(BaseModel):
    """Stored bond note."""
    note_id: str
    agent_id: AgentId
    toward: str
    note_text: str
    note_type: BondNoteType
    thread_key: Optional[str] = None
    actor: ActorType
    source: SourceType
    created_at: str


class HalsethRelationalStateEntry(BaseModel):
    """Single companion_relational_state row proxied from Halseth."""
    id: str
    companion_id: str
    toward: str
    state_text: str
    weight: float
    state_type: str
    noted_at: str


class BondStateResponse(BaseModel):
    """Relational state view proxied from Halseth companion_relational_state.

    Halseth is authoritative for relational state -- Phoenix does not duplicate it.
    This endpoint proxies and returns gracefully when Halseth is unavailable.
    """
    agent_id: AgentId
    toward: Optional[str] = None
    entries: List[HalsethRelationalStateEntry] = Field(default_factory=list)
    halseth_available: bool = False
    generated_at: str


class MindOrientResponse(BaseModel):
    """Response for continuity recovery view."""

    agent_id: AgentId
    identity_anchor: Optional[IdentityAnchorSnapshot] = None
    latest_handoff: Optional[SessionHandoffRecord] = None
    top_threads: List[MindThreadRecord] = Field(default_factory=list)
    recent_notes: List[ContinuityNoteSimpleRecord] = Field(default_factory=list)
    limbic_state: Optional[LimbicStateRecord] = None
    generated_at: str


class MindGroundResponse(BaseModel):
    """Response for actionable grounding view."""

    agent_id: AgentId
    open_threads: List[MindThreadRecord] = Field(default_factory=list)
    recent_handoffs: List[SessionHandoffRecord] = Field(default_factory=list)
    recent_notes: List[ContinuityNoteSimpleRecord] = Field(default_factory=list)
    generated_at: str


# ---------------------------------------------------------------------------
# Slice 5: Autonomy v0
# ---------------------------------------------------------------------------

SeedType = Literal["interest", "curiosity", "thread", "dream", "planted"]
SeedStatus = Literal["available", "used", "expired", "dismissed"]
RunStatus = Literal["exploring", "synthesizing", "completed", "failed", "cancelled"]
RunPhase = Literal["explore", "synthesize"]
LogEntryType = Literal["search", "read", "inference", "discovery", "note", "error"]
ReflectionType = Literal["insight", "journal", "thread_update", "continuity_note", "discovery"]
ScheduleFrequency = Literal["every_4h", "every_6h", "every_8h", "every_12h", "daily"]


class AutonomyScheduleWriteRequest(BaseModel):
    """Create/update an autonomy schedule for a companion. One per companion (upsert)."""
    agent_id: AgentId
    enabled: bool = True
    frequency: ScheduleFrequency = "every_6h"
    max_explore_calls: int = Field(10, ge=1, le=50)
    max_synthesize_calls: int = Field(3, ge=1, le=5)
    quiet_hours_start: Optional[str] = None  # HH:MM UTC
    quiet_hours_end: Optional[str] = None    # HH:MM UTC
    allowed_actions: List[str] = Field(default_factory=lambda: ["search", "read", "inference"])
    metadata: WriteMetadata


class AutonomyScheduleRecord(BaseModel):
    """Stored autonomy schedule."""
    schedule_id: str
    agent_id: AgentId
    enabled: bool
    frequency: ScheduleFrequency
    max_explore_calls: int
    max_synthesize_calls: int
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None
    allowed_actions: List[str]
    actor: ActorType
    source: SourceType
    created_at: str
    updated_at: str


class AutonomySeedWriteRequest(BaseModel):
    """Plant or record an autonomy seed (interest, curiosity, dream, or Raziel-planted topic)."""
    agent_id: AgentId
    seed_type: SeedType
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    source_ref: Optional[str] = None  # soft ref: thread_key, dream_id, vault doc, etc.
    metadata: WriteMetadata


class AutonomySeedRecord(BaseModel):
    """Stored autonomy seed."""
    seed_id: str
    agent_id: AgentId
    seed_type: SeedType
    title: str
    description: Optional[str] = None
    source_ref: Optional[str] = None
    status: SeedStatus
    planted_by: ActorType
    source: SourceType
    created_at: str


class AutonomyRunStartRequest(BaseModel):
    """Begin an autonomous run."""
    agent_id: AgentId
    seed_id: Optional[str] = None
    seed_title: Optional[str] = Field(None, max_length=200)  # used when no seed_id
    explore_model: Optional[str] = Field(None, max_length=100)  # e.g. "deepseek-v3"
    max_explore_calls: int = Field(10, ge=1, le=50)
    metadata: WriteMetadata


class AutonomyRunRecord(BaseModel):
    """Stored/retrieved autonomous run record."""
    run_id: str
    agent_id: AgentId
    seed_id: Optional[str] = None
    phase: RunPhase
    status: RunStatus
    explore_model: Optional[str] = None
    synthesize_model: Optional[str] = None
    explore_calls: int
    synthesize_calls: int
    max_explore_calls: int
    seed_title: Optional[str] = None
    error_message: Optional[str] = None
    actor: ActorType
    source: SourceType
    correlation_id: Optional[str] = None
    started_at: str
    phase_changed_at: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: str


class AutonomyRunLogRequest(BaseModel):
    """Append a log entry during Phase 1 exploration."""
    entry_type: LogEntryType
    content: str = Field(..., min_length=1)
    model_used: Optional[str] = Field(None, max_length=100)
    token_count: Optional[int] = Field(None, ge=0)


class AutonomyRunLogRecord(BaseModel):
    """Stored exploration log entry."""
    log_id: str
    run_id: str
    agent_id: AgentId
    entry_type: LogEntryType
    content: str
    model_used: Optional[str] = None
    token_count: Optional[int] = None
    step_index: int
    created_at: str


class AutonomyRunReflectRequest(BaseModel):
    """Write a Phase 2 synthesis reflection."""
    reflection_type: ReflectionType
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    model_used: Optional[str] = Field(None, max_length=100)  # e.g. "claude-sonnet-4-20250514"
    target_ref: Optional[str] = None  # soft ref to where synthesis was deposited


class AutonomyReflectionRecord(BaseModel):
    """Stored Phase 2 synthesis reflection."""
    reflection_id: str
    run_id: str
    agent_id: AgentId
    reflection_type: ReflectionType
    title: str
    content: str
    model_used: Optional[str] = None
    target_ref: Optional[str] = None
    actor: ActorType
    source: SourceType
    created_at: str


class AutonomyRunCompleteRequest(BaseModel):
    """Mark a run as completed, failed, or cancelled."""
    status: Literal["completed", "failed", "cancelled"]
    error_message: Optional[str] = None


class AutonomyRunDetailResponse(BaseModel):
    """Full run detail: run record + exploration logs + synthesis reflections."""
    run: AutonomyRunRecord
    logs: List[AutonomyRunLogRecord] = Field(default_factory=list)
    reflections: List[AutonomyReflectionRecord] = Field(default_factory=list)

