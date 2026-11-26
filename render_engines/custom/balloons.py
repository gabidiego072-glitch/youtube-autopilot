"""'¿Qué pasaría si llenaras tu casa de GLOBOS?' (Nov 26, the owner: "más hipotéticos, como la rampa, y no solo
coches"). ONE house, ONE street, ONE trip, each step caused by the last:

  one balloon -> hundreds out of the windows -> the house creaks and lifts -> past the neighbours -> over the town
  -> through the clouds -> a plane -> the thin air swells the balloons -> they pop -> the house falls -> splash, in
  the town lake.

params: stage (one of STAGES). Built from render_engines/custom/parts.py.
"""

from __future__ import annotations

import math
import random

import bpy
from mathutils import Vector

from render_engines.core.blender.animation import key
from render_engines.core.colors import hex_to_linear
from render_engines.custom import parts as P
from render_engines.custom.ramp import _camera, _hero

SEED = 2611
STAGES = (
    "hook", "one", "fill", "creak", "liftoff", "town", "clouds", "plane", "swell", "pop", "fall", "splash",
)  # fmt: skip
W, D, H = 12.0, 10.0, 6.0  # your house: walls; the roof ridge is at H + 4
CLUSTER = Vector((0.0, 0.0, 27.0))  # centre of the balloon bunch over the house (in the house's own space)
STREET_Y = 18.0
LAKE = Vector((150.0, 210.0, 0.0))
COLOURS = ["#e74c3c", "#f1c40f", "#3498db", "#2ecc71", "#9b59b6", "#ff7eb6", "#ff9f1a"]
HAZE = "#d4e4ea"
SKY = {"low": "#9fd3f5", "mid": "#7fbdf0", "high": "#4f8fdc", "thin": "#2f5fb0"}


# ---------------------------------------------------------------- the world


