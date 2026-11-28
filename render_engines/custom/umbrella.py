"""'What if your umbrella could LIFT you?' (Nov 28, the owner: "haz lo que veas"; hypothetical ideas like the ramp, a
different one on each channel). ONE windy day, ONE street, ONE umbrella, each height caused by the last gust:

  the windiest day of the year -> you open your umbrella and your feet leave the ground -> over the cars -> past the
  rooftops -> over the whole city -> into a storm cloud -> lightning -> the umbrella flips inside out -> you fall...
  into a rooftop pool. And it's still windy.

params: stage (one of STAGES). The street and the city are the ramp video's (ramp.py), the sky the balloon video's
(balloons.py); built from render_engines/custom/parts.py.
"""

from __future__ import annotations

import math
import random

import bmesh
import bpy
from mathutils import Vector

from render_engines.core.blender.animation import key
from render_engines.custom import balloons as B
from render_engines.custom import parts as P
from render_engines.custom import ramp as R
from render_engines.custom.ramp import _camera, _hero

SEED = 2812
STAGES = ("hook", "windy", "open", "cars", "roofs", "city", "storm", "lightning", "flip", "pool")
START = Vector((-40.0, -8.5, 0.18))  # on the pavement of the ramp street
POOL = Vector((150.0, -30.5, 30.0))  # a rooftop pool, between the street buildings and the far grid
STORM = Vector((150.0, -4.0, 305.0))


def near_roofs() -> list:
    """(x, y, height) of the buildings along the street: the same random draws as ramp._city()."""
    rng = random.Random(R.SEED)
    out = []
    for x in range(-300, 320, 20):
        for s in (1, -1):
            if abs(x - R.CROSS_X) < 18 or (s < 0 and abs(x - R.HOUSE.x) < 16):
                continue
            out.append((x, s * 18.5, rng.uniform(12, 38)))
    return out


def _umbrella(hero, open_frame: int | None = None, flip_frame: int | None = None):
    """A red umbrella held over your head: an 8-panel canopy on a shaft, opening (and flipping) on cue."""
    rig = P._empty("umbrella")
    rig.parent = hero.root
    rig.location = (0.0, 0.0, 2.05)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=False, segments=8, radius1=1.25, radius2=0.02, depth=0.6)
    mesh = bpy.data.meshes.new("canopy")
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(P.mat("canopy", "#e53935", rough=0.5))
    canopy = bpy.data.objects.new("canopy", mesh)
    bpy.context.scene.collection.objects.link(canopy)
    canopy.parent = rig
    canopy.location = (0, 0, 0.75)
    stick = P._mesh_object(
        "stick",
        [(P.mat("stick", "#2b2b2b", 0.5), [((0, 0, -0.3), (0.05, 0.05, 1.4))]),
         (P.mat("handle", "#6b4a2e", 0.6), [((0.06, 0, -0.42), (0.18, 0.06, 0.14))])],
    )  # fmt: skip
    stick.parent = rig
    for side in ("L", "R"):
        hero.raise_arm(-200, -199, side, hold=100000)  # both hands up on the handle, the whole time
    if open_frame is not None:
        key(canopy, "scale", open_frame - 1, (0.25, 0.25, 1.6))
        key(canopy, "scale", open_frame + 5, (1.1, 1.1, 0.9))
        key(canopy, "scale", open_frame + 9, (1, 1, 1))
    if flip_frame is not None:  # inside out: the cone turns into a bowl
        key(canopy, "scale", flip_frame - 1, (1, 1, 1))
        key(canopy, "scale", flip_frame + 3, (1.15, 1.15, -1.3))
        key(canopy, "rotation_euler", flip_frame + 3, (0.3, 0.2, 0))
    return rig


def _fly(root, f0: int, f1: int, a, b, ease: float = 1.0, sway: float = 0.0, n: int = 10) -> None:
    a, b = Vector(a), Vector(b)
    for i in range(n + 1):
        t = i / n
        p = a.lerp(b, t**ease)
        p.y += sway * math.sin(t * 7.0)
        key(root, "location", f0 + round((f1 - f0) * t), tuple(p))
        key(
            root,
            "rotation_euler",
            f0 + round((f1 - f0) * t),
            (0.08 * math.sin(t * 9), 0.06 * math.cos(t * 7), math.pi / 2),
        )


