"""Disk-backed cache for /analyze responses.

Audiveris is slow (a 30-page sonata can take 20+ minutes). When the same PDF
is uploaded a second time we don't want to re-run OMR — the OMR result for a
given PDF is deterministic for a given param set. We key cache entries by
SHA-256 of the PDF bytes plus the active param set id so a server config change
invalidates entries automatically.

The cache stores the serialised AnalyzeResponse JSON; the API layer just
re-hydrates it. Layout is:

    <root>/<sha256>__<param_set_id>.json

Concurrent writes are tolerated by writing to a temp file in the same directory
and renaming atomically.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _default_cache_dir() -> Path:
    env = os.environ.get("ANALYZE_CACHE_DIR")
    if env:
        return Path(env)
    # Inside Docker /app is the working dir, so this lands in /app/cache.
    return Path(os.environ.get("APP_DATA_DIR", ".")) / "cache" / "analyze"


def hash_pdf_bytes(*chunks: bytes) -> str:
    """SHA-256 hex digest over the concatenated chunks. Order matters."""
    h = hashlib.sha256()
    for chunk in chunks:
        h.update(chunk)
    return h.hexdigest()


def _safe_token(value: str | None) -> str:
    if not value:
        return "noparam"
    # Filenames must avoid shell-unsafe characters. Param set ids include
    # `@sha8` so allow @ and - in the safe set.
    return re.sub(r"[^A-Za-z0-9_.@\-]+", "_", value)[:80]


class AnalyzeCache:
    """Read/write the serialised AnalyzeResponse for a PDF + param set."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or _default_cache_dir()).resolve()

    def path_for(self, key: str, param_set_id: str | None) -> Path:
        return self.root / f"{key}__{_safe_token(param_set_id)}.json"

    def get(self, key: str, param_set_id: str | None) -> dict[str, Any] | None:
        path = self.path_for(key, param_set_id)
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            # A corrupt or partial cache file should not break /analyze; just
            # treat it as a miss and let the next successful run overwrite it.
            logger.warning("Cache read failed for %s: %s", path, exc)
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    def put(
        self,
        key: str,
        param_set_id: str | None,
        payload: dict[str, Any],
    ) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.path_for(key, param_set_id)
        # Atomic write: temp file in the same dir then rename.
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.root,
                prefix=".tmp_",
                suffix=".json",
                delete=False,
            ) as fh:
                json.dump(payload, fh, ensure_ascii=False)
                tmp_path = Path(fh.name)
            os.replace(tmp_path, path)
        except OSError as exc:
            logger.warning("Cache write failed for %s: %s", path, exc)

    def invalidate(self, key: str, param_set_id: str | None = None) -> None:
        """Delete the cache entry for `key` (and optional param set).

        When `param_set_id` is None all entries with the same key are dropped
        — used by the force-reanalyze path so a stale entry under any param
        set cannot mask the new result.
        """
        if param_set_id is not None:
            path = self.path_for(key, param_set_id)
            path.unlink(missing_ok=True)
            return
        if not self.root.exists():
            return
        for p in self.root.glob(f"{key}__*.json"):
            p.unlink(missing_ok=True)