def _ground(rng: random.Random) -> None:
    P._mesh_object("ground", [(P.mat("grass", "#7cc46a", 1.0), [((0, 0, -0.12), (12000, 12000, 0.1))])])
    for k, (size, tone) in enumerate(((20000, "#a6c9a0"), (32000, "#bcd5c0"), (60000, "#cfe0dc"))):
        P._mesh_object(f"haze{k}", [(P.mat(f"haze{k}", tone, 1.0), [((0, 0, -0.2 - 0.1 * k), (size, size, 0.05))])])
    road, walk, line = P.mat("road", "#4f5257", 0.9), P.mat("walk", "#c9c3b8", 0.9), P.mat("line", "#f2f2f2", 0.9)
    P._mesh_object("road", [(road, [((0, STREET_Y, -0.03), (1600, 8, 0.03))])])
    P._mesh_object("walks", [(walk, [((0, STREET_Y + s * 5.5, 0), (1600, 3, 0.15)) for s in (1, -1)])])
    P._mesh_object("lines", [(line, [((x, STREET_Y, 0), (2.6, 0.18, 0.02)) for x in range(-400, 400, 7)])])
    lake = P.mat("lake", "#2e86c1", rough=0.15)
    shore = P.mat("shore", "#e5d3a1", rough=1.0)
    P._mesh_object("lake_shore", [(shore, [((LAKE.x, LAKE.y, -0.09), (104, 84, 0.08))])])
    P._mesh_object("lake", [(lake, [((LAKE.x, LAKE.y, -0.06), (96, 76, 0.07))])])
    # neighbours along the street, a grid of streets with houses around, fields and a town far away
    lots = []
    for x in range(-200, 220, 20):
        if abs(x) > 12:
            lots.append((x, 0, rng.uniform(9, 12), rng.uniform(8, 10), rng.uniform(5, 6.5), 1))
        lots.append((x, 2 * STREET_Y, rng.uniform(9, 12), rng.uniform(8, 10), rng.uniform(5, 6.5), -1))
    for gy in range(80, 520, 40):
        for gx in range(-400, 420, 22):
            if (Vector((gx, gy, 0)) - LAKE).length < 70:
                continue
            lots.append((gx, gy, rng.uniform(9, 12), rng.uniform(8, 10), rng.uniform(5, 7), 1))
    for gy in range(-60, -420, -40):
        for gx in range(-400, 420, 22):
            lots.append((gx, gy, rng.uniform(9, 12), rng.uniform(8, 10), rng.uniform(5, 7), -1))
    P.houses("hood", lots, seed=SEED)
    streets = [((0, gy - 20, -0.02), (900, 6, 0.02)) for gy in range(80, 560, 40)]
    streets += [((0, gy + 20, -0.02), (900, 6, 0.02)) for gy in range(-60, -460, -40)]
    P._mesh_object("streets", [(road, streets)])
    trees = [
        ((x + rng.uniform(-2, 2), STREET_Y + s * 8, 0), (0.5, 0.5, 3.2)) for x in range(-200, 220, 14) for s in (1, -1)
    ]
    trees = [t for t in trees if abs(t[0][0]) > 9]
    crowns = [((t[0][0], t[0][1], 3.0), (3.2, 3.2, 3.0)) for t in trees]
    P._mesh_object("trees", [(P.mat("trunk", "#7a4f2a"), trees), (P.mat("leaf", "#3f9b3f"), crowns)])
    fields = ["#9ccc65", "#c5b358", "#7cb342", "#d4c27a", "#8fbf5a"]
    patches = {k: [] for k in range(len(fields))}
    for _ in range(900):  # what the ground looks like from a kilometre up
        r, a = rng.uniform(700, 9000), rng.uniform(0, 2 * math.pi)
        s = rng.uniform(250, 900)
        patches[rng.randrange(len(fields))].append(
            ((r * math.cos(a), r * math.sin(a), -0.06 + rng.random() * 0.01), (s, s * rng.uniform(0.6, 1.4), 0.02))
        )
    P._mesh_object("fields", [(P.mat(f"field{k}", c, 1.0), patches[k]) for k, c in enumerate(fields)])
    towns = []
    for _ in range(40):
        r, a = rng.uniform(1500, 8000), rng.uniform(0, 2 * math.pi)
        tx, ty = r * math.cos(a), r * math.sin(a)
        towns += [
            ((tx + rng.uniform(-90, 90), ty + rng.uniform(-90, 90), 0), (14, 14, rng.uniform(5, 30))) for _ in range(12)
        ]
    P._mesh_object("towns", [(P.mat("town", "#c9b79c", 0.9), towns)])


def _house():
    """Your house on a rig (everything that flies): walls, roof, porch, windows, chimney."""
    rig = P._empty("home")
    wall, roof = P.mat("my_wall", "#f6e7cf", rough=0.9), P.mat("my_roof", "#c0392b", rough=0.8)
    glass, door = P.mat("bld_glass", "#33475c", rough=0.2), P.mat("bld_door", "#3b2a1e")
    trim = P.mat("my_trim", "#ffffff", rough=0.7)
    body = P._mesh_object(
        "my_house",
        [
            (wall, [((0, 0, 0), (W, D, H))]),
            (
                glass,
                [((dx, D / 2 + 0.05, 2.4), (2.4, 0.12, 2.0)) for dx in (-3.6, 3.6)]
                + [((W / 2 + 0.05, dy, 2.4), (0.12, 2.4, 2.0)) for dy in (-2.2, 2.2)],
            ),
            (door, [((0, D / 2 + 0.06, 0), (1.8, 0.14, 3.0))]),
            (trim, [((0, D / 2 + 1.6, 0), (6.0, 3.0, 0.4))]),  # the porch
            (P.mat("house_brick", "#8e4b32"), [((3.2, -1.5, H + 1), (1.4, 1.4, 4.4))]),
            (P.mat("dirt", "#6d5a44", 1.0), [((0, 0, -0.9), (W + 0.4, D + 0.4, 0.9))]),  # the foundations
        ],
    )
    body.parent = rig
    verts = [(-W / 2 - 0.6, -D / 2 - 0.6, H), (W / 2 + 0.6, -D / 2 - 0.6, H), (W / 2 + 0.6, D / 2 + 0.6, H),
             (-W / 2 - 0.6, D / 2 + 0.6, H), (-W / 2 - 0.6, 0, H + 4), (W / 2 + 0.6, 0, H + 4)]  # fmt: skip
    mesh = bpy.data.meshes.new("my_roof")
    mesh.from_pydata(verts, [], [(0, 1, 5, 4), (3, 4, 5, 2), (0, 4, 3), (1, 2, 5), (0, 3, 2, 1)])
    mesh.materials.append(roof)
    r = bpy.data.objects.new("my_roof", mesh)
    bpy.context.scene.collection.objects.link(r)
    r.parent = rig
    return rig