def _gusts(f0: int, f1: int, centre, n: int = 30, seed: int = 0) -> None:
    """Leaves and paper blown along the street by the wind (+x)."""
    rng = random.Random(seed)
    leaf, paper = P.mat("gust_leaf", "#d89a2b", 0.8), P.mat("gust_paper", "#f4f1ea", 0.8)
    for i in range(n):
        bit = P._mesh_object(f"gust{i}", [(leaf if i % 3 else paper, [((0, 0, 0), (0.35, 0.25, 0.02))])])
        y, z = centre[1] + rng.uniform(-6, 6), centre[2] + rng.uniform(0.2, 4.0)
        x0 = centre[0] - rng.uniform(10, 30)
        key(bit, "location", f0, (x0, y, z))
        key(bit, "location", f1, (x0 + rng.uniform(40, 70), y + rng.uniform(-2, 2), z + rng.uniform(-1, 2)))
        key(bit, "rotation_euler", f1, (rng.uniform(5, 15), rng.uniform(5, 15), rng.uniform(0, 6)))


def _storm(f0: int, f1: int, flash: int | None = None) -> None:
    dark = P._soft("storm_cloud", "#5a636e")
    rng = random.Random(SEED + 3)
    path = [STORM + Vector((-20, 0, -30)).lerp(Vector((6, 0, 6)), k / 10) for k in range(11)]
    for i in range(140):
        r = rng.uniform(5, 11)
        c = Vector((STORM.x + rng.uniform(-45, 45), STORM.y + rng.uniform(-30, 30), STORM.z + rng.uniform(-30, 25)))
        if min((c - q).length for q in path) < r + 7:  # a tunnel for you (and the camera) through the cloud
            continue
        p = P._sphere(f"sc{i}", r, dark, tuple(c))
        p.visible_shadow = False
    rain = P.mat("rain", "#cfe3f2", rough=0.2)
    for i in range(220):
        r = P._mesh_object(f"rain{i}", [(rain, [((0, 0, 0), (0.03, 0.03, 1.6))])])
        x, y = STORM.x + rng.uniform(-30, 30), STORM.y + rng.uniform(-20, 20)
        z = STORM.z + rng.uniform(-30, 10)
        key(r, "location", f0, (x, y, z))
        key(r, "location", f1, (x + 3, y, z - 45))
    if flash is not None:  # a bolt right beside you, for three frames
        pts, p = [], Vector((STORM.x - 1, STORM.y + 7, STORM.z + 32))  # just behind you, in the camera's view
        for _k in range(9):
            pts.append(p.copy())
            p += Vector((rng.uniform(-3, 3), rng.uniform(-2, 2), -8))
        bolt = P.rope("bolt", pts, 0.6, P.mat("bolt", "#eaf4ff", emit=25.0))
        key(bolt, "scale", flash - 1, (0.001, 0.001, 0.001))
        key(bolt, "scale", flash, (1, 1, 1))
        key(bolt, "scale", flash + 3, (1, 1, 1))
        key(bolt, "scale", flash + 4, (0.001, 0.001, 0.001))
        light = bpy.data.objects.new("flash", bpy.data.lights.new("flash", "POINT"))
        light.location = (STORM.x - 1, STORM.y + 6, STORM.z)
        bpy.context.scene.collection.objects.link(light)
        for f, e in ((flash - 1, 0), (flash, 2e5), (flash + 3, 2e5), (flash + 4, 0)):  # bright, never white
            light.data.energy = e
            light.data.keyframe_insert("energy", frame=f)


def _pool_building() -> None:
    P._mesh_object(
        "pool_tower",
        [
            (P.mat("pool_wall", "#cfd8dc", 0.8), [((POOL.x, POOL.y, 0), (14, 9, POOL.z))]),
            (P.mat("pool_rim", "#ffffff", 0.7), [((POOL.x, POOL.y, POOL.z), (14.2, 9.2, 0.6))]),
            (P.mat("pool_water", "#29b6f6", rough=0.1), [((POOL.x, POOL.y, POOL.z + 0.62), (11, 6.4, 0.02))]),
            (P.mat("bld_glass", "#33475c", rough=0.2),
             [((POOL.x + dx, POOL.y - 4.56, z), (2.2, 0.12, 1.8)) for dx in (-4, 0, 4) for z in range(3, 28, 4)]),
        ],
    )  # fmt: skip


