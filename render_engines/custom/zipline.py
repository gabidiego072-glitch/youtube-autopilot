"""'What if you built a ZIPLINE from your house to school?' (Nov 26, the owner: "más hipotéticos, como la rampa, y no
solo coches"; a different idea for each channel). ONE cable, ONE town, ONE trip, each part caused by the last:

  late for school -> a cable from your house on the hill to the school -> you hook on -> over the park -> over the
  traffic -> over the river -> faster and faster -> the school wall -> SPLAT -> tomorrow every house has a cable.

params: stage (one of STAGES). Built from render_engines/custom/parts.py.
"""

from __future__ import annotations

import math
import random

import bpy
from mathutils import Matrix, Vector

from render_engines.core.blender.animation import key
from render_engines.core.colors import hex_to_linear
from render_engines.custom import parts as P
from render_engines.custom.ramp import _camera, _hero

SEED = 2612
STAGES = ("hook", "late", "shoot", "push", "park", "road", "river", "faster", "school", "splat", "everyone")
HILL_TOP = 22.0  # your house stands on a hill at x = 0
START = Vector((4.0, 0.0, HILL_TOP + 9.0))  # the cable leaves from your roof
END = Vector((684.0, 0.0, 10.0))  # ...and ends on the school wall (the wall is at x = 686)
SAG = 7.0
PARK = (80.0, 250.0)
ROAD_X = 320.0
RIVER = (400.0, 470.0)
SCHOOL_X = 686.0
HANG = 2.3  # from the cable down to your hands


def cable_point(u: float) -> Vector:
    p = START.lerp(END, u)
    p.z -= SAG * 4 * u * (1 - u)
    return p


# ---------------------------------------------------------------- the world


def _sky(scene) -> None:
    world = scene.world or bpy.data.worlds.new("zl_world")
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
    ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[1].position = 0.0, 0.3
    ramp.color_ramp.elements[0].color = hex_to_linear("#d9ecf5")
    ramp.color_ramp.elements[1].color = hex_to_linear("#8cc8f2")
    links.new(ramp.outputs["Color"], nodes["Background"].inputs[0])
    sun = bpy.data.objects.new("zl_sun", bpy.data.lights.new("zl_sun", "SUN"))
    sun.data.energy = 3.6
    sun.rotation_euler = (math.radians(50), 0, math.radians(-30))
    scene.collection.objects.link(sun)


def _hill() -> None:
    """A smooth round hill under your house: a flattened sphere."""
    mesh = P.ball_mesh("hill", 1.0, 1.0, subdivisions=4)
    hill = P.instance(
        "hill", mesh, P.mat("hill_grass", "#5ea94e", 1.0), (0, 0, HILL_TOP - 60 * 0.36), (80, 80, 60 * 0.36)
    )
    hill.data.polygons.foreach_set("use_smooth", [True] * len(hill.data.polygons))
    path = [((-6 - 10 * k, 0, HILL_TOP - 0.3 - k * 2.2), (11, 3, 0.4)) for k in range(4)]
    P._mesh_object("hill_path", [(P.mat("walk", "#c9c3b8", 0.9), path)])


def _house() -> None:
    wall, roof = P.mat("my_wall", "#f6e7cf", rough=0.9), P.mat("my_roof", "#2f6db5", rough=0.8)
    glass, door = P.mat("bld_glass", "#33475c", rough=0.2), P.mat("bld_door", "#3b2a1e")
    x, z = -6.0, HILL_TOP - 0.4
    P._mesh_object(
        "my_house",
        [
            (wall, [((x, 0, z), (12, 10, 6.5))]),
            (glass, [((x + 6.05, dy, z + 3.6), (0.12, 2.4, 2.0)) for dy in (-2.5, 2.5)]),
            (door, [((x, 5.06, z), (1.8, 0.14, 3.0))]),
            (P.mat("post", "#6b4a2e", 0.8), [((START.x - 0.5, 0, z + 6.5), (0.5, 0.5, START.z - z - 6.0))]),
            (P.mat("deck", "#a0764b", 0.8), [((START.x - 2.5, 0, z + 6.5), (5, 5, 0.3))]),  # your launch deck
        ],
    )
    verts = [(x - 6.6, -5.6, z + 6.5), (x + 6.6, -5.6, z + 6.5), (x + 6.6, 5.6, z + 6.5), (x - 6.6, 5.6, z + 6.5),
             (x - 6.6, 0, z + 10.5), (x - 0.2, 0, z + 10.5)]  # fmt: skip
    mesh = bpy.data.meshes.new("my_roof")
    mesh.from_pydata(verts, [], [(0, 1, 5, 4), (3, 4, 5, 2), (0, 4, 3), (1, 2, 5)])
    mesh.materials.append(roof)
    r = bpy.data.objects.new("my_roof", mesh)
    bpy.context.scene.collection.objects.link(r)


