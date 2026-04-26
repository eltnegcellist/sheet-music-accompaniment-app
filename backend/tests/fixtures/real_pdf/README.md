# Real-PDF E2E fixtures

Drop your own MusicXML-bearing PDFs into this directory to measure the
pipeline's behaviour on real-world input.

## How to run

The `test_real_pdf_e2e.py` test is **opt-in** because Audiveris takes
10–60 minutes per PDF.

```sh
# Inside the backend container (Audiveris is installed there):
RUN_REAL_PDF_E2E=1 pytest tests/pipeline/test_real_pdf_e2e.py -s
```

The first run shells out to Audiveris and writes the resulting MusicXML
into `.cache/<sha256>.musicxml`. Subsequent invocations reuse that
cache, so changes to the postprocess code can be re-evaluated in
seconds instead of minutes:

```sh
RUN_REAL_PDF_E2E=cached pytest tests/pipeline/test_real_pdf_e2e.py -s
```

The `-s` flag is required to see the lift table that the test prints.

## What's measured

For each PDF, the test runs the cached Audiveris MusicXML through every
shipped param-set version (v1_baseline, v3_with_postprocess, v4_with_pitch,
v5_real_pdf) and prints `final_score` per fixture × param set. The
soft assertion only fires when v5 regresses below v1 on average — it's
deliberately conservative so a single oddball PDF can't block CI.

## What goes in this directory

- `*.pdf`        — your input PDFs (gitignored)
- `.cache/*.musicxml` — cached Audiveris output, keyed by PDF sha256

Both are ignored by git so the repository stays small and copyrighted
material doesn't accidentally leak.

## Refreshing the cache

If you upgrade Audiveris (different `AUDIVERIS_VERSION` in the
Dockerfile) and want to re-OCR everything:

```sh
rm -rf tests/fixtures/real_pdf/.cache
RUN_REAL_PDF_E2E=1 pytest tests/pipeline/test_real_pdf_e2e.py -s
```
