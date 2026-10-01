"""Real API/pipeline server with only the expensive recognition drivers replayed."""
import hashlib
import json
import os
import sys
from pathlib import Path

import uvicorn
from pypdf import PdfWriter

source, out = map(Path, sys.argv[1:3])
out.mkdir(parents=True, exist_ok=True)
os.environ["API_TOKEN"] = "integration-test-token"
os.environ["ANALYZE_CACHE_DIR"] = str(out / "cache")
from app import main
from app.omr import engine, hybrid_runner
from app.omr.result import OmrResult

provenance = json.loads((source / "source.json").read_text())
for name, info in provenance["files"].items():
    assert hashlib.sha256((source / name).read_bytes()).hexdigest() == info["sha256"]
state = {"recognition_calls": []}

def replay(name):
    def driver(pdf, directory, **kwargs):
        state["recognition_calls"].append(name)
        return OmrResult((source / (name + ".musicxml")).read_text(), [], [], ["replay-source:" + name])
    return driver

engine.run_audiveris_chunked = hybrid_runner.run_audiveris_chunked = replay("audiveris")
engine.run_homr = hybrid_runner.run_homr = replay("homr")
main.app.add_api_route("/__test__/state", lambda: state, methods=["GET"])
writer = PdfWriter()
writer.add_blank_page(width=612, height=792)
writer.write(out / "replay.pdf")
(out / "audio.musicxml").write_text("""<?xml version="1.0" encoding="utf-8"?>
<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list>
<part id="P1"><measure number="1"><attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes><direction><sound tempo="120"/></direction><note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>whole</type></note></measure>
<measure number="2"><note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration><type>whole</type></note></measure></part></score-partwise>""")
uvicorn.run(main.app, host="127.0.0.1", port=18765)
