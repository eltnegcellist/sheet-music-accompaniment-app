# Third-Party Notices

IMSLP Accompanist is Copyright (C) 2026 Hidetaka Ito and contributors.
It is distributed under the GNU Affero General Public License, version 3
or (at your option) any later version. See `LICENSE` and the corresponding
source at <https://github.com/eltnegcellist/sheet-music-accompaniment-app>.

The distributed desktop application contains or uses the following principal
third-party works. Their licenses remain in force; this notice does not replace
the license files shipped with the application.

## Audiveris 5.10.2

Audiveris is licensed under the GNU Affero General Public License version 3.
Source: <https://github.com/Audiveris/audiveris/tree/5.10.2>

The exact Audiveris license text is included in distributed builds as
`AUDIVERIS-LICENSE`.

## homr 0.7.0

The Apple Silicon Mac distribution includes homr 0.7.0 for local neural
recognition and the confidence-gated Hybrid engine. Server deployments can
also install homr as an optional backend. homr is licensed under the GNU Affero General Public
License version 3.
Source: <https://github.com/liebharc/homr/tree/v0.7.0>

The Mac distribution includes homr's CPU/CoreML model files and a relocatable
CPython 3.11.16 runtime from python-build-standalone release 20260929.
The Python archive is verified against its pinned SHA-256 at build time.
`homr/HOMR-LICENSE`, `homr/PYTHON-LICENSE`, and the installed package list are
included with the distribution notices. Python package license files remain
in their bundled dist-info directories; the runtime manifest records model
filenames and SHA-256 hashes.
Python source: <https://www.python.org/>
Portable Python build source: <https://github.com/astral-sh/python-build-standalone/tree/20260929>

## Audio samples

The Salamander Grand Piano V2 recordings by Alexander Holm are licensed under
Creative Commons Attribution 3.0:
<https://creativecommons.org/licenses/by/3.0/>.
The application streams a subset hosted by the Tone.js project.

Solo instrument samples are provided by the tonejs-instruments project and
are based on the University of Iowa Electronic Music Studios sample library.
See <https://github.com/nbrosowsky/tonejs-instruments> for its current notices
and per-instrument attribution.

## Other bundled components

The application also bundles a Temurin/OpenJDK runtime, Tesseract OCR, Poppler,
Python packages, Rust crates, and JavaScript packages. Their applicable license
and notice files are preserved in the application bundle by the release
scripts. Dependency lockfiles in this repository identify exact versions.

No warranty is provided, to the extent permitted by applicable law.
