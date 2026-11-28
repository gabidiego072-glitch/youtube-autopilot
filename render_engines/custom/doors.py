"""'What if every door led somewhere RANDOM?' (Nov 28; the owner: "haz lo que veas"). ONE kid late for school, and
every door they open drops them somewhere else, each one stranger than the last:

  your bedroom door -> a beach -> a snowy mountain -> a jungle -> a desert -> the roof of a skyscraper -> the Moon ->
  and the last door finally opens at school... on a Saturday.

params: stage (one of STAGES). Each place is a small set far from the others; the rooftop uses the elevator video's
tower in the ramp city, the school is the zipline video's. Built from render_engines/custom/parts.py.
"""

from __future__ import annotations

import math
import random

import bmesh
import bpy
from mathutils import Vector

from render_engines.core.blender.animation import key
from render_engines.core.colors import hex_to_linear
from render_engines.custom import balloons as B
from render_engines.custom import parts as P
from render_engines.custom.ramp import _camera, _hero

SEED = 2814
STAGES = ("hook", "room", "beach", "snow", "jungle", "desert", "rooftop", "moon", "school")
SETS = {
    "room": Vector((5000.0, 0.0, 0.0)),
    "beach": Vector((6000.0, 0.0, 0.0)),
    "snow": Vector((7000.0, 0.0, 0.0)),
    "jungle": Vector((8000.0, 0.0, 0.0)),
    "desert": Vector((9000.0, 0.0, 0.0)),
    "moon": Vector((10000.0, 0.0, 0.0)),
}


def _flat_sky(scene, colour: str, strength: float = 1.0) -> None:
    world = scene.world or bpy.data.worlds.new("dr_world")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = hex_to_linear(colour)
    bg.inputs[1].default_value = strength


def _sun(energy: float = 3.6, angle=(48, 0, 30)) -> None:
    sun = bpy.data.objects.new("dr_sun", bpy.data.lights.new("dr_sun", "SUN"))
    sun.data.energy = energy
    sun.rotation_euler = tuple(math.radians(a) for a in angle)
    bpy.context.scene.collection.objects.link(sun)


def _door(name: str, at, yaw: float = 0.0, open_frame: int | None = None, glow: str = "#fff3c4"):
    """A free-standing door: white frame, blue leaf swinging open, light pouring out of the doorway.
    The doorway faces +y (before yaw). Returns the root."""
    root = P._empty(name, tuple(at))
    root.rotation_euler = (0, 0, yaw)
    frame = P._mesh_object(
        f"{name}_frame",
        [(P.mat("door_frame", "#f7f7f2", 0.6), [((-0.62, 0, 0), (0.16, 0.24, 2.3)), ((0.62, 0, 0), (0.16, 0.24, 2.3)),
                                                 ((0, 0, 2.22), (1.4, 0.24, 0.16))])],
    )  # fmt: skip
    frame.parent = root
    light = P._mesh_object(
        f"{name}_light", [(P.mat(f"glow_{glow}", glow, emit=3.0), [((0, -0.02, 0.02), (1.08, 0.02, 2.18))])]
    )
    light.parent = root
    hinge = P._empty(f"{name}_hinge")
    hinge.parent = root
    hinge.location = (-0.54, 0.1, 0)
    knob = P.mat("door_knob", "#f6c21a", 0.3, metal=0.8)
    leaf = P._mesh_object(
        f"{name}_leaf",
        [(P.mat("door_leaf", "#2f6db5", 0.5), [((0.54, 0, 0.02), (1.06, 0.08, 2.18))]),
         (knob, [((0.95, 0.07, 1.0), (0.08, 0.08, 0.08))])],
    )  # fmt: skip
    leaf.parent = hinge
    if open_frame is None:
        hinge.rotation_euler = (0, 0, math.radians(-100))
    else:
        key(hinge, "rotation_euler", open_frame - 1, (0, 0, 0))
        key(hinge, "rotation_euler", open_frame + 8, (0, 0, math.radians(-100)))
        P._appear(light, open_frame)
        key(light, "scale", open_frame, (1, 1, 1))
    return root


