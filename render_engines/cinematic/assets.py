"""Free 3D models from libraries (Nov 20): look a thing up here before building it from shapes.

Models live in render_engines/assets/<pack>/<Model>.obj (the owner chose the packs: simple, geometric, never
realistic; see app/content/ASSETS.md). Each model is imported once and copied (sharing its mesh) where needed.
"""

from __future__ import annotations

from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parent.parent / "assets"
_templates: dict[tuple[str, str], bpy.types.Object] = {}


def available(pack: str) -> list[str]:
    folder = ROOT / pack
    return sorted(p.stem for p in folder.glob("*.obj")) if folder.is_dir() else []


def _template(pack: str, model: str) -> bpy.types.Object:
    key = (pack, model)
    if key in _templates:
        return _templates[key]
    before = set(bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=str(ROOT / pack / f"{model}.obj"), forward_axis="NEGATIVE_Z", up_axis="Y")
    new = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    if len(new) > 1:
        with bpy.context.temp_override(active_object=new[0], selected_editable_objects=new):
            bpy.ops.object.join()
    obj = new[0]
    for c in list(obj.users_collection):  # a hidden template: only its copies are in the scene
        c.objects.unlink(obj)
    # origin at the base, centred: the model then stands where it is placed
    zs = [v.co.z for v in obj.data.vertices] or [0.0]
    xs = [v.co.x for v in obj.data.vertices] or [0.0]
    ys = [v.co.y for v in obj.data.vertices] or [0.0]
    shift = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, min(zs))
    for v in obj.data.vertices:
        v.co.x -= shift[0]
        v.co.y -= shift[1]
        v.co.z -= shift[2]
    obj["height"] = (max(zs) - min(zs)) or 1.0
    _templates[key] = obj
    return obj


def place(pack: str, model: str, name: str, location, height: float, rot_z: float = 0.0, col=None):
    """A copy of the model standing at `location`, scaled to `height` metres."""
    template = _template(pack, model)
    obj = template.copy()  # shares the mesh: hundreds of trees cost one
    obj.name = name
    s = height / float(template["height"])
    obj.scale = (s, s, s)
    obj.location = tuple(location)
    obj.rotation_euler = (0.0, 0.0, rot_z)
    (col or bpy.context.scene.collection).objects.link(obj)
    return obj
