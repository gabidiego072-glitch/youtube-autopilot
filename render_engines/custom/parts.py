"""Better-looking parts for the custom kits (Nov 24, after the owner: "mejorar gráficamente coches, choques, landing,
edificios"). Still code-made and toon (no realism), but with the details that make things read at a glance:

- car(): bevelled body, glass cabin with a roof, wheels with hubs, head/tail lights, bumpers (sedan, taxi, van).
- building(): bevelled tower with a window grid (some lit), a parapet, rooftop units and a ground-floor door.
- city(): many buildings with all their windows batched into a few meshes, so a whole city stays fast.
- landing(): a heavy landing: crater, crack, a dust ring rolling outward, flying rocks, a camera shake.
- crash(): a car hit: crumple, spin and roll along the hit, sparks, glass, smoke.

Every function takes Blender frames; nothing random without a seed, so all shards of a render see the same world.
"""

from __future__ import annotations

import math
import random

import bpy
from mathutils import Euler, Vector

from render_engines.core.blender.animation import key, set_interpolation
from render_engines.core.colors import hex_to_linear

# ---------------------------------------------------------------- basics


def mat(name: str, colour: str, rough: float = 0.6, emit: float = 0.0, metal: float = 0.0):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = hex_to_linear(colour)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit:
        b.inputs["Emission Color"].default_value = hex_to_linear(colour)
        b.inputs["Emission Strength"].default_value = emit
    m.diffuse_color = (*hex_to_linear(colour)[:3], 1.0)  # what the outline/solid views show
    return m


def _box(verts: list, faces: list, centre, size, base: bool = True) -> None:
    """Append a box (base at centre z when `base`) to the vertex and face lists."""
    x, y, z = centre
    sx, sy, sz = size
    z0 = z if base else z - sz / 2
    first = len(verts)
    for dz in (0.0, sz):
        for dx, dy in ((-sx / 2, -sy / 2), (sx / 2, -sy / 2), (sx / 2, sy / 2), (-sx / 2, sy / 2)):
            verts.append((x + dx, y + dy, z0 + dz))
    b = first
    faces += [
        (b, b + 3, b + 2, b + 1),  # bottom, facing down
        (b + 4, b + 5, b + 6, b + 7),  # top, facing up
        *[(b + i, b + (i + 1) % 4, b + 4 + (i + 1) % 4, b + 4 + i) for i in range(4)],
    ]


def _mesh_object(name: str, parts: list, link: bool = True):
    """parts: [(material, [(centre, size), ...])] -> one object, one material slot per part."""
    verts, faces, mats = [], [], []
    for slot, (_material, boxes) in enumerate(parts):
        before = len(faces)
        for centre, size in boxes:
            _box(verts, faces, centre, size)
        mats += [slot] * (len(faces) - before)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    for material, _ in parts:
        mesh.materials.append(material)
    for poly, slot in zip(mesh.polygons, mats, strict=True):
        poly.material_index = slot
    obj = bpy.data.objects.new(name, mesh)
    if link:
        bpy.context.scene.collection.objects.link(obj)
    return obj


def _bevel(obj, width: float, segments: int = 2) -> None:
    mod = obj.modifiers.new("bevel", "BEVEL")
    mod.width, mod.segments, mod.limit_method = width, segments, "ANGLE"


def _empty(name: str, location=(0, 0, 0)):
    e = bpy.data.objects.new(name, None)
    e.location = location
    bpy.context.scene.collection.objects.link(e)
    return e


# ---------------------------------------------------------------- cars

CAR_KINDS = {
    #         length, width, body h, cabin (len, h, offset back), colour
    "sedan": (4.3, 1.85, 0.62, (2.3, 0.62, 0.25), "#d63a2f"),
    "taxi": (4.4, 1.85, 0.62, (2.3, 0.62, 0.25), "#f6c21a"),
    "van": (5.0, 2.0, 1.25, (3.9, 0.75, 0.45), "#ecf0f1"),
}
_car_templates: dict = {}


