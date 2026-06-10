"""
Tests for identity loader -- specifically the two paths through construct_prompt_context:
  1. system_prompt present  → returned directly (real identities)
  2. system_prompt absent   → assembled from fragments (stub fallthrough)

Knoll called this out: stub YAML passes because the fallthrough was never validated.
"""

import sys
import tempfile
from pathlib import Path

import yaml
import pytest

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from services.brain.identity.loader import AgentIdentity, IdentityLoader


# ── Unit: AgentIdentity schema ────────────────────────────────────────────────

class TestAgentIdentitySchema:
    def test_system_prompt_defaults_to_none(self):
        identity = AgentIdentity(name="Test", role="tester")
        assert identity.system_prompt is None

    def test_system_prompt_accepted(self):
        identity = AgentIdentity(name="Test", role="tester", system_prompt="You are Test.")
        assert identity.system_prompt == "You are Test."

    def test_empty_system_prompt_is_falsy(self):
        identity = AgentIdentity(name="Test", role="tester", system_prompt="")
        assert not identity.system_prompt


# ── Unit: construct_prompt_context ────────────────────────────────────────────

class TestConstructPromptContext:
    def setup_method(self):
        self.loader = IdentityLoader.__new__(IdentityLoader)
        self.loader._cache = {}

    def test_system_prompt_path_returns_prompt_directly(self):
        identity = AgentIdentity(
            name="Cypher",
            role="Blade companion",
            system_prompt="You are Cypher (he/him). Blade companion.",
            anchors=["Clarity over cleverness"],
            cadence="Direct. Warm.",
            system_prompt_fragments=["This fragment should not appear"],
        )
        result = self.loader.construct_prompt_context(identity)
        assert result == "You are Cypher (he/him). Blade companion."
        assert "This fragment should not appear" not in result

    def test_system_prompt_strips_whitespace(self):
        identity = AgentIdentity(
            name="Cypher",
            role="Blade companion",
            system_prompt="  You are Cypher.\n  ",
        )
        result = self.loader.construct_prompt_context(identity)
        assert result == "You are Cypher."

    def test_fallthrough_assembles_fragments(self):
        identity = AgentIdentity(
            name="Stub",
            role="Test role",
            anchors=["anchor one"],
            cadence="Test cadence",
            constraints=["constraint one"],
            system_prompt_fragments=["fragment one", "fragment two"],
        )
        result = self.loader.construct_prompt_context(identity)
        assert "Stub" in result
        assert "Test role" in result
        assert "anchor one" in result
        assert "Test cadence" in result
        assert "constraint one" in result
        assert "fragment one" in result
        assert "fragment two" in result

    def test_fallthrough_handles_empty_fields(self):
        identity = AgentIdentity(name="Minimal", role="minimal role")
        result = self.loader.construct_prompt_context(identity)
        assert "Minimal" in result
        assert "minimal role" in result


# ── Integration: real YAML files load and route correctly ────────────────────

class TestRealYamlFiles:
    def setup_method(self):
        data_dir = Path(__file__).parent.parent / "identity" / "data"
        self.loader = IdentityLoader(identity_dir=data_dir)

    @pytest.mark.parametrize("agent_id", ["cypher", "drevan", "gaia"])
    def test_real_identity_loads(self, agent_id):
        identity, version = self.loader.load_identity(agent_id)
        assert identity.name
        assert identity.role
        assert version  # non-empty hash

    @pytest.mark.parametrize("agent_id", ["cypher", "drevan", "gaia"])
    def test_real_identity_uses_system_prompt_path(self, agent_id):
        identity, _ = self.loader.load_identity(agent_id)
        assert identity.system_prompt, (
            f"{agent_id}.yaml is missing system_prompt -- "
            "loader will fall through to fragment assembly with empty context"
        )
        result = self.loader.construct_prompt_context(identity)
        assert len(result) > 200, f"{agent_id} system_prompt suspiciously short"
        assert identity.name in result

    @pytest.mark.parametrize(("agent_id", "expected_phrase"), [
        ("cypher", "blade"),
        ("drevan", "vaselrin"),
        ("gaia", "perimeter"),
    ])
    def test_real_identity_contains_core_concept(self, agent_id, expected_phrase):
        identity, _ = self.loader.load_identity(agent_id)
        result = self.loader.construct_prompt_context(identity)
        assert expected_phrase.lower() in result.lower(), (
            f"{agent_id} system_prompt missing expected phrase '{expected_phrase}'"
        )


# ── Integration: stub YAML fallthrough still works ───────────────────────────

class TestUnknownFieldsRejected:
    """extra='forbid' catches typos at load time, not silently at prompt-build time."""

    def test_typo_in_system_prompt_key_raises(self):
        typo_yaml = """
name: "TypoAgent"
role: "Test"
system_promt: "This should fail -- not silently become None"
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            stub_path = Path(tmpdir) / "typagent.yaml"
            stub_path.write_text(typo_yaml)
            loader = IdentityLoader(identity_dir=Path(tmpdir))
            with pytest.raises((ValueError, Exception), match=r"(?i)(extra|unexpected|forbidden|promt)"):
                loader.load_identity("typagent")

    def test_unknown_field_raises(self):
        bad_yaml = """
