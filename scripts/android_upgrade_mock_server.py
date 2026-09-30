#!/usr/bin/env python3
"""Loopback-only fixture server. It exercises HTTP/preflight, never performs OMR."""
import json
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

XML = '<?xml version="1.0"?><score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list><part id="P1"><measure number="1"><attributes><divisions>1</divisions><key><fifths>0</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes><note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>whole</type></note></measure></part></score-partwise>'
STATE = {"supported": False, "capabilities": 0, "uploads": []}

class Handler(BaseHTTPRequestHandler):
    def send_json(self, value, status=200):
        data = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "https://appassets.androidplatform.net")
        self.send_header("Access-Control-Allow-Headers", "Authorization,Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_json({})

    def do_GET(self):
        if self.path == "/capabilities":
            STATE["capabilities"] += 1
            self.send_json({"omr_engines": ["audiveris", "homr", "hybrid"] if STATE["supported"] else ["audiveris"], "per_request_engine_selection": True})
        elif self.path == "/test/state":
            self.send_json(STATE)
        elif self.path in ("/health", "/auth/check"):
            self.send_json({"ok": True})
        else:
            self.send_json({"error": "unknown path"}, 404)

    def do_POST(self):
        if self.path == "/test/support":
            STATE["supported"] = True
            self.send_json({"ok": True})
            return
        if self.path != "/analyze":
            self.send_json({"error": "unknown path"}, 404)
            return
        size = int(self.headers.get("Content-Length", "0"))
        if size > 1000000:
            self.send_json({"error": "fixture request too large"}, 413)
            return
        body = self.rfile.read(size)
        message = BytesParser(policy=default).parsebytes(
            ("Content-Type: " + self.headers["Content-Type"] + "\r\nMIME-Version: 1.0\r\n\r\n").encode() + body
        )
        parts = {part.get_param("name", header="content-disposition"): part for part in message.iter_parts()}
        engine = parts["omr_engine"].get_payload(decode=True).decode()
        authorized = self.headers.get("Authorization") == "Bearer upgrade-smoke-token"
        STATE["uploads"].append({"engine": engine, "authorized": authorized, "pdf_name": parts["pdf"].get_filename()})
        if not STATE["supported"] or engine != "hybrid" or not authorized:
            self.send_json({"error": "invalid Hybrid request"}, 400)
            return
        self.send_json({"music_xml": XML, "accompaniment_part_id": "P1", "solo_part_id": None, "measures": [], "divisions": 1, "tempo_bpm": 100, "time_signature": {"beats":4,"beat_type":4}, "page_sizes": [], "warnings": [], "omr_engine":"hybrid", "score_title":"Hybrid transport smoke"})

if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 18765), Handler).serve_forever()
