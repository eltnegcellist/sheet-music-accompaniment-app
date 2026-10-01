#!/usr/bin/env python3
"""Exercise the signed Mac bundle through its actual frozen /analyze endpoint."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET
import requests

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    resources = args.app / "Contents/Resources/resources"
    data = args.output / "app-data"
    env = os.environ.copy()
    env.update(
        AUDIVERIS_LAUNCHER=str(resources / "runtime/audiveris/bin/Audiveris"),
        JAVA_HOME=str(resources / "runtime/jre"),
        TESSDATA_PREFIX=str(resources / "runtime/tessdata"),
        TESSERACT_CMD=str(resources / "runtime/tesseract/bin/tesseract"),
        HOMR_LAUNCHER=str(resources / "runtime/homr/bin/homr"),
        HOMR_COREML_MODEL_CACHE_DIR=str(data / "homr/coreml"),
        HOMR_OFFLINE="1",
        PIPELINE_PARAM_SET="v5_real_pdf",
        PATH=str(resources / "runtime/poppler/bin") + os.pathsep + env.get("PATH", ""),
    )
    python = resources / "runtime/homr/python/bin/python3.11"
    providers = json.loads(subprocess.check_output([
        str(python), "-I", "-B", "-c",
        "import json, onnxruntime; print(json.dumps(onnxruntime.get_available_providers()))",
    ], text=True))
    assert "CoreMLExecutionProvider" in providers, providers
    report = {"providers": providers, "offline_homr": True, "engines": {}}
    stdout_path = args.output / "sidecar.stdout"
    stderr_path = args.output / "sidecar.stderr"
    with stdout_path.open("w") as stdout, stderr_path.open("w") as stderr:
        proc = subprocess.Popen([
            str(args.app / "Contents/MacOS/accompanist-server"),
            "--host", "127.0.0.1", "--port", "0", "--app-data", str(data),
        ], env=env, stdout=stdout, stderr=stderr)
        try:
            url = None
            for _ in range(90):
                if proc.poll() is not None:
                    raise RuntimeError("Bundled sidecar exited: " + stderr_path.read_text())
                lines = stdout_path.read_text().splitlines()
                ready = next((line[6:] for line in lines if line.startswith("READY ")), None)
                if ready:
                    url = "http://127.0.0.1:" + str(json.loads(ready)["port"])
                    try:
                        if requests.get(url + "/health", timeout=2).ok:
                            break
                    except requests.RequestException:
                        pass
                time.sleep(1)
            else:
                raise RuntimeError("Bundled sidecar did not become ready")
            caps = requests.get(url + "/capabilities", timeout=5)
            caps.raise_for_status()
            assert caps.json()["per_request_engine_selection"] is True
            for engine in ("audiveris", "homr", "hybrid"):
                started = time.monotonic()
                with args.pdf.open("rb") as pdf:
                    response = requests.post(
                        url + "/analyze",
                        files={"pdf": ("mac-smoke.pdf", pdf, "application/pdf")},
                        data={"omr_engine": engine}, timeout=1800,
                    )
                if not response.ok:
                    raise RuntimeError(f"{engine}: HTTP {response.status_code}: {response.text}")
                result = response.json()
                assert result["omr_engine"] == engine, result
                xml = ET.fromstring(result["music_xml"])
                pitches = len(xml.findall(".//note/pitch"))
                assert pitches > 0 and result["accompaniment_part_id"], result
                (args.output / f"{engine}.musicxml").write_text(result["music_xml"])
                report["engines"][engine] = {
                    "seconds": round(time.monotonic() - started, 2),
                    "pitched_notes": pitches,
                    "accompaniment_part_id": result["accompaniment_part_id"],
                    "warnings": result.get("warnings", []),
                }
                print(json.dumps({engine: report["engines"][engine]}, ensure_ascii=False), flush=True)
            cache = requests.get(url + "/cache", timeout=5).json()
            assert len({entry["param_set_id"] for entry in cache}) == 3, cache
            report["engine_cache_entries"] = len(cache)
            report["passed"] = True
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            (args.output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")

if __name__ == "__main__":
    main()
