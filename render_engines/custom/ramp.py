"""'What if you fixed a traffic jam with a RAMP?' (Nov 24, "unnecessary engineering"): ONE street, ONE jam, and a
fix that makes the next problem, scene after scene, in the same world:

  the jam -> a ramp at the back of the queue -> cars jump the jam -> they land on the cross street (crash) -> a giant
  net -> they bounce back -> onto your house -> a ramp on your roof -> they fly over the city -> ramps on every roof ->
  the jam is gone from your street... because it is in the sky now.

params: stage (one of STAGES). Built from render_engines/custom/parts.py (cars, buildings, crashes, landings).
"""

from __future__ import annotations

import math
import random

import bpy
from mathutils import Vector

from render_engines.cinematic.character import build_character
from render_engines.core.blender.animation import key
from render_engines.core.colors import hex_to_linear
from render_engines.custom import parts as P

SEED = 2411
STAGES = (
    "hook", "jam", "build", "jump", "cross_crash", "net", "bounce", "house", "roof_ramp", "city", "everywhere",
    "sky_jam", "ending",
)  # fmt: skip
RAMP_X0, RAMP_X1, RAMP_H = -72.0, -56.0, 5.0  # the first ramp, across the street at the back of the queue
JAM_X0, JAM_X1 = -44.0, 90.0
CROSS_X = 112.0  # the cross street runs along y here
NET_X = 98.0
HOUSE = Vector((22.0, -19.0, 0.0))  # your house, beside the street; its roof top is at z ~11
ROOF_Z = 7.0
HERO_COLOURS = {"body": "#f07c22", "accent": "#1f2a44", "hair": "#2b1a10"}


# ---------------------------------------------------------------- the world (the same in every scene)


