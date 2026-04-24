"""Load and resolve parameter sets.

Each YAML may declare `meta.parent: <id>` to inherit from another file in
the same directory; the loader deep-merges children onto parents so a
child only spells out the differences. After resolution the result is
validated against `schema.json` and written to `resolved_params.yaml`
for replay.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml
from jsonschema import Draft202012Validator


class ParamsError(RuntimeError):
    """Raised when a params file is missing, unparseable, or invalid."""


@dataclass(frozen=True)
class ResolvedParams:
    """Resolved + validated parameter set ready to drive a pipeline run.

    `id` is the leaf id (not the parent's). `sha` is a content hash so
    log lines can pin the exact resolved bytes even if files mutate.
    """

    id: str
    data: dict[str, Any]
    sha: str

    def param_set_id(self) -> str:
        return f"{self.id}@{self.sha[:8]}"


def deep_merge(parent: Mapping[str, Any], child: Mapping[str, Any]) -> dict[str, Any]:
    """Merge `child` onto `parent`. Dicts recurse; everything else is replaced.

    Lists are intentionally replaced wholesale: extending lists silently
    is a common source of "why is this value still here" bugs and we want
    children to fully own their array values.
    """
    out: dict[str, Any] = dict(parent)
    for key, value in child.items():
        if (
            key in out
            and isinstance(out[key], Mapping)
            and isinstance(value, Mapping)
        ):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ParamsError(f"Params file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        try:
            data = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            raise ParamsError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ParamsError(f"Params file root must be a mapping: {path}")
    return data


def _content_sha(data: Mapping[str, Any]) -> str:
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_params(
    set_id: str,
    params_dir: Path,
    schema_path: Path | None = None,
    _seen: tuple[str, ...] = (),
) -> ResolvedParams:
    """Load `<set_id>.yaml`, resolve `meta.parent` recursively, validate.

    Cycles are detected via `_seen`; missing parents raise `ParamsError`.
    Schema validation runs on the *resolved* document so children that
    only set diff fields don't need to satisfy the full schema alone.
    """
    if set_id in _seen:
        chain = " -> ".join([*_seen, set_id])
        raise ParamsError(f"Cyclic parent chain in params: {chain}")

    raw = _read_yaml(params_dir / f"{set_id}.yaml")
    parent_id = raw.get("meta", {}).get("parent")
    if parent_id:
        parent = load_params(parent_id, params_dir, schema_path=None, _seen=(*_seen, set_id))
        merged = deep_merge(parent.data, raw)
        # Child's meta.id must win — deep_merge already does that, but be defensive
        merged.setdefault("meta", {})["id"] = raw["meta"]["id"]
        # Drop the parent pointer from the resolved doc; resolved params
        # are flat and self-contained.
        merged["meta"].pop("parent", None)
    else:
        merged = dict(raw)
        merged.setdefault("meta", {}).pop("parent", None)

    if schema_path is not None:
        _validate(merged, schema_path)
    return ResolvedParams(
        id=merged["meta"]["id"],
        data=merged,
        sha=_content_sha(merged),
    )


def _validate(data: Mapping[str, Any], schema_path: Path) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    if not errors:
        return
    formatted = "\n".join(
        f"  - {'.'.join(str(p) for p in err.absolute_path) or '<root>'}: {err.message}"
        for err in errors
    )
    raise ParamsError(f"Params schema violations:\n{formatted}")


def write_resolved(resolved: ResolvedParams, target: Path) -> Path:
    """Persist the resolved doc next to the run's artifacts for replay."""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(resolved.data, sort_keys=True), encoding="utf-8")
    return target