def _step_out(door_at, f0: int, fps: int, out: float = 3.2, yaw: float = 0.0, start: float = 0.12, frames: int = 30):
    """You walk out of the doorway into the new place."""
    a = Vector(door_at) + Vector((0, -0.4, 0))
    b = Vector(door_at) + Vector((0, out, 0))
    hero = _hero(a, math.pi / 2, f0)
    if a.z:  # walk() keys the feet at z = 0: lift the whole walk onto the roof
        lift = P._empty("walk_level", (0, 0, a.z))
        hero.root.parent = lift
    s = f0 + int(fps * start * 4)
    hero.walk(s, s + frames, (a.x, a.y), (b.x, b.y), fps)
    return hero


def _ground(name: str, centre, colour: str, size: float = 2000.0) -> None:
    P._mesh_object(name, [(P.mat(name, colour, rough=1.0), [((centre.x, centre.y, -0.12), (size, size, 0.1))])])


def _cones(name: str, items, material, segments: int = 8):
    """Cones (pines, mountains, dunes): items = [(x, y, z, radius, height)] in one mesh."""
    bm = bmesh.new()
    for x, y, z, r, h in items:
        geom = bmesh.ops.create_cone(bm, cap_ends=True, segments=segments, radius1=r, radius2=0.0, depth=h)
        bmesh.ops.translate(bm, verts=geom["verts"], vec=(x, y, z + h / 2))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(material)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _discs(name: str, items, material, segments: int = 24):
    """Flat round discs (crater floors and rims): items = [(x, y, z, radius, thickness)]."""
    bm = bmesh.new()
    for x, y, z, r, t in items:
        geom = bmesh.ops.create_cone(bm, cap_ends=True, segments=segments, radius1=r, radius2=r, depth=t)
        bmesh.ops.translate(bm, verts=geom["verts"], vec=(x, y, z + t / 2))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(material)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _beach(o, rng) -> None:
    _flat_sky(bpy.context.scene, "#8fd3ff")
    _sun(4.0, (55, 0, 140))
    _ground("sand", o, "#f2d79b")
    P._mesh_object("sea", [(P.mat("sea", "#1e9bd7", rough=0.1), [((o.x, o.y - 520, -0.08), (2000, 1000, 0.1))])])
    P._mesh_object("foam", [(P.mat("foam", "#ffffff", 0.6), [((o.x, o.y - 19.6, -0.07), (2000, 1.2, 0.1))])])
    trunks, leaves = [], []
    for _ in range(9):
        x, y = o.x + rng.uniform(-24, 24), o.y - rng.uniform(2, 16)
        if abs(x - o.x) < 4:
            continue
        h = rng.uniform(5, 8)
        trunks.append(((x, y, 0), (0.5, 0.5, h)))
        leaves += [
            ((x + dx, y + dy, h - 0.3), (2.6 if dx else 0.9, 0.9 if dx else 2.6, 0.25))
            for dx, dy in ((1.3, 0), (-1.3, 0), (0, 1.3), (0, -1.3))
        ]
    P._mesh_object(
        "palms", [(P.mat("palm_trunk", "#9c6b3c", 0.8), trunks), (P.mat("palm_leaf", "#2e9e44", 0.7), leaves)]
    )
    P._mesh_object("towel", [(P.mat("towel", "#ff5a7a", 0.9), [((o.x - 3.6, o.y - 3.0, 0), (1.0, 2.0, 0.03))])])
    _cones("parasol", [(o.x - 4.5, o.y - 1.5, 2.2, 1.6, 0.6)], P.mat("parasol", "#ffd23f", 0.6), 10)
    P._mesh_object("parasol_pole", [(P.mat("stick", "#2b2b2b"), [((o.x - 4.5, o.y - 1.5, 0), (0.06, 0.06, 2.3))])])