def build(spec: dict, ctx, scene, params: dict) -> None:
    stage = params.get("stage", "windy")
    stage = stage if stage in STAGES else "windy"
    f0, f1 = ctx.frame_start, ctx.frame_end
    fps = scene.render.fps or 24
    rng = random.Random(SEED + STAGES.index(stage))

    def at(fr: float) -> int:
        return f0 + int((f1 - f0) * fr)

    level = {"city": "mid", "storm": "thin", "lightning": "thin", "flip": "high", "pool": "mid", "hook": "mid"}
    B._sky(scene, level.get(stage, "low"))
    R._streets()
    R._city(random.Random(R.SEED))
    _pool_building()
    roofs = near_roofs()

    hero = _hero(START, math.pi / 2, f0)
    root = hero.root

    if stage == "windy":  # the windiest day of the year: everything flies down the street
        hero.look_at(f0, (0, -8.5, 1.5))
        _umbrella(hero)  # still closed
        bpy.data.objects["canopy"].scale = (0.25, 0.25, 1.6)
        _gusts(f0, f1, START + Vector((0, 4, 0)), 40, SEED)
        for i, x in enumerate((-30, -18)):
            p = _hero((x, -8.0, 0.18), math.pi, f0)
            p.raise_arm(at(0.2 + 0.2 * i), at(0.3 + 0.2 * i), "R", hold=40)  # holding on to a hat
        _camera(scene, (-54, -3.5, 1.9), (-38, -8.2, 1.4), 22, f0, f1, 0.05)

    elif stage == "open":  # you open it... and your feet leave the ground
        open_f = at(0.25)
        _umbrella(hero, open_frame=open_f)
        key(root, "location", f0, tuple(START))
        key(root, "location", open_f + 6, tuple(START))
        _fly(root, open_f + 6, f1, START, START + Vector((3.0, 1.0, 2.2)), ease=1.6)
        _gusts(f0, f1, START + Vector((0, 4, 0)), 25, SEED + 1)
        _camera(scene, (-48, -2.5, 2.2), (-39, -8.0, 2.4), 22, f0, f1, 0.04)

    elif stage in ("cars", "hook"):  # a few metres up, over the traffic
        a = START + Vector((4, 5.0, 2.6)) if stage == "cars" else Vector((-6, -3.0, 26.0))
        b = START + Vector((22, 6.0, 6.5)) if stage == "cars" else Vector((26, -2.0, 33.0))
        _umbrella(hero)
        _fly(root, f0, f1, a, b, sway=0.4)
        cols = ["#d63a2f", "#2f7fd6", "#ecf0f1", "#2ecc71", "#f6c21a", "#8e44ad"]
        for i in range(16):
            lane = -2.6 if i % 2 else 2.6
            c = P.car(f"car{i}", (-80 + 8 * i, lane, 0), 0.0 if lane < 0 else math.pi, "sedan" if i % 3 else "taxi",
                      cols[i % 6])  # fmt: skip
            P.drive(c, f0, f1, 26)
        if stage == "cars":
            _camera(scene, (5, 8.5, 2.5), (0, -1.5, -4.5), 20, f0, f1, follow=root)  # you, and the cars below
        else:
            _camera(scene, (9, 6, 1.5), (0, 0, 0.5), 20, f0, f1, follow=root)  # flying between the towers

    elif stage == "roofs":  # rooftop height: people up there can't believe it
        _umbrella(hero)
        _fly(root, f0, f1, (10, -4.0, 20.0), (42, -3.0, 36.0), sway=0.5)
        top = [r for r in roofs if r[1] < 0 and r[0] == 0][0]  # the roof the camera sees behind you
        for k in range(3):
            p = _hero((top[0] - 3 + 3 * k, top[1] + 3, top[2] + 0.6), math.pi / 2, f0)
            p.look_at(f0, (30, -3, 32))
            p.raise_arm(at(0.25 + 0.15 * k), at(0.32 + 0.15 * k), "R", hold=40)
        _camera(scene, (7, 8, 1.0), (0, -2, -4), 20, f0, f1, follow=root)

    elif stage == "city":  # over the whole city
        _umbrella(hero)
        _fly(root, f0, f1, (60, -4.0, 95.0), (120, -4.0, 150.0), ease=0.9, sway=1.0)
        _camera(scene, (4, 7, 7), (0, -1, -16), 22, f0, f1, follow=root)

    elif stage == "storm":  # straight into a storm cloud
        _umbrella(hero)
        _storm(f0, f1)
        _fly(root, f0, f1, STORM + Vector((-20, 0, -30)), STORM + Vector((-4, 0, -4)), ease=0.8, sway=1.2)
        _camera(scene, (3.5, -6, 0.5), (0, 0, 1.2), 20, f0, f1, follow=root)

    elif stage == "lightning":  # lightning, right next to you
        _umbrella(hero)
        flash = at(0.45)
        _storm(f0, f1, flash)
        _fly(root, f0, f1, STORM + Vector((-4, 0, -4)), STORM + Vector((6, 0, 6)), sway=1.5)
        hero.look_at(flash, (STORM.x - 1, STORM.y + 7, STORM.z))
        cam = _camera(scene, (3.5, -6, 0.5), (0, 0, 1.2), 20, f0, f1, follow=root)
        P.shake(cam, flash, fps, strength=0.2)

    elif stage == "flip":  # inside out: and you start to fall
        flip = at(0.3)
        _umbrella(hero, flip_frame=flip)
        key(root, "location", f0, tuple(STORM + Vector((8, 0, -20))))
        key(root, "location", flip, tuple(STORM + Vector((9, 0, -19))))
        key(root, "location", f1, tuple(STORM + Vector((4, -10, -95))))
        for k, f in enumerate(range(flip, f1 + 1, 6)):  # tumbling
            key(root, "rotation_euler", f, (0.7 * k, 0.25 * k, math.pi / 2))
        P.clouds("cl", (STORM.x, STORM.y), 600, 120, STORM.z - 110, STORM.z - 60, seed=SEED + 4)
        cam = _camera(scene, (6, -10, -3.0), (0, 0, 0.8), 20, f0, f1, follow=root)
        P.shake(cam, flip, fps, strength=0.15, seconds=float(f1 - flip) / fps)

    elif stage == "pool":  # ...into a rooftop pool. And it's still windy.
        hit = at(0.35)
        _umbrella(hero, flip_frame=f0 - 30)
        key(root, "location", f0, tuple(POOL + Vector((-2, 0, 40))))
        key(root, "location", hit, tuple(POOL + Vector((0, 0, -0.6))))
        key(root, "location", hit + 8, tuple(POOL + Vector((0, 0, -0.2))))
        key(root, "location", f1, tuple(POOL + Vector((0.6, 0, -0.1))))
        key(root, "rotation_euler", f0, (1.2, 0.3, math.pi / 2))
        key(root, "rotation_euler", hit, (0, 0, math.pi / 2))
        water = P._soft("splash", "#d6eefc")
        for i in range(20):
            a = i / 20 * 2 * math.pi
            p = P._sphere(f"sp{i}", 0.5, water, tuple(POOL))
            p.visible_shadow = False
            P._appear(p, hit)
            key(p, "scale", hit, (1.0, 1.0, 1.0))
            key(p, "location", hit, tuple(POOL + Vector((math.cos(a) * 1.5, math.sin(a) * 1.2, 0.9))))
            key(p, "location", hit + int(fps * 0.6),
                tuple(POOL + Vector((math.cos(a) * 5, math.sin(a) * 3.5, rng.uniform(3, 6)))))  # fmt: skip
            key(p, "scale", hit + int(fps * 0.6), (1.8, 1.8, 1.8))
            key(p, "scale", hit + int(fps * 1.1), (0.001, 0.001, 0.001))
        _gusts(hit, f1 + 10, POOL + Vector((0, 0, 1)), 20, SEED + 2)
        cam = _camera(scene, (POOL.x + 21, POOL.y + 3.5, POOL.z + 13), (POOL.x, POOL.y, POOL.z + 1.5), 22, f0, f1, 0.04)
        P.shake(cam, hit, fps, strength=0.2)

    if params.get("outlines") is False:
        scene.render.use_freestyle = False
