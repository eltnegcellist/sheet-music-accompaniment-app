"""Tests for the postprocess edit log."""

import json

from app.pipeline.postprocess.edits import EditEvent, EditLocation, EditLog


def test_append_records_event_in_order():
    log = EditLog()
    log.append("rest_insert", reason="duration short by 1", location=EditLocation(measure=3))
    log.append("snap", reason="rounded 0.95 to 1", location=EditLocation(measure=3, voice=1))
    events = list(log)
    assert len(events) == len(log) == 2
    assert [e.op for e in events] == ["rest_insert", "snap"]


def test_to_dict_drops_none_location_fields():
    ev = EditEvent(
        op="snap",
        location=EditLocation(measure=2),  # part/voice/beat unset
        reason="r",
    )
    d = ev.to_dict()
    assert d["location"] == {"measure": 2}
    assert d["before"] == {} and d["after"] == {}


def test_by_op_counts_grouped():
    log = EditLog()
    log.append("snap", reason="r")
    log.append("snap", reason="r")
    log.append("rest_insert", reason="r")
    assert log.by_op() == {"snap": 2, "rest_insert": 1}


def test_flush_writes_json_lines(tmp_path):
    target = tmp_path / "out" / "postprocess_edits.jsonl"
    log = EditLog()
    log.append(
        "snap",
        reason="rounded",
        location=EditLocation(part="P1", measure=1, voice=1, beat=2.5),
        before={"duration": 0.95},
        after={"duration": 1.0},
    )
    log.flush(target)
    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["op"] == "snap"
    assert parsed["location"] == {"part": "P1", "measure": 1, "voice": 1, "beat": 2.5}
    assert parsed["before"] == {"duration": 0.95}
    assert parsed["after"] == {"duration": 1.0}


def test_flush_creates_parent_directories(tmp_path):
    target = tmp_path / "deeply" / "nested" / "log.jsonl"
    EditLog().flush(target)
    assert target.exists()


def test_flush_requires_path_when_log_was_init_without_one():
    log = EditLog()
    try:
        log.flush()
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_log_with_path_remembers_default(tmp_path):
    target = tmp_path / "default.jsonl"
    log = EditLog(path=target)
    log.append("snap", reason="r")
    log.flush()
    assert target.exists()
