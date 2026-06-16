#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebMind SQLite database module.

Manages aiosqlite connection and schema init for:

Slice 2 (continuity):
  - limbic_states: synthesized swarm state records
  - continuity_notes: companion and synthesis notes (cap: 100/agent)
  - session_handoffs: session checkpoints per companion (cap: 30/agent)
  - mind_threads: persistent companion threads
  - mind_thread_events: append-only event log for thread changes (TTL: 90d)

Slice 3 (life support):
  - life_reminders: companion reminders with status lifecycle

Slice 4 (bond layer):
  - bond_threads: relational threads per companion (toward a person)
  - bond_handoff_summaries: relational session handoffs (cap: 30/agent)
  - bond_notes: bond observations and repair notes (cap: 200/agent)

Slice 5 (autonomy):
  - autonomy_schedules: per-companion run schedule (one per companion)
  - autonomy_seeds: interest/curiosity seeds for autonomous exploration
  - autonomy_runs: execution records for autonomous runs (TTL: 90d terminal)
  - autonomy_run_logs: phase-1 exploration step log (TTL: 90d)
  - autonomy_reflections: phase-2 synthesis output

Slice 6 (growth):
  - growth_journal: developmental observations/insights (cap: 200/agent, salience-aware)
  - growth_patterns: recurring companion patterns (cap: 50/agent, confidence-aware)
  - growth_markers: significant developmental moments (cap: 100/agent)
