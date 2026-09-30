"""Unit tests for confidence-gated hybrid OMR decisions."""

from __future__ import annotations

from pathlib import Path

from app.omr import hybrid_runner
from app.omr.result import OmrResult


def _xml(piano_pitch: str = "C", *, measures: int = 1) -> str:
    body = []
    for i in range(1, measures + 1):
        body.append(
            f"""
            <measure number="{i}">
              <attributes><divisions>1</divisions><staves>2</staves></attributes>
              <note>
                <pitch><step>{piano_pitch}</step><octave>4</octave></pitch>
                <duration>1</duration><voice>1</voice><staff>1</staff>
              </note>
              <note>
                <pitch><step>G</step><octave>3</octave></pitch>
                <duration>1</duration><voice>1</voice><staff>2</staff>
              </note>
            </measure>
            """
        )
    return (
        "<score-partwise><part-list>"
        "<score-part id='S'><part-name>Cello</part-name></score-part>"
        "<score-part id='P'><part-name>Piano</part-name></score-part>"
        "</part-list>"
        "<part id='S'><measure number='1'><attributes><divisions>1</divisions></attributes>"
        "<note><pitch><step>C</step><octave>3</octave></pitch><duration>1</duration></note>"
        "</measure></part>"
        "<part id='P'>"
        + "".join(body)
        + "</part></score-partwise>"
    )


def _result(xml: str, warning: str) -> OmrResult:
    return OmrResult(
        music_xml=xml,
        measures=[],
        page_sizes=[(595.0, 842.0)],
        warnings=[warning],
    )


def test_hybrid_falls_back_to_homr_when_audiveris_fails(tmp_path, monkeypatch):
    def fail_aud(*_args, **_kwargs):
        raise RuntimeError("aud failed")

    monkeypatch.setattr(hybrid_runner, "run_audiveris_chunked", fail_aud)
    monkeypatch.setattr(
        hybrid_runner,
        "run_homr",
        lambda *_args, **_kwargs: _result(_xml("D"), "homr"),
    )

    result = hybrid_runner.run_hybrid(tmp_path / "score.pdf", tmp_path / "out")

    assert "<step>D</step>" in result.music_xml
    assert any("Audiverisが失敗" in w for w in result.warnings)


def test_hybrid_uses_homr_on_strong_rhythm_gain(tmp_path, monkeypatch):
    aud = _result(_xml("C"), "aud")
    homr = _result(_xml("D"), "homr")
    monkeypatch.setattr(hybrid_runner, "run_audiveris_chunked", lambda *_a, **_k: aud)
    monkeypatch.setattr(hybrid_runner, "run_homr", lambda *_a, **_k: homr)

    def metrics(xml: str):
        if "<step>D</step>" in xml:
            return {"final_score": 0.95, "measure_duration_match": 0.95}
        return {"final_score": 0.75, "measure_duration_match": 0.50}

    monkeypatch.setattr(hybrid_runner, "_metrics", metrics)

    result = hybrid_runner.run_hybrid(tmp_path / "score.pdf", tmp_path / "out")

    assert "<step>D</step>" in result.music_xml
    assert any("homr結果を採用" in w for w in result.warnings)


def test_hybrid_keeps_audiveris_rhythm_and_fuses_safe_homr_pitch(
    tmp_path, monkeypatch
):
    aud = _result(_xml("C"), "aud")
    homr = _result(_xml("D"), "homr")
    monkeypatch.setattr(hybrid_runner, "run_audiveris_chunked", lambda *_a, **_k: aud)
    monkeypatch.setattr(hybrid_runner, "run_homr", lambda *_a, **_k: homr)
    monkeypatch.setattr(
        hybrid_runner,
        "_metrics",
        lambda _xml_text: {
            "final_score": 0.95,
            "measure_duration_match": 0.98,
        },
    )

    result = hybrid_runner.run_hybrid(
        tmp_path / "score.pdf",
        tmp_path / "out",
        minimum_safe_pitch_rate=0.5,
        minimum_safe_pitch_notes=1,
    )

    assert "<step>D</step>" in result.music_xml
    assert "<duration>1</duration>" in result.music_xml
    assert any("音高をhomr結果から採用" in w for w in result.warnings)

def test_hybrid_fuses_contiguous_matches_when_homr_has_trailing_extra_measures(
    tmp_path, monkeypatch
):
    aud = _result(_xml("C", measures=2), "aud")
    homr = _result(_xml("D", measures=3), "homr")
    monkeypatch.setattr(hybrid_runner, "run_audiveris_chunked", lambda *_a, **_k: aud)
    monkeypatch.setattr(hybrid_runner, "run_homr", lambda *_a, **_k: homr)
    monkeypatch.setattr(
        hybrid_runner,
        "_metrics",
        lambda _xml_text: {
            "final_score": 0.95,
            "measure_duration_match": 0.98,
        },
    )

    result = hybrid_runner.run_hybrid(
        tmp_path / "score.pdf",
        tmp_path / "out",
        minimum_safe_pitch_rate=0.5,
        minimum_safe_pitch_notes=1,
    )

    assert result.music_xml.count("<step>D</step>") >= 2
    assert any("音高をhomr結果から採用" in w for w in result.warnings)