def _bunch(rig, rng: random.Random, keep: float = 1.0, count: int = 420) -> list:
    """The balloons over the roof, tied by strings to the ridge. Returns [(object, home position)]."""
    mesh = P.ball_mesh("balloon", 1.0, 1.18)
    mats = [P.mat(f"balloon{k}", c, rough=0.25) for k, c in enumerate(COLOURS)]
    out = []
    for i in range(count):
        while True:
            p = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)))
            if p.length <= 1:
                break
        pos = CLUSTER + Vector((p.x * 14, p.y * 12, p.z * 9))
        if rng.random() > keep:
            continue
        b = P.instance(f"bal{i}", mesh, mats[i % len(mats)], pos, rng.uniform(0.9, 1.25), parent=rig)
        out.append((b, pos))
    string = P.mat("string", "#f4f4f4", rough=0.8)
    for i in range(18):
        a = Vector((rng.uniform(-W / 2 + 1, W / 2 - 1), rng.uniform(-0.4, 0.4), H + 4))
        b = CLUSTER + Vector((rng.uniform(-9, 9), rng.uniform(-7, 7), -8))
        P.rope(f"str{i}", [a, a.lerp(b, 0.5) + Vector((0, 0, -0.4)), b], 0.05, string).parent = rig
    return out


def _sky(scene, level: str) -> None:
    world = scene.world or bpy.data.worlds.new("bl_world")
    scene.world = world
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    coord, split, ramp = (
        nodes.new("ShaderNodeTexCoord"),
        nodes.new("ShaderNodeSeparateXYZ"),
        nodes.new("ShaderNodeValToRGB"),
    )
    links.new(coord.outputs["Generated"], split.inputs[0])
    links.new(split.outputs["Z"], ramp.inputs["Fac"])
    ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[1].position = 0.0, 0.35
    ramp.color_ramp.elements[0].color = hex_to_linear(HAZE)  # a pale band on the horizon, like real air
    ramp.color_ramp.elements[1].color = hex_to_linear(SKY[level])
    links.new(ramp.outputs["Color"], nodes["Background"].inputs[0])
    sun = bpy.data.objects.new("bl_sun", bpy.data.lights.new("bl_sun", "SUN"))
    sun.data.energy = 3.6
    sun.rotation_euler = (math.radians(45), 0, math.radians(35))
    scene.collection.objects.link(sun)


def _fly(rig, f0: int, f1: int, a, b, tilt=(0.0, 0.0)) -> None:
    key(rig, "location", f0, tuple(a))
    key(rig, "location", f1, tuple(b))
    key(rig, "rotation_euler", f0, (tilt[0], 0, 0))
    key(rig, "rotation_euler", f1, (tilt[1], 0, 0))


def _sway(rig, f0: int, f1: int, at, amp: float = 0.04) -> None:
    for k, f in enumerate(range(f0, f1 + 1, 18)):
        key(rig, "rotation_euler", f, (amp * math.sin(k * 1.7), amp * 0.6 * math.cos(k * 1.3), 0))
    key(rig, "location", f0, tuple(at))
    key(rig, "location", f1, tuple(Vector(at) + Vector((2.0, 1.0, 1.5))))


