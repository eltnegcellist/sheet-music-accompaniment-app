"""Unit tests for the sidecar entry script.

Exercise the small helpers in app.server directly so a regression in
argv parsing, env handoff, or the READY contract gets caught before
the (slow) PyInstaller build kicks in.
"""

from __future__ import annotations

import io
import os
import socket
import sys

import pytest

from app import server


def test_parse_args_defaults() -> None:
    args = server._parse_args([])
    assert args.host == "127.0.0.1"
    assert args.port == 0
    assert args.app_data is None
    assert args.param_set is None
    assert args.log_level == "info"


def test_parse_args_full() -> None:
    args = server._parse_args(
        ["--host", "0.0.0.0", "--port", "9000", "--app-data", "/tmp/x", "--param-set", "v5"]
    )
    assert args.host == "0.0.0.0"
    assert args.port == 9000
    assert args.app_data == "/tmp/x"
    assert args.param_set == "v5"


def test_apply_env_sets_only_when_supplied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_DATA_DIR", raising=False)
    monkeypatch.delenv("PIPELINE_PARAM_SET", raising=False)
    server._apply_env(server._parse_args([]))
    assert "APP_DATA_DIR" not in os.environ
    assert "PIPELINE_PARAM_SET" not in os.environ

    server._apply_env(
        server._parse_args(["--app-data", "/var/cache/app", "--param-set", "v5_real_pdf"])
    )
    assert os.environ["APP_DATA_DIR"] == "/var/cache/app"
    assert os.environ["PIPELINE_PARAM_SET"] == "v5_real_pdf"


def test_bind_socket_returns_assigned_port_when_zero() -> None:
    sock = server._bind_socket("127.0.0.1", 0)
    try:
        host, port = sock.getsockname()[:2]
        assert host == "127.0.0.1"
        assert 1024 < port < 65536
    finally:
        sock.close()


def test_emit_ready_writes_single_json_line(capsys: pytest.CaptureFixture[str]) -> None:
    server._emit_ready("127.0.0.1", 12345)
    captured = capsys.readouterr().out
    lines = [line for line in captured.splitlines() if line]
    assert len(lines) == 1
    line = lines[0]
    assert line.startswith("READY ")
    import json

    payload = json.loads(line[len("READY ") :])
    assert payload == {"host": "127.0.0.1", "port": 12345}


def test_check_bundled_binaries_warns_on_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("AUDIVERIS_LAUNCHER", "/nonexistent/Audiveris")
    monkeypatch.setenv("TESSERACT_CMD", "/nonexistent/tesseract")
    monkeypatch.setenv("JAVA_HOME", "/nonexistent/jre")

    server._check_bundled_binaries()

    captured = capsys.readouterr().err
    assert "AUDIVERIS_LAUNCHER" in captured
    assert "TESSERACT_CMD" in captured
    assert "JAVA_HOME" in captured


def test_check_bundled_binaries_silent_when_unset(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for var in ("AUDIVERIS_LAUNCHER", "TESSERACT_CMD", "JAVA_HOME"):
        monkeypatch.delenv(var, raising=False)
    server._check_bundled_binaries()
    assert capsys.readouterr().err == ""


@pytest.mark.skipif(sys.platform != "linux", reason="prctl is Linux-only")
def test_install_prctl_pdeathsig_runs_silently(capsys: pytest.CaptureFixture[str]) -> None:
    # The call should succeed in any normal Linux process. We can't easily
    # verify the kernel state, but we can at least confirm no warning is
    # emitted on stderr.
    server._install_prctl_pdeathsig()
    captured = capsys.readouterr().err
    assert "WARN" not in captured
