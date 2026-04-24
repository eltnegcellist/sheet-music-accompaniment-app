"""Tests for the params loader.

Covers two angles:
  * unit tests for `deep_merge` and inheritance resolution
  * integration tests against the shipped `params/v1_baseline.yaml` and
    `params/schema.json` so we catch divergences between code, YAML
    fixtures, and schema in a single CI run.
"""

from pathlib import Path

import pytest
import yaml

from app.pipeline.params_loader import (
    ParamsError,
    deep_merge,
    load_params,
    write_resolved,
)

REPO = Path(__file__).resolve().parents[2]
PARAMS_DIR = REPO / "params"
SCHEMA = PARAMS_DIR / "schema.json"


# --- deep_merge ----------------------------------------------------------


def test_deep_merge_recurses_dicts():
    parent = {"a": {"x": 1, "y": 2}, "b": 1}
    child = {"a": {"y": 99}}
    assert deep_merge(parent, child) == {"a": {"x": 1, "y": 99}, "b": 1}


def test_deep_merge_replaces_lists_wholesale():
    parent = {"l": [1, 2, 3]}
    child = {"l": [9]}
    # Lists are replaced, not extended — children fully own array values.
    assert deep_merge(parent, child) == {"l": [9]}


def test_deep_merge_does_not_mutate_inputs():
    parent = {"a": {"x": 1}}
    child = {"a": {"y": 2}}
    deep_merge(parent, child)
    assert parent == {"a": {"x": 1}}
    assert child == {"a": {"y": 2}}


# --- shipped fixtures ----------------------------------------------------


def test_v1_baseline_passes_schema():
    r = load_params("v1_baseline", PARAMS_DIR, schema_path=SCHEMA)
    assert r.id == "v1_baseline"
    assert "parent" not in r.data["meta"]
    assert r.data["preprocess"]["staff_norm"]["enabled"] is False


def test_v2_inherits_then_overrides():
    r = load_params("v2_staff_norm", PARAMS_DIR, schema_path=SCHEMA)
    assert r.id == "v2_staff_norm"
    # Inherited from v1
    assert r.data["preprocess"]["binarize"]["k"] == 0.20
    # Overridden in v2
    assert r.data["preprocess"]["staff_norm"]["enabled"] is True
    assert r.data["preprocess"]["quality_gate"]["on_fail"] == "retry_alt_params"


def test_resolved_sha_is_stable_across_loads():
    a = load_params("v2_staff_norm", PARAMS_DIR, schema_path=SCHEMA)
    b = load_params("v2_staff_norm", PARAMS_DIR, schema_path=SCHEMA)
    assert a.sha == b.sha


def test_param_set_id_format():
    r = load_params("v1_baseline", PARAMS_DIR, schema_path=SCHEMA)
    sid = r.param_set_id()
    assert sid.startswith("v1_baseline@")
    # Suffix is the first 8 hex chars of the sha.
    assert len(sid.split("@", 1)[1]) == 8


# --- error paths ---------------------------------------------------------


def test_missing_file_raises(tmp_path):
    with pytest.raises(ParamsError, match="not found"):
        load_params("does_not_exist", tmp_path)


def test_invalid_yaml_raises(tmp_path):
    (tmp_path / "bad.yaml").write_text(":\n: invalid")
    with pytest.raises(ParamsError, match="Invalid YAML"):
        load_params("bad", tmp_path)


def test_non_mapping_root_raises(tmp_path):
    (tmp_path / "list.yaml").write_text("- 1\n- 2")
    with pytest.raises(ParamsError, match="must be a mapping"):
        load_params("list", tmp_path)


def test_cycle_detected(tmp_path):
    (tmp_path / "a.yaml").write_text("meta:\n  id: a\n  version: 1\n  parent: b\n")
    (tmp_path / "b.yaml").write_text("meta:\n  id: b\n  version: 1\n  parent: a\n")
    with pytest.raises(ParamsError, match="Cyclic"):
        load_params("a", tmp_path)


def test_schema_violation_surfaces_path(tmp_path):
    # Copy v1 then break a value to confirm the error path is reported.
    src = yaml.safe_load((PARAMS_DIR / "v1_baseline.yaml").read_text(encoding="utf-8"))
    src["preprocess"]["binarize"]["method"] = "no_such_method"
    (tmp_path / "broken.yaml").write_text(yaml.safe_dump(src))
    with pytest.raises(ParamsError, match="preprocess.binarize.method"):
        load_params("broken", tmp_path, schema_path=SCHEMA)


# --- write_resolved ------------------------------------------------------


def test_write_resolved_round_trip(tmp_path):
    r = load_params("v2_staff_norm", PARAMS_DIR, schema_path=SCHEMA)
    target = tmp_path / "nested" / "resolved_params.yaml"
    written = write_resolved(r, target)
    assert written == target
    reloaded = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert reloaded == r.data