def _you(rig, frame: int, wave: bool = True):
    """You, on the porch, riding with the house."""
    hero = _hero((1.8, D / 2 + 1.8, 0.4), math.pi / 2, frame)
    hero.root.parent = rig
    if wave:
        hero.wave(frame + 6, frame + 60, "R")
    return hero


def _pop(obj, frame: int) -> None:
    s = obj.scale[0]
    key(obj, "scale", frame - 2, (s, s, s))
    key(obj, "scale", frame, (s * 1.3, s * 1.3, s * 1.3))
    key(obj, "scale", frame + 1, (0.001, 0.001, 0.001))


def _plane(f0: int, f1: int, x: float, y: float, z: float) -> None:
    white, blue = P.mat("plane_white", "#f4f6f8", rough=0.4), P.mat("plane_blue", "#1f5fae", rough=0.4)
    glass = P.mat("bld_glass", "#33475c", rough=0.2)
    plane = P._mesh_object(
        "plane",
        [
            (white, [((0, 0, -2), (44, 5, 5)), ((-2, 0, -0.6), (9, 38, 0.6)), ((-20, 0, 1), (6, 0.6, 8))]),
            (blue, [((0, 0, -2.2), (44.2, 5.1, 1.2)), ((-20, 0, 7), (6.2, 0.7, 2))]),
            (glass, [((x, 2.52, 0.8), (1.0, 0.1, 0.9)) for x in range(-16, 18, 3)]),
            (P.mat("engine", "#9aa3ad", metal=0.5), [((-2, s * 9, -2.6), (5, 2.6, 2.6)) for s in (1, -1)]),
        ],
    )
    key(plane, "location", f0, (x - 260, y, z))  # crosses right behind the house mid-scene
    key(plane, "location", f1, (x + 300, y, z - 6))


# ---------------------------------------------------------------- the scenes


