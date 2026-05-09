"""
Regression tests for the 2026-05-09 4-agent audit findings (Brain repo).

Locks in B1 (config-driven depth caps), B2 (per-companion top_p map),
B3 (_call_legacy honors INFERENCE_TEMPERATURE), B4 (router uses
INFERENCE_TEMPERATURE-derived default), and B5 (NaN/bool-safe orient
confidence rendering).
"""
from __future__ import annotations

import inspect
import math
import os

import pytest


# ── B1: depth caps come from Config, not bare literals ───────────────────────
def test_b1_max_depth_reads_from_config():
    from services.brain.brain_config import Config
    from services.brain.agents import evaluator
    assert evaluator.MAX_DEPTH == Config.MAX_SWARM_DEPTH
    assert evaluator.DEPTH_BIAS_THRESHOLD == Config.DEPTH_BIAS_THRESHOLD


def test_b1_max_depth_env_override(monkeypatch):
    monkeypatch.setenv("MAX_SWARM_DEPTH", "7")
    monkeypatch.setenv("DEPTH_BIAS_THRESHOLD", "4")
    import importlib
    from services.brain import brain_config
    importlib.reload(brain_config)
    assert brain_config.Config.MAX_SWARM_DEPTH == 7
    assert brain_config.Config.DEPTH_BIAS_THRESHOLD == 4


# ── B2: per-companion top_p map exists with documented values ────────────────
def test_b2_companion_top_p_map_defaults():
    from services.brain.brain_config import Config
    # Defaults: Drevan widest tail (Calethian fix 5/5), Cypher / Gaia tighter.
    assert Config.DREVAN_TOP_P == pytest.approx(0.95)
    assert Config.CYPHER_TOP_P == pytest.approx(0.9)
    assert Config.GAIA_TOP_P   == pytest.approx(0.85)
    # Drevan must remain >= Cypher >= Gaia or word salad returns.
    assert Config.DREVAN_TOP_P >= Config.CYPHER_TOP_P >= Config.GAIA_TOP_P


def test_b2_companion_top_p_env_override(monkeypatch):
    monkeypatch.setenv("CYPHER_TOP_P", "0.88")
    monkeypatch.setenv("GAIA_TOP_P", "0.80")
    import importlib
    from services.brain import brain_config
    importlib.reload(brain_config)
    assert brain_config.Config.CYPHER_TOP_P == pytest.approx(0.88)
    assert brain_config.Config.GAIA_TOP_P   == pytest.approx(0.80)


def test_b2_evaluator_has_companion_top_p_map(monkeypatch):
    # Construct a SwarmEvaluator with no Halseth wiring, just to confirm the map exists.
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-noop")
    from services.brain.agents.cooldown import CompanionCooldown
    from services.brain.agents.evaluator import SwarmEvaluator
    ev = SwarmEvaluator(CompanionCooldown())
    assert hasattr(ev, "_companion_top_p")
    assert set(ev._companion_top_p.keys()) == {"drevan", "cypher", "gaia"}
    # Per-companion lookup must NOT all collapse to a single value.
    vals = list(ev._companion_top_p.values())
    assert len(set(vals)) > 1, "all three companions still share one top_p literal"


# ── B3: _call_legacy honors INFERENCE_TEMPERATURE, not bare 0.7 ──────────────
def test_b3_call_legacy_uses_inference_temperature():
    from services.brain.agents import evaluator
    src = inspect.getsource(evaluator.SwarmEvaluator._call_legacy)
    assert "INFERENCE_TEMPERATURE" in src, (
        "_call_legacy must reference INFERENCE_TEMPERATURE, not a hardcoded literal"
    )
    # No bare 0.7 temperature literal should remain in the legacy path.
    assert '"temperature": 0.7' not in src


# ── B4: router uses Config-derived default, not three bare 0.7 literals ──────
def test_b4_router_temperature_not_hardcoded():
    from services.brain.agents import router
    src = inspect.getsource(router)
    # The Config-derived default must be present.
    assert "DEFAULT_INFERENCE_TEMP" in src
    # No bare `= 0.7` or `, 0.7)` temperature defaults should remain.
    assert "= 0.7" not in src
    assert ", 0.7)" not in src


# ── B5: NaN-safe + bool-safe confidence rendering in orient context ──────────
def test_b5_orient_confidence_handles_nan():
    from services.brain.halseth_client import format_orient_context
    orient = {
        "active_conclusions": [
            {"belief_type": "fact", "text": "x", "confidence": float("nan")}
        ]
    }
    out = format_orient_context(orient)
    assert "nan" not in out.lower()
    assert "(?)" in out


def test_b5_orient_confidence_handles_bool():
    from services.brain.halseth_client import format_orient_context
    orient = {
        "active_conclusions": [
            {"belief_type": "fact", "text": "x", "confidence": True}
        ]
    }
    out = format_orient_context(orient)
    # True historically formatted as "1.00" because bool subclasses int.
    assert "1.00" not in out
    assert "(?)" in out


def test_b5_orient_confidence_handles_real_float():
    from services.brain.halseth_client import format_orient_context
    orient = {
        "active_conclusions": [
            {"belief_type": "fact", "text": "x", "confidence": 0.7321}
        ]
    }
    out = format_orient_context(orient)
    assert "(0.73)" in out


def test_b5_orient_confidence_handles_none():
    from services.brain.halseth_client import format_orient_context
    orient = {
        "active_conclusions": [
            {"belief_type": "fact", "text": "x", "confidence": None}
        ]
    }
    out = format_orient_context(orient)
    assert "None" not in out
    assert "(?)" in out
