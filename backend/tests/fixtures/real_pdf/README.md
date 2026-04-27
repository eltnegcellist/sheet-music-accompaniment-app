# Real-PDF E2E fixtures

Drop your own MusicXML-bearing PDFs into this directory to measure the
pipeline's behaviour on real-world input.

## How to run

The `test_real_pdf_e2e.py` test is **opt-in** because Audiveris takes
10–60 minutes per PDF, and Audiveris itself is only installed inside
the `backend` Docker container — not on your host.

### Option A: Docker (recommended on Windows / macOS)

```powershell
# PowerShell — note the env-var passing is via `docker compose -e ...`,
# NOT PowerShell's $env:VAR. Compose injects the var into the container.

# First run (drives Audiveris, slow):
docker compose exec -e RUN_REAL_PDF_E2E=1 backend `
  pytest -s tests/pipeline/test_real_pdf_e2e.py

# Re-run with cache (fast — no Audiveris):
docker compose exec -e RUN_REAL_PDF_E2E=cached backend `
  pytest -s tests/pipeline/test_real_pdf_e2e.py
```

```sh
# bash / zsh equivalent
docker compose exec -e RUN_REAL_PDF_E2E=1 backend \
  pytest -s tests/pipeline/test_real_pdf_e2e.py
```

The PDFs you drop into this directory show up inside the container at
`/app/tests/fixtures/real_pdf/` automatically (the directory is
bind-mounted via `docker-compose.yml`).

### Option B: directly from a Linux shell

If you have Audiveris on `PATH` on the host:

```sh
RUN_REAL_PDF_E2E=1 pytest -s tests/pipeline/test_real_pdf_e2e.py
RUN_REAL_PDF_E2E=cached pytest -s tests/pipeline/test_real_pdf_e2e.py
```

### Option C: PowerShell directly (Audiveris on host)

PowerShell does **not** support the `VAR=value command` Bash syntax —
that's why you saw `用語 'RUN_REAL_PDF_E2E=1' は ... 認識されません`.
Use `$env:` instead:

```powershell
$env:RUN_REAL_PDF_E2E = "1"
pytest -s tests/pipeline/test_real_pdf_e2e.py
Remove-Item Env:\RUN_REAL_PDF_E2E
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
RUN_REAL_PDF_E2E=1 pytest -s tests/pipeline/test_real_pdf_e2e.py
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `RUN_REAL_PDF_E2E=1: 用語 ... 認識されません` | Bash syntax in PowerShell | Use Option A or C above |
| Test reports `Audiveris not on PATH` | Audiveris not installed on host | Use Option A (Docker) |
| Test reports `No PDFs found under ...` | Dir is empty | Copy a `.pdf` into this dir |
| Test reports `no cached Audiveris output yet` (cached mode) | First run with `=cached` | Run once with `=1` first |
| Audiveris hangs or NPE | Known issue on some scores | Set a smaller PDF first; check `audiveris_runner.py` notes about `-export` |
