"""Cheap API surface checks that don't need Audiveris on PATH.

These mirror what the tauri-ci `sidecar-smoke` job exercises against the
PyInstaller bundle, but at the FastAPI layer so regressions get caught
in `pytest backend/tests/` before we even build the binary.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Point both the writable root and the explicit cache override at a
    # tmp dir so the test never touches the developer's real cache.
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANALYZE_CACHE_DIR", str(tmp_path / "cache" / "analyze"))

    # CORS env handling lives at module import time, so re-import app.main
    # under the patched env to make sure the test sees the same wiring
    # the sidecar would.
    import importlib

    import app.main as main_module
    main_module = importlib.reload(main_module)

    from fastapi.testclient import TestClient

    return TestClient(main_module.app)


def test_health_returns_ok(client) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_capabilities_advertise_neural_engine(client) -> None:
    resp = client.get("/capabilities")
    assert resp.status_code == 200
    body = resp.json()
    assert body["omr_engines"] == ["audiveris", "homr", "hybrid"]
    assert body["per_request_engine_selection"] is True


def test_cache_listing_starts_empty(client) -> None:
    resp = client.get("/cache")
    assert resp.status_code == 200
    assert resp.json() == []


def test_analyze_rejects_request_with_no_files(client) -> None:
    # /analyze takes pdf and/or music_xml as multipart fields. Sending an
    # empty form should fail with a client error, not a 500.
    resp = client.post("/analyze", files={})
    assert 400 <= resp.status_code < 500, resp.text


def test_cors_allowlist_honours_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOWED_ORIGINS", "tauri://localhost,http://localhost:5173")
    import importlib
    import app.main as main_module
    main_module = importlib.reload(main_module)
    from fastapi.testclient import TestClient

    with TestClient(main_module.app) as client:
        # Preflight from an allowed origin must echo back Access-Control-Allow-Origin.
        resp = client.options(
            "/health",
            headers={
                "Origin": "tauri://localhost",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-origin") == "tauri://localhost"

        # An origin not in the allowlist should not get the header back.
        resp = client.options(
            "/health",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-origin") in (None, "")


def test_engine_override_maps_to_expected_param_sets() -> None:
    import app.main as main_module

    assert main_module._param_set_for_engine("audiveris") == "v5_real_pdf"
    assert main_module._param_set_for_engine("homr") == "v6_homr"
    assert main_module._param_set_for_engine("hybrid") == "v7_hybrid"


def test_engine_override_rejects_unknown_value() -> None:
    import app.main as main_module

    with pytest.raises(ValueError, match="Unsupported OMR engine"):
        main_module._param_set_for_engine("unknown")