def build(spec: dict, ctx, scene, params: dict) -> None:
    stage = params.get("stage", "one")
    stage = stage if stage in STAGES else "one"
    f0, f1 = ctx.frame_start, ctx.frame_end
    fps = scene.render.fps or 24

    def at(fr: float) -> int:
        return f0 + int((f1 - f0) * fr)

    rng = random.Random(SEED)
    level = {"plane": "high", "swell": "thin", "pop": "thin", "fall": "high", "hook": "mid", "clouds": "mid"}
    _sky(scene, level.get(stage, "low"))
    _ground(rng)
    rig = _house()
    keep = {"one": 0.0, "fall": 0.22, "splash": 0.18}.get(stage, 1.0)
    bunch = _bunch(rig, random.Random(SEED + 1), keep) if keep else []
    if stage in ("clouds", "hook", "fall", "plane"):
        P.clouds("cl", (0, 0), 1400, 260, 300, 360, seed=SEED + 2)

    if stage == "one":
        # you, in front of your house, with ONE balloon
        rig.location = (0, 0, 0)
        hero = _hero((3.0, D / 2 + 4.0, 0.18), math.pi * 0.45, f0)
        hero.raise_arm(f0, f0 + 8, "R", hold=200)
        b = P.instance("first", P.ball_mesh("balloon", 1.0, 1.18), P.mat("balloon0", COLOURS[0], rough=0.25),
                       (3.4, D / 2 + 4.0, 5.2), 0.9)  # fmt: skip
        P.rope("first_str", [(3.4, D / 2 + 4.0, 4.4), (3.3, D / 2 + 4.0, 2.9)], 0.03, P.mat("string", "#f4f4f4"))
        key(b, "location", f0, (3.4, D / 2 + 4.0, 5.2))
        key(b, "location", f1, (3.5, D / 2 + 4.0, 5.5))
        _camera(scene, (9, STREET_Y + 3.5, 2.4), (2.0, 7, 3.6), 26, f0, f1, 0.1)

    elif stage == "fill":
        # balloons pour out of the windows and the chimney and bunch up over the roof
        exits = [Vector((dx, D / 2 + 0.5, 3.4)) for dx in (-3.6, 3.6)] + [Vector((3.2, -1.5, H + 5.6))]
        order = sorted(bunch, key=lambda bp: bp[1].z)
        for i, (b, home) in enumerate(order):
            s = b.scale[0]
            fa = f0 + int((f1 - f0) * 0.85 * i / max(1, len(order)))
            src = exits[i % len(exits)]
            key(b, "scale", fa - 1, (0.001, 0.001, 0.001))
            key(b, "scale", fa, (s * 0.4, s * 0.4, s * 0.4))
            key(b, "location", fa, tuple(src))
            key(b, "location", fa + int(fps * 0.9), tuple(home))
            key(b, "scale", fa + int(fps * 0.9), (s, s, s))
        _you(rig, f0, wave=False)
        _camera(scene, (13, STREET_Y + 5, 5), (0, 0, 15), 18, f0, f1, 0.04)

    elif stage == "creak":
        # the house shudders and tears off its foundations
        for k, f in enumerate(range(f0, at(0.55), 3)):
            key(rig, "location", f, (0.08 * (-1) ** k, 0, 0.04 * k))
        key(rig, "location", at(0.75), (0, 0, 1.6))
        key(rig, "location", f1, (0, 0, 2.6))
        P._mesh_object("hole", [(P.mat("pit", "#3d3226", 1.0), [((0, 0, -0.02), (W + 0.6, D + 0.6, 0.03))])])
        dust = P._soft("creak_dust", "#d8cbb5")
        for i in range(16):
            a = i / 16 * 2 * math.pi
            p = P._sphere(f"cd{i}", 1.0, dust, (math.cos(a) * 7, math.sin(a) * 6, 0.3))
            p.visible_shadow = False
            key(p, "scale", f0, (0.001, 0.001, 0.001))
            key(p, "scale", at(0.45), (0.3, 0.3, 0.3))
            key(p, "scale", f1, (2.2, 2.2, 1.2))
            key(p, "location", f1, (math.cos(a) * 11, math.sin(a) * 9, 1.4))
        _you(rig, f0, wave=False).raise_arm(at(0.5), at(0.6), "L", hold=40)
        _camera(scene, (7, STREET_Y + 2, 1.2), (0, 2, 3.5), 22, f0, f1, 0.05)

    elif stage == "liftoff":
        _fly(rig, f0, f1 + int(fps * 0.5), (0, 0, 3), (4, 2, 40))
        _you(rig, f0)
        for i, x in enumerate((-20, 20)):  # the neighbours look up
            n = _hero((x + 2, STREET_Y - 5.5, 0.18), math.pi / 2, f0)
            n.look_at(f0, (0, 0, 30))
            n.raise_arm(f0 + 10 + 6 * i, f0 + 18 + 6 * i, "R", hold=40)
        _camera(scene, (-14, STREET_Y + 9, 2.0), (2, 0, 20), 18, f0, f1, 0.03)

    elif stage == "town":
        _fly(rig, f0, f1, (20, 30, 120), (55, 70, 160))
        _you(rig, f0)
        _camera(scene, (60, 80, 30), (0, 0, -40), 22, f0, f1, follow=rig)

    elif stage == "clouds":
        _fly(rig, f0, f1, (60, 80, 290), (70, 100, 370), (0.02, -0.03))
        _you(rig, f0, wave=False)
        _camera(scene, (36, 46, 4), (0, 0, 14), 22, f0, f1, follow=rig)

    elif stage == "hook":
        _sway(rig, f0, f1, (80, 110, 430))
        _you(rig, f0)
        _camera(scene, (30, 40, 2), (0, 0, 15), 22, f0, f1, follow=rig)

    elif stage == "plane":
        _sway(rig, f0, f1, (90, 120, 900))
        _you(rig, f0, wave=False).raise_arm(at(0.35), at(0.45), "R", hold=60)
        _plane(at(0.05), f1 + int(fps * 0.4), 92, 120 - 22, 908)
        _camera(scene, (44, 58, 4), (0, 0, 12), 24, f0, f1, follow=rig)

    elif stage == "swell":
        _sway(rig, f0, f1, (100, 130, 1500), 0.02)
        for b, _ in bunch:
            s = b.scale[0]
            key(b, "scale", f0, (s, s, s))
            key(b, "scale", f1, (s * 1.45, s * 1.45, s * 1.45))
        _you(rig, f0, wave=False)
        _camera(scene, (24, 32, 26), (0, 0, 24), 24, f0, f1, follow=rig)

    elif stage == "pop":
        _sway(rig, f0, f1, (100, 130, 1500), 0.0)
        key(rig, "rotation_euler", at(0.5), (0, 0, 0))
        key(rig, "rotation_euler", f1, (0.18, -0.12, 0))
        r = random.Random(SEED + 5)
        for b, _ in bunch:
            s = b.scale[0] * 1.45
            b.scale = (s, s, s)
            if r.random() < 0.78:
                _pop(b, at(r.uniform(0.15, 0.98)))
        _you(rig, f0, wave=False).raise_arm(at(0.3), at(0.4), "L", hold=60)
        _camera(scene, (24, 32, 26), (0, 0, 22), 24, f0, f1, follow=rig)

    elif stage == "fall":
        _fly(rig, f0, f1, (120, 160, 520), (128, 170, 250), (0.25, 0.4))
        _you(rig, f0, wave=False).raise_arm(f0, f0 + 4, "R", hold=200)
        cam = _camera(scene, (34, 40, -22), (0, 0, 8), 20, f0, f1, follow=rig)
        P.shake(cam, f0 + 2, fps, strength=0.15, seconds=float(f1 - f0) / fps)

    elif stage == "splash":
        hit = at(0.3)
        _fly(rig, f0 - int(fps * 0.6), hit, (LAKE.x, LAKE.y, 40), (LAKE.x, LAKE.y, -1.6), (0.2, 0.0))
        key(rig, "location", f1, (LAKE.x + 1, LAKE.y + 0.5, -1.2))
        water = P._soft("splash", "#d6eefc")
        r = random.Random(SEED + 9)
        for i in range(26):
            a = i / 26 * 2 * math.pi
            p = P._sphere(f"sp{i}", 1.0, water, (LAKE.x, LAKE.y, 0))
            p.visible_shadow = False
            up = r.uniform(5, 14)
            key(p, "scale", hit - 1, (0.001, 0.001, 0.001))
            key(p, "scale", hit, (1.2, 1.2, 1.2))
            key(p, "location", hit, (LAKE.x + math.cos(a) * 6, LAKE.y + math.sin(a) * 5, 0.5))
            key(p, "location", hit + int(fps * 0.6), (LAKE.x + math.cos(a) * 13, LAKE.y + math.sin(a) * 11, up))
            key(p, "scale", hit + int(fps * 0.6), (2.0, 2.0, 2.0))
            key(p, "location", hit + int(fps * 1.2), (LAKE.x + math.cos(a) * 16, LAKE.y + math.sin(a) * 14, 0))
            key(p, "scale", hit + int(fps * 1.2), (0.001, 0.001, 0.001))
        _you(rig, f0, wave=False).wave(at(0.6), f1, "R")
        cam = _camera(scene, (LAKE.x + 34, LAKE.y - 44, 9), (LAKE.x, LAKE.y, 6), 24, f0, f1, 0.05)
        P.shake(cam, hit, fps, strength=0.3)

    if params.get("outlines") is False:
        scene.render.use_freestyle = False