"""

from contextlib import asynccontextmanager

import aiosqlite
from services.webmind.config import Config

# Extract file path from sqlite:/// URL (e.g. "./data/webmind.db")
_DB_PATH: str = Config.WEBMIND_DB_URL.replace("sqlite:///", "", 1)

_CREATE_LIMBIC_STATES = """
CREATE TABLE IF NOT EXISTS limbic_states (
    state_id           TEXT PRIMARY KEY,
    generated_at       TEXT NOT NULL,
    synthesis_source   TEXT NOT NULL,
    active_concerns    TEXT NOT NULL DEFAULT '[]',
    live_tensions      TEXT NOT NULL DEFAULT '[]',
    drift_vector       TEXT NOT NULL,
    open_questions     TEXT NOT NULL DEFAULT '[]',
    emotional_register TEXT NOT NULL,
    swarm_threads      TEXT NOT NULL DEFAULT '[]',
    companion_notes    TEXT NOT NULL DEFAULT '{}',
    created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_CONTINUITY_NOTES = """
CREATE TABLE IF NOT EXISTS continuity_notes (
    note_id     TEXT PRIMARY KEY,
    agent_id    TEXT NOT NULL CHECK (agent_id IN ('drevan', 'cypher', 'gaia', 'swarm')),
    thread_key  TEXT,
    note_text   TEXT NOT NULL,
    source      TEXT NOT NULL DEFAULT 'synthesis_loop',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_NOTES_IDX = """
CREATE INDEX IF NOT EXISTS idx_notes_agent_created
ON continuity_notes (agent_id, created_at DESC);
"""

_CREATE_LIMBIC_IDX = """
CREATE INDEX IF NOT EXISTS idx_limbic_created
ON limbic_states (created_at DESC);
"""

_CREATE_MIND_THREADS = """
CREATE TABLE IF NOT EXISTS mind_threads (
    thread_key        TEXT NOT NULL,
    agent_id          TEXT NOT NULL CHECK (agent_id IN ('drevan', 'cypher', 'gaia')),
    title             TEXT NOT NULL,
    description       TEXT,
    status            TEXT NOT NULL DEFAULT 'open'
                          CHECK (status IN ('open', 'paused', 'resolved', 'archived')),
    priority          INTEGER NOT NULL DEFAULT 5,
    lane              TEXT,
    last_touched_at   TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    created_by_actor  TEXT NOT NULL,
    updated_by_actor  TEXT NOT NULL,
    source            TEXT NOT NULL,
    correlation_id    TEXT,
    PRIMARY KEY (thread_key, agent_id)
);
"""

_CREATE_THREADS_IDX = """
CREATE INDEX IF NOT EXISTS idx_threads_agent_status
ON mind_threads (agent_id, status, priority DESC);
"""

_CREATE_SESSION_HANDOFFS = """
CREATE TABLE IF NOT EXISTS session_handoffs (
    handoff_id     TEXT PRIMARY KEY,
    agent_id       TEXT NOT NULL CHECK (agent_id IN ('drevan', 'cypher', 'gaia')),
    thread_id      TEXT,
    title          TEXT NOT NULL,
    summary        TEXT NOT NULL,
    next_steps     TEXT NOT NULL,
    open_loops     TEXT NOT NULL,
    state_hint     TEXT,
    actor          TEXT NOT NULL,
    source         TEXT NOT NULL,
    correlation_id TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (thread_id, agent_id)
        REFERENCES mind_threads (thread_key, agent_id)
        ON DELETE RESTRICT
);
"""

_CREATE_HANDOFFS_IDX = """
CREATE INDEX IF NOT EXISTS idx_handoffs_agent_created
ON session_handoffs (agent_id, created_at DESC);
"""

_CREATE_MIND_THREAD_EVENTS = """
CREATE TABLE IF NOT EXISTS mind_thread_events (
    event_id       TEXT PRIMARY KEY,
    thread_key     TEXT NOT NULL,
    agent_id       TEXT NOT NULL CHECK (agent_id IN ('drevan', 'cypher', 'gaia')),
    event_type     TEXT NOT NULL
                       CHECK (event_type IN ('created', 'updated', 'status_changed', 'note_added')),
    event_summary  TEXT NOT NULL,
    payload_json   TEXT NOT NULL DEFAULT '{}',
    actor          TEXT NOT NULL,
    source         TEXT NOT NULL,
    correlation_id TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (thread_key, agent_id)
        REFERENCES mind_threads (thread_key, agent_id)
        ON DELETE CASCADE
);
"""

_CREATE_THREAD_EVENTS_IDX = """
CREATE INDEX IF NOT EXISTS idx_thread_events_key_agent
ON mind_thread_events (thread_key, agent_id, created_at DESC);
"""

_CREATE_LIFE_REMINDERS = """
CREATE TABLE IF NOT EXISTS life_reminders (
    reminder_id  TEXT PRIMARY KEY,
    agent_id     TEXT NOT NULL CHECK (agent_id IN ('drevan', 'cypher', 'gaia', 'swarm')),
    title        TEXT NOT NULL,
    body         TEXT,
    due_at       TEXT NOT NULL,
    recurrence   TEXT CHECK (recurrence IN ('daily', 'weekly', 'monthly', NULL)),
    status       TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'snoozed', 'dismissed')),
    dismissed_at TEXT,
    created_by   TEXT NOT NULL,
    source       TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_REMINDERS_IDX = """
CREATE INDEX IF NOT EXISTS idx_reminders_agent_status_due
ON life_reminders (agent_id, status, due_at);
"""

# ---------------------------------------------------------------------------
# Slice 4: Bond Layer
# ---------------------------------------------------------------------------

_CREATE_BOND_THREADS = """
CREATE TABLE IF NOT EXISTS bond_threads (
    thread_key   TEXT PRIMARY KEY,
    agent_id     TEXT NOT NULL CHECK (agent_id IN ('drevan', 'cypher', 'gaia')),
    toward       TEXT NOT NULL,
    title        TEXT NOT NULL,
    description  TEXT,
    status       TEXT NOT NULL DEFAULT 'open'
                     CHECK (status IN ('open', 'paused', 'resolved', 'archived')),
    thread_type  TEXT NOT NULL DEFAULT 'commitment'
                     CHECK (thread_type IN ('commitment', 'repair', 'shared_memory', 'ongoing')),
    priority     INTEGER NOT NULL DEFAULT 5,
    created_by   TEXT NOT NULL,
    source       TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
"""

