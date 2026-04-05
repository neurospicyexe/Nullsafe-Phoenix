#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebMind SQLite database module.

Manages aiosqlite connection and schema init for:
- limbic_states: synthesized swarm state records
- continuity_notes: companion and synthesis notes
"""

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
    agent_id    TEXT NOT NULL,
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


async def init_db() -> None:
    """Create tables and indexes if they do not exist."""
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(_CREATE_LIMBIC_STATES)
        await db.execute(_CREATE_CONTINUITY_NOTES)
        await db.execute(_CREATE_NOTES_IDX)
        await db.execute(_CREATE_LIMBIC_IDX)
        await db.commit()


def get_db_path() -> str:
    """Return current DB path (may be overridden in tests)."""
    return _DB_PATH
