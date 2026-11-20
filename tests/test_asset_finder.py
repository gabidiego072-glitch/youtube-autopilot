"""Nov 20: the system finds free 3D models by itself; the owner does not install anything."""

import json
from pathlib import Path
from types import SimpleNamespace

from app.services.assets import finder
from app.services.autopilot.runner import _bundle_models


def test_library_packs_come_first():
    found = finder.find_model("big trees", token="")
    assert found and found["file"].endswith(".obj") and "Tree" in Path(found["file"]).name


def test_without_a_token_nothing_is_downloaded(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSET_CACHE", str(tmp_path))
    assert finder.find_model("airplane", ai=object(), blender="blender", token="") is None


def test_sketchfab_results_keep_only_free_simple_models():
    results = {
        "results": [
            {"uid": "a", "name": "Plane", "license": {"slug": "by"}, "faceCount": 900, "user": {"displayName": "Ann"}},
            {"uid": "b", "name": "Real", "license": {"slug": "by"}, "faceCount": 900_000, "user": {}},
            {"uid": "c", "name": "Paid", "license": {"slug": "st"}, "faceCount": 10, "user": {}},
            {
                "uid": "e",
                "name": "NC",
                "license": {"label": "CC Attribution-NonCommercial"},
                "faceCount": 10,
                "user": {},
            },
            {"uid": "f", "name": "Label", "license": {"label": "CC Attribution"}, "faceCount": 10, "user": {}},
            {"uid": "d", "name": "Free", "license": {"slug": "cc0"}, "faceCount": 10, "user": {"username": "z"}},
        ]
    }
    client = SimpleNamespace(get=lambda *a, **k: SimpleNamespace(json=lambda: results))
    found = finder.search_sketchfab("plane", client)
    assert [f["uid"] for f in found] == ["a", "f", "d"] and found[0]["license"] == "CC BY 4.0"


def test_a_cached_model_is_reused_and_a_recent_miss_is_not_searched_again(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSET_CACHE", str(tmp_path))
    model = tmp_path / "cat" / "model" / "model.glb"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"glb")
    (tmp_path / "cat" / "meta.json").write_text(json.dumps({"file": str(model), "credit": "x"}))
    assert finder.find_model("cat", token="t", ai=object(), blender="b")["file"] == str(model)
    (tmp_path / "ufo").mkdir()
    (tmp_path / "ufo" / "meta.json").write_text(json.dumps({"none": True, "at": 9e12}))
    assert finder.find_model("ufo", token="t", ai=object(), blender="b") is None


def test_a_found_model_goes_with_the_work_files_and_its_credit_to_the_description(tmp_path):
    src = tmp_path / "cache" / "cat" / "model" / "model.glb"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"glb")
    specs = [{"props": [{"id": "obj", "type": "file_model", "file": str(src)}], "credit": '"Cat" by Ann (CC BY 4.0)'}]
    out, credits = _bundle_models(specs, tmp_path / "work")
    moved = Path(out[0]["props"][0]["file"])
    assert moved.exists() and (tmp_path / "work") in moved.parents and credits == ['"Cat" by Ann (CC BY 4.0)']


def test_a_found_model_gets_its_real_size_from_the_ai(monkeypatch):
    from app.services.scenes import objects

    monkeypatch.setattr(objects, "library_model", lambda name: None)
    monkeypatch.setattr(finder, "find_model", lambda name, **_: {"file": "/m/plane.glb", "credit": "c"})
    ai = SimpleNamespace(generate_json=lambda **_: SimpleNamespace(data={"height_m": 17.0}))
    design = objects.design_object(ai, "airplane")
    assert design["library"] == "file" and design["height"] == 17.0 and design["credit"] == "c"
