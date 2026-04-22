from app.ocr.tempo_ocr import _OcrLine, _pick_title_from_ocr_lines


def test_pick_title_prefers_large_centered_line_over_tempo_or_instrument():
    lines = [
        _OcrLine(text="Andante", confidence=92, x=420, y=120, width=220, height=24),
        _OcrLine(text="Violin", confidence=90, x=50, y=170, width=110, height=20),
        _OcrLine(
            text="Sonata in A major",
            confidence=88,
            x=210,
            y=60,
            width=640,
            height=56,
        ),
        _OcrLine(text="Composed by X", confidence=87, x=260, y=145, width=360, height=22),
    ]
    picked = _pick_title_from_ocr_lines(lines, image_width=1000)
    assert picked == "Sonata in A major"


def test_pick_title_returns_none_for_only_noise_lines():
    lines = [
        _OcrLine(text="Allegro", confidence=90, x=300, y=70, width=180, height=22),
        _OcrLine(text="Violin", confidence=85, x=100, y=90, width=150, height=20),
        _OcrLine(text="III", confidence=80, x=480, y=110, width=40, height=18),
    ]
    assert _pick_title_from_ocr_lines(lines, image_width=1000) is None
