"""The cloud-overlay loader seam: absent module = silent no-op; present
module gets install(app) called exactly once with the app."""

import sys
import types

from app import _install_cloud_overlay, app


def test_disabled_by_default_even_when_module_present(monkeypatch):
    # Dependency-confusion hardening: without the explicit flag, a
    # cloud_overlay package on sys.path must NOT execute.
    calls = []
    fake = types.ModuleType("cloud_overlay")
    fake.install = lambda application: calls.append(application)
    monkeypatch.setitem(sys.modules, "cloud_overlay", fake)
    monkeypatch.delenv("OPENSWEEP_CLOUD_OVERLAY", raising=False)
    _install_cloud_overlay(app)
    assert calls == []


def test_missing_overlay_is_a_noop_when_enabled(monkeypatch):
    monkeypatch.setenv("OPENSWEEP_CLOUD_OVERLAY", "1")
    assert "cloud_overlay" not in sys.modules
    _install_cloud_overlay(app)  # must not raise


def test_present_overlay_install_is_called_when_enabled(monkeypatch):
    calls = []
    fake = types.ModuleType("cloud_overlay")
    fake.install = lambda application: calls.append(application)
    monkeypatch.setitem(sys.modules, "cloud_overlay", fake)
    monkeypatch.setenv("OPENSWEEP_CLOUD_OVERLAY", "1")
    _install_cloud_overlay(app)
    assert calls == [app]


def test_overlay_without_install_is_tolerated(monkeypatch):
    fake = types.ModuleType("cloud_overlay")
    monkeypatch.setitem(sys.modules, "cloud_overlay", fake)
    monkeypatch.setenv("OPENSWEEP_CLOUD_OVERLAY", "true")
    _install_cloud_overlay(app)  # must not raise
