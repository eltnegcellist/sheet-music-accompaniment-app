"""Lock down the launcher resolution order in app.omr.audiveris_runner.

Tauri ships its sidecar with AUDIVERIS_LAUNCHER set to the bundled
binary; Docker leaves the env unset and relies on the .deb installer
putting `Audiveris` on PATH; legacy installs use AUDIVERIS_HOME. Make
sure all three fallbacks stay in the documented order so a refactor
doesn't silently regress one of them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.omr.audiveris_runner import AudiverisError, _audiveris_command


def _make_executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(0o755)
    return path


def test_explicit_launcher_env_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bundled = _make_executable(tmp_path / "bundled" / "Audiveris")
    on_path = _make_executable(tmp_path / "path-bin" / "Audiveris")
    monkeypatch.setenv("AUDIVERIS_LAUNCHER", str(bundled))
    monkeypatch.setenv("PATH", str(on_path.parent))

    cmd = _audiveris_command(tmp_path / "doc.pdf", tmp_path / "out")
    assert cmd[0] == str(bundled)


def test_path_used_when_env_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    on_path = _make_executable(tmp_path / "path-bin" / "Audiveris")
    monkeypatch.delenv("AUDIVERIS_LAUNCHER", raising=False)
    monkeypatch.setenv("PATH", str(on_path.parent))

    cmd = _audiveris_command(tmp_path / "doc.pdf", tmp_path / "out")
    assert cmd[0] == str(on_path)


def test_audiveris_home_used_when_env_and_path_miss(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home_launcher = _make_executable(tmp_path / "home" / "bin" / "Audiveris")
    monkeypatch.delenv("AUDIVERIS_LAUNCHER", raising=False)
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("AUDIVERIS_HOME", str(tmp_path / "home"))

    cmd = _audiveris_command(tmp_path / "doc.pdf", tmp_path / "out")
    assert cmd[0] == str(home_launcher)


def test_explicit_env_falls_back_when_pointed_at_missing_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    on_path = _make_executable(tmp_path / "path-bin" / "Audiveris")
    monkeypatch.setenv("AUDIVERIS_LAUNCHER", str(tmp_path / "does-not-exist"))
    monkeypatch.setenv("PATH", str(on_path.parent))

    cmd = _audiveris_command(tmp_path / "doc.pdf", tmp_path / "out")
    assert cmd[0] == str(on_path)


def test_no_launcher_anywhere_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("AUDIVERIS_LAUNCHER", raising=False)
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("AUDIVERIS_HOME", str(tmp_path / "empty"))

    with pytest.raises(AudiverisError) as exc_info:
        _audiveris_command(tmp_path / "doc.pdf", tmp_path / "out")
    assert "AUDIVERIS_LAUNCHER" in str(exc_info.value)


def test_command_includes_expected_flags(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bundled = _make_executable(tmp_path / "Audiveris")
    monkeypatch.setenv("AUDIVERIS_LAUNCHER", str(bundled))

    pdf = tmp_path / "score.pdf"
    out = tmp_path / "out"
    cmd = _audiveris_command(pdf, out)
    assert "-batch" in cmd
    assert "-export" in cmd
    assert "-output" in cmd
    assert str(out) in cmd
    assert str(pdf) in cmd
