#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebMind SQLite database module.

Manages aiosqlite connection and schema init for:
- limbic_states: synthesized swarm state records
- continuity_notes: companion and synthesis notes
- session_handoffs: session checkpoints per companion
- mind_threads: persistent companion threads
- mind_thread_events: append-only event log for thread changes
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


async def init_db() -> None:
    """Create tables and indexes if they do not exist.

    Order matters: mind_threads must exist before session_handoffs and
    mind_thread_events, which hold FKs into it.

    Note: this uses aiosqlite.connect() directly (not get_db()) because DDL
    does not return rows and does not need row_factory. If you ever add a
    read inside init_db (e.g. a migration version check), use get_db() or
    set db.row_factory = aiosqlite.Row explicitly -- bare connect() returns
    tuples, not Row objects.
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