def _school() -> None:
    x0 = SCHOOL_X
    brick, white = P.mat("school_brick", "#c4673f", 0.9), P.mat("school_trim", "#f2efe8", 0.8)
    glass = P.mat("bld_glass", "#33475c", rough=0.2)
    P._mesh_object(
        "school",
        [
            (brick, [((x0 + 22, 0, 0), (44, 70, 14))]),
            (white, [((x0 + 22, 0, 14), (45, 71, 1.0)), ((x0 - 0.2, 0, 0), (0.3, 16, 4))]),
            (
                glass,
                [
                    ((x0 - 0.06, y, z), (0.12, 4, 2.6))
                    for y in range(-30, 31, 8)
                    for z in (2.0, 7.0)
                    if abs(y) > 6 or z > 5
                ],
            ),
            (P.mat("bld_door", "#3b2a1e"), [((x0 - 0.1, 0, 0), (0.14, 5, 3.4))]),
            (P.mat("clock", "#ffffff", emit=0.4), [((x0 - 0.1, 0, 11.2), (0.14, 3, 2))]),
        ],
    )
    pitch = [((x0 + 22, 75, -0.02), (60, 36, 0.03))]
    lines = [
        ((x0 + 22, 75, 0.02), (0.4, 36, 0.02)),
        ((x0 + 22, 57.2, 0.02), (60, 0.4, 0.02)),
        ((x0 + 22, 92.8, 0.02), (60, 0.4, 0.02)),
    ]
    P._mesh_object("pitch", [(P.mat("pitch", "#4fae4a", 1.0), pitch), (P.mat("line", "#f2f2f2", 0.9), lines)])
    sign = P.mat("school_sign", "#1f5fae", 0.6)
    P._mesh_object("school_sign", [(sign, [((x0 - 0.3, 0, 15.2), (0.3, 20, 3))])])


def _town(rng: random.Random) -> None:
    P._mesh_object("ground", [(P.mat("grass", "#7cc46a", 1.0), [((0, 0, -0.12), (6000, 6000, 0.1))])])
    road, line = P.mat("road", "#4f5257", 0.9), P.mat("line", "#f2f2f2", 0.9)
    P._mesh_object("road", [(road, [((ROAD_X, 0, -0.03), (16, 1600, 0.03))])])
    P._mesh_object(
        "lines", [(line, [((ROAD_X + s * 0.1, y, 0.0), (0.2, 2.6, 0.02)) for y in range(-400, 400, 7) for s in (0,)])]
    )
    water = P.mat("river", "#2e86c1", rough=0.12)
    bank = P.mat("shore", "#cdbb8a", rough=1.0)
    mid = (RIVER[0] + RIVER[1]) / 2
    P._mesh_object("river_bank", [(bank, [((mid, 0, -0.09), (RIVER[1] - RIVER[0] + 10, 1600, 0.08))])])
    P._mesh_object("river", [(water, [((mid, 0, -0.07), (RIVER[1] - RIVER[0], 1600, 0.08))])])
    P._mesh_object(
        "bridge", [(P.mat("bridge", "#9aa3ad", 0.7), [((mid, -140, 3.0), (RIVER[1] - RIVER[0] + 20, 10, 1.2))])]
    )
    # the park: paths, trees, a pond and benches
    trees, crowns = [], []
    for _ in range(170):
        x, y = rng.uniform(*PARK), rng.uniform(-110, 110)
        if abs(y) < 5:
            y += 10 * (1 if y >= 0 else -1)
        h = rng.uniform(3.5, 6.5)
        trees.append(((x, y, 0), (0.6, 0.6, h)))
        crowns.append(((x, y, h - 1.0), (rng.uniform(3.5, 5.5),) * 2 + (rng.uniform(3.5, 5),)))
    P._mesh_object("trees", [(P.mat("trunk", "#7a4f2a"), trees), (P.mat("leaf", "#3f9b3f"), crowns)])
    paths = [(((PARK[0] + PARK[1]) / 2, y, -0.02), (PARK[1] - PARK[0], 3, 0.03)) for y in (-60, 30)]
    paths += [((x, 0, -0.02), (3, 220, 0.03)) for x in (120, 200)]
    P._mesh_object("park_paths", [(P.mat("park_path", "#d8c9a6", 1.0), paths)])
    P._mesh_object("pond", [(water, [((160, 70, -0.05), (30, 20, 0.06))])])
    # houses between the river and the school, and around the hill
    lots = []
    for x in range(490, 660, 22):
        for y in list(range(-150, -15, 22)) + list(range(22, 160, 22)):
            lots.append((x + rng.uniform(-2, 2), y, rng.uniform(9, 12), rng.uniform(8, 10), rng.uniform(5, 7), 1))
    for _ in range(70):
        a, r = rng.uniform(0, 2 * math.pi), rng.uniform(95, 260)
        x, y = math.cos(a) * r - 40, math.sin(a) * r
        if PARK[0] - 10 < x < PARK[1] + 10 and abs(y) < 120:
            continue
        lots.append((x, y, rng.uniform(9, 12), rng.uniform(8, 10), rng.uniform(5, 7), 1 if y < 0 else -1))
    P.houses("hood", lots, seed=SEED)
    far = [
        (x, y, rng.uniform(20, 30), rng.uniform(20, 30), rng.uniform(15, 60))
        for x in range(-600, 1400, 60)
        for y in (-520, -580, 520, 580)
    ]
    P.city("far", far, seed=SEED + 1, windows=False)