def _snow(o, rng, f0: int, f1: int) -> None:
    _flat_sky(bpy.context.scene, "#c9d8e6")
    _sun(2.6, (40, 0, 30))
    _ground("snowfield", o, "#f6f8fb")
    pines = [
        (o.x + rng.uniform(-50, 50), o.y - rng.uniform(3, 70), 0, rng.uniform(1.4, 2.4), rng.uniform(5, 9))
        for _ in range(60)
    ]
    pines = [p for p in pines if abs(p[0] - o.x) > 3.5]
    _cones("pines", pines, P.mat("pine", "#2e5e3e", 0.8), 7)
    _cones(
        "pine_snow",
        [(x, y, z + h * 0.55, r * 0.55, h * 0.47) for x, y, z, r, h in pines],
        P.mat("pine_snow", "#ffffff", 0.7),
        7,
    )
    peaks = ((-180, 140, 160), (0, 170, 210), (170, 130, 150))
    _cones("mountains", [(o.x + dx, o.y - 260, 0, r, h) for dx, r, h in peaks], P.mat("rock", "#8d96a3", 0.9), 9)
    caps = [(o.x + dx, o.y - 260, h * 0.6, r * 0.4, h * 0.4) for dx, r, h in peaks]
    _cones("caps", caps, P.mat("snowcap", "#ffffff", 0.7), 9)
    flake = P.mat("flake", "#ffffff", 0.5, emit=0.3)
    for i in range(160):  # falling snow
        x, y, z = o.x + rng.uniform(-8, 8), o.y + rng.uniform(-8, 8), rng.uniform(0.5, 9)
        s = P._mesh_object(f"flake{i}", [(flake, [((0, 0, 0), (0.06, 0.06, 0.06))])])
        key(s, "location", f0, (x, y, z))
        key(s, "location", f1, (x + rng.uniform(-1, 1), y, z - rng.uniform(3, 6)))


def _jungle(o, rng) -> None:
    _flat_sky(bpy.context.scene, "#a8d8b0")
    _sun(2.4, (60, 0, 60))
    _ground("jungle_floor", o, "#3f6b2a")
    trunks, crowns, ferns = [], [], []
    for _ in range(90):
        x, y = o.x + rng.uniform(-36, 36), o.y - rng.uniform(-6, 50)
        if abs(x - o.x) < 3.5 and -8 < y - o.y < 10:
            continue
        h = rng.uniform(9, 18)
        trunks.append(((x, y, 0), (0.7, 0.7, h)))
        for k in range(3):
            crowns.append(((x, y, h - 2 - 3 * k), (rng.uniform(4, 7),) * 2 + (2.2,)))
    for _ in range(80):
        x, y = o.x + rng.uniform(-12, 12), o.y - rng.uniform(-4, 18)
        if abs(x - o.x) < 2.2 and -4 < y - o.y < 10:
            continue
        ferns.append(((x, y, 0), (rng.uniform(0.8, 1.6),) * 2 + (rng.uniform(0.5, 1.2),)))
    P._mesh_object("jungle", [(P.mat("jtrunk", "#5b3f22", 0.8), trunks), (P.mat("jleaf", "#1f7a33", 0.8), crowns),
                              (P.mat("fern", "#3fa34d", 0.8), ferns)])  # fmt: skip
    vine = P.mat("vine", "#2c6b2f", 0.8)
    for i in range(10):
        x = o.x + rng.uniform(-6, 6)
        y = o.y - rng.uniform(1, 9)
        P.rope(f"vine{i}", [(x, y, 14), (x + 0.3, y, 9), (x - 0.2, y, 5.5)], 0.06, vine)
    parrot = P._mesh_object(
        "parrot",
        [
            (P.mat("parrot", "#e53935", 0.5), [((0, 0, 0), (0.35, 0.25, 0.5))]),
            (P.mat("parrot_wing", "#1e88e5", 0.5), [((0, 0.14, 0.1), (0.3, 0.06, 0.35))]),
            (P.mat("beak", "#f6c21a", 0.5), [((0, -0.17, 0.42), (0.1, 0.12, 0.08))]),
        ],
    )
    parrot.location = (o.x - 1.6, o.y - 1.0, 3.0)
    parrot.rotation_euler = (0, 0, 0.3)


