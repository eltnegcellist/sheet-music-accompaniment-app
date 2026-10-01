import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET
import httpx

out = Path(sys.argv[1])
client = httpx.Client(base_url="http://127.0.0.1:18765", timeout=60)
assert client.get("/health").status_code == 200
assert client.get("/capabilities").status_code == 401
assert client.get("/auth/check", headers={"Authorization": "Bearer wrong"}).status_code == 401
client.headers["Authorization"] = "Bearer integration-test-token"
caps = client.get("/capabilities").json()
assert caps["omr_engines"] == ["audiveris", "homr", "hybrid"]
assert caps["per_request_engine_selection"] is True

def analyze(engine):
    response = client.post("/analyze", data={"omr_engine": engine},
        files={"pdf": ("replay.pdf", (out / "replay.pdf").read_bytes(), "application/pdf")})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["omr_engine"] == engine
    assert result["accompaniment_part_id"]
    assert ET.fromstring(result["music_xml"]).find("./part/measure") is not None
    return result

def calls():
    return client.get("/__test__/state").json()["recognition_calls"]

hybrid = analyze("hybrid")
assert any("25小節 / 170音 (81.3%)" in w for w in hybrid["warnings"]), hybrid["warnings"]
assert calls() == ["audiveris", "homr"]
assert analyze("hybrid")["music_xml"] == hybrid["music_xml"]
assert calls() == ["audiveris", "homr"]
analyze("homr")
analyze("audiveris")
assert calls() == ["audiveris", "homr", "homr", "audiveris"]
for name in ("hybrid", "homr", "audiveris"):
    analyze(name)
assert len(calls()) == 4
invalid = client.post("/analyze", data={"omr_engine": "invalid"},
    files={"pdf": ("replay.pdf", (out / "replay.pdf").read_bytes(), "application/pdf")})
assert invalid.status_code == 400
(out / "hybrid-response.json").write_text(json.dumps(hybrid, ensure_ascii=False))
(out / "api-verification.json").write_text(json.dumps({"passed": True,
    "checks": ["token-auth", "capabilities", "production-hybrid-safe-fusion", "engine-cache-isolation", "invalid-engine"],
    "recognition_calls": calls()}, indent=2))
print("Real API and production Hybrid replay passed.")
