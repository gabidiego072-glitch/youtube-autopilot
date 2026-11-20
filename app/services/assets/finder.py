"""Find a free 3D model for a thing a line says, by itself (Nov 20, the owner: "the system does it alone").

Order: the models already in the library (the packs in the repo and the ones found for earlier videos), then
Sketchfab (free models, CC0 or CC-BY, needs SKETCHFAB_API_TOKEN). A candidate is rendered once and an AI judges
it against the owner's style (simple, geometric, made with code, never realistic); the first that passes is
kept in the library for the next videos. Nothing found: the caller builds the thing from simple shapes.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

PACKS = Path(__file__).resolve().parents[3] / "render_engines" / "assets"
SEARCH = "https://api.sketchfab.com/v3/search"
DOWNLOAD = "https://api.sketchfab.com/v3/models/{uid}/download"
# free to use in monetised videos (CC BY: credit the author). The search gives only the licence's label
# (Nov 20: matching a "slug" kept nothing). NonCommercial, ShareAlike and Sketchfab's own licences are left out.
LICENSES = {"cc0": "CC0", "by": "CC BY 4.0", "cc0 public domain": "CC0", "cc attribution": "CC BY 4.0"}
MAX_FACES = 30_000  # more is a detailed, realistic model; the owner wants simple ones
MAX_BYTES = 25_000_000
CANDIDATES = 3
NONE_DAYS = 7

STYLE_SYSTEM = """You check 3D models for a YouTube Shorts channel whose look is simple, geometric, low-poly,
cartoon-like, "made with code" (flat colours, few polygons), never realistic or photographic. You see one render
of a model. Answer whether it clearly shows the asked thing AND fits that look."""
STYLE_SCHEMA = {
    "type": "object",
    "properties": {
        "shows_it": {"type": "boolean"},
        "simple_style": {"type": "boolean"},
        "note": {"type": "string"},
    },
    "required": ["shows_it", "simple_style"],
}


def cache_dir() -> Path:
    root = Path(os.environ.get("ASSET_CACHE", "") or (Path(os.environ.get("MEDIA_ROOT", "media")) / "asset_cache"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def slug(thing: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", thing.lower()).strip("_")[:40]


def from_packs(thing: str) -> dict | None:
    """A model from the packs in the repo (Quaternius simple nature: tree, bush, rock, grass)."""
    words = set(re.findall(r"[a-z]+", thing.lower()))
    for pack in sorted(PACKS.glob("*")) if PACKS.is_dir() else []:
        for model in sorted(pack.glob("*.obj")):
            name = re.sub(r"\d+$", "", model.stem).lower()
            if name in words or f"{name}s" in words:
                return {"file": str(model), "credit": "", "source": f"pack {pack.name}"}
    return None


def from_cache(thing: str) -> dict | None:
    meta = cache_dir() / slug(thing) / "meta.json"
    if meta.exists():
        data = json.loads(meta.read_text(encoding="utf-8"))
        if data.get("file") and Path(data["file"]).exists():
            return data
        if data.get("none") and time.time() - float(data.get("at", 0)) < NONE_DAYS * 86400:
            return {"none": True}  # nothing fitted recently: try again after a while (a judge may have been down)
    return None


def search_sketchfab(thing: str, client: httpx.Client) -> list[dict]:
    params = {
        "type": "models",
        "q": f"{thing} low poly",
        "downloadable": "true",
        "sort_by": "-likeCount",
        "count": 24,
    }
    data = client.get(SEARCH, params=params, timeout=30).json()
    found = []
    for m in data.get("results", []):
        info = m.get("license") or {}
        lic = (info.get("slug") or info.get("label") or "").strip().lower()
        if lic not in LICENSES or int(m.get("faceCount") or 0) > MAX_FACES:
            continue
        found.append(
            {
                "uid": m["uid"],
                "name": m.get("name", ""),
                "author": (m.get("user") or {}).get("displayName") or (m.get("user") or {}).get("username", ""),
                "license": LICENSES[lic],
                "url": m.get("viewerUrl", ""),
            }
        )
    return found


def download_sketchfab(candidate: dict, token: str, client: httpx.Client, folder: Path) -> Path | None:
    info = client.get(DOWNLOAD.format(uid=candidate["uid"]), headers={"Authorization": f"Token {token}"}, timeout=30)
    if info.status_code != 200:
        log.warning("sketchfab download %s: HTTP %s", candidate["uid"], info.status_code)
        return None
    data = info.json()
    pick = data.get("glb") or data.get("gltf")
    if not pick or int(pick.get("size") or 0) > MAX_BYTES:
        return None
    blob = client.get(pick["url"], timeout=120).content
    folder.mkdir(parents=True, exist_ok=True)
    if data.get("glb"):
        path = folder / "model.glb"
        path.write_bytes(blob)
        return path
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        z.extractall(folder)
    gltf = next(iter(sorted(folder.rglob("*.gltf"))), None)
    return gltf


PREVIEW = """
import bpy, sys, math
from mathutils import Vector
path, out = sys.argv[sys.argv.index("--") + 1:][:2]
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
if path.endswith(".obj"):
    bpy.ops.wm.obj_import(filepath=path)