def _car_body(kind: str, colour: str):
    """One shared mesh per kind and colour: copies of a car cost nothing."""
    tkey = (kind, colour)
    if tkey in _car_templates:
        return _car_templates[tkey]
    length, width, body_h, (cab_l, cab_h, back), _ = CAR_KINDS[kind]
    clear = 0.32  # ground clearance: the wheels show under the body
    paint = mat(f"car_paint_{kind}_{colour}", colour, rough=0.35)
    glass = mat("car_glass", "#22313f", rough=0.15)
    dark = mat("car_trim", "#2b2b2e", rough=0.8)
    head = mat("car_head", "#fff6d5", emit=2.0)
    tail = mat("car_tail", "#ff2b2b", emit=1.5)
    cab_x = -back
    cab_z = clear + body_h
    parts = [
        (
            paint,
            [((0, 0, clear), (length, width, body_h)), ((cab_x, 0, cab_z + cab_h - 0.06), (cab_l, width - 0.18, 0.08))],
        ),
        (glass, [((cab_x, 0, cab_z), (cab_l - 0.1, width - 0.22, cab_h - 0.06))]),
        (
            dark,
            [
                ((length / 2 + 0.04, 0, clear), (0.16, width + 0.04, 0.22)),  # bumpers
                ((-length / 2 - 0.04, 0, clear), (0.16, width + 0.04, 0.22)),
                ((0, 0, clear + body_h * 0.45), (length + 0.01, width + 0.02, 0.05)),  # side stripe
            ],
        ),
        (
            head,
            [((length / 2 + 0.01, s * (width / 2 - 0.3), clear + body_h * 0.6), (0.05, 0.38, 0.16)) for s in (1, -1)],
        ),
        (
            tail,
            [((-length / 2 - 0.01, s * (width / 2 - 0.28), clear + body_h * 0.6), (0.05, 0.32, 0.14)) for s in (1, -1)],
        ),
    ]
    if kind == "taxi":
        parts.append((mat("car_sign", "#ffffff", emit=0.6), [((cab_x, 0, cab_z + cab_h), (0.7, 0.3, 0.22))]))
    body = _mesh_object(f"car_tpl_{kind}_{colour}", parts, link=False)
    _bevel(body, 0.06)
    wheel = bpy.data.meshes.get("car_wheel_mesh")
    if wheel is None:
        bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.36, depth=0.26, rotation=(math.pi / 2, 0, 0))
        w = bpy.context.object
        w.data.materials.append(mat("car_tyre", "#1b1b1d", rough=0.9))
        wheel = w.data
        wheel.name = "car_wheel_mesh"
        bpy.data.objects.remove(w)
    _car_templates[tkey] = (body.data, wheel, length, width)
    return _car_templates[tkey]


def car(name: str, location, yaw: float = 0.0, kind: str = "sedan", colour: str | None = None):
    """A car on the ground at `location`, facing +x turned by `yaw` (radians). Returns its root empty; the body is
    root.children[0] and the wheels the rest (spin them with drive())."""
    kind = kind if kind in CAR_KINDS else "sedan"
    colour = colour or CAR_KINDS[kind][4]
    body_mesh, wheel_mesh, length, width = _car_body(kind, colour)
    root = _empty(name, location)
    root.rotation_euler = (0, 0, yaw)
    body = bpy.data.objects.new(f"{name}_body", body_mesh)
    bpy.context.scene.collection.objects.link(body)
    body.parent = root
    _bevel(body, 0.06)
    for i, (fx, fy) in enumerate(((1, 1), (1, -1), (-1, 1), (-1, -1))):
        w = bpy.data.objects.new(f"{name}_wheel{i}", wheel_mesh)
        bpy.context.scene.collection.objects.link(w)
        w.parent = root
        w.location = (fx * (length / 2 - 0.85), fy * (width / 2 + 0.02), 0.36)  # just out of the body: they show
    return root


def drive(root, start: int, end: int, distance: float) -> None:
    """Move a car forward along its facing between two frames, wheels turning to match."""
    yaw = root.rotation_euler.z
    a = Vector(root.location)
    b = a + Vector((math.cos(yaw), math.sin(yaw), 0)) * distance
    key(root, "location", start, tuple(a))
    key(root, "location", end, tuple(b))
    set_interpolation(root, "LINEAR", "location")
    for w in root.children[1:]:
        key(w, "rotation_euler", start, (0, 0, 0))
        key(w, "rotation_euler", end, (0, distance / 0.36, 0))
        set_interpolation(w, "LINEAR", "rotation_euler")


# ---------------------------------------------------------------- buildings

BUILDING_TONES = ["#d9cbb5", "#b8c4cf", "#e0a37a", "#9aa7b4", "#cf8f6b", "#c9b79c", "#8fa3a6"]