def _wedge(name: str, x0: float, x1: float, y: float, width: float, z0: float, height: float, rising: int = 1):
    """A ramp: flat on z0, rising toward +x (rising=1) or -x (rising=-1). Yellow with black stripes on the slope."""
    lo, hi = (x0, x1) if rising > 0 else (x1, x0)
    w = width / 2
    verts = [
        (lo, y - w, z0),
        (hi, y - w, z0),
        (hi, y + w, z0),
        (lo, y + w, z0),
        (hi, y - w, z0 + height),
        (hi, y + w, z0 + height),
    ]
    faces = [(0, 3, 2, 1), (0, 1, 4), (3, 5, 2), (1, 2, 5, 4), (0, 4, 5, 3)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    if rising < 0:
        mesh.flip_normals()
    mesh.materials.append(P.mat("ramp_yellow", "#f6c21a", rough=0.5))
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    stripes = []
    for k in range(1, 4):  # black chevrons across the slope
        t = k / 4
        x = lo + (hi - lo) * t
        stripes.append(((x, y, z0 + height * t + 0.02), (abs(hi - lo) * 0.06, width * 0.98, 0.05)))
    P._mesh_object(f"{name}_stripes", [(P.mat("ramp_black", "#1d1d1f"), stripes)])
    return obj


def _house() -> None:
    x, y = HOUSE.x, HOUSE.y
    wall, roof = P.mat("house_wall", "#f3e2c7", rough=0.9), P.mat("house_roof", "#c0392b", rough=0.8)
    glass, door = P.mat("bld_glass", "#33475c", rough=0.2), P.mat("bld_door", "#3b2a1e")
    P._mesh_object(
        "house",
        [
            (wall, [((x, y, 0), (16, 12, ROOF_Z))]),
            (glass, [((x + dx, y + 6.05, z), (2.2, 0.1, 1.8)) for dx in (-5, 5) for z in (1.4, 4.4)]),
            (door, [((x, y + 6.06, 0), (2.0, 0.12, 2.6))]),
        ],
    )
    verts = [
        (x - 8.6, y - 6.6, ROOF_Z),
        (x + 8.6, y - 6.6, ROOF_Z),
        (x + 8.6, y + 6.6, ROOF_Z),
        (x - 8.6, y + 6.6, ROOF_Z),
    ]
    verts += [(x - 8.6, y, ROOF_Z + 4), (x + 8.6, y, ROOF_Z + 4)]
    mesh = bpy.data.meshes.new("house_roof")
    mesh.from_pydata(verts, [], [(0, 1, 5, 4), (3, 4, 5, 2), (0, 4, 3), (1, 2, 5), (0, 3, 2, 1)])
    mesh.materials.append(roof)
    obj = bpy.data.objects.new("house_roof", mesh)
    bpy.context.scene.collection.objects.link(obj)
    P._mesh_object(
        "house_chimney", [(P.mat("house_brick", "#8e4b32"), [((x + 4, y - 2, ROOF_Z + 1), (1.4, 1.4, 4.5))])]
    )


def _streets() -> None:
    road, walk, line = P.mat("road", "#4f5257", 0.9), P.mat("walk", "#c9c3b8", 0.9), P.mat("line", "#f2f2f2", 0.9)
    P._mesh_object("ground", [(P.mat("grass", "#7cc46a", 1.0), [((0, 0, -0.12), (3000, 3000, 0.1))])])
    P._mesh_object("road_main", [(road, [((0, 0, -0.03), (1600, 12, 0.03))])])
    P._mesh_object("road_cross", [(road, [((CROSS_X, 0, -0.035), (12, 1600, 0.03))])])  # never coplanar
    gap0, gap1 = CROSS_X - 11, CROSS_X + 11  # the sidewalks stop at the crossing
    side = [(((-800 + gap0) / 2, s * 8.5, 0), (gap0 + 800, 5, 0.18)) for s in (1, -1)]
    side += [(((gap1 + 800) / 2, s * 8.5, 0), (800 - gap1, 5, 0.18)) for s in (1, -1)]
    side += [((CROSS_X + s * 8.5, c * 405.5, 0), (5, 789, 0.18)) for s in (1, -1) for c in (1, -1)]
    P._mesh_object("sidewalks", [(walk, side)])
    dashes = [((x, 0, 0.0), (2.6, 0.18, 0.02)) for x in range(-400, 400, 7) if abs(x - CROSS_X) > 10]
    dashes += [((CROSS_X, y, 0.0), (0.18, 2.6, 0.02)) for y in range(-400, 400, 7) if abs(y) > 10]
    P._mesh_object("lines", [(line, dashes)])


def _city(rng: random.Random) -> list:
    """Buildings along the street (detailed) and a grid city around it. Returns the far roofs (x, y, top)."""
    near = []
    for x in range(-300, 320, 20):
        for s in (1, -1):
            if abs(x - CROSS_X) < 18 or (s < 0 and abs(x - HOUSE.x) < 16):
                continue
            near.append((x, s * 18.5, 16, 13, rng.uniform(12, 38)))
    P.city("street", near, seed=SEED, lit=0.14)
    far, roofs = [], []
    for gx in range(-720, 760, 46):
        for gy in list(range(52, 520, 46)) + list(range(-52, -520, -46)):
            if abs(gx - CROSS_X) < 30:
                continue
            centre = math.exp(-((gx / 420) ** 2 + (gy / 300) ** 2))
            h = rng.uniform(10, 24) + 70 * centre * rng.random()
            w, d = rng.uniform(24, 34), rng.uniform(24, 34)
            far.append((gx, gy, w, d, h))
            roofs.append((gx, gy, h))
    P.city("grid", far, seed=SEED + 1, lit=0.08)
    trees = [((x + rng.uniform(-2, 2), s * 11.5, 0), (0.5, 0.5, 3.2)) for x in range(-280, 300, 24) for s in (1, -1)]
    crowns = [((c[0][0], c[0][1], 3.0), (3.0, 3.0, 2.6)) for c in trees]
    P._mesh_object("trees", [(P.mat("trunk", "#7a4f2a"), trees), (P.mat("leaf", "#3f9b3f"), crowns)])
    return roofs


def _jam(rng: random.Random, frame: int, keep: bool = True) -> list:
    """The queue: two full lanes, all facing +x, stopped."""
    if not keep:
        return []
    cols = ["#d63a2f", "#2f7fd6", "#2ecc71", "#ecf0f1", "#8e44ad", "#34495e"]
    cars = []
    for lane in (-2.6, 2.6):
        x = JAM_X0
        while x < JAM_X1:
            kind = rng.choices(("sedan", "taxi", "van"), (6, 2, 1))[0]
            cars.append(
                P.car(f"jam{len(cars)}", (x, lane, 0), 0.0, kind, rng.choice(cols) if kind == "sedan" else None)
            )
            x += 6.4 if kind != "van" else 7.2
    return cars


def _world(scene, stage: str) -> dict:
    rng = random.Random(SEED)
    _streets()
    _house()
    roofs = _city(rng)
    jam = _jam(rng, 0, keep=stage not in ("sky_jam", "ending"))
    ramp = _wedge("ramp", RAMP_X0, RAMP_X1, 0.0, 12.0, 0.0, RAMP_H) if stage != "jam" else None
    world = scene.world or bpy.data.worlds.new("rp_world")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = hex_to_linear("#9fd3f5")
    sun = bpy.data.objects.new("rp_sun", bpy.data.lights.new("rp_sun", "SUN"))
    sun.data.energy = 3.6
    sun.rotation_euler = (math.radians(48), 0, math.radians(30))
    scene.collection.objects.link(sun)
    return {"jam": jam, "ramp": ramp, "roofs": roofs}


# ---------------------------------------------------------------- motion helpers


def _arc(root, fa: int, fb: int, a, b, apex: float) -> None:
    """A flight from a to b peaking `apex` metres above the straight line, nose along the path."""
    a, b = Vector(a), Vector(b)
    yaw = math.atan2(b.y - a.y, b.x - a.x)
    flat = max(0.1, (b - a).xy.length)
    n = 12
    for i in range(n + 1):
        t = i / n
        p = a.lerp(b, t)
        p.z += 4 * apex * t * (1 - t)
        dz = (b.z - a.z) + 4 * apex * (1 - 2 * t)
        f = fa + round((fb - fa) * t)
        key(root, "location", f, tuple(p))
        key(root, "rotation_euler", f, (0.0, -math.atan2(dz, flat) * 0.8, yaw))


def _grow(obj, start: int, end: int, axis: str = "z") -> None:
    small = {"x": (0.01, 1, 1), "y": (1, 0.01, 1), "z": (1, 1, 0.01)}[axis]
    key(obj, "scale", start - 1, small)
    key(obj, "scale", start, small)
    key(obj, "scale", end, (1, 1, 1))


def _hero(location, yaw: float, frame: int):
    hero = build_character("hero", HERO_COLOURS, tuple(location), hat=False)
    hero.set_yaw(frame, yaw, turn_frames=0)
    return hero


def _launch(name: str, fa: int, fb: int, lane: float = 0.0, kind: str = "sedan", colour: str | None = None):
    """A car that drives up the street ramp and takes off from its top: returns (car, take-off frame, top)."""
    car = P.car(name, (RAMP_X0 - 40, lane, 0), 0.0, kind, colour)
    top = Vector((RAMP_X1, lane, RAMP_H + 0.2))
    take = fa + int((fb - fa) * 0.35)
    key(car, "location", fa, (RAMP_X0 - 40, lane, 0))
    key(car, "rotation_euler", fa, (0, 0, 0))
    key(car, "location", fa + int((take - fa) * 0.7), (RAMP_X0, lane, 0.05))
    key(car, "rotation_euler", fa + int((take - fa) * 0.7), (0, -math.atan2(RAMP_H, RAMP_X1 - RAMP_X0), 0))
    key(car, "location", take, tuple(top))
    return car, take, top


def _net(frame_up: int | None, bulge: int | None = None):
    """A giant net across the street in front of the crossing: two towers and a mesh of ropes."""
    post, rope = P.mat("net_post", "#7f8c8d", metal=0.4), P.mat("net_rope", "#f2f2f2", rough=0.7)
    posts = P._mesh_object("net_posts", [(post, [((NET_X, s * 16, 0), (1.4, 1.4, 34)) for s in (1, -1)])])
    lines = [((NET_X, 0, z), (0.25, 32, 0.25)) for z in range(4, 34, 2)]
    lines += [((NET_X, y, 3), (0.25, 0.25, 31)) for y in range(-15, 16, 2)]
    net = P._mesh_object("net", [(rope, lines)])
    if frame_up is not None:
        for obj in (posts, net):
            _grow(obj, frame_up, frame_up + 24)
    if bulge is not None:
        key(net, "scale", bulge - 1, (1, 1, 1))
        key(net, "scale", bulge + 4, (9, 1, 1))  # the ropes stretch where the car hits
        key(net, "scale", bulge + 14, (1, 1, 1))
    return net


def _camera(scene, loc, target, lens: float, f0: int, f1: int, push: float = 0.05, follow=None):
    aim = P._empty("rp_aim", tuple(target))
    cam = bpy.data.objects.new("rp_cam", bpy.data.cameras.new("rp_cam"))
    scene.collection.objects.link(cam)
    cam.data.lens, cam.data.clip_end = lens, 6000
    if follow is not None:  # a chase camera that rides with an object
        rig = P._empty("rp_rig")
        c = rig.constraints.new("COPY_LOCATION")
        c.target = follow
        cam.parent = rig
        cam.location = tuple(loc)
        aim.parent = rig
        aim.location = tuple(target)
    else:
        a, t = Vector(loc), Vector(target)
        key(cam, "location", f0, tuple(a))
        key(cam, "location", f1, tuple(a.lerp(t, push)))
    look = cam.constraints.new("TRACK_TO")
    look.target = aim
    look.track_axis, look.up_axis = "TRACK_NEGATIVE_Z", "UP_Y"
    scene.camera = cam
    return cam


def _sky_ring(f0: int, f1: int, count: int = 26, radius: float = 42.0, height: float = 44.0) -> None:
    """The jam in the sky: a slow ring of cars circling over the street, nose to tail."""
    rng = random.Random(SEED + 7)
    for i in range(count):
        a0 = i / count * 2 * math.pi
        car = P.car(f"sky{i}", (0, 0, 0), 0.0, rng.choice(("sedan", "sedan", "taxi", "van")))
        for k, f in enumerate((f0, (f0 + f1) // 2, f1)):
            a = a0 + 0.06 * k
            z = height + 6 * math.sin(a * 3)
            key(car, "location", f, (radius * math.cos(a), radius * math.sin(a) * 0.7, z))
            key(car, "rotation_euler", f, (0, 0, a + math.pi / 2))


# ---------------------------------------------------------------- the scenes


def build(spec: dict, ctx, scene, params: dict) -> None:
    stage = params.get("stage", "jam")
    stage = stage if stage in STAGES else "jam"
    f0, f1 = ctx.frame_start, ctx.frame_end
    fps = scene.render.fps or 24

    def at(fr: float) -> int:
        return f0 + int((f1 - f0) * fr)

    w = _world(scene, stage)
    rng = random.Random(SEED + STAGES.index(stage))
    roof_top = Vector((HOUSE.x, HOUSE.y, ROOF_Z + 4))

    if stage in ("hook", "house"):
        # a car falls out of the sky onto your roof; you watch from the street
        hero = _hero((HOUSE.x + 14, -8.5, 0.18), math.pi * 0.62, f0)
        car = P.car("faller", (0, 0, 0), math.pi, "taxi")
        hit = at(0.42 if stage == "hook" else 0.5)
        _arc(car, f0, hit, (NET_X - 4, 0, 18), roof_top + Vector((2, 0, 0.6)), 10)
        P.crash("roofhit", car, hit, fps, direction=(-1, -0.2, 0), force=0.35, seed=1)
        P.landing("rooflanding", roof_top, hit, fps, size=5, seed=2, ground="#c0392b")
        hero.raise_arm(hit, hit + 6, "L", hold=40)
        hero.raise_arm(hit, hit + 6, "R", hold=40)
        if stage == "hook":  # more cars flying over the city behind
            for i in range(3):
                c = P.car(f"flyer{i}", (0, 0, 0), 0.0, "sedan", ["#2f7fd6", "#2ecc71", "#8e44ad"][i])
                _arc(c, f0 - 10 + i * 9, f1 + 30, (-160, -60 - 40 * i, 30), (260, -120 - 30 * i, 20), 60)
        cam = _camera(scene, (HOUSE.x + 18, 9, 5), (HOUSE.x - 1, HOUSE.y + 1, 9), 20, f0, f1, 0.08)
        P.shake(cam, hit, fps, strength=0.35)

    elif stage == "jam":
        hero = _hero((JAM_X0 + 6, -8.5, 0.18), math.pi / 2, f0)
        hero.idle(f0, f1, fps, 1)
        _camera(scene, (JAM_X0 - 18, -4, 4.5), (JAM_X0 + 40, 1, 1.5), 26, f0, f1, 0.06)

    elif stage == "build":
        hero = _hero((RAMP_X1 + 4, -8.5, 0.18), math.pi, f0)
        hero.raise_arm(at(0.15), at(0.3), "R", hold=60)
        _grow(w["ramp"], at(0.2), at(0.55))
        _camera(scene, (RAMP_X0 - 20, -8, 5), (RAMP_X1, 0, 2), 24, f0, f1, 0.08)

    elif stage == "jump":
        for i, lane in enumerate((-2.6, 2.6, -2.6)):
            fa = f0 + i * int(fps * 0.6)
            car, take, top = _launch(
                f"jumper{i}", fa, fa + int(fps * 3.4), lane, colour=["#2f7fd6", "#d63a2f", "#2ecc71"][i]
            )
            _arc(car, take, take + int(fps * 2.6), top, (CROSS_X - 2, lane, 0.4), 34)
        _camera(scene, (RAMP_X1 + 34, -7, 2.5), (RAMP_X1 + 4, 0, 12), 18, f0, f1, 0.04)

    elif stage == "cross_crash":
        car = P.car("lander", (0, 0, 0), 0.0, "sedan", "#2f7fd6")
        hit = at(0.4)
        _arc(car, f0 - int(fps * 1.2), hit, (20, -2.6, 30), (CROSS_X - 1, -1.5, 0.3), 8)
        victim = P.car("victim", (CROSS_X - 2.6, -30, 0), math.pi / 2, "van")
        key(victim, "location", f0, (CROSS_X - 2.6, -30, 0))
        key(victim, "location", hit, (CROSS_X - 2.6, -3, 0))
        P.crash("crossA", victim, hit, fps, direction=(0.4, 1, 0), force=0.8, seed=3)
        P.crash("crossB", car, hit + 1, fps, direction=(1, -0.3, 0), force=0.6, seed=4)
        P.landing("crossdust", (CROSS_X - 1, -1.5, 0), hit, fps, size=5, seed=5)
        for i, y in enumerate((14, 24, -40)):
            P.car(f"cross{i}", (CROSS_X + 2.6, y, 0), -math.pi / 2, "sedan", ["#ecf0f1", "#d63a2f", "#f6c21a"][i])
        cam = _camera(scene, (CROSS_X - 26, -5, 4), (CROSS_X, -1, 1.5), 24, f0, f1, 0.06)
        P.shake(cam, hit, fps, strength=0.4)

    elif stage == "net":
        hero = _hero((NET_X - 6, -9, 0.18), 0.0, f0)
        hero.raise_arm(at(0.1), at(0.25), "R", hold=60)
        _net(at(0.2))
        _camera(scene, (NET_X - 50, -6, 6), (NET_X, 0, 14), 24, f0, f1, 0.06)

    elif stage == "bounce":
        hit = at(0.4)
        car, take, top = _launch("bouncer", f0 - int(fps * 1.6), hit - int(fps * 1.0), 0.0, colour="#d63a2f")
        _arc(car, take, hit, top, (NET_X - 1.5, 0, 17), 16)
        _net(None, bulge=hit)
        _arc(car, hit, f1 + int(fps * 1.5), (NET_X - 1.5, 0, 17), roof_top + Vector((2, 0, 0.6)), 14)
        _camera(scene, (NET_X - 36, 8, 4), (NET_X, 0, 15), 24, f0, f1, 0.05)

    elif stage == "roof_ramp":
        hero = _hero((HOUSE.x + 4, HOUSE.y + 3.5, ROOF_Z + 2.0), math.pi, f0)
        hero.raise_arm(at(0.1), at(0.25), "R", hold=50)
        rr = _wedge("roof_ramp", HOUSE.x - 9, HOUSE.x + 1, HOUSE.y, 6.0, ROOF_Z + 4, 6.0, rising=-1)
        _grow(rr, at(0.2), at(0.55))
        _camera(scene, (HOUSE.x + 14, 8, 15), (HOUSE.x - 3, HOUSE.y, ROOF_Z + 5), 24, f0, f1, 0.07)

    elif stage == "city":
        _wedge("roof_ramp", HOUSE.x - 9, HOUSE.x + 1, HOUSE.y, 6.0, ROOF_Z + 4, 6.0, rising=-1)
        _net(None)
        car = P.car("rocket", (0, 0, 0), math.pi, "sedan", "#2f7fd6")
        lip = Vector((HOUSE.x - 9, HOUSE.y, ROOF_Z + 10.5))
        far = Vector((-520, -240, 40))
        _arc(car, f0, f1 + int(fps * 2.5), lip, far, 190)
        _camera(scene, (9, 7, 3.5), (0, 0, 0), 22, f0, f1, follow=car)

    elif stage == "everywhere":
        _net(None)
        roofs = [r for r in w["roofs"] if abs(r[0]) < 150 and 40 < r[1] < 230]
        rng.shuffle(roofs)
        picks = roofs[:22]
        for i, (x, y, h) in enumerate(picks):
            _wedge(f"rr{i}", x - 7, x + 7, y, 8, h, 5, rising=rng.choice((1, -1)))
        for i in range(26):
            a, b = rng.sample(picks, 2)
            car = P.car(f"air{i}", (0, 0, 0), 0.0, rng.choice(("sedan", "taxi", "van")))
            phase = rng.uniform(-1.0, 0.6)
            span = int(fps * rng.uniform(2.5, 4.0))
            fa = f0 + int(phase * span)
            _arc(car, fa, fa + span, (a[0], a[1], a[2] + 5), (b[0], b[1], b[2] + 1), rng.uniform(60, 140))
        _camera(scene, (0, -40, 75), (0, 90, 55), 20, f0, f1, 0.05)

    elif stage in ("sky_jam", "ending"):
        hero = _hero((6, -8.5, 0.18), math.pi / 2, f0)
        hero.look_at(f0, (0, 0, 44))
        _sky_ring(f0, f1)
        if stage == "sky_jam":
            _camera(scene, (-22, -6, 1.6), (6, 2, 42), 18, f0, f1, 0.03)
        else:
            _camera(scene, (-50, -85, 100), (0, 0, 40), 22, f0, f1, 0.06)

    if params.get("outlines") is False:
        scene.render.use_freestyle = False
