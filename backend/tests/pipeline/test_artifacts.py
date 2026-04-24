from app.pipeline.artifacts import FileArtifactStore
from app.pipeline.contracts import ArtifactRef


def test_path_for_creates_parents(tmp_path):
    store = FileArtifactStore(root=tmp_path, job_id="job1")
    p = store.path_for("preprocess", "binary.png")
    assert p.parent.exists()
    assert p.parent == tmp_path / "job1" / "preprocess"


def test_put_get_returns_latest(tmp_path):
    store = FileArtifactStore(root=tmp_path, job_id="job1")
    p1 = store.path_for("musicxml", "a.xml")
    p1.write_text("<xml/>")
    p2 = store.path_for("musicxml", "b.xml")
    p2.write_text("<xml/>")
    store.put(ArtifactRef(kind="musicxml", path=str(p1)))
    store.put(ArtifactRef(kind="musicxml", path=str(p2)))
    latest = store.get("musicxml")
    assert latest is not None
    assert latest.path.endswith("b.xml")
    assert len(store.list("musicxml")) == 2


def test_put_normalises_to_absolute(tmp_path, monkeypatch):
    store = FileArtifactStore(root=tmp_path, job_id="job1")
    monkeypatch.chdir(tmp_path)
    store.put(ArtifactRef(kind="x", path="./rel.txt"))
    got = store.get("x")
    assert got is not None
    assert got.path.startswith("/")  # absolute


def test_list_all(tmp_path):
    store = FileArtifactStore(root=tmp_path, job_id="job1")
    store.put(ArtifactRef(kind="a", path=str(tmp_path / "a")))
    store.put(ArtifactRef(kind="b", path=str(tmp_path / "b")))
    assert {r.kind for r in store.list()} == {"a", "b"}
