# Mac local OMR

The Apple Silicon Mac bundle contains the FastAPI sidecar, Audiveris/JRE,
Poppler/Tesseract, and a separate portable Python 3.11 interpreter with homr
0.7.0 and its CPU/CoreML models. No external OMR server, Python installation,
or first-use model download is required.

Open **OMR** in the toolbar to choose Audiveris, homr, or Hybrid. The default
remains Audiveris. Desktop preferences are separate from Android server settings.
Each engine uses its existing parameter set and a separate cache.

homr uses CoreML segmentation when available. On Apple Silicon, PDFs with four
or more pages also request the CoreML encoder. The transformer decoder stays on
CPU. First use compiles models; compiled caches live in the application data
directory under `homr/coreml`, not inside the signed app. Pages are processed
sequentially to bound memory use. GPU speedups and M4 performance require actual
device measurement.

The `macos-local-release` workflow builds on an ARM Mac runner, ad-hoc signs the
app, makes its Resources directory read-only, and exercises the frozen backend's
/analyze API using all three engines on one real Saint-Saëns page. homr's Python
network calls are denied during this test. It checks engine-specific caches,
CoreML provider availability, and the app signature after inference. This is a
packaging smoke test; the existing 18-page quality benchmark is not repeated.

Successful main builds publish a prerelease DMG under `macos-v0.2.0`, together
with SHA-256 sums, model hashes, and the smoke report. The source commit is the
release target. The DMG is not notarized; see
[unsigned installation instructions](macos_unsigned_distribution.md).

Remaining device checks: install on the user's M4, select all three engines,
load a PDF, play/stop the accompaniment, restart to check preference/cache
retention, and measure first-use versus warmed-up analysis time.