_CREATE_BOND_THREADS_IDX = """
CREATE INDEX IF NOT EXISTS idx_bond_threads_agent_status
ON bond_threads (agent_id, status, priority DESC);
"""

_CREATE_BOND_THREADS_TOWARD_IDX = """
CREATE INDEX IF NOT EXISTS idx_bond_threads_agent_toward
ON bond_threads (agent_id, toward, status);
"""

_CREATE_BOND_HANDOFFS = """
CREATE TABLE IF NOT EXISTS bond_handoff_summaries (
    handoff_id           TEXT PRIMARY KEY,
    agent_id             TEXT NOT NULL CHECK (agent_id IN ('drevan', 'cypher', 'gaia')),
    toward               TEXT NOT NULL,
    relational_state     TEXT NOT NULL,
    carried_forward      TEXT NOT NULL,
    open_threads_summary TEXT,
    repair_needed        INTEGER NOT NULL DEFAULT 0,
    actor                TEXT NOT NULL,
    source               TEXT NOT NULL,
    created_at           TEXT NOT NULL
);
"""

_CREATE_BOND_HANDOFFS_IDX = """
CREATE INDEX IF NOT EXISTS idx_bond_handoffs_agent_toward
ON bond_handoff_summaries (agent_id, toward, created_at DESC);
"""

_CREATE_BOND_NOTES = """
CREATE TABLE IF NOT EXISTS bond_notes (
    note_id     TEXT PRIMARY KEY,
    agent_id    TEXT NOT NULL CHECK (agent_id IN ('drevan', 'cypher', 'gaia')),
    toward      TEXT NOT NULL,
    note_text   TEXT NOT NULL,
    note_type   TEXT NOT NULL DEFAULT 'observation'
                    CHECK (note_type IN ('observation', 'repair', 'commitment', 'gratitude', 'rupture')),
    thread_key  TEXT,
    actor       TEXT NOT NULL,
    source      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (thread_key) REFERENCES bond_threads (thread_key) ON DELETE RESTRICT
);
"""

_CREATE_BOND_NOTES_IDX = """
CREATE INDEX IF NOT EXISTS idx_bond_notes_agent_toward
ON bond_notes (agent_id, toward, created_at DESC);
"""

# ---------------------------------------------------------------------------
# Slice 5: Autonomy v0
# ---------------------------------------------------------------------------

_CREATE_AUTONOMY_SCHEDULES = """
CREATE TABLE IF NOT EXISTS autonomy_schedules (
    schedule_id          TEXT PRIMARY KEY,
    agent_id             TEXT NOT NULL CHECK (agent_id IN ('drevan', 'cypher', 'gaia')),
    enabled              INTEGER NOT NULL DEFAULT 1,
    frequency            TEXT NOT NULL DEFAULT 'every_6h'
                             CHECK (frequency IN ('every_4h', 'every_6h', 'every_8h', 'every_12h', 'daily')),
    max_explore_calls    INTEGER NOT NULL DEFAULT 10
                             CHECK (max_explore_calls >= 1 AND max_explore_calls <= 50),
    max_synthesize_calls INTEGER NOT NULL DEFAULT 3
                             CHECK (max_synthesize_calls >= 1 AND max_synthesize_calls <= 5),
    quiet_hours_start    TEXT,
    quiet_hours_end      TEXT,
    allowed_actions      TEXT NOT NULL DEFAULT '["search","read","inference"]',
    actor                TEXT NOT NULL,
    source               TEXT NOT NULL,
    created_at           TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at           TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (agent_id)
);
"""

_CREATE_AUTONOMY_SEEDS = """
CREATE TABLE IF NOT EXISTS autonomy_seeds (
    seed_id    TEXT PRIMARY KEY,
    agent_id   TEXT NOT NULL CHECK (agent_id IN ('drevan', 'cypher', 'gaia')),
    seed_type  TEXT NOT NULL
                   CHECK (seed_type IN ('interest', 'curiosity', 'thread', 'dream', 'planted')),
    title      TEXT NOT NULL,
    description TEXT,
    source_ref  TEXT,
    status     TEXT NOT NULL DEFAULT 'available'
                   CHECK (status IN ('available', 'used', 'expired', 'dismissed')),
    planted_by TEXT NOT NULL,
    source     TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_SEEDS_IDX = """