else:
    bpy.ops.import_scene.gltf(filepath=path)
objs = [o for o in sc.objects if o.type == "MESH"]
pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
c, r = (lo + hi) / 2, max((hi - lo).length / 2, 0.01)
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); sc.collection.objects.link(cam); sc.camera = cam
cam.location = c + Vector((r * 1.9, -r * 2.4, r * 1.3))
cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
sun = bpy.data.objects.new("s", bpy.data.lights.new("s", "SUN")); sun.data.energy = 3
sun.rotation_euler = (math.radians(45), 0, math.radians(30)); sc.collection.objects.link(sun)
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.8, 0.85, 0.9, 1)
sc.render.engine = "CYCLES"; sc.cycles.samples = 8
sc.render.resolution_x = sc.render.resolution_y = 384
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
"""


def preview(blender: str, model: Path, out: Path) -> Path | None:
    script = out.with_suffix(".py")
    script.write_text(PREVIEW, encoding="utf-8")
    try:
        subprocess.run(
            [blender, "-b", "--factory-startup", "--python", str(script), "--", str(model), str(out)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=240,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None
    return out if out.exists() and out.stat().st_size > 0 else None


def fits_style(ai, thing: str, image: Path) -> bool:
    try:
        result = ai.generate_json(
            system=STYLE_SYSTEM, prompt=f"The asked thing: {thing}", schema=STYLE_SCHEMA, images=[image.read_bytes()]
        )
    except Exception as exc:  # noqa: BLE001 - no judge: do not take an unchecked model
        log.warning("style check failed for %s: %s", thing, exc)
        return False
    data = result.data if isinstance(result.data, dict) else {}
    return bool(data.get("shows_it")) and bool(data.get("simple_style"))


def find_model(thing: str, ai=None, blender: str | None = None, token: str | None = None) -> dict | None:
    """{"file", "credit", "source"} for `thing`, or None (then it is built from shapes)."""
    thing = " ".join(thing.lower().split())[:40]
    if not thing:
        return None
    found = from_packs(thing) or from_cache(thing)
    if found:
        return None if found.get("none") else found
    token = token if token is not None else os.environ.get("SKETCHFAB_API_TOKEN", "")
    if not (token and ai and blender):
        return None
    folder = cache_dir() / slug(thing)
    with httpx.Client(follow_redirects=True) as client:
        try:
            candidates = search_sketchfab(thing, client)
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("sketchfab search failed for %s: %s", thing, exc)
            return None
        for candidate in candidates[:CANDIDATES]:
            tmp = Path(tempfile.mkdtemp(prefix="asset_"))
            try:
                path = download_sketchfab(candidate, token, client, tmp / "model")
                if path is None:
                    continue
                image = preview(blender, path, tmp / "preview.png")
                if image is None or not fits_style(ai, thing, image):
                    log.info("model %r for %s rejected by the style check", candidate["name"], thing)
                    continue
                if folder.exists():
                    shutil.rmtree(folder)
                shutil.copytree(path.parent, folder / "model")
                shutil.copy(image, folder / "preview.png")
                credit = f'"{candidate["name"]}" by {candidate["author"]} ({candidate["license"]}) {candidate["url"]}'
                meta = {
                    "file": str(folder / "model" / path.name),
                    "credit": credit if candidate["license"] != "CC0" else "",
                    "source": "sketchfab",
                }
                (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
                return meta
            except (httpx.HTTPError, OSError, zipfile.BadZipFile, ValueError) as exc:
                log.warning("model %r for %s failed: %s", candidate.get("name"), thing, exc)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
    folder.mkdir(parents=True, exist_ok=True)  # remember that nothing fitted: do not search again every video
    (folder / "meta.json").write_text(json.dumps({"none": True, "at": time.time()}), encoding="utf-8")
    return None