def _cable(extra: list | None = None) -> None:
    steel = P.mat("cable", "#2b2b2b", rough=0.4, metal=0.6)
    pts = [cable_point(i / 80) for i in range(81)]
    P.rope("cable", pts, 0.14, steel)
    for i, (a, b) in enumerate(extra or []):
        P.rope(
            f"cable{i}",
            [a.lerp(b, k / 30) - Vector((0, 0, 4 * SAG * k / 30 * (1 - k / 30) * 0.6)) for k in range(31)],
            0.3,
            steel,
        )


def _rider(name: str, colours: dict | None = None):
    """A trolley on the cable with someone hanging from its handle, arms up. Returns (trolley, person)."""
    trolley = P._mesh_object(
        f"{name}_trolley",
        [
            (P.mat("trolley", "#f6c21a", 0.5), [((0, 0, -0.25), (0.8, 0.35, 0.5))]),
            (
                P.mat("handle", "#2b2b2b", 0.5),
                [((0, 0, -HANG + 0.15), (0.1, 0.1, HANG - 0.4)), ((0, 0, -HANG + 0.1), (0.1, 0.9, 0.12))],
            ),
        ],
    )
    from render_engines.cinematic.character import build_character

    person = build_character(
        name, colours or {"body": "#f07c22", "accent": "#1f2a44", "hair": "#2b1a10"}, (0, 0, 0), hat=False
    )
    person.root.parent = trolley
    person.root.location = (0, 0, -HANG - 1.75)
    person.root.rotation_euler = (0, 0, math.pi / 2)
    for side in ("L", "R"):
        person.arms[side].rotation_euler = (math.radians(170), 0, 0)
    for side, sw in (("L", 1), ("R", -1)):  # legs dangling, a little apart
        person.legs[side].rotation_euler = (math.radians(12 * sw), 0, 0)
    return trolley, person


def _ride(trolley, f0: int, f1: int, u0: float, u1: float, wobble: float = 0.0) -> None:
    n = 10
    for i in range(n + 1):
        t = i / n
        u = u0 + (u1 - u0) * t
        p = cable_point(u)
        f = f0 + round((f1 - f0) * t)
        key(trolley, "location", f, tuple(p))
        key(trolley, "rotation_euler", f, (wobble * math.sin(i * 1.9), 0, 0))  # swinging side to side


# ---------------------------------------------------------------- the scenes