def _desert(o, rng) -> None:
    _flat_sky(bpy.context.scene, "#ffd9a0")
    _sun(4.6, (30, 0, 200))
    _ground("dunesand", o, "#e9b86b")
    dunes = P.ball_mesh("dune", 1.0, 1.0)
    for i in range(14):
        P.instance(f"dune{i}", dunes, P.mat("dune", "#e2a95a", 1.0),
                   (o.x + rng.uniform(-150, 150), o.y - rng.uniform(30, 260), -0.5),
                   (rng.uniform(25, 60), rng.uniform(20, 45), rng.uniform(5, 14)))  # fmt: skip
    cactus = P.mat("cactus", "#4f8f3a", 0.8)
    for i in range(7):
        x, y = o.x + rng.uniform(-14, 14), o.y - rng.uniform(3, 26)
        if abs(x - o.x) < 2.5:
            continue
        h = rng.uniform(2.5, 4.5)
        P._mesh_object(f"cactus{i}", [(cactus, [((x, y, 0), (0.5, 0.5, h)), ((x + 0.55, y, h * 0.45), (0.6, 0.4, 0.35)),
                                                ((x + 0.75, y, h * 0.45), (0.35, 0.35, h * 0.35))])])  # fmt: skip


def _moon(o, rng, f0: int, f1: int) -> None:
    _flat_sky(bpy.context.scene, "#03040a")
    _sun(4.0, (60, 0, 40))
    _ground("regolith", o, "#9a9a9e")
    crater, rim = P.mat("crater", "#5d5d62", 1.0), P.mat("rim", "#c2c2c6", 1.0)
    for i in range(30):  # craters: a dark floor inside a lighter rim (two flat discs)
        x, y, r = o.x + rng.uniform(-60, 60), o.y - rng.uniform(8, 120), rng.uniform(2, 10)
        _discs(f"rim{i}", [(x, y, -0.1, r * 1.25, 0.14)], rim)
        _discs(f"crater{i}", [(x, y, -0.08, r, 0.14)], crater)
    stars = P.mat("star", "#ffffff", emit=6.0)
    star_mesh = P.ball_mesh("star", 1.0, 1.0, subdivisions=1)
    for i in range(200):
        a, e = rng.uniform(0, 2 * math.pi), rng.uniform(0.12, 1.3)
        d = 900
        P.instance(f"star{i}", star_mesh, stars,
                   (o.x + d * math.sin(a) * math.cos(e), o.y + d * math.cos(a) * math.cos(e), d * math.sin(e)),
                   rng.uniform(0.8, 1.8))  # fmt: skip
    earth_at = Vector((o.x - 150, o.y - 420, 150))  # in the sky in front of the camera, which looks back at the door
    rock = P.mat("moonrock", "#7d7d82", 1.0)
    rocks = [
        (
            (o.x + rng.uniform(-20, 20), o.y - rng.uniform(2, 40), 0),
            (rng.uniform(0.3, 1.2),) * 2 + (rng.uniform(0.2, 0.7),),
        )
        for _ in range(40)
    ]
    P._mesh_object("moonrocks", [(rock, rocks)])
    globe = P.ball_mesh("earth", 1.0, 1.0, subdivisions=4)
    earth = P.instance("earth", globe, P.mat("earth", "#2f73d6", 0.4, emit=0.6), earth_at, 40)
    land = P.mat("earth_land", "#3fa34d", 0.6, emit=0.5)
    for k, (dx, dz, s) in enumerate(((-12, 10, 14), (14, -6, 11), (4, 22, 8))):
        P.instance(f"land{k}", P.ball_mesh("earth", 1.0, 1.0, subdivisions=4), land,
                   earth_at + Vector((dx, 33, dz)), s)  # fmt: skip
    earth.visible_shadow = False


