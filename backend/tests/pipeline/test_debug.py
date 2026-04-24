import io
import json

from app.pipeline.debug import EventLogger, StructuredEvent, is_debug_enabled, now_iso


def test_is_debug_enabled_env(monkeypatch):
    monkeypatch.setenv("PIPELINE_DEBUG", "1")
    assert is_debug_enabled() is True


def test_is_debug_enabled_params():
    assert is_debug_enabled({"debug": {"enabled": True}}) is True
    assert is_debug_enabled({"debug": {"enabled": False}}) is False
    assert is_debug_enabled({}) is False


def test_event_emit_jsonlines_round_trip():
    sink = io.StringIO()
    log = EventLogger(sink=sink)
    log.emit(
        StructuredEvent(
            ts=now_iso(),
            event="stage.end",
            job_id="j1",
            stage="omr.audiveris",
            status="ok",
            page_id="j1:p0",
            duration_ms=120,
            metrics={"valid_xml": True},
        )
    )
    line = sink.getvalue().strip()
    parsed = json.loads(line)
    assert parsed["job_id"] == "j1"
    assert parsed["stage"] == "omr.audiveris"
    assert parsed["status"] == "ok"
    assert parsed["metrics"] == {"valid_xml": True}


def test_event_emit_drops_empty_optionals():
    sink = io.StringIO()
    EventLogger(sink=sink).emit(
        StructuredEvent(
            ts=now_iso(),
            event="stage.start",
            job_id="j1",
            stage="preprocess",
            status="ok",
        )
    )
    parsed = json.loads(sink.getvalue().strip())
    # No nulls should leak into the log.
    assert "page_id" not in parsed
    assert "metrics" not in parsed


def test_event_logger_requires_sink_or_path():
    try:
        EventLogger()
    except ValueError:
        return
    raise AssertionError("expected ValueError when neither sink nor path is given")


def test_now_iso_format_matches_spec():
    s = now_iso()
    # YYYY-MM-DDTHH:MM:SS.mmmZ — len 24
    assert len(s) == 24
    assert s.endswith("Z")
    assert s[10] == "T"