name: "BadAgent"
role: "Test"
system_prompt: "Valid"
completely_made_up_field: "This should fail"
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            stub_path = Path(tmpdir) / "badagent.yaml"
            stub_path.write_text(bad_yaml)
            loader = IdentityLoader(identity_dir=Path(tmpdir))
            with pytest.raises((ValueError, Exception)):
                loader.load_identity("badagent")


class TestStubYamlFallthrough:
    def test_stub_yaml_without_system_prompt_assembles_correctly(self):
        stub_yaml = """
name: "StubAgent"
role: "Test stub"
anchors:
  - "stub anchor"
cadence: "stub cadence"
constraints:
  - "stub constraint"
system_prompt_fragments:
  - "stub fragment"
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            stub_path = Path(tmpdir) / "stubagent.yaml"
            stub_path.write_text(stub_yaml)
            loader = IdentityLoader(identity_dir=Path(tmpdir))
            identity, _ = loader.load_identity("stubagent")

        assert identity.system_prompt is None
        result = loader.construct_prompt_context(identity)
        assert "StubAgent" in result
        assert "stub fragment" in result
        assert "stub anchor" in result


# ── Unit: kernel overlay (Halseth-synced canonical identity) ─────────────────

class TestKernelOverlay:
    def _make_loader(self):
        loader = IdentityLoader.__new__(IdentityLoader)
        loader._cache = {}
        loader._kernel_cache = {}
        return loader

    def _identity(self):
        return AgentIdentity(name="Cypher", role="Blade companion", system_prompt="You are Cypher.")

    def test_no_env_means_no_overlay(self, monkeypatch):
        monkeypatch.delenv("HALSETH_URL", raising=False)
        monkeypatch.delenv("HALSETH_ADMIN_SECRET", raising=False)
        loader = self._make_loader()
        identity, version = loader._apply_kernel_overlay("cypher", self._identity(), "abc123")
        assert identity.system_prompt == "You are Cypher."
        assert version == "abc123"

    def test_overlay_appends_kernel_and_changes_version(self, monkeypatch):
        monkeypatch.setenv("HALSETH_URL", "https://halseth.test")
        monkeypatch.setenv("HALSETH_ADMIN_SECRET", "s3cret")
        loader = self._make_loader()
        bundle = "# SHARED DOCTRINE\nidentity is constant, substrate varies. " + ("x" * 250)

        class FakeResp:
            def raise_for_status(self):
                pass
            def json(self):
                return {"bundle": bundle}

        import services.brain.identity.loader as loader_mod
        monkeypatch.setattr(loader_mod.httpx, "get", lambda *a, **k: FakeResp())

        identity, version = loader._apply_kernel_overlay("cypher", self._identity(), "abc123")
        assert "IDENTITY KERNEL" in identity.system_prompt
        assert "identity is constant" in identity.system_prompt
        assert version.startswith("abc123+k")
        # Cached copy stays pristine -- overlay returns a copy
        assert self._identity().system_prompt == "You are Cypher."

    def test_halseth_down_degrades_to_yaml_only(self, monkeypatch):
        monkeypatch.setenv("HALSETH_URL", "https://halseth.test")
        monkeypatch.setenv("HALSETH_ADMIN_SECRET", "s3cret")
        loader = self._make_loader()

        import services.brain.identity.loader as loader_mod
        def boom(*a, **k):
            raise RuntimeError("connection refused")
        monkeypatch.setattr(loader_mod.httpx, "get", boom)

        identity, version = loader._apply_kernel_overlay("cypher", self._identity(), "abc123")
        assert identity.system_prompt == "You are Cypher."
        assert version == "abc123"

    def test_ttl_cache_serves_without_refetch(self, monkeypatch):
        monkeypatch.setenv("HALSETH_URL", "https://halseth.test")
        monkeypatch.setenv("HALSETH_ADMIN_SECRET", "s3cret")
        loader = self._make_loader()
        calls = {"n": 0}
        bundle = "# KERNEL " + ("y" * 250)

        class FakeResp:
            def raise_for_status(self):
                pass
            def json(self):
                return {"bundle": bundle}

        import services.brain.identity.loader as loader_mod
        def counted_get(*a, **k):
            calls["n"] += 1
            return FakeResp()
        monkeypatch.setattr(loader_mod.httpx, "get", counted_get)

        loader._apply_kernel_overlay("cypher", self._identity(), "v1")
        loader._apply_kernel_overlay("cypher", self._identity(), "v1")
        assert calls["n"] == 1

    def test_stale_cache_beats_nothing_when_halseth_drops(self, monkeypatch):
        monkeypatch.setenv("HALSETH_URL", "https://halseth.test")
        monkeypatch.setenv("HALSETH_ADMIN_SECRET", "s3cret")
        loader = self._make_loader()
        # Pre-seed an expired cache entry, then make the fetch fail
        loader._kernel_cache["cypher"] = ("# OLD KERNEL " + ("z" * 250), -10_000.0)

        import services.brain.identity.loader as loader_mod
        def boom(*a, **k):
            raise RuntimeError("connection refused")
        monkeypatch.setattr(loader_mod.httpx, "get", boom)

        identity, version = loader._apply_kernel_overlay("cypher", self._identity(), "v1")
        assert "OLD KERNEL" in identity.system_prompt