def _building_parts(x, y, w, d, h, rng, lit: float):
    """Boxes for one building, by role: body, trim (parapet + base), windows dark / lit, roof units, door."""
    out = {"body": [], "trim": [], "dark": [], "lit": [], "roof": [], "door": []}
    out["body"].append(((x, y, 0), (w, d, h)))
    out["trim"].append(((x, y, h), (w + 0.4, d + 0.4, 0.6)))  # parapet
    out["trim"].append(((x, y, 0), (w + 0.25, d + 0.25, 3.2)))  # ground-floor band
    floor_h, col_w = 3.2, 2.6
    floors = max(1, int((h - 4.0) / floor_h))
    for face in range(4):
        along = w if face % 2 == 0 else d
        cols = max(1, int((along - 1.0) / col_w))
        for f in range(floors):
            z = 4.0 + f * floor_h + 0.6
            for c in range(cols):
                t = (c + 0.5) / cols - 0.5
                if face == 0:
                    centre, size = (x + t * along, y - d / 2 - 0.06, z), (1.3, 0.1, 1.7)
                elif face == 2:
                    centre, size = (x + t * along, y + d / 2 + 0.06, z), (1.3, 0.1, 1.7)
                elif face == 1:
                    centre, size = (x + w / 2 + 0.06, y + t * along, z), (0.1, 1.3, 1.7)
                else:
                    centre, size = (x - w / 2 - 0.06, y + t * along, z), (0.1, 1.3, 1.7)
                out["lit" if rng.random() < lit else "dark"].append((centre, size))
    for _ in range(rng.randint(1, 3)):  # air units and a water tank on the roof
        ux, uy = x + rng.uniform(-w / 3, w / 3), y + rng.uniform(-d / 3, d / 3)
        out["roof"].append(((ux, uy, h + 0.6), (rng.uniform(1.5, 3), rng.uniform(1.5, 3), rng.uniform(1, 2.2))))
    out["door"].append(((x, y - d / 2 - 0.08, 0), (2.2, 0.12, 2.6)))
    return out


def _building_materials(tone: int):
    return {
        "body": mat(f"bld_body{tone}", BUILDING_TONES[tone % len(BUILDING_TONES)], rough=0.85),
        "trim": mat("bld_trim", "#6f6a66", rough=0.9),
        "dark": mat("bld_glass", "#33475c", rough=0.2),
        "lit": mat("bld_lit", "#ffd98a", emit=1.2),
        "roof": mat("bld_roof", "#9a9ea4", rough=0.9),
        "door": mat("bld_door", "#3b2a1e", rough=0.8),
    }


def building(name: str, x: float, y: float, w: float, d: float, h: float, tone: int = 0, seed: int = 0, lit=0.12):
    """One building (base at z 0, the door facing -y). Returns the object."""
    rng = random.Random(seed)
    parts = _building_parts(x, y, w, d, h, rng, lit)
    mats = _building_materials(tone)
    obj = _mesh_object(name, [(mats[k], v) for k, v in parts.items() if v])
    _bevel(obj, 0.08, 1)
    return obj


def city(name: str, blocks, seed: int = 0, lit: float = 0.12) -> None:
    """blocks: [(x, y, w, d, h), ...]. All buildings batched by tone and role (fast for thousands)."""
    rng = random.Random(seed)
    batches: dict = {}
    for x, y, w, d, h in blocks:
        tone = rng.randrange(len(BUILDING_TONES))
        for role, boxes in _building_parts(x, y, w, d, h, rng, lit).items():
            batches.setdefault((tone if role == "body" else -1, role), []).extend(boxes)
    for (tone, role), boxes in batches.items():
        mats = _building_materials(max(tone, 0))
        _mesh_object(f"{name}_{role}{tone if tone >= 0 else ''}", [(mats[role], boxes)])


# ---------------------------------------------------------------- landing


def _soft(name: str, colour: str):
    from render_engines.cinematic.effects import soft_puff_material

    return soft_puff_material(name, colour, 0.85)


def _sphere(name: str, radius: float, material, location):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=radius, location=location)
    s = bpy.context.object
    s.name = name
    s.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return s


def _appear(obj, frame: int) -> None:
    key(obj, "scale", max(0, frame - 1), (0.001, 0.001, 0.001))