def build(spec: dict, ctx, scene, params: dict) -> None:
    stage = params.get("stage", "room")
    stage = stage if stage in STAGES else "room"
    f0, f1 = ctx.frame_start, ctx.frame_end
    fps = scene.render.fps or 24
    rng = random.Random(SEED + STAGES.index(stage))

    def at(fr: float) -> int:
        return f0 + int((f1 - f0) * fr)

    if stage == "room":  # late for school: you open your bedroom door... and light pours in
        o = SETS["room"]
        B._sky(scene, "low")
        P.bedroom("room", o, seed=SEED)
        # the door on the right-hand wall, opening into the room (it faces -x)
        _door("bedroom_door", (o.x + 2.86, o.y - 0.4, 0), math.pi / 2, open_frame=at(0.45), glow="#fff6d8")
        hero = _hero((o.x - 0.6, o.y - 1.2, 0), 0.0, f0)
        hero.walk(at(0.05), at(0.4), (o.x - 0.6, o.y - 1.2), (o.x + 2.0, o.y - 0.4), fps)
        hero.reach(at(0.38), at(0.46), "R", hold=10)
        _camera(scene, (o.x - 2.3, o.y - 2.2, 1.7), (o.x + 2.6, o.y - 0.3, 1.3), 18, f0, f1, 0.04)
        return _end(scene, params)

    if stage in ("beach", "snow", "jungle", "desert", "moon", "hook"):
        place = "moon" if stage == "hook" else stage
        o = SETS[place]
        {"beach": _beach, "jungle": _jungle, "desert": _desert}.get(place, lambda o, r: None)(o, rng)
        if place == "snow":
            _snow(o, rng, f0, f1)
        if place == "moon":
            _moon(o, rng, f0, f1)
        _door(f"{place}_door", o)
        hero = _step_out(o, f0, fps, out=2.6 if place != "moon" else 3.4)
        if place == "snow":  # knee deep: you sink a little with each step
            key(hero.root, "location", at(0.85), (o.x, o.y + 2.6, -0.35))
        if place == "moon":  # low gravity: a slow, high hop
            hop = at(0.55)
            key(hero.root, "location", hop, (o.x, o.y + 3.4, 0.0))
            key(hero.root, "location", hop + int(fps * 0.9), (o.x, o.y + 4.6, 1.8))
            key(hero.root, "location", hop + int(fps * 1.8), (o.x, o.y + 5.8, 0.0))
            for side in ("L", "R"):
                hero.raise_arm(hop, hop + 8, side, hold=40)
        if place == "jungle":
            hero.look_at(at(0.6), (o.x - 1.6, o.y - 1.0, 3.0))  # the parrot
        cams = {
            "moon": ((o.x + 3.5, o.y + 9.5, 1.4), (o.x - 0.5, o.y + 1.5, 1.8)),
            "snow": ((o.x + 2.8, o.y + 7.5, 1.6), (o.x, o.y + 1.0, 1.3)),
        }
        cam = cams.get(place, ((o.x + 2.6, o.y + 7.0, 1.6), (o.x, o.y + 1.0, 1.3)))
        _camera(scene, cam[0], cam[1], 20, f0, f1, 0.04)
        return _end(scene, params)

    if stage == "rooftop":  # the roof of a skyscraper: the elevator video's tower in the ramp city
        from render_engines.custom import elevator as E
        from render_engines.custom import ramp as R

        B._sky(scene, "low")
        R._streets()
        R._city(random.Random(R.SEED))
        E._tower()
        top = Vector((E.TOWER.x + 3.0, E.TOWER.y + 4.0, E.TOWER_H + 1.2))
        _door("roof_door", top, 0.0)
        hero = _step_out(top, f0, fps, out=2.4)
        hero.look_at(at(0.6), (E.TOWER.x + 3, E.TOWER.y + 30, 0))
        _camera(
            scene, (top.x + 3.5, top.y + 7.0, top.z + 1.4), (top.x - 0.5, top.y + 1.0, top.z + 1.0), 16, f0, f1, 0.03
        )
        return _end(scene, params)

    # school: the last door opens right in front of school... on a Saturday (empty, doors shut)
    from render_engines.custom import zipline as Z

    Z._sky(scene)
    Z._town(random.Random(Z.SEED))
    Z._school()
    spot = Vector((Z.SCHOOL_X - 14.0, 0.0, 0.0))
    _door("school_door", spot, -math.pi / 2)
    hero = _hero(spot + Vector((0.4, 0, 0)), 0.0, f0)
    hero.walk(at(0.1), at(0.45), (spot.x + 0.4, 0.0), (spot.x + 5.0, 0.0), fps)
    hero.look_at(at(0.55), (Z.SCHOOL_X, 0, 4))
    hero.raise_arm(at(0.7), at(0.78), "R", hold=30)
    _camera(scene, (spot.x - 9.0, -2.5, 2.2), (Z.SCHOOL_X, 0.5, 3.5), 20, f0, f1, 0.04)
    return _end(scene, params)


def _end(scene, params: dict) -> None:
    if params.get("outlines") is False:
        scene.render.use_freestyle = False
