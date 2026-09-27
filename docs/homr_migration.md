# Neural OMR migration and benchmark

## Status

homr 0.7.0 is integrated as an **experimental, opt-in neural OMR engine**.
The production preset remains `v5_real_pdf` (Audiveris) until representative
scores show a clear musical-accuracy improvement. The neural preset is
`v6_homr`.

The first migration task is now a reproducible benchmark rather than an
immediate engine switch.

## Why homr is the first neural candidate

homr 0.7 uses learned segmentation followed by transformer-based semantic
recognition and outputs MusicXML. It supports grand-staff/piano-form notation,
which matches this application's accompaniment use case.

The application rasterizes PDF pages one at a time at 300 DPI to bound memory,
then passes the ordered image paths to homr in one invocation. Current homr
creates a merged MusicXML file for multi-image input.

## Local setup

homr 0.7 requires Python 3.11 or newer.

```bash
cd backend
python3.11 -m venv .venv-homr
source .venv-homr/bin/activate
pip install -e ".[dev,homr]"
```

The `homr` optional dependency installs `homr[cpu]==0.7.0`, including the
ONNX Runtime CPU inference backend. Model assets are managed by homr when it
runs. An existing launcher can be selected with `HOMR_COMMAND`.

To run the API with neural OMR:

```bash
PIPELINE_PARAM_SET=v6_homr uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Benchmark corpus

Do not judge an OMR engine from one score. Build a small representative corpus,
ideally 30-50 pages across:

- clean piano-form engraving;
- violin/cello + piano scores;
- dense polyphony/chords;
- tuplets, ties, accidentals and key changes;
- older IMSLP scans;
- skewed/noisy scans or camera-like inputs.

For quantitative cases, keep the reference MusicXML beside the PDF locally.
For real IMSLP scans without ground truth, omit the reference and compare the
saved recognized MusicXML by playback/listening.

Start from:

`backend/benchmark/manifest.example.yaml`

Copyrighted PDFs and local benchmark outputs are gitignored.

## Run Audiveris vs homr

```bash
cd backend
python -m app.benchmark.omr_compare \
  --manifest benchmark/manifest.yaml \
  --engines audiveris,homr \
  --output benchmark-results
```

The runner preserves each recognized MusicXML and writes:

- `results.csv`
- `results.json`
- one output directory per score / engine

When reference MusicXML exists, the primary metrics are:

1. **note_exact_f1** — pitch + measure-local onset + duration all match;
2. **onset_pitch_f1** — pitch + onset match, separating duration errors;
3. **rhythm_f1** — onset + duration match while ignoring pitch;
4. part-count and measure-count ratios;
5. **playback_score** — accompaniment-oriented aggregate dominated by exact
   pitch/onset/duration accuracy;
6. **gross_failure** — catches severe note or measure-structure collapse.

The existing intrinsic pipeline score is also recorded, but it must not replace
reference-based accuracy. A structurally plausible wrong transcription can
still score well intrinsically.

## Known limitations

- homr returns MusicXML but not Audiveris-compatible per-measure PDF bounding
  boxes. Sheet-view playback works, while original-PDF measure highlighting is
  currently unavailable for neural output.
- homr still has incomplete notation coverage; dynamics and uncommon symbols
  are not the main promotion criterion for this accompaniment app, but pitch,
  rhythm, voices, repeats and measure structure are.
- model files and a Python 3.11 inference environment increase server/runtime
  footprint.
- homr is AGPL-3.0. The application is AGPL-3.0-or-later and must preserve the
  corresponding notices/source obligations.

## Promotion gate

Do **not** make homr the default merely because it is deep-learning based.
Promote it only after the benchmark shows a material reduction in musically
significant failures.

The proposed gate is:

- reference `note_exact_f1` and `playback_score` improve materially across
  the corpus, not only on one edition;
- at least half of pages that are gross failures under Audiveris become usable
  under homr;
- no unacceptable regression in clean/simple scores;
- runtime and memory remain acceptable on the intended self-host server;
- end-to-end playback remains correct in the Android client.

Keep Audiveris as a reversible fallback even if homr becomes the default.

## Later candidates

After the Audiveris/homr baseline is measured, add adapters for research models
such as Sheet Music Transformer or Acai OMR only if their inference setup is
reproducible and their licenses/dependencies are suitable. The benchmark format
is intentionally engine-neutral so those outputs can be compared against the
same corpus later.