CREATE INDEX IF NOT EXISTS idx_seeds_agent_status
ON autonomy_seeds (agent_id, status, created_at DESC);
"""

_CREATE_AUTONOMY_RUNS = """
CREATE TABLE IF NOT EXISTS autonomy_runs (
    run_id            TEXT PRIMARY KEY,
    agent_id          TEXT NOT NULL CHECK (agent_id IN ('drevan', 'cypher', 'gaia')),
    seed_id           TEXT,
    phase             TEXT NOT NULL DEFAULT 'explore'
                          CHECK (phase IN ('explore', 'synthesize')),
    status            TEXT NOT NULL DEFAULT 'exploring'
                          CHECK (status IN ('exploring', 'synthesizing', 'completed', 'failed', 'cancelled')),
    explore_model     TEXT,
    synthesize_model  TEXT,
    explore_calls     INTEGER NOT NULL DEFAULT 0,
    synthesize_calls  INTEGER NOT NULL DEFAULT 0,
    max_explore_calls INTEGER NOT NULL DEFAULT 10,
    seed_title        TEXT,
    error_message     TEXT,
    actor             TEXT NOT NULL,
    source            TEXT NOT NULL,
    correlation_id    TEXT,
    started_at        TEXT NOT NULL,
    phase_changed_at  TEXT,
    completed_at      TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (seed_id) REFERENCES autonomy_seeds (seed_id) ON DELETE SET NULL
);
"""

_CREATE_RUNS_AGENT_STATUS_IDX = """
CREATE INDEX IF NOT EXISTS idx_runs_agent_status
ON autonomy_runs (agent_id, status, started_at DESC);
"""

_CREATE_RUNS_AGENT_CREATED_IDX = """
CREATE INDEX IF NOT EXISTS idx_runs_agent_created
ON autonomy_runs (agent_id, created_at DESC);
"""

_CREATE_AUTONOMY_RUN_LOGS = """
CREATE TABLE IF NOT EXISTS autonomy_run_logs (
    log_id      TEXT PRIMARY KEY,
    run_id      TEXT NOT NULL,
    agent_id    TEXT NOT NULL CHECK (agent_id IN ('drevan', 'cypher', 'gaia')),
    entry_type  TEXT NOT NULL
                    CHECK (entry_type IN ('search', 'read', 'inference', 'discovery', 'note', 'error')),
    content     TEXT NOT NULL,
    model_used  TEXT,
    token_count INTEGER,
    step_index  INTEGER NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (run_id) REFERENCES autonomy_runs (run_id) ON DELETE CASCADE
);
"""

_CREATE_RUN_LOGS_IDX = """
CREATE INDEX IF NOT EXISTS idx_run_logs_run
ON autonomy_run_logs (run_id, step_index);
"""

_CREATE_AUTONOMY_REFLECTIONS = """
CREATE TABLE IF NOT EXISTS autonomy_reflections (
    reflection_id   TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL,
    agent_id        TEXT NOT NULL CHECK (agent_id IN ('drevan', 'cypher', 'gaia')),
    reflection_type TEXT NOT NULL
                        CHECK (reflection_type IN ('insight', 'journal', 'thread_update', 'continuity_note', 'discovery')),
    title           TEXT NOT NULL,
    content         TEXT NOT NULL,
    model_used      TEXT,
    target_ref      TEXT,
    actor           TEXT NOT NULL,
    source          TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (run_id) REFERENCES autonomy_runs (run_id) ON DELETE CASCADE
);
"""

_CREATE_REFLECTIONS_RUN_IDX = """
CREATE INDEX IF NOT EXISTS idx_reflections_run
ON autonomy_reflections (run_id, created_at);
"""

_CREATE_REFLECTIONS_AGENT_IDX = """
CREATE INDEX IF NOT EXISTS idx_reflections_agent
ON autonomy_reflections (agent_id, created_at DESC);
"""

# ---------------------------------------------------------------------------
# Slice 6: Growth Layer
# ---------------------------------------------------------------------------

_CREATE_GROWTH_JOURNAL = """
CREATE TABLE IF NOT EXISTS growth_journal (
    entry_id   TEXT PRIMARY KEY,
    agent_id   TEXT NOT NULL CHECK (agent_id IN ('drevan', 'cypher', 'gaia')),
    entry_type TEXT NOT NULL
                   CHECK (entry_type IN ('observation', 'insight', 'milestone', 'pattern', 'reflection')),
    content    TEXT NOT NULL,
    salience   TEXT NOT NULL DEFAULT 'normal'
                   CHECK (salience IN ('low', 'normal', 'high')),
    source     TEXT NOT NULL,
    tags       TEXT NOT NULL DEFAULT '[]',
    actor      TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_GROWTH_JOURNAL_CREATED_IDX = """
CREATE INDEX IF NOT EXISTS idx_growth_journal_agent_created
ON growth_journal (agent_id, created_at DESC);
"""

# ASC on created_at so the prune query (find oldest LOW entries) is index-efficient
_CREATE_GROWTH_JOURNAL_SALIENCE_IDX = """
CREATE INDEX IF NOT EXISTS idx_growth_journal_agent_salience
ON growth_journal (agent_id, salience, created_at ASC);
"""

_CREATE_GROWTH_PATTERNS = """
CREATE TABLE IF NOT EXISTS growth_patterns (
    pattern_id          TEXT PRIMARY KEY,
    agent_id            TEXT NOT NULL CHECK (agent_id IN ('drevan', 'cypher', 'gaia')),
    pattern_name        TEXT NOT NULL,
    description         TEXT NOT NULL,
    supporting_evidence TEXT NOT NULL DEFAULT '[]',
    confidence          TEXT NOT NULL DEFAULT 'normal'
                            CHECK (confidence IN ('low', 'normal', 'high')),
    first_observed_at   TEXT NOT NULL,
    recurrence_count    INTEGER NOT NULL DEFAULT 1,
    source              TEXT NOT NULL,
    actor               TEXT NOT NULL,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_GROWTH_PATTERNS_CREATED_IDX = """
CREATE INDEX IF NOT EXISTS idx_growth_patterns_agent_created
ON growth_patterns (agent_id, created_at DESC);
"""

_CREATE_GROWTH_PATTERNS_CONFIDENCE_IDX = """
CREATE INDEX IF NOT EXISTS idx_growth_patterns_agent_confidence
ON growth_patterns (agent_id, confidence, created_at ASC);
"""

_CREATE_GROWTH_MARKERS = """
CREATE TABLE IF NOT EXISTS growth_markers (
    marker_id          TEXT PRIMARY KEY,
    agent_id           TEXT NOT NULL CHECK (agent_id IN ('drevan', 'cypher', 'gaia')),
    marker_type        TEXT NOT NULL
                           CHECK (marker_type IN ('shift', 'threshold', 'milestone', 'commitment')),
    title              TEXT NOT NULL,
    context            TEXT,
    related_thread_key TEXT,
    actor              TEXT NOT NULL,
    source             TEXT NOT NULL,
    created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_GROWTH_MARKERS_IDX = """
CREATE INDEX IF NOT EXISTS idx_growth_markers_agent_created
ON growth_markers (agent_id, created_at DESC);
"""


async def init_db() -> None:
    """Create tables and indexes if they do not exist.

    Order matters: mind_threads must exist before session_handoffs and
    mind_thread_events, which hold FKs into it.

    Note: this uses aiosqlite.connect() directly (not get_db()) because DDL
    does not return rows and does not need row_factory. If you ever add a
    read inside init_db (e.g. a migration version check), use get_db() or
    set db.row_factory = aiosqlite.Row explicitly -- bare connect() returns
    tuples, not Row objects.

    WAL mode note: SQLite defaults to DELETE journal mode (one writer at a
    time, serialize at lock level). If you ever enable WAL mode here via
    `PRAGMA journal_mode=WAL`, also set `PRAGMA busy_timeout=5000` or
    concurrent writes will raise OperationalError: database is locked under
    any real concurrency. Do not enable WAL without the busy timeout.
    """
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(_CREATE_LIMBIC_STATES)
        await db.execute(_CREATE_CONTINUITY_NOTES)
        await db.execute(_CREATE_NOTES_IDX)
        await db.execute(_CREATE_LIMBIC_IDX)
        # mind_threads must come before tables that reference it
        await db.execute(_CREATE_MIND_THREADS)
        await db.execute(_CREATE_THREADS_IDX)
        await db.execute(_CREATE_SESSION_HANDOFFS)
        await db.execute(_CREATE_HANDOFFS_IDX)
        await db.execute(_CREATE_MIND_THREAD_EVENTS)
        await db.execute(_CREATE_THREAD_EVENTS_IDX)
        await db.execute(_CREATE_LIFE_REMINDERS)
        await db.execute(_CREATE_REMINDERS_IDX)
        # Slice 4: Bond Layer -- bond_threads before bond_notes (FK dependency)
        await db.execute(_CREATE_BOND_THREADS)
        await db.execute(_CREATE_BOND_THREADS_IDX)
        await db.execute(_CREATE_BOND_THREADS_TOWARD_IDX)
        await db.execute(_CREATE_BOND_HANDOFFS)
        await db.execute(_CREATE_BOND_HANDOFFS_IDX)
        await db.execute(_CREATE_BOND_NOTES)
        await db.execute(_CREATE_BOND_NOTES_IDX)
        # Slice 5: Autonomy v0 -- seeds before runs (FK), runs before logs/reflections (FK)
        await db.execute(_CREATE_AUTONOMY_SCHEDULES)
        await db.execute(_CREATE_AUTONOMY_SEEDS)
        await db.execute(_CREATE_SEEDS_IDX)
        await db.execute(_CREATE_AUTONOMY_RUNS)
        await db.execute(_CREATE_RUNS_AGENT_STATUS_IDX)
        await db.execute(_CREATE_RUNS_AGENT_CREATED_IDX)
        await db.execute(_CREATE_AUTONOMY_RUN_LOGS)
        await db.execute(_CREATE_RUN_LOGS_IDX)
        await db.execute(_CREATE_AUTONOMY_REFLECTIONS)
        await db.execute(_CREATE_REFLECTIONS_RUN_IDX)
        await db.execute(_CREATE_REFLECTIONS_AGENT_IDX)
        # Slice 6: Growth Layer -- no FK dependencies, all standalone
        await db.execute(_CREATE_GROWTH_JOURNAL)
        await db.execute(_CREATE_GROWTH_JOURNAL_CREATED_IDX)
        await db.execute(_CREATE_GROWTH_JOURNAL_SALIENCE_IDX)
        await db.execute(_CREATE_GROWTH_PATTERNS)
        await db.execute(_CREATE_GROWTH_PATTERNS_CREATED_IDX)
        await db.execute(_CREATE_GROWTH_PATTERNS_CONFIDENCE_IDX)
        await db.execute(_CREATE_GROWTH_MARKERS)
        await db.execute(_CREATE_GROWTH_MARKERS_IDX)
        await db.commit()


def get_db_path() -> str:
    """Return current DB path (may be overridden in tests)."""
    return _DB_PATH


@asynccontextmanager
async def get_db():
    """Async context manager for a DB connection with FKs enforced.

    PRAGMA foreign_keys is a per-connection setting in SQLite -- it resets
    to OFF on every new connection. Always use get_db() rather than opening
    aiosqlite.connect() directly so enforcement is never accidentally skipped.
    """
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        db.row_factory = aiosqlite.Row
        yield db
