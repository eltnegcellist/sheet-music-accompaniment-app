"""Filesystem-backed artifact store.

Each job gets its own root directory `<root>/<job_id>/` and stages drop
files keyed by `kind`. Stages do not invent their own paths — they call
`store.path_for(kind, name)` and write into the returned path. This keeps
the layout consistent across stages and lets debug mode swap the root
without touching stage code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .contracts import ArtifactRef


@dataclass
class FileArtifactStore:
    """Per-job artifact storage on the local filesystem.

    Two intentionally simple operations:
      * `path_for(kind, name)` reserves a path for a stage to write into.
      * `put` records the resulting `ArtifactRef` so other stages can
        retrieve it by `kind`.
    """

    root: Path
    job_id: str

    def __post_init__(self) -> None:
        self._refs: dict[str, list[ArtifactRef]] = {}
        (self.root / self.job_id).mkdir(parents=True, exist_ok=True)

    @property
    def job_dir(self) -> Path:
        return self.root / self.job_id

    def path_for(self, kind: str, name: str) -> Path:
        """Reserve a path under `job_dir/<kind>/<name>` and ensure parents exist."""
        target = self.job_dir / kind / name
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def put(self, ref: ArtifactRef) -> ArtifactRef:
        # Normalise to absolute path so retrievers do not need to know the cwd.
        ref = ArtifactRef(
            kind=ref.kind,
            path=str(Path(ref.path).resolve()),
            meta=dict(ref.meta),
        )
        self._refs.setdefault(ref.kind, []).append(ref)
        return ref

    def get(self, kind: str) -> ArtifactRef | None:
        bucket = self._refs.get(kind)
        return bucket[-1] if bucket else None

    def list(self, kind: str | None = None) -> list[ArtifactRef]:
        if kind is None:
            out: list[ArtifactRef] = []
            for bucket in self._refs.values():
                out.extend(bucket)
            return out
        return list(self._refs.get(kind, []))
