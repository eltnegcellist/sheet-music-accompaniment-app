# homr migration plan

## Status

homr 0.7.0 is integrated as an **experimental, opt-in OMR engine**. The
production preset remains `v5_real_pdf` (Audiveris). Use `v6_homr` only for
comparison until representative scores have been measured.

The current distributed DMG does not bundle homr or its model files. This
phase establishes the engine boundary, bounded-memory PDF adapter, parameter
preset, tests, and license notices before changing packaging.

## Why this fits an M4 Mac with 16 GB RAM

homr 0.7 uses ONNX Runtime for inference rather than requiring a local
PyTorch training stack. On Apple Silicon it can use CoreML for segmentation.
This adapter further limits peak memory by rasterizing only one PDF page at a
time at 300 DPI. All rendered pages are then passed to homr's folder mode and
recognized sequentially, avoiding multiple concurrent model workers.

The optional `--coreml-encoder` mode is deliberately disabled in the first
preset. Its compilation cost can dominate a short score; it should be enabled
only after an M4 benchmark shows a benefit for the user's typical page count.

## Local setup

homr requires Python 3.11 or newer.

```bash
cd backend
python3.11 -m venv .venv-homr
source .venv-homr/bin/activate
pip install -e ".[dev,homr]"
homr --init
PIPELINE_PARAM_SET=v6_homr uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`homr --init` downloads the model files. An existing or separately managed
launcher can be selected with `HOMR_COMMAND`. `OMR_ENGINE=homr` overrides the
engine in a parameter set for temporary testing.

## Known limitations

- homr currently returns MusicXML but not Audiveris-compatible per-measure
  bounding boxes. Sheet-view playback works, while highlighting measures on
  the original PDF is disabled for homr results.
- OMR symbol coverage is not complete. A real-score benchmark is required;
  using a neural model does not guarantee that every edition improves.
- Model files materially increase the app bundle. Packaging and first-run
  model initialization remain a separate phase.
- homr is AGPL-3.0. This application is already AGPL-3.0-or-later and lists
  homr in `THIRD_PARTY_NOTICES.md`; a bundled release must also preserve homr's
  license and corresponding-source notice.

## Promotion gate

Before making homr the default or putting it in the DMG, compare Audiveris and
homr on the same representative PDFs and record:

1. wrong/missing pitches and rhythms;
2. structural failures (parts, measures, voices, repeats);
3. end-to-end time and peak memory on the M4 16 GB Mac;
4. first-run model download and disk footprint;
5. playback and sheet-view regressions.

Promote only if the musically significant error rate improves without an
unacceptable memory or startup penalty. Keep the engine switch reversible so
scores that work better in Audiveris retain a fallback path.