def build(spec: dict, ctx, scene, params: dict) -> None:
    stage = params.get("stage", "late")
    stage = stage if stage in STAGES else "late"
    f0, f1 = ctx.frame_start, ctx.frame_end
    fps = scene.render.fps or 24

    def at(fr: float) -> int:
        return f0 + int((f1 - f0) * fr)

    rng = random.Random(SEED)
    _sky(scene)
    _town(rng)
    _hill()
    _house()
    _school()
    if stage == "everyone":
        ends = []
        r = random.Random(SEED + 3)
        for _ in range(26):  # cables from houses all over town, all to the school
            a = r.uniform(-1.2, 1.2) + math.pi
            d = r.uniform(250, 700)
            ends.append(
                (
                    Vector((SCHOOL_X + math.cos(a) * d, math.sin(a) * d * 0.8, r.uniform(16, 30))),
                    Vector((SCHOOL_X - 1, r.uniform(-30, 30), r.uniform(6, 12))),
                )
            )
        _cable(ends)
    elif stage != "late":
        _cable()
    if stage == "shoot":  # the cable shoots out from your roof all the way to the school
        cable = bpy.data.objects["cable"]
        turn = (END - START).normalized().to_track_quat("X", "Z")  # local x runs along the cable
        cable.data.transform(turn.inverted().to_matrix().to_4x4() @ Matrix.Translation(-START))
        cable.location = START
        cable.rotation_mode = "QUATERNION"
        cable.rotation_quaternion = turn
        key(cable, "scale", at(0.2) - 1, (0.001, 1, 1))
        key(cable, "scale", at(0.6), (1, 1, 1))

    you_u = {"hook": (0.57, 0.66), "push": (0.0, 0.04), "park": (0.1, 0.3), "road": (0.36, 0.5), "river": (0.53, 0.7),
             "faster": (0.7, 0.92), "school": (0.9, 0.995)}  # fmt: skip

    if stage == "late":
        hero = _hero((4.0, 8.0, HILL_TOP - 0.3), 0.0, f0)  # on your hill, the school far away
        hero.look_at(f0, (SCHOOL_X, 0, 10))
        hero.raise_arm(at(0.4), at(0.5), "R", hold=50)
        _camera(scene, (-8, 12, HILL_TOP + 2.5), (40, 0, HILL_TOP - 4), 24, f0, f1, 0.06)

    elif stage == "shoot":
        hero = _hero((START.x - 2, 1.0, HILL_TOP + 6.4), 0.0, f0)
        hero.raise_arm(f0, f0 + 6, "R", hold=80)
        _camera(scene, (18, -24, HILL_TOP + 8), (4, 0, HILL_TOP + 5), 22, f0, f1, 0.05)

    elif stage in you_u:
        trolley, you = _rider("you")
        u0, u1 = you_u[stage]
        _ride(trolley, f0, f1, u0, u1, wobble=0.05 if stage in ("faster", "school") else 0.02)
        if stage == "hook":  # just over the river, from below the water line, fast
            _camera(scene, (4, -5, -1.5), (-2, 0, -5), 18, f0, f1, follow=trolley)
        elif stage == "push":
            key(trolley, "location", f0, tuple(cable_point(0.0) - Vector((0.8, 0, 0))))
            _camera(scene, (-5, -4, -1.5), (4, 0, -3.5), 22, f0, f1, follow=trolley)
        elif stage == "park":
            for i in range(5):  # people in the park look up
                x = 120 + 14 * i
                p = _hero((x, rng.uniform(-14, 14), 0.18), math.pi / 2, f0)
                p.look_at(f0, (x + 20, 0, 18))
                if i % 2:
                    p.raise_arm(at(0.3), at(0.4), "R", hold=40)
            _camera(scene, (6, -7, -2), (0, 0, -5), 22, f0, f1, follow=trolley)
        elif stage == "road":
            cols = ["#d63a2f", "#2f7fd6", "#2ecc71", "#ecf0f1", "#8e44ad", "#f6c21a"]
            for i in range(14):
                lane = 3.0 if i % 2 else -3.0
                y = -90 + i * 13
                c = P.car(
                    f"car{i}",
                    (ROAD_X + lane, y, 0),
                    math.pi / 2 if lane > 0 else -math.pi / 2,
                    "sedan" if i % 3 else "taxi",
                    cols[i % 6],
                )
                P.drive(c, f0, f1, 18)
            _camera(scene, (-4, -8, -1), (3, 0, -6), 20, f0, f1, follow=trolley)
        elif stage == "river":
            boat = P._mesh_object(
                "boat",
                [
                    (P.mat("boat", "#ecf0f1", 0.5), [((0, 0, 0), (4, 10, 1.4))]),
                    (P.mat("boat_red", "#d63a2f", 0.5), [((0, -1, 1.4), (2.6, 4, 1.6))]),
                ],
            )
            key(boat, "location", f0, ((RIVER[0] + RIVER[1]) / 2 + 8, -40, -0.2))
            key(boat, "location", f1, ((RIVER[0] + RIVER[1]) / 2 + 8, -10, -0.2))
            _camera(scene, (3, 5, -2.5), (0, 0, -4.5), 20, f0, f1, follow=trolley)
        elif stage == "faster":
            _camera(scene, (-7, -2, -2.5), (6, 0, -3.5), 24, f0, f1, follow=trolley)
        elif stage == "school":
            for k in range(6):  # classmates at the windows
                _hero((SCHOOL_X - 4, -18 + 7 * k, 0.18), math.pi, f0).raise_arm(
                    at(0.4 + 0.05 * k), at(0.5 + 0.05 * k), "R", hold=40
                )
            _camera(scene, (SCHOOL_X - 6, -16, 6), (SCHOOL_X - 60, 0, 8), 24, f0, f1, 0.04)

    elif stage == "splat":
        trolley, you = _rider("you")
        hit = at(0.3)
        _ride(trolley, f0 - int(fps * 0.6), hit, 0.97, 1.0)
        key(trolley, "location", hit + 2, tuple(cable_point(1.0) + Vector((0.35, 0, 0))))
        key(trolley, "location", f1, tuple(cable_point(1.0) + Vector((0.2, 0, -0.1))))
        for side in ("L", "R"):  # flat against the wall, arms and legs out
            key(you.arms[side], "rotation_euler", hit, (math.radians(170), 0, 0))
            key(
                you.arms[side],
                "rotation_euler",
                hit + 3,
                (math.radians(100), 0, math.radians(60 if side == "L" else -60)),
            )
            key(you.legs[side], "rotation_euler", hit + 3, (0, 0, math.radians(25 if side == "L" else -25)))
        P.landing(
            "wall", cable_point(1.0) + Vector((1.2, 0, -HANG - 0.8)), hit, fps, size=3.0, seed=5, ground="#c4673f"
        )
        crowd = [_hero((SCHOOL_X - 5 - 2 * k, -10 + 4 * k, 0.18), math.pi * 0.1, f0) for k in range(4)]
        for k, c in enumerate(crowd):
            c.look_at(hit, (SCHOOL_X, 0, 8))
            c.raise_arm(hit + 4 + 3 * k, hit + 10 + 3 * k, "R", hold=40)
        cam = _camera(scene, (SCHOOL_X - 22, -14, 4), (SCHOOL_X, 0, 7), 24, f0, f1, 0.06)
        P.shake(cam, hit, fps, strength=0.35)

    elif stage == "everyone":
        r = random.Random(SEED + 4)
        cols = ["#2f7fd6", "#2ecc71", "#d63a2f", "#8e44ad", "#f6c21a", "#1abc9c"]
        cables = [o for o in bpy.data.objects if o.name.startswith("cable") and o.name != "cable"]
        for k in range(14):
            trolley, _ = _rider(f"kid{k}", {"body": cols[k % 6], "accent": "#1f2a44", "hair": "#2b1a10"})
            pts = cables[k % len(cables)].data.vertices
            n = len(pts) // 4
            idx = [int(n * t) * 4 for t in (0.1, 0.5, 0.95)]
            seg = [Vector(pts[i].co) for i in idx]
            fa = f0 - int(r.uniform(0, 1.5) * fps)
            key(trolley, "location", fa, tuple(seg[0]))
            key(trolley, "location", fa + int(fps * 2.5), tuple(seg[1]))
            key(trolley, "location", fa + int(fps * 4.5), tuple(seg[2]))
        _trolley, you = _rider("you")
        _ride(_trolley, f0, f1, 0.4, 0.75)
        _camera(scene, (SCHOOL_X - 150, -130, 60), (SCHOOL_X - 30, 0, 8), 22, f0, f1, 0.05)

    if params.get("outlines") is False:
        scene.render.use_freestyle = False