def landing(name: str, at, frame: int, fps: int, size: float = 4.0, seed: int = 0, ground: str = "#8a7f72") -> None:
    """A heavy landing at `at` on `frame`: a crater, a ring of dust rolling outward, rocks flying out."""
    rng = random.Random(seed)
    at = Vector(at)
    crater = _mesh_object(
        f"{name}_crater", [(mat(f"{name}_crater", "#3d3833", rough=1.0), [((0, 0, 0), (2, 2, 0.04))])]
    )
    crater.location = at + Vector((0, 0, 0.01))
    _appear(crater, frame)
    key(crater, "scale", frame, (0.2, 0.2, 1))
    key(crater, "scale", frame + 3, (size * 0.5, size * 0.5, 1))
    # the dust ring: puffs born on the impact that roll outward low over the ground, grow and vanish
    dust = _soft(f"{name}_dust", "#d8cbb5")
    n = 18
    life = int(fps * 1.4)
    for i in range(n):
        a = i / n * 2 * math.pi + rng.uniform(-0.1, 0.1)
        p = _sphere(f"{name}_dust{i}", size * 0.12, dust, at)
        p.visible_shadow = False
        _appear(p, frame)
        key(p, "location", frame, tuple(at + Vector((0, 0, size * 0.05))))
        key(p, "scale", frame, (0.4, 0.4, 0.4))
        reach = size * rng.uniform(1.6, 2.2)
        key(p, "location", frame + life, tuple(at + Vector((math.cos(a) * reach, math.sin(a) * reach, size * 0.25))))
        key(p, "scale", frame + life, (2.4, 2.4, 1.6))
        key(p, "scale", frame + life + 1, (0.001, 0.001, 0.001))
    # rocks: thrown up and out, falling back under gravity
    rock = mat(f"{name}_rock", ground, rough=1.0)
    g = 9.81
    for i in range(14):
        r = _mesh_object(f"{name}_rock{i}", [(rock, [((0, 0, -0.5), (1, 1, 1))])])
        s = size * rng.uniform(0.03, 0.08)
        a, up, out = rng.uniform(0, 2 * math.pi), rng.uniform(4, 8), rng.uniform(2, 5)
        _appear(r, frame)
        for k in range(8):
            t = k / 7 * (2 * up / g)
            p = at + Vector((math.cos(a) * out * t, math.sin(a) * out * t, max(0.0, up * t - g * t * t / 2) + s))
            key(r, "location", frame + int(t * fps), tuple(p))
            key(r, "rotation_euler", frame + int(t * fps), (t * 9, t * 7, 0))
        key(r, "scale", frame, (s, s, s))


def shake(cam, frame: int, fps: int, strength: float = 0.25, seconds: float = 0.5, seed: int = 0) -> None:
    """Camera shake around its current (local) location, dying out."""
    rng = random.Random(seed)
    base = Vector(cam.location)
    steps = max(3, int(seconds * fps / 2))
    key(cam, "location", frame - 1, tuple(base))
    for k in range(steps):
        fall = 1 - k / steps
        off = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))) * strength * fall
        key(cam, "location", frame + 2 * k, tuple(base + off))
    key(cam, "location", frame + 2 * steps, tuple(base))


# ---------------------------------------------------------------- crash


def crash(name: str, car_root, frame: int, fps: int, direction=(1, 0, 0), force: float = 1.0, seed: int = 0) -> None:
    """The car is hit on `frame`: it crumples, gets thrown along `direction` spinning and rolling, and comes to rest
    on its side; sparks, glass and smoke burst from the hit."""
    rng = random.Random(seed)
    d = Vector(direction).normalized()
    start = Vector(car_root.location)
    rot = Euler(car_root.rotation_euler)
    key(car_root, "location", frame, tuple(start))
    key(car_root, "rotation_euler", frame, tuple(rot))
    fly = int(fps * 0.9 * force)
    for k in range(1, 7):
        t = k / 6
        p = start + d * (6 * force * (1 - (1 - t) ** 2))
        p.z = start.z + 2.2 * force * 4 * t * (1 - t)
        key(car_root, "location", frame + int(fly * t), tuple(p))
        key(car_root, "rotation_euler", frame + int(fly * t), (rot.x + math.pi / 2 * t, rot.y, rot.z + 1.4 * force * t))
    body = car_root.children[0]
    key(body, "scale", frame, (1, 1, 1))
    key(body, "scale", frame + 2, (0.82, 1.06, 0.9))  # crumpled for good
    hit = start + Vector((0, 0, 0.8))
    spark = mat("crash_spark", "#ffb02e", emit=6.0)
    glass = mat("crash_glass", "#bfe6ff", rough=0.1)
    for i in range(22):
        is_spark = i < 12
        s = _mesh_object(f"{name}_bit{i}", [(spark if is_spark else glass, [((0, 0, 0), (1, 1, 1))])])
        size = 0.06 if is_spark else rng.uniform(0.08, 0.16)
        a = math.atan2(d.y, d.x) + rng.uniform(-1.2, 1.2)
        v = rng.uniform(4, 9) * (1.3 if is_spark else 1)
        up = rng.uniform(2, 5)
        _appear(s, frame)
        key(s, "scale", frame, (size, size, size))
        life = int(fps * (0.35 if is_spark else 0.8))
        for k in range(5):
            t = k / 4 * life / fps
            p = hit + Vector((math.cos(a) * v * t, math.sin(a) * v * t, max(-0.75, up * t - 4.9 * t * t)))
            key(s, "location", frame + int(t * fps), tuple(p))
        if is_spark:
            key(s, "scale", frame + life + 1, (0.001, 0.001, 0.001))
    from render_engines.cinematic.effects import puffs

    rest = start + d * 6 * force
    puffs(f"{name}_smoke", (rest.x, rest.y, 0.8), frame + fly, frame + fly + fps * 3, fps, count=10, rise=4, seed=seed)
